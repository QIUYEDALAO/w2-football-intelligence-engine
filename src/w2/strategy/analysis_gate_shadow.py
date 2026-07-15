from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from w2.domain.enums import SettlementOutcome
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.models.fair_market_estimate import (
    snapshot_score_matrix,
    verify_estimate_semantics,
    verify_estimate_snapshot,
)

SCHEMA_VERSION = "w2.analysis_gate_v2_shadow.v1"
POLICY_PATH = Path(__file__).with_name("ah_strict_shadow.v1.json")
STRICT_POLICY = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
STRICT_GATE_HASH = hashlib.sha256(
    json.dumps(STRICT_POLICY, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
STRICT_STRATEGY_VERSION = str(STRICT_POLICY["strategy_version"])
_THRESHOLDS = STRICT_POLICY["thresholds"]
_CONFIRMATION = STRICT_POLICY["confirmation"]
MIN_NET_EV = float(_THRESHOLDS["min_net_ev"])
MAX_LOSS_PROBABILITY = float(_THRESHOLDS["max_loss_probability"])
MAX_DOWNSIDE_PROBABILITY = float(_THRESHOLDS["max_downside_probability"])


def build_analysis_gate_v2_shadow(
    *,
    estimate: Mapping[str, Any],
    gate: Mapping[str, Any],
    odds: object,
    selection_line: object | None = None,
    fixture_id: object | None = None,
    kickoff_utc: object | None = None,
    quote_id: object | None = None,
    quote_captured_at: object | None = None,
) -> dict[str, Any]:
    is_strict_ah = str(gate.get("market") or "") == "ASIAN_HANDICAP"
    semantic_status = str(
        estimate.get("semantic_status") or "LEGACY_DISTRIBUTION_CONTEXT_UNVERIFIED"
    )
    evidence_eligible = (
        estimate.get("schema_version") == "w2.fme_snapshot.v2"
        and semantic_status == "VERIFIED"
        and estimate.get("evidence_eligible") is True
        and verify_estimate_snapshot(estimate)
        and verify_estimate_semantics(estimate)
    )
    base = {
        "schema_version": SCHEMA_VERSION,
        "estimate_id": estimate.get("estimate_id"),
        "model_basis_id": estimate.get("model_basis_id"),
        "fixture_id": str(fixture_id or estimate.get("fixture_id") or ""),
        "kickoff_utc": kickoff_utc,
        "quote_id": quote_id,
        "quote_captured_at": quote_captured_at,
        "market": gate.get("market"),
        "selection": gate.get("selection"),
        "home_centric_market_line": gate.get("market_line"),
        "selection_line": _number(selection_line),
        "line": _number(selection_line),
        "odds": _number(odds),
        "current_gate_status": gate.get("status"),
        "current_gate_pass": gate.get("status") == "ELIGIBLE",
        "thresholds": {
            "min_net_ev": MIN_NET_EV,
            "max_loss_probability": MAX_LOSS_PROBABILITY,
            "max_downside_probability": MAX_DOWNSIDE_PROBABILITY,
        },
        "strategy_version": STRICT_STRATEGY_VERSION if is_strict_ah else SCHEMA_VERSION,
        "strict_gate_hash": STRICT_GATE_HASH if is_strict_ah else None,
        "confirmation_required": is_strict_ah,
        "confirmation_status": "PENDING" if is_strict_ah else "NOT_REQUIRED",
        "affects_decision": False,
        "affects_pick": False,
        "affects_tier": False,
        "shadow_only": True,
        "visible_eligible": False,
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
    home_centric_line = _number(gate.get("market_line"))
    line = _number(selection_line)
    if line is None and home_centric_line is not None:
        line = (
            -home_centric_line
            if market == "ASIAN_HANDICAP" and selection == "AWAY_AH"
            else home_centric_line
        )
        base["selection_line"] = line
        base["line"] = line
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
    settlement_probabilities = _rounded_probabilities(buckets)
    return {
        **base,
        "status": (
            "CONFIRMATION_PENDING"
            if candidate_pass and is_strict_ah
            else "PASS"
            if candidate_pass
            else "FAIL"
        ),
        "reason": None if candidate_pass else "SHADOW_THRESHOLDS_NOT_MET",
        "candidate_pass": candidate_pass,
        "net_ev": round(net_ev, 8),
        "loss_probability": round(loss_probability, 8),
        "downside_probability": round(downside_probability, 8),
        "settlement_probabilities": settlement_probabilities,
    }


def confirm_strict_ah_shadow(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        (dict(item) for item in candidates),
        key=lambda item: (
            _parse_time(item.get("quote_captured_at")) or datetime.min.replace(tzinfo=UTC)
        ),
    )
    latest = ordered[-1] if ordered else {}
    base = {
        **latest,
        "schema_version": "w2.ah_strict_shadow_confirmation.v1",
        "strategy_version": STRICT_STRATEGY_VERSION,
        "strict_gate_hash": STRICT_GATE_HASH,
        "confirmation_required": True,
        "shadow_only": True,
        "visible_eligible": False,
        "affects_decision": False,
        "affects_pick": False,
        "affects_tier": False,
        "not_a_recommendation": True,
    }
    if not ordered:
        return {**base, "status": "CONFIRMATION_PENDING", "reason": "FIRST_SNAPSHOT_REQUIRED"}
    if str(latest.get("market") or "") != "ASIAN_HANDICAP":
        return {**base, "status": "FAIL", "reason": "UNSUPPORTED_STRICT_MARKET"}
    if latest.get("candidate_pass") is not True:
        return {**base, "status": "FAIL", "reason": "LATEST_THRESHOLDS_NOT_MET"}
    if (
        latest.get("evidence_eligible") is not True
        or latest.get("semantic_status") != "VERIFIED"
        or not latest.get("fixture_id")
        or not latest.get("model_basis_id")
        or not latest.get("estimate_id")
        or not latest.get("quote_id")
    ):
        return {**base, "status": "FAIL", "reason": "LATEST_EVIDENCE_INVALID"}

    kickoff = _parse_time(latest.get("kickoff_utc"))
    latest_time = _parse_time(latest.get("quote_captured_at"))
    if (
        kickoff is None
        or latest_time is None
        or not _inside_confirmation_window(latest_time, kickoff)
    ):
        return {**base, "status": "FAIL", "reason": "OUTSIDE_CONFIRMATION_WINDOW"}

    within_window = [
        item
        for item in ordered
        if _parse_time(item.get("kickoff_utc")) == kickoff
        and (captured := _parse_time(item.get("quote_captured_at"))) is not None
        and _inside_confirmation_window(captured, kickoff)
    ]
    if len(within_window) < int(_CONFIRMATION["minimum_snapshots"]):
        return {
            **base,
            "status": "CONFIRMATION_PENDING",
            "confirmation_status": "PENDING",
            "reason": "SECOND_SNAPSHOT_REQUIRED",
        }

    previous = within_window[-2]
    if previous.get("fixture_id") != latest.get("fixture_id") or previous.get(
        "market"
    ) != latest.get("market"):
        return {**base, "status": "FAIL", "reason": "CONFIRMATION_IDENTITY_MISMATCH"}
    if previous.get("model_basis_id") != latest.get("model_basis_id"):
        return {
            **base,
            "status": "CONFIRMATION_PENDING",
            "confirmation_status": "RESET",
            "reason": "MODEL_BASIS_CHANGED_CONFIRMATION_RESET",
        }
    if previous.get("selection") != latest.get("selection"):
        return {**base, "status": "FAIL", "reason": "DIRECTION_REVERSAL"}
    if not previous.get("quote_id") or previous.get("quote_id") == latest.get("quote_id"):
        return {
            **base,
            "status": "CONFIRMATION_PENDING",
            "confirmation_status": "PENDING",
            "reason": "DISTINCT_QUOTE_REQUIRED",
        }
    previous_time = _parse_time(previous.get("quote_captured_at"))
    if previous_time is None or latest_time - previous_time < timedelta(
        minutes=int(_CONFIRMATION["minimum_interval_minutes"])
    ):
        return {
            **base,
            "status": "CONFIRMATION_PENDING",
            "confirmation_status": "PENDING",
            "reason": "MINIMUM_INTERVAL_NOT_MET",
        }
    if previous.get("candidate_pass") is not True:
        return {**base, "status": "FAIL", "reason": "FIRST_THRESHOLDS_NOT_MET"}
    if (
        previous.get("evidence_eligible") is not True
        or previous.get("semantic_status") != "VERIFIED"
        or not previous.get("estimate_id")
    ):
        return {**base, "status": "FAIL", "reason": "FIRST_EVIDENCE_INVALID"}

    return {
        **base,
        "status": "PASS",
        "candidate_pass": True,
        "confirmation_status": "CONFIRMED",
        "reason": None,
        "evidence_bindings": [
            {
                "estimate_id": previous.get("estimate_id"),
                "quote_id": previous.get("quote_id"),
            },
            {
                "estimate_id": latest.get("estimate_id"),
                "quote_id": latest.get("quote_id"),
            },
        ],
    }


def _inside_confirmation_window(captured_at: datetime, kickoff: datetime) -> bool:
    return (
        kickoff - timedelta(hours=int(_CONFIRMATION["earliest_before_kickoff_hours"]))
        <= (captured_at)
        <= kickoff - timedelta(minutes=int(_CONFIRMATION["latest_before_kickoff_minutes"]))
    )


def _parse_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _settlement_side(market: str, selection: str) -> str | None:
    if market == "ASIAN_HANDICAP":
        return {"HOME_AH": "HOME", "AWAY_AH": "AWAY"}.get(selection)
    if market == "TOTALS" and selection in {"OVER", "UNDER"}:
        return selection
    return None


def _rounded_probabilities(values: Mapping[str, float]) -> dict[str, float]:
    rounded = {key: round(value, 8) for key, value in values.items()}
    residual = round(1.0 - sum(rounded.values()), 8)
    if residual:
        largest = min(rounded, key=lambda key: (-rounded[key], key))
        rounded[largest] = round(rounded[largest] + residual, 8)
    return rounded


def _number(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None
