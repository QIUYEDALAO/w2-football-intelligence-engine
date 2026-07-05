from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

_READINESS_KEYS = (
    "data_status",
    "reason_code",
    "reason_human",
    "action",
    "next_eval_at",
    "provider_budget_status",
    "missing_fields",
    "stale_fields",
    "source",
)

_SAFE_DEBUG_KEYS = (
    "action_label",
    "environment",
    "legacy_fallback",
    "legacy_formal",
    "readiness_source",
    "staging_only",
)


def build_l2_diagnostics(card: Mapping[str, Any]) -> dict[str, Any]:
    """Build a small, whitelisted diagnostics payload for collapsed L2 display."""
    pick = _mapping(card.get("pick"))
    return _drop_empty(
        {
            "fixture_id": _text(card.get("fixture_id")),
            "source": _optional_text(card.get("source")),
            "decision_tier": _text(card.get("decision_tier")),
            "data_status": _text(card.get("data_status")),
            "lifecycle_status": _optional_text(card.get("lifecycle_status")),
            "outcome_tracked": _optional_bool(card.get("outcome_tracked")),
            "lock_eligible": card.get("lock_eligible") is True,
            "recommendation_id": _optional_text(card.get("recommendation_id")),
            "reason_code": _optional_text(card.get("reason_code")),
            "action": _optional_text(card.get("action")),
            "next_eval_at": _optional_text(card.get("next_eval_at")),
            "provider_budget_status": _optional_text(card.get("provider_budget_status")),
            "missing_fields": _text_list(card.get("missing_fields")),
            "stale_fields": _text_list(card.get("stale_fields")),
            "data_readiness_summary": _readiness_summary(card.get("data_readiness")),
            "market_snapshot": _drop_empty(
                {
                    "market": _optional_text(pick.get("market")),
                    "selection": _optional_text(pick.get("selection")),
                    "line": _optional_text(pick.get("line")),
                    "odds": _optional_text(pick.get("odds")),
                }
            ),
            "card_hash": _optional_text(card.get("card_hash")),
            "safe_debug": _safe_debug(card),
        }
    )


def _readiness_summary(value: Any) -> dict[str, Any]:
    readiness = _mapping(value)
    return _drop_empty(
        {
            key: _text_list(readiness.get(key))
            if key in {"missing_fields", "stale_fields"}
            else _optional_text(readiness.get(key))
            for key in _READINESS_KEYS
        }
    )


def _safe_debug(card: Mapping[str, Any]) -> dict[str, Any]:
    debug = _mapping(card.get("safe_debug")) or _mapping(card.get("diagnostics"))
    return _drop_empty(
        {
            key: _safe_value(debug.get(key), fallback=card.get(key))
            for key in _SAFE_DEBUG_KEYS
        }
    )


def _safe_value(value: Any, *, fallback: Any = None) -> Any:
    actual = fallback if value is None else value
    if isinstance(actual, bool):
        return actual
    if isinstance(actual, int | float):
        return actual
    return _optional_text(actual)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _drop_empty(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item is not None and item != "" and item != [] and item != {}
    }


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [_text(item) for item in value if _text(item)]


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def _optional_text(value: Any) -> str | None:
    text = _text(value).strip()
    return text or None
