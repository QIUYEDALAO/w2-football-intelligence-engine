from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from w2.domain.enums import SettlementOutcome
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.models.fair_market_estimate import snapshot_score_matrix, verify_estimate_snapshot

SCHEMA_VERSION = "w2.analysis_gate_v2_shadow.v1"
MIN_NET_EV = 0.02
MAX_LOSS_PROBABILITY = 0.35
MAX_DOWNSIDE_PROBABILITY = 0.55


def build_analysis_gate_v2_shadow(
    *,
    estimate: Mapping[str, Any],
    gate: Mapping[str, Any],
    odds: object,
) -> dict[str, Any]:
    semantic_status = str(
        estimate.get("semantic_status") or "LEGACY_DISTRIBUTION_CONTEXT_UNVERIFIED"
    )
    evidence_eligible = (
        estimate.get("schema_version") == "w2.fme_snapshot.v2"
        and semantic_status == "PASS"
        and estimate.get("evidence_eligible") is True
        and verify_estimate_snapshot(estimate)
    )
    base = {
        "schema_version": SCHEMA_VERSION,
        "estimate_id": estimate.get("estimate_id"),
        "market": gate.get("market"),
        "selection": gate.get("selection"),
        "line": gate.get("market_line"),
        "odds": _number(odds),
        "current_gate_status": gate.get("status"),
        "current_gate_pass": gate.get("status") == "ELIGIBLE",
        "thresholds": {
            "min_net_ev": MIN_NET_EV,
            "max_loss_probability": MAX_LOSS_PROBABILITY,
            "max_downside_probability": MAX_DOWNSIDE_PROBABILITY,
        },
        "affects_decision": False,
        "affects_pick": False,
        "affects_tier": False,
        "shadow_only": True,
        "raw_shadow_capture": True,
        "diagnostic_only": not evidence_eligible,
        "evidence_eligible": evidence_eligible,
        "not_a_recommendation": True,
        "semantic_status": semantic_status,
    }
    if estimate.get("estimate_id") and not verify_estimate_snapshot(estimate):
        return {**base, "status": "INSUFFICIENT", "reason": "INVALID_ESTIMATE_INTEGRITY"}
    matrix = snapshot_score_matrix(estimate)
    market = str(gate.get("market") or "")
    selection = str(gate.get("selection") or "")
    line = _number(gate.get("market_line"))
    decimal_odds = _number(odds)
    settlement_side = _settlement_side(market, selection)
    if matrix is None or line is None or decimal_odds is None or decimal_odds <= 1:
        return {**base, "status": "INSUFFICIENT", "reason": "MISSING_SHADOW_INPUT"}
    if settlement_side is None:
        return {**base, "status": "INSUFFICIENT", "reason": "UNSUPPORTED_SELECTION"}
    buckets = {outcome.value: 0.0 for outcome in SettlementOutcome}
    decimal_line = Decimal(str(line))
    for (home, away), probability in matrix.items():
        outcome = (
            settle_asian_handicap(home, away, settlement_side, decimal_line)
            if market == "ASIAN_HANDICAP"
            else settle_total_goals(home + away, settlement_side, decimal_line)
        )
        buckets[outcome.value] += probability
    net_ev = (
        buckets["WIN"] * (decimal_odds - 1)
        + buckets["HALF_WIN"] * (decimal_odds - 1) / 2
        - buckets["HALF_LOSS"] / 2
        - buckets["LOSS"]
    )
    loss_probability = buckets["LOSS"]
    downside_probability = buckets["HALF_LOSS"] + loss_probability
    candidate_pass = (
        net_ev >= MIN_NET_EV
        and loss_probability <= MAX_LOSS_PROBABILITY
        and downside_probability <= MAX_DOWNSIDE_PROBABILITY
    )
    return {
        **base,
        "status": "PASS" if candidate_pass else "FAIL",
        "reason": None if candidate_pass else "SHADOW_THRESHOLDS_NOT_MET",
        "candidate_pass": candidate_pass,
        "net_ev": round(net_ev, 8),
        "loss_probability": round(loss_probability, 8),
        "downside_probability": round(downside_probability, 8),
        "settlement_probabilities": {
            key: round(value, 8) for key, value in buckets.items()
        },
    }


def _settlement_side(market: str, selection: str) -> str | None:
    if market == "ASIAN_HANDICAP":
        return {"HOME_AH": "HOME", "AWAY_AH": "AWAY"}.get(selection)
    if market == "TOTALS" and selection in {"OVER", "UNDER"}:
        return selection
    return None


def _number(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None
