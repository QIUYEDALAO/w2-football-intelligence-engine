from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class MatchDecisionState(StrEnum):
    LOCKED = "LOCKED"
    FORMAL = "FORMAL"
    WATCH = "WATCH"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    MARKET_NOT_READY = "MARKET_NOT_READY"


@dataclass(frozen=True)
class MatchDecision:
    state: MatchDecisionState
    reason: str
    label_cn: str


INDEPENDENT_SIGNAL_MINIMUM = 3
EDGE_FORMAL_MINIMUM = 0.25

_LIVE_STATUS_PARTS = (
    "LIVE",
    "IN_PLAY",
    "1H",
    "2H",
    "HT",
    "ET",
    "PEN",
    "FINISHED",
    "FT",
    "MATCH_FINISHED",
)
_MARKET_BLOCKERS = {
    "MISSING_AH_MARKET",
    "MISSING_MARKET_AH",
    "MISSING_ODDS",
    "AH_MAINLINE_AMBIGUOUS",
    "AH_PRIMARY_MAINLINE_MISSING",
    "AH_MAINLINE_JUMP_REQUIRES_PRIMARY_CONFIRMATION",
    "AH_MARKET_LINE_MAGNITUDE_MISMATCH",
    "AH_MARKET_HOME_LINE_MAGNITUDE_MISMATCH",
    "AH_MARKET_ABS_LINE_MISMATCH",
    "AH_MARKET_LINE_SIDE_MISMATCH",
}
_VALID_FORMAL_SELECTIONS = {"HOME_AH", "AWAY_AH"}


def decide_match(
    match: dict[str, Any],
    *,
    independent_signal_minimum: int = INDEPENDENT_SIGNAL_MINIMUM,
    edge_minimum: float = EDGE_FORMAL_MINIMUM,
) -> MatchDecision:
    if _is_locked(match):
        return MatchDecision(
            MatchDecisionState.LOCKED,
            "MATCH_STARTED_OR_SETTLEMENT_PRESENT",
            "赛前判断已锁定",
        )

    shadow = _dict(match.get("pricing_shadow"))
    if not shadow:
        return MatchDecision(
            MatchDecisionState.DATA_INSUFFICIENT,
            "MISSING_PRICING_SHADOW",
            "数据不足",
        )
    shadow_status = str(shadow.get("status") or "")
    if shadow_status == "INSUFFICIENT_INDEPENDENT_FACTORS":
        return MatchDecision(
            MatchDecisionState.DATA_INSUFFICIENT,
            shadow_status,
            "数据不足",
        )
    signal_count = _number(shadow.get("independent_signal_count"))
    if signal_count is not None and signal_count < independent_signal_minimum:
        return MatchDecision(
            MatchDecisionState.DATA_INSUFFICIENT,
            "INDEPENDENT_SIGNAL_COUNT_BELOW_MINIMUM",
            "数据不足",
        )

    market_blocker = _market_blocker(shadow)
    if market_blocker is not None:
        return MatchDecision(
            MatchDecisionState.MARKET_NOT_READY,
            market_blocker,
            "盘口未就绪",
        )
    market_ah = _number(shadow.get("market_ah"))
    if market_ah is None:
        return MatchDecision(
            MatchDecisionState.MARKET_NOT_READY,
            "MISSING_MARKET_AH",
            "盘口未就绪",
        )

    fair_ah = _number(shadow.get("fair_ah"))
    edge_ah = _number(shadow.get("edge_ah"))
    if fair_ah is None:
        return MatchDecision(
            MatchDecisionState.WATCH,
            "MISSING_FAIR_AH",
            "观察",
        )
    if edge_ah is None:
        edge_ah = market_ah - fair_ah
    if abs(edge_ah) < edge_minimum:
        return MatchDecision(
            MatchDecisionState.WATCH,
            "EDGE_BELOW_FORMAL_THRESHOLD",
            "观察",
        )
    if _direction_inconsistent(match, edge_ah):
        return MatchDecision(
            MatchDecisionState.WATCH,
            "RECOMMENDATION_DIRECTION_INCONSISTENT",
            "观察",
        )
    if not _has_valid_formal_recommendation(match):
        return MatchDecision(
            MatchDecisionState.WATCH,
            "INVALID_FORMAL_RECOMMENDATION_PAYLOAD",
            "观察",
        )
    return MatchDecision(
        MatchDecisionState.FORMAL,
        "FORMAL_REPORTABLE",
        "正式推荐",
    )


def _is_locked(match: dict[str, Any]) -> bool:
    status_text = " ".join(
        str(match.get(key) or "") for key in ("status", "raw_status", "lifecycle_state")
    ).upper()
    if any(part in status_text for part in _LIVE_STATUS_PARTS):
        return True
    validation = _dict(match.get("validation"))
    settlement = str(validation.get("settlement") or validation.get("settlement_status") or "")
    if settlement and settlement != "PENDING":
        return True
    if match.get("result") is not None:
        return True
    locked = _dict(match.get("locked_pre_match_recommendation"))
    return bool(locked)


def _market_blocker(shadow: dict[str, Any]) -> str | None:
    for key in (
        "ah_mainline_blocker",
        "canonical_ah_market_blocker",
        "canonical_ah_market_validation_status",
    ):
        value = shadow.get(key)
        if isinstance(value, str) and value and value not in {"READY", "VALID"}:
            if value in _MARKET_BLOCKERS or key != "canonical_ah_market_validation_status":
                return value
    for item in _list(shadow.get("formal_blockers")):
        if isinstance(item, str) and item in _MARKET_BLOCKERS:
            return item
    canonical = _dict(shadow.get("canonical_ah_market"))
    blocker = canonical.get("blocker")
    if isinstance(blocker, str) and blocker:
        return blocker
    return None


def _direction_inconsistent(match: dict[str, Any], edge_ah: float) -> bool:
    recommendation = _dict(match.get("recommendation"))
    selection = str(recommendation.get("selection") or "")
    if selection not in _VALID_FORMAL_SELECTIONS:
        return False
    if edge_ah > 0:
        return selection != "HOME_AH"
    if edge_ah < 0:
        return selection != "AWAY_AH"
    return True


def _has_valid_formal_recommendation(match: dict[str, Any]) -> bool:
    recommendation = _dict(match.get("recommendation"))
    tier = str(recommendation.get("tier") or "").upper()
    formal_payload = tier == "FORMAL" or match.get("formal_recommendation") is True
    if not formal_payload:
        return False
    market = str(recommendation.get("market") or "").upper()
    if market != "ASIAN_HANDICAP":
        return False
    selection = str(recommendation.get("selection") or "").upper()
    if selection not in _VALID_FORMAL_SELECTIONS:
        return False
    if _number(recommendation.get("line")) is None:
        return False
    odds = recommendation.get("odds")
    return odds is None or _number(odds) is not None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None
