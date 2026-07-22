from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

PRIMARY_THRESHOLD = 0.55
SECONDARY_THRESHOLD = 0.65
MAX_SECONDARY_CORRELATION = 0.35
SELECTABLE_MARKETS = frozenset({"ASIAN_HANDICAP", "TOTALS"})


@dataclass(frozen=True, kw_only=True)
class MarketSelection:
    primary_market: str | None
    secondary_markets: tuple[str, ...]
    audit: tuple[dict[str, Any], ...]


def select_analysis_markets(markets: Iterable[dict[str, Any]]) -> MarketSelection:
    audited: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    for market in markets:
        name = str(market.get("market") or "")
        score = _number(market.get("decision_score"), market.get("signal_strength"))
        decision = str(market.get("decision") or "")
        candidate = market.get("market_candidate")
        candidate_ready = (
            bool(candidate.get("ev_eligible")) if isinstance(candidate, dict) else True
        )
        line_ready = str(market.get("line_status") or "READY") == "READY" and candidate_ready
        complete = (
            decision in {"PICK", "ANALYSIS_PICK"} and line_ready and score >= PRIMARY_THRESHOLD
        )
        reason = "ELIGIBLE" if complete else _ineligible_reason(decision, line_ready, score, name)
        row = {
            "market": name,
            "decision_score": round(score, 6),
            "eligible": complete and name in SELECTABLE_MARKETS,
            "reason": reason,
            "calibration_error": _number(market.get("calibration_error"), 1.0),
            "quote_age_seconds": _number(market.get("quote_age_seconds"), 10**12),
            "bookmaker_count": int(market.get("bookmaker_count") or 0),
            "ranking_basis": "CALIBRATED"
            if market.get("calibration_comparable") is True
            else "ANALYSIS_ONLY_UNCALIBRATED",
        }
        audited.append(row)
        if row["eligible"]:
            eligible.append({**market, **row})
    eligible.sort(key=_rank_key)
    primary = eligible[0] if eligible else None
    secondaries: tuple[str, ...] = ()
    if primary is not None and len(eligible) > 1:
        candidate = eligible[1]
        correlation = _number(candidate.get("settlement_correlation"), 1.0)
        support = candidate.get("scoreline_support_intersection")
        if (
            float(candidate["decision_score"]) >= SECONDARY_THRESHOLD
            and abs(correlation) <= MAX_SECONDARY_CORRELATION
            and isinstance(support, list)
            and bool(support)
        ):
            secondaries = (str(candidate["market"]),)
    primary_name = str(primary["market"]) if primary is not None else None
    return MarketSelection(
        primary_market=primary_name,
        secondary_markets=secondaries,
        audit=tuple(audited),
    )


def apply_market_selection(payload: dict[str, Any]) -> None:
    markets = payload.get("markets")
    if not isinstance(markets, list):
        return
    typed = [row for row in markets if isinstance(row, dict)]
    selection = select_analysis_markets(typed)
    payload["market_selection_audit"] = list(selection.audit)
    payload["primary_market"] = selection.primary_market
    payload["secondary_picks"] = [
        row for row in typed if str(row.get("market")) in selection.secondary_markets
    ]
    for row in typed:
        row["decision_score"] = round(
            _number(row.get("decision_score"), row.get("signal_strength")), 6
        )
        row["selection_role"] = (
            "PRIMARY"
            if row.get("market") == selection.primary_market
            else "SECONDARY"
            if row.get("market") in selection.secondary_markets
            else None
        )
        row["ranking_basis"] = next(
            (
                audit["ranking_basis"]
                for audit in selection.audit
                if audit["market"] == row.get("market")
            ),
            "ANALYSIS_ONLY_UNCALIBRATED",
        )


def enrich_secondary_evidence(payload: dict[str, Any]) -> None:
    markets = payload.get("markets")
    simulation = payload.get("simulation")
    if not isinstance(markets, list) or not isinstance(simulation, dict):
        return
    lambda_home = _optional_number(simulation.get("lambda_home"))
    lambda_away = _optional_number(simulation.get("lambda_away"))
    if lambda_home is None or lambda_away is None:
        return
    by_name = {str(row.get("market") or ""): row for row in markets if isinstance(row, dict)}
    ah = by_name.get("ASIAN_HANDICAP")
    totals = by_name.get("TOTALS")
    if not isinstance(ah, dict) or not isinstance(totals, dict):
        return
    ah_line = _optional_number(ah.get("line"))
    totals_line = _optional_number(totals.get("line"))
    if ah_line is None or totals_line is None:
        return
    weighted: list[tuple[float, float, float, str]] = []
    support: list[tuple[float, str]] = []
    for home in range(11):
        for away in range(11):
            probability = _poisson(lambda_home, home) * _poisson(lambda_away, away)
            ah_return = _settlement_return(
                market="ASIAN_HANDICAP",
                tendency=str(ah.get("tendency") or ""),
                line=ah_line,
                home=home,
                away=away,
            )
            totals_return = _settlement_return(
                market="TOTALS",
                tendency=str(totals.get("tendency") or ""),
                line=totals_line,
                home=home,
                away=away,
            )
            score = f"{home}-{away}"
            weighted.append((probability, ah_return, totals_return, score))
            if ah_return > 0 and totals_return > 0:
                support.append((probability, score))
    correlation = _weighted_correlation(weighted)
    intersection = [score for _, score in sorted(support, reverse=True)[:10]]
    for row in (ah, totals):
        row["settlement_correlation"] = round(correlation, 6)
        row["scoreline_support_intersection"] = intersection


def _rank_key(row: dict[str, Any]) -> tuple[float, float, float, int, str]:
    return (
        -float(row["decision_score"]),
        float(row["calibration_error"]),
        float(row["quote_age_seconds"]),
        -int(row["bookmaker_count"]),
        str(row["market"]),
    )


def _ineligible_reason(decision: str, line_ready: bool, score: float, market: str) -> str:
    if market not in SELECTABLE_MARKETS:
        return "MARKET_NOT_SELECTABLE"
    if decision not in {"PICK", "ANALYSIS_PICK"}:
        return "DECISION_NOT_PICK"
    if not line_ready:
        return "QUOTE_NOT_COMPLETE_OR_FRESH"
    if score < PRIMARY_THRESHOLD:
        return "SCORE_BELOW_PRIMARY_THRESHOLD"
    return "INELIGIBLE"


def _number(*values: Any) -> float:
    for value in values:
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _optional_number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _poisson(expected: float, goals: int) -> float:
    return math.exp(-expected) * expected**goals / math.factorial(goals)


def _settlement_return(*, market: str, tendency: str, line: float, home: int, away: int) -> float:
    parts = (line - 0.25, line + 0.25) if abs(line * 2 - round(line * 2)) > 1e-9 else (line, line)
    returns: list[float] = []
    for part in parts:
        if market == "ASIAN_HANDICAP":
            selected_margin = home - away if "HOME" in tendency else away - home
            value = selected_margin + part
        else:
            value = home + away - part if "OVER" in tendency else part - home - away
        returns.append(1.0 if value > 0 else -1.0 if value < 0 else 0.0)
    return sum(returns) / len(returns)


def _weighted_correlation(rows: list[tuple[float, float, float, str]]) -> float:
    total_weight = sum(row[0] for row in rows)
    if total_weight <= 0:
        return 1.0
    mean_x = sum(weight * x for weight, x, _, _ in rows) / total_weight
    mean_y = sum(weight * y for weight, _, y, _ in rows) / total_weight
    covariance = sum(weight * (x - mean_x) * (y - mean_y) for weight, x, y, _ in rows)
    variance_x = sum(weight * (x - mean_x) ** 2 for weight, x, _, _ in rows)
    variance_y = sum(weight * (y - mean_y) ** 2 for weight, _, y, _ in rows)
    denominator = math.sqrt(variance_x * variance_y)
    return covariance / denominator if denominator > 0 else 1.0
