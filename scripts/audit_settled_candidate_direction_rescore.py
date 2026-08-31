#!/usr/bin/env python3
"""Replay settled candidates and compare model direction with the result.

The input is the frozen, read-only CSV export produced by
``settled_candidate_rescore_export.sql``.  It contains no provider or database
calls.  Direction is derived from the persisted full score matrix; the V1
counterfactual removes only the persisted home-advantage shift.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.markets.settlement_probability import effective_settlement_probability
from w2.strategy.simulate import (
    _exact_score_matrix_with_uncertainty,
    ah_settlement_distribution,
    score_matrix_from_simulation,
)

csv.field_size_limit(sys.maxsize)

SIDES = {"HOME": "AWAY", "AWAY": "HOME", "OVER": "UNDER", "UNDER": "OVER"}
OUTCOMES = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")


def _json(value: str | None) -> dict[str, Any]:
    return json.loads(value) if value else {}


def _float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _effective(distribution: dict[str, Any]) -> float:
    value = effective_settlement_probability(distribution)
    if value is None:
        raise ValueError("invalid five-state distribution")
    return float(value)


def _distribution(
    market: str,
    selection: str,
    line: Decimal,
    matrix: dict[tuple[int, int], float],
) -> dict[str, float]:
    if market == "ASIAN_HANDICAP":
        return ah_settlement_distribution(
            matrix, simulations=1, selection=selection, line=float(line)
        )
    counts: Counter[int] = Counter()
    for (home, away), probability in matrix.items():
        counts[home + away] += probability
    values = {outcome: 0.0 for outcome in OUTCOMES}
    for total, probability in counts.items():
        outcome = settle_total_goals(total, selection, line).value
        values[outcome] += probability
    return values


def _direction(
    market: str,
    line: Decimal,
    matrix: dict[tuple[int, int], float],
    *,
    selected_side: str | None = None,
) -> dict[str, Any]:
    sides = ("HOME", "AWAY") if market == "ASIAN_HANDICAP" else ("OVER", "UNDER")
    # AH evaluation lines are expressed from the selected side's perspective
    # (e.g. AWAY +0.5), while the two-sided ladder uses a canonical HOME line.
    canonical_home_line = -line if market == "ASIAN_HANDICAP" and selected_side == "AWAY" else line
    distributions = {
        side: _distribution(
            market,
            side,
            canonical_home_line
            if side == "HOME" and market == "ASIAN_HANDICAP"
            else (-canonical_home_line if market == "ASIAN_HANDICAP" else line),
            matrix,
        )
        for side in sides
    }
    probabilities = {side: round(_effective(dist), 6) for side, dist in distributions.items()}
    ordered = sorted(sides, key=lambda side: (-probabilities[side], side))
    return {
        "predicted": ordered[0],
        "probabilities": probabilities,
        "settlement_distributions": distributions,
        "margin": round(probabilities[ordered[0]] - probabilities[ordered[1]], 6),
    }


def _actual(market: str, selection: str, line: Decimal, home: int, away: int) -> dict[str, Any]:
    target = (
        settle_asian_handicap(home, away, selection, line)
        if market == "ASIAN_HANDICAP"
        else settle_total_goals(home + away, selection, line)
    ).value
    opposite = SIDES[selection]
    opposite_line = -line if market == "ASIAN_HANDICAP" else line
    reverse = (
        settle_asian_handicap(home, away, opposite, opposite_line)
        if market == "ASIAN_HANDICAP"
        else settle_total_goals(home + away, opposite, opposite_line)
    ).value
    if target in {"WIN", "HALF_WIN"}:
        direction = selection
    elif reverse in {"WIN", "HALF_WIN"}:
        direction = opposite
    else:
        direction = "PUSH"
    return {
        "direction": direction,
        "target_settlement": target,
        "opposite_settlement": reverse,
        "score": f"{home}-{away}",
    }


def _no_home_matrix(
    simulation: dict[str, Any],
) -> tuple[dict[tuple[int, int], float], dict[str, Any]]:
    """Remove the recorded home shift while preserving total and uncertainty."""
    params = simulation.get("calibration", {}).get("params", {})
    applied = _float(params.get("applied_home_advantage_goals"))
    home = _float(simulation.get("lambda_home"))
    away = _float(simulation.get("lambda_away"))
    if applied is None or home is None or away is None:
        raise ValueError("home-advantage inputs are incomplete")
    minimum = _float(params.get("minimum_lambda")) or 0.15
    maximum = _float(params.get("maximum_lambda")) or 4.25
    raw_home = home - applied / 2.0
    raw_away = away + applied / 2.0
    adjusted_home = min(max(raw_home, minimum), maximum)
    adjusted_away = min(max(raw_away, minimum), maximum)
    rho = _float(params.get("dixon_coles_rho")) or 0.0
    sigma_home = _float(simulation.get("lambda_sigma_home")) or 0.0
    sigma_away = _float(simulation.get("lambda_sigma_away")) or 0.0
    max_goals = int(
        params.get("max_goals") or simulation.get("calibration", {}).get("max_goals") or 12
    )
    matrix = _exact_score_matrix_with_uncertainty(
        adjusted_home,
        adjusted_away,
        sigma_home=sigma_home,
        sigma_away=sigma_away,
        rho=rho,
        max_goals=max_goals,
    )
    return matrix, {
        "lambda_home": round(adjusted_home, 6),
        "lambda_away": round(adjusted_away, 6),
        "applied_home_advantage_goals": 0.0,
        "clamp_changed_shift": (adjusted_home != raw_home or adjusted_away != raw_away),
    }


def _replay_row(raw: dict[str, str]) -> dict[str, Any]:
    evaluation = _json(raw["evaluation_payload"])
    capture = _json(raw.get("model_capture_payload"))
    checkpoint = _json(raw.get("checkpoint_payload"))
    simulation = checkpoint.get("analysis_card", {}).get("simulation", {})
    if not simulation:
        raise ValueError(f"{raw.get('fixture_id')}: missing checkpoint simulation")
    matrix = score_matrix_from_simulation(simulation)
    if not matrix:
        raise ValueError(f"{raw.get('fixture_id')}: empty score matrix")
    market = str(raw["market"])
    selection = str(raw["selection"]).upper().replace("_AH", "").replace("_TOTALS", "")
    line = Decimal(str(evaluation["exact_line"]))
    home, away = int(raw["home_goals"]), int(raw["away_goals"])
    predicted = _direction(market, line, matrix, selected_side=selection)
    actual = _actual(market, selection, line, home, away)
    no_home_matrix, no_home_lambdas = _no_home_matrix(simulation)
    no_home = _direction(market, line, no_home_matrix, selected_side=selection)
    four_fields = capture.get("four_field_xg_identity", {}).get("four_fields", {})
    readiness = simulation.get("input_readiness", {})
    return {
        "evaluation_id": raw["evaluation_id"],
        "fixture_id": raw["fixture_id"],
        "market": market,
        "selection": selection,
        "line": float(line),
        "evaluated_at": raw["evaluated_at"],
        "calibration_identity": evaluation.get("calibration_identity")
        or capture.get("calibration_identity"),
        "model_version": simulation.get("model_version"),
        "input": {
            "four_field_xg": four_fields,
            "xg_status": readiness.get("xg_status"),
            "xg_ready": readiness.get("xg_ready"),
            "home_advantage_applied": readiness.get("home_advantage_applied"),
        },
        "production_replay": {
            "lambda_home": _float(simulation.get("lambda_home")),
            "lambda_away": _float(simulation.get("lambda_away")),
            "predicted": predicted,
            "original_selection": selection,
            "original_selection_matches_model": predicted["predicted"] == selection,
        },
        "no_home_advantage": {"predicted": no_home, **no_home_lambdas},
        "actual": actual,
        "settlement_outcome": actual["target_settlement"],
        "direction_correct": predicted["predicted"] == actual["direction"],
        "original_bet_direction_correct": selection == actual["direction"],
        "settlement": raw.get("result_status"),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_market: dict[str, Any] = {}
    for market in ("ASIAN_HANDICAP", "TOTALS"):
        scoped = [row for row in rows if row["market"] == market]
        by_market[market] = {
            "count": len(scoped),
            "model_predicted_direction": dict(
                Counter(row["production_replay"]["predicted"]["predicted"] for row in scoped)
            ),
            "actual_direction": dict(Counter(row["actual"]["direction"] for row in scoped)),
            "model_direction_correct": sum(row["direction_correct"] for row in scoped),
            "original_selection_matches_model": sum(
                row["production_replay"]["original_selection_matches_model"] for row in scoped
            ),
            "original_bet_direction_correct": sum(
                row["original_bet_direction_correct"] for row in scoped
            ),
            "no_home_advantage_flips": sum(
                row["no_home_advantage"]["predicted"]["predicted"]
                != row["production_replay"]["predicted"]["predicted"]
                for row in scoped
            ),
            "no_home_advantage_flip_to_actual": sum(
                row["no_home_advantage"]["predicted"]["predicted"] == row["actual"]["direction"]
                and row["production_replay"]["predicted"]["predicted"] != row["actual"]["direction"]
                for row in scoped
            ),
        }
    return {
        "by_market": by_market,
        "by_result_status": dict(Counter(row["settlement"] for row in rows)),
        "by_settlement_outcome": {
            outcome: {
                "count": sum(row["settlement_outcome"] == outcome for row in rows),
                "model_direction_correct": sum(
                    row["settlement_outcome"] == outcome and row["direction_correct"]
                    for row in rows
                ),
                "original_bet_direction_correct": sum(
                    row["settlement_outcome"] == outcome and row["original_bet_direction_correct"]
                    for row in rows
                ),
            }
            for outcome in OUTCOMES
        },
        "model_direction_correct": sum(row["direction_correct"] for row in rows),
        "original_selection_matches_model": sum(
            row["production_replay"]["original_selection_matches_model"] for row in rows
        ),
        "original_bet_direction_correct": sum(
            row["original_bet_direction_correct"] for row in rows
        ),
        "no_home_advantage_flips": sum(
            row["no_home_advantage"]["predicted"]["predicted"]
            != row["production_replay"]["predicted"]["predicted"]
            for row in rows
        ),
    }


def audit(path: Path) -> dict[str, Any]:
    rows = [_replay_row(raw) for raw in csv.DictReader(path.open(newline="", encoding="utf-8"))]
    if not rows:
        raise ValueError("input export is empty")
    result = {
        "schema_version": "w2.settled_candidate_direction_rescore.v1",
        "input_rows": len(rows),
        "fixture_count": len({row["fixture_id"] for row in rows}),
        "rows": rows,
        "summary": _summary(rows),
        "limitations": [
            (
                "This is a diagnostic replay of an already observed cohort; no parameter "
                "or threshold selection is authorized."
            ),
            (
                "Direction is compared separately from admission and P&L; a correct "
                "direction can still lose because of the AH line or totals line."
            ),
        ],
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.input)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
