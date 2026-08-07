from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

INTELLIGENCE_STATES = (
    "COLLECTION_INCIDENT",
    "DATA_INCOMPLETE",
    "MODEL_DIAGNOSTIC_WARNING",
    "MARKET_ANOMALY",
    "MODEL_MARKET_DISAGREEMENT",
    "MARKET_MOVEMENT",
    "MARKET_STABLE",
)
RISK_DIMENSIONS = ("EVENT_RISK", "DATA_RISK", "MODEL_RISK", "COLLECTION_RISK")
RECOMMENDATION_DECISION_V4_ROLE = "DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY"


def build_intelligence_projection(card: Mapping[str, Any]) -> dict[str, Any]:
    collection = _collection_reasons(card)
    data = _data_reasons(card)
    model = _model_reasons(card)
    anomaly = _market_anomaly_reasons(card)
    disagreement = _model_market_disagreement_reasons(card)
    movement = _market_movement_reasons(card)
    reasons_by_state = {
        "COLLECTION_INCIDENT": collection,
        "DATA_INCOMPLETE": data,
        "MODEL_DIAGNOSTIC_WARNING": model,
        "MARKET_ANOMALY": anomaly,
        "MODEL_MARKET_DISAGREEMENT": disagreement,
        "MARKET_MOVEMENT": movement,
    }
    state = next(
        (name for name in INTELLIGENCE_STATES if reasons_by_state.get(name)),
        "MARKET_STABLE",
    )
    reason_codes = [
        reason
        for name in INTELLIGENCE_STATES
        for reason in sorted(set(reasons_by_state.get(name, [])))
    ] or ["MARKET_STABLE_NO_MATERIAL_ALERT"]
    event = _event_reasons(card)
    return {
        "intelligence_state": state,
        "intelligence_reason_codes": reason_codes,
        "recommendation_decision_v4_role": RECOMMENDATION_DECISION_V4_ROLE,
        "risk_dimensions": {
            "EVENT_RISK": _risk_dimension("EVENT_RISK", event, "未发现明确赛事风险证据"),
            "DATA_RISK": _risk_dimension("DATA_RISK", data, "数据证据完整"),
            "MODEL_RISK": _risk_dimension(
                "MODEL_RISK",
                [*model, *disagreement],
                "模型诊断未见警告",
                attention_codes=set(disagreement),
            ),
            "COLLECTION_RISK": _risk_dimension(
                "COLLECTION_RISK", collection, "采集运行未见异常"
            ),
        },
    }


def intelligence_state_rank(state: Any) -> int:
    try:
        return INTELLIGENCE_STATES.index(str(state))
    except ValueError:
        return len(INTELLIGENCE_STATES)


def _risk_dimension(
    name: str,
    reasons: Sequence[str],
    ok_explanation: str,
    *,
    attention_codes: set[str] | None = None,
) -> dict[str, Any]:
    codes = sorted(set(reasons))
    if not codes:
        return {
            "dimension": name,
            "status": "OK",
            "reason_codes": [],
            "explanation": ok_explanation,
        }
    status = "ATTENTION" if attention_codes and set(codes) <= attention_codes else "INCIDENT"
    return {
        "dimension": name,
        "status": status,
        "reason_codes": codes,
        "explanation": "；".join(code.replace("_", " ") for code in codes),
    }


def _collection_reasons(card: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if str(card.get("provider_budget_status") or "").upper() == "EXHAUSTED":
        reasons.append("COLLECTION_PROVIDER_BUDGET_EXHAUSTED")
    projection_health = _mapping(card.get("projection_health"))
    if str(projection_health.get("status") or "").upper() == "SYSTEM_DEGRADED":
        reasons.append("COLLECTION_SYSTEM_DEGRADED")
    for code in _source_reason_codes(card):
        if any(
            marker in code
            for marker in ("PROVIDER", "SCHEDULER", "SCHEMA", "RUNTIME", "QUOTA")
        ):
            reasons.append(f"COLLECTION_{code}")
        elif any(marker in code for marker in ("COLLECTION_FAILED", "COLLECTION_ERROR")):
            reasons.append(code)
    return reasons


def _data_reasons(card: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not str(card.get("competition_id") or "").strip():
        reasons.append("DATA_IDENTITY_MISSING")
    data_status = str(card.get("data_status") or "").upper()
    if data_status and data_status != "READY":
        reasons.append(f"DATA_STATUS_{data_status}")
    if _string_list(card.get("missing_fields")) or _string_list(card.get("missing_inputs")):
        reasons.append("DATA_REQUIRED_INPUT_MISSING")
    if _string_list(card.get("stale_fields")):
        reasons.append("DATA_FIELD_STALE")
    for code in _source_reason_codes(card):
        if any(
            marker in code
            for marker in ("IDENTITY", "MAPPING", "XG", "QUOTE_MISSING", "QUOTE_STALE")
        ):
            reasons.append(f"DATA_{code}")
    return reasons


def _model_reasons(card: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    simulation = _mapping(card.get("simulation"))
    if str(simulation.get("status") or "").upper() != "READY":
        reasons.append("MODEL_SIMULATION_NOT_READY")
    for code in _source_reason_codes(card):
        if any(
            marker in code
            for marker in ("MODEL", "CALIBRATION", "SIMULATION", "FEATURE_STALE")
        ):
            reasons.append(code if code.startswith("MODEL_") else f"MODEL_{code}")
    return reasons


def _event_reasons(card: Mapping[str, Any]) -> list[str]:
    return [
        f"EVENT_{code}"
        for code in _source_reason_codes(card)
        if any(marker in code for marker in ("EVENT_RISK", "INJURY", "LINEUP_CHANGE"))
    ]


def _market_anomaly_reasons(card: Mapping[str, Any]) -> list[str]:
    movement = _movement(card)
    status = str(movement.get("status") or "").upper()
    pattern = str(movement.get("pattern") or "").upper()
    if status == "ANOMALY" or movement.get("anomaly") is True or pattern == "JUMP_LINE":
        return [f"MARKET_ANOMALY_{pattern or status or 'EXPLICIT'}"]
    return []


def _market_movement_reasons(card: Mapping[str, Any]) -> list[str]:
    movement = _movement(card)
    if str(movement.get("status") or "").upper() != "READY":
        return []
    pattern = str(movement.get("pattern") or "").upper()
    if movement.get("line_moved") is True or pattern not in {"", "STABLE", "INSUFFICIENT"}:
        return [f"MARKET_MOVEMENT_{pattern or 'LINE'}"]
    return []


def _model_market_disagreement_reasons(card: Mapping[str, Any]) -> list[str]:
    divergence = _mapping(card.get("model_market_divergence"))
    status = str(divergence.get("status") or "").upper()
    magnitude = divergence.get("magnitude")
    explicit = divergence.get("disagreement") is True or status in {
        "READY",
        "SIGNIFICANT",
        "ACTIONABLE",
    }
    if (
        explicit
        and isinstance(magnitude, int | float)
        and not isinstance(magnitude, bool)
        and magnitude > 0
    ):
        return ["MODEL_MARKET_DISAGREEMENT_OBSERVED"]
    return []


def _movement(card: Mapping[str, Any]) -> Mapping[str, Any]:
    movement = _mapping(card.get("market_movement"))
    return movement or _mapping(card.get("odds_movement"))


def _source_reason_codes(card: Mapping[str, Any]) -> list[str]:
    values = [
        card.get("reason_code"),
        card.get("analysis_blocker"),
        *_string_list(card.get("risk_reason_codes")),
    ]
    return sorted(
        {
            str(value).strip().upper()
            for value in values
            if value is not None and str(value).strip()
        }
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [str(item) for item in value if item is not None]
    return []
