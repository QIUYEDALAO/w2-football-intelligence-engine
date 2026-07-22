from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from decimal import Decimal
from typing import Any

from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.strategy.simulate import sample_score_matrix, score_matrix_from_simulation


def scoreline_picks_from_card(card: dict[str, Any], *, limit: int = 3) -> list[dict[str, Any]]:
    simulation_picks = _simulation_scoreline_picks(card)
    if simulation_picks:
        return simulation_picks[:limit]
    markets = [item for item in card.get("markets", []) if isinstance(item, dict)]
    score_market = next((item for item in markets if item.get("market") == "SCORE"), {})
    references = score_market.get("reference_scores", []) if isinstance(score_market, dict) else []
    if not isinstance(references, list):
        return []
    picks: list[dict[str, Any]] = []
    for item in references:
        if not isinstance(item, dict) or not item.get("scoreline"):
            continue
        scoreline = str(item["scoreline"])
        probability = _probability(item.get("conditional_probability") or item.get("probability"))
        picks.append(
            {
                "scoreline": scoreline,
                "home_goals": _score_part(scoreline, 0),
                "away_goals": _score_part(scoreline, 1),
                "probability": probability,
                "probability_label": _probability_label(
                    item.get("probability_label"),
                    probability,
                ),
            }
        )
    return picks[:limit]


def scoreline_reference_from_card(
    card: dict[str, Any],
    *,
    recommendation: dict[str, Any] | None = None,
    decision_hash: str | None = None,
) -> dict[str, Any] | None:
    simulation = _simulation_from_card(card)
    if not isinstance(simulation, dict) or simulation.get("status") != "READY":
        return None
    top_scorelines = scoreline_picks_from_card(card)
    high_total_probability = _over_probability(simulation, 3.5)
    very_high_total_probability = _over_probability(simulation, 4.5)
    projection = _scoreline_projection(
        card,
        simulation=simulation,
        recommendation=recommendation,
        secondary_recommendations=[
            item for item in card.get("secondary_picks", []) if isinstance(item, dict)
        ],
        decision_hash=decision_hash,
    )
    return {
        "source": "formal_simulation",
        "label": "模拟比分参考",
        "top_scorelines": top_scorelines,
        "direction_top3": projection["top3"] if projection["status"] == "READY" else [],
        "scoreline_projection": projection,
        "high_total": {
            "threshold": 4,
            "probability": high_total_probability,
            "probability_label": _probability_label(None, high_total_probability),
            "representative_scoreline": _representative_high_total_scoreline(
                simulation,
                minimum_total=4,
            ),
        },
        "very_high_total": {
            "threshold": 5,
            "probability": very_high_total_probability,
            "probability_label": _probability_label(None, very_high_total_probability),
        },
        "ah_key_scorelines": _ah_key_scorelines(simulation, recommendation=recommendation),
    }


def _scoreline_projection(
    card: dict[str, Any],
    *,
    simulation: dict[str, Any],
    recommendation: dict[str, Any] | None,
    secondary_recommendations: list[dict[str, Any]],
    decision_hash: str | None,
) -> dict[str, Any]:
    base = {
        "schema_version": "w2.scoreline_projection.v1",
        "simulation_method": "seeded_joint_score_sampling",
        "simulations_requested": 10_000,
        "simulations_completed": 0,
        "decision_hash": decision_hash,
        "top3": [],
    }
    if not isinstance(recommendation, dict):
        return {**base, "status": "NOT_READY", "reason": "SELECTED_CANDIDATE_MISSING"}
    tier = str(recommendation.get("tier") or "").upper()
    is_pick_tier = tier in {"ANALYSIS_PICK", "RECOMMEND", "FORMAL"}
    if not decision_hash and not is_pick_tier and not recommendation.get("formal_recommendation"):
        return {**base, "status": "NOT_READY", "reason": "SELECTED_CANDIDATE_MISSING"}
    constraint, blocker = _canonical_constraint(
        recommendation, require_quote=bool(decision_hash)
    )
    if blocker:
        return {**base, "status": "NOT_READY", "reason": blocker}
    if constraint is None:
        return {**base, "status": "NOT_READY", "reason": "SCORELINE_CONSTRAINT_INCOMPLETE"}
    secondary = []
    for item in secondary_recommendations:
        normalized, secondary_blocker = _canonical_constraint(item, require_quote=False)
        if normalized is not None and secondary_blocker is None:
            secondary.append(normalized)
    summary = simulation.get("score_matrix_summary")
    matrix = score_matrix_from_simulation(simulation)
    if not matrix:
        return {**base, "status": "NOT_READY", "reason": "SCORE_MATRIX_INVALID"}
    matrix_rows = [
        {"home_goals": score[0], "away_goals": score[1], "probability": probability}
        for score, probability in sorted(matrix.items())
    ]
    matrix_hash = str(
        summary.get("score_matrix_hash")
        if isinstance(summary, dict)
        else ""
    ) or _canonical_hash(matrix_rows)
    input_hash = str(
        (simulation.get("calibration") or {}).get("simulation_input_hash") or ""
    )
    identity = [
        str(card.get("fixture_id") or ""),
        str(decision_hash or ""),
        str(simulation.get("model_version") or ""),
        str(simulation.get("calibration_version") or ""),
        input_hash,
        matrix_hash,
    ]
    seed = int(hashlib.sha256(":".join(identity).encode()).hexdigest()[:16], 16)
    sampled = sample_score_matrix(matrix, simulations=10_000, seed=seed)
    consistent: Counter[tuple[int, int]] = Counter()
    settlements: dict[tuple[int, int], tuple[str, list[str]]] = {}
    for score, count in sampled.items():
        primary = _constraint_settlement(constraint, *score)
        secondary_outcomes = [_constraint_settlement(item, *score) for item in secondary]
        if primary in {"WIN", "HALF_WIN"} and all(
            outcome in {"WIN", "HALF_WIN"} for outcome in secondary_outcomes
        ):
            consistent[score] = count
            settlements[score] = (primary, secondary_outcomes)
    consistent_count = sum(consistent.values())
    if consistent_count == 0:
        return {
            **base,
            "status": "NOT_READY",
            "reason": "SCORELINE_CONSTRAINT_EMPTY",
            "seed": seed,
            "source_score_matrix_hash": matrix_hash,
            "simulation_input_hash": input_hash,
            "simulations_completed": 10_000,
            "primary_constraint": constraint,
            "secondary_constraints": secondary,
            "consistent_sample_count": 0,
            "consistent_sample_rate": 0.0,
            "consistency_status": "EMPTY",
        }
    top3 = []
    for (home, away), count in consistent.most_common(3):
        primary, secondary_outcomes = settlements[(home, away)]
        top3.append(
            {
                "scoreline": f"{home}-{away}",
                "home_goals": home,
                "away_goals": away,
                "sample_count": count,
                "unconditional_probability": round(count / 10_000, 6),
                "conditional_probability": round(count / consistent_count, 6),
                "probability": round(count / 10_000, 6),
                "probability_label": f"{count / 100:.1f}%",
                "primary_settlement": primary,
                "secondary_settlements": secondary_outcomes,
                "source": "decision_simulation_direction_top3",
                "market": constraint["market"],
                "selection": _display_selection(constraint),
                "line": constraint["line"],
            }
        )
    payload = {
        **base,
        "status": "READY",
        "reason": None,
        "seed": seed,
        "source_score_matrix_hash": matrix_hash,
        "simulation_input_hash": input_hash,
        "simulations_completed": 10_000,
        "primary_constraint": constraint,
        "secondary_constraints": secondary,
        "consistent_sample_count": consistent_count,
        "consistent_sample_rate": round(consistent_count / 10_000, 6),
        "top3": top3,
        "consistency_status": "PASS",
    }
    return {**payload, "evidence_hash": _canonical_hash(payload)}


def _canonical_constraint(
    recommendation: dict[str, Any], *, require_quote: bool = True
) -> tuple[dict[str, Any] | None, str | None]:
    market = str(recommendation.get("market") or "").upper()
    selection = str(
        recommendation.get("selection")
        or recommendation.get("tendency")
        or recommendation.get("lean")
        or ""
    ).upper()
    aliases = {
        ("ASIAN_HANDICAP", "HOME_AH"): "HOME",
        ("ASIAN_HANDICAP", "HOME"): "HOME",
        ("ASIAN_HANDICAP", "AWAY_AH"): "AWAY",
        ("ASIAN_HANDICAP", "AWAY"): "AWAY",
        ("TOTALS", "OVER"): "OVER",
        ("TOTALS", "UNDER"): "UNDER",
    }
    normalized = aliases.get((market, selection))
    try:
        line = Decimal(str(recommendation.get("line")))
    except Exception:
        return None, "SCORELINE_CONSTRAINT_INCOMPLETE"
    if normalized is None:
        return None, "SCORELINE_SELECTION_UNSUPPORTED"
    if market == "ASIAN_HANDICAP" and require_quote:
        quote_identity = recommendation.get("quote_identity")
        quotes = quote_identity.get("quotes") if isinstance(quote_identity, dict) else None
        side_quote = quotes.get(normalized.lower()) if isinstance(quotes, dict) else None
        quote_line = side_quote.get("line") if isinstance(side_quote, dict) else (
            quote_identity.get("line") if isinstance(quote_identity, dict) else None
        )
        if quote_line is None:
            return None, "AH_SELECTED_QUOTE_LINE_MISSING"
        try:
            if Decimal(str(quote_line)) != line:
                return None, "AH_SELECTED_SIDE_LINE_MISMATCH"
        except Exception:
            return None, "AH_SELECTED_SIDE_LINE_MISMATCH"
    return {"market": market, "selection": normalized, "line": str(line)}, None


def _display_selection(constraint: dict[str, Any]) -> str:
    if constraint["market"] == "ASIAN_HANDICAP":
        return f"{constraint['selection']}_AH"
    return str(constraint["selection"])


def _constraint_settlement(
    constraint: dict[str, Any], home_goals: int, away_goals: int
) -> str:
    line = Decimal(str(constraint["line"]))
    if constraint["market"] == "ASIAN_HANDICAP":
        return settle_asian_handicap(
            home_goals, away_goals, str(constraint["selection"]), line
        ).value
    return settle_total_goals(
        home_goals + away_goals, str(constraint["selection"]), line
    ).value


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def _direction_top3_scorelines(
    simulation: dict[str, Any],
    *,
    recommendation: dict[str, Any] | None,
    secondary_recommendations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(recommendation, dict):
        return []
    if recommendation.get("tier") not in {
        "ANALYSIS_PICK",
        "RECOMMEND",
        "FORMAL",
    } and not recommendation.get("formal_recommendation"):
        return []
    market = str(recommendation.get("market") or "")
    selection = str(recommendation.get("selection") or "")
    selected_line = _number(recommendation.get("line"))
    lambda_home = _number(simulation.get("lambda_home"))
    lambda_away = _number(simulation.get("lambda_away"))
    if lambda_home is None or lambda_away is None:
        return []
    if market == "ASIAN_HANDICAP" and selected_line is None:
        return []
    if market == "TOTALS" and selected_line is None:
        return []
    if market not in {"ASIAN_HANDICAP", "TOTALS", "ONE_X_TWO", "1X2"}:
        return []

    matches: list[dict[str, Any]] = []
    for home in range(0, 11):
        for away in range(0, 11):
            outcome = _recommended_outcome_for_scoreline(
                market=market,
                selection=selection,
                line=selected_line,
                home_goals=home,
                away_goals=away,
            )
            if outcome not in {"WIN", "HALF_WIN"}:
                continue
            if not _matches_secondary_recommendations(
                secondary_recommendations or [],
                home_goals=home,
                away_goals=away,
            ):
                continue
            probability = _poisson_probability(lambda_home, home) * _poisson_probability(
                lambda_away,
                away,
            )
            matches.append(
                {
                    "scoreline": f"{home}-{away}",
                    "home_goals": home,
                    "away_goals": away,
                    "probability": round(probability, 6),
                    "probability_label": _probability_label(None, probability),
                    "selection": selection,
                    "line": selected_line,
                    "outcome": outcome,
                    "source": "decision_simulation_direction_top3",
                }
            )
    return sorted(matches, key=lambda item: float(item["probability"]), reverse=True)[:3]


def _matches_secondary_recommendations(
    recommendations: list[dict[str, Any]],
    *,
    home_goals: int,
    away_goals: int,
) -> bool:
    for recommendation in recommendations:
        market = str(recommendation.get("market") or "")
        tendency = str(
            recommendation.get("selection")
            or recommendation.get("tendency")
            or recommendation.get("lean")
            or ""
        )
        selection = (
            "HOME_AH"
            if market == "ASIAN_HANDICAP" and "HOME" in tendency
            else "AWAY_AH"
            if market == "ASIAN_HANDICAP" and "AWAY" in tendency
            else "OVER"
            if market == "TOTALS" and "OVER" in tendency
            else "UNDER"
            if market == "TOTALS" and "UNDER" in tendency
            else tendency
        )
        outcome = _recommended_outcome_for_scoreline(
            market=market,
            selection=selection,
            line=_number(recommendation.get("line")),
            home_goals=home_goals,
            away_goals=away_goals,
        )
        if outcome not in {"WIN", "HALF_WIN"}:
            return False
    return True


def _recommended_outcome_for_scoreline(
    *,
    market: str,
    selection: str,
    line: float | None,
    home_goals: int,
    away_goals: int,
) -> str:
    if market == "ASIAN_HANDICAP" and line is not None:
        if selection == "HOME_AH":
            side = "HOME"
            home_line = line
        elif selection == "AWAY_AH":
            side = "AWAY"
            home_line = -line
        else:
            return "LOSS"
        return _ah_outcome_for_scoreline(
            side=side,
            home_line=home_line,
            home_goals=home_goals,
            away_goals=away_goals,
        )
    if market == "TOTALS" and line is not None:
        total_goals = home_goals + away_goals
        if selection == "OVER":
            adjustments = [total_goals - part for part in _quarter_line_parts(line)]
        elif selection == "UNDER":
            adjustments = [part - total_goals for part in _quarter_line_parts(line)]
        else:
            return "LOSS"
        outcomes = [_single_ah_outcome(value) for value in adjustments]
        if outcomes[0] == outcomes[1]:
            return outcomes[0]
        if set(outcomes) == {"WIN", "PUSH"}:
            return "HALF_WIN"
        if set(outcomes) == {"LOSS", "PUSH"}:
            return "HALF_LOSS"
        return "PUSH"
    if market in {"ONE_X_TWO", "1X2"}:
        if selection == "HOME":
            return "WIN" if home_goals > away_goals else "LOSS"
        if selection == "AWAY":
            return "WIN" if away_goals > home_goals else "LOSS"
        if selection == "DRAW":
            return "WIN" if home_goals == away_goals else "LOSS"
    return "LOSS"


def _simulation_from_card(card: dict[str, Any]) -> dict[str, Any] | None:
    simulation = card.get("simulation")
    if isinstance(simulation, dict):
        return simulation
    shadow = card.get("pricing_shadow")
    if isinstance(shadow, dict):
        simulation = shadow.get("simulation")
        if isinstance(simulation, dict):
            return simulation
    return None


def _simulation_scoreline_picks(card: dict[str, Any]) -> list[dict[str, Any]]:
    simulation = _simulation_from_card(card)
    if not isinstance(simulation, dict) or simulation.get("status") != "READY":
        return []
    raw_picks = simulation.get("scoreline_picks")
    if not isinstance(raw_picks, list):
        return []
    picks: list[dict[str, Any]] = []
    for item in raw_picks:
        if not isinstance(item, dict) or not item.get("scoreline"):
            continue
        scoreline = str(item["scoreline"])
        probability = _probability(item.get("probability"))
        picks.append(
            {
                "scoreline": scoreline,
                "home_goals": _score_part(scoreline, 0),
                "away_goals": _score_part(scoreline, 1),
                "probability": probability,
                "probability_label": _probability_label(
                    item.get("probability_label"),
                    probability,
                ),
            }
        )
    return picks


def _over_probability(simulation: dict[str, Any], line: float) -> float | None:
    ou = simulation.get("ou_probabilities")
    ladder = ou.get("ladder") if isinstance(ou, dict) else None
    if not isinstance(ladder, list):
        return None
    for item in ladder:
        if not isinstance(item, dict):
            continue
        item_line = _number(item.get("line"))
        if item_line is not None and math.isclose(item_line, line, abs_tol=1e-9):
            return _probability(item.get("over"))
    return None


def _representative_high_total_scoreline(
    simulation: dict[str, Any],
    *,
    minimum_total: int,
) -> dict[str, Any] | None:
    lambda_home = _number(simulation.get("lambda_home"))
    lambda_away = _number(simulation.get("lambda_away"))
    if lambda_home is None or lambda_away is None:
        return None
    best: tuple[float, int, int] | None = None
    for home in range(0, 7):
        for away in range(0, 7):
            if home + away < minimum_total:
                continue
            probability = _poisson_probability(lambda_home, home) * _poisson_probability(
                lambda_away,
                away,
            )
            if best is None or probability > best[0]:
                best = (probability, home, away)
    if best is None:
        return None
    probability, home, away = best
    return {
        "scoreline": f"{home}-{away}",
        "home_goals": home,
        "away_goals": away,
        "probability": round(probability, 6),
        "probability_label": _probability_label(None, probability),
        "source": "exact_poisson_from_lambda",
    }


def _ah_key_scorelines(
    simulation: dict[str, Any],
    *,
    recommendation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(recommendation, dict):
        return []
    if recommendation.get("market") != "ASIAN_HANDICAP":
        return []
    selection = str(recommendation.get("selection") or "")
    selected_line = _number(recommendation.get("line"))
    lambda_home = _number(simulation.get("lambda_home"))
    lambda_away = _number(simulation.get("lambda_away"))
    if selected_line is None or lambda_home is None or lambda_away is None:
        return []
    if selection == "HOME_AH":
        side = "HOME"
        home_line = selected_line
    elif selection == "AWAY_AH":
        side = "AWAY"
        home_line = -selected_line
    else:
        return []

    grouped: dict[str, dict[str, Any]] = {}
    totals: dict[str, float] = {}
    for home in range(0, 8):
        for away in range(0, 8):
            outcome = _ah_outcome_for_scoreline(
                side=side,
                home_line=home_line,
                home_goals=home,
                away_goals=away,
            )
            probability = _poisson_probability(lambda_home, home) * _poisson_probability(
                lambda_away,
                away,
            )
            totals[outcome] = totals.get(outcome, 0.0) + probability
            current = grouped.get(outcome)
            if current is not None and probability <= float(current["representative_probability"]):
                continue
            grouped[outcome] = {
                "outcome": outcome,
                "label": _ah_outcome_label(outcome),
                "scoreline": f"{home}-{away}",
                "home_goals": home,
                "away_goals": away,
                "representative_probability": round(probability, 6),
                "representative_probability_label": _probability_label(None, probability),
                "settlement_probability": None,
                "settlement_probability_label": None,
                "source": "exact_poisson_from_lambda",
            }

    ordered: list[dict[str, Any]] = []
    for outcome in ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"):
        item = grouped.get(outcome)
        if item is None:
            continue
        settlement_probability = totals.get(outcome)
        item["settlement_probability"] = (
            round(settlement_probability, 6) if settlement_probability is not None else None
        )
        item["settlement_probability_label"] = _probability_label(None, settlement_probability)
        ordered.append(item)
    return ordered


def _ah_outcome_for_scoreline(
    *,
    side: str,
    home_line: float,
    home_goals: int,
    away_goals: int,
) -> str:
    selected_line = home_line if side == "HOME" else -home_line
    goal_margin = home_goals - away_goals if side == "HOME" else away_goals - home_goals
    parts = _quarter_line_parts(selected_line)
    outcomes = [_single_ah_outcome(goal_margin + part) for part in parts]
    if outcomes[0] == outcomes[1]:
        return outcomes[0]
    if set(outcomes) == {"WIN", "PUSH"}:
        return "HALF_WIN"
    if set(outcomes) == {"LOSS", "PUSH"}:
        return "HALF_LOSS"
    return "PUSH"


def _quarter_line_parts(line: float) -> tuple[float, float]:
    doubled = round(line * 2) / 2
    if math.isclose(line, doubled, abs_tol=1e-9):
        return (doubled, doubled)
    lower = math.floor(line * 2) / 2
    upper = math.ceil(line * 2) / 2
    return (lower, upper)


def _single_ah_outcome(adjusted_margin: float) -> str:
    if adjusted_margin > 0:
        return "WIN"
    if adjusted_margin < 0:
        return "LOSS"
    return "PUSH"


def _ah_outcome_label(outcome: str) -> str:
    labels = {
        "WIN": "全赢",
        "HALF_WIN": "半赢",
        "PUSH": "走水",
        "HALF_LOSS": "半输",
        "LOSS": "全输",
    }
    return labels.get(outcome, outcome)


def _poisson_probability(rate: float, goals: int) -> float:
    return math.exp(-rate) * rate**goals / math.factorial(goals)


def _number(value: Any) -> float | None:
    if isinstance(value, int | float):
        numeric = float(value)
    elif isinstance(value, str):
        try:
            numeric = float(value)
        except ValueError:
            return None
    else:
        return None
    return numeric if math.isfinite(numeric) else None


def _probability(value: Any) -> float | None:
    if isinstance(value, int | float):
        numeric = float(value)
    elif isinstance(value, str):
        try:
            numeric = float(value.strip().rstrip("%"))
            if value.strip().endswith("%"):
                numeric /= 100
        except ValueError:
            return None
    else:
        return None
    if numeric > 1:
        numeric /= 100
    if numeric < 0:
        return None
    return numeric


def _probability_label(existing: Any, probability: float | None) -> str | None:
    if isinstance(existing, str) and existing.strip():
        return existing
    if probability is None:
        return None
    return f"{round(probability * 100)}%"


def _score_part(scoreline: str, index: int) -> int | None:
    parts = scoreline.split("-", 1)
    if len(parts) != 2:
        return None
    try:
        return int(parts[index])
    except ValueError:
        return None
