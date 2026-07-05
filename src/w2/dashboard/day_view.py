from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from w2.domain.decision_policy import compute_outcome_tracked
from w2.domain.enums import DataStatus, DecisionTier, LifecycleStatus
from w2.domain.legacy_decision_shim import legacy_decision_view

CARD_SOURCE_CONTRACT = "decision_contract"
CARD_SOURCE_LEGACY = "legacy_fallback"


def build_dashboard_day_view(
    dashboard_payload: Mapping[str, Any],
    *,
    environment: str,
) -> dict[str, Any]:
    """Build a read-only DayView envelope from the existing dashboard payload."""
    football_day = _text(
        dashboard_payload.get("selected_football_day"),
        dashboard_payload.get("date"),
    )
    cards = [_day_view_card(card) for card in _dashboard_cards(dashboard_payload)]
    counts = _counts(cards)
    return {
        "generated_at": _format_time(dashboard_payload.get("generated_at")),
        "date": _text(dashboard_payload.get("date"), football_day),
        "football_day": football_day,
        "selected_football_day": football_day,
        "environment": environment,
        "timezone": _text(dashboard_payload.get("timezone"), "Asia/Shanghai"),
        "window": _text(dashboard_payload.get("window"), "today"),
        "source": "dashboard_read_model",
        "version": _mapping_copy(dashboard_payload.get("version")),
        "checkpoint_key": f"dashboard:day_view:{football_day}",
        "would_write_checkpoint": False,
        "provider_calls": 0,
        "db_writes": 0,
        "counts": counts,
        "freshness": _freshness(dashboard_payload, cards, counts),
        "cards": cards,
    }


def _dashboard_cards(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = payload.get("all")
    if not isinstance(rows, Sequence) or isinstance(rows, str | bytes | bytearray):
        return []
    return [row for row in rows if isinstance(row, Mapping)]


def _day_view_card(card: Mapping[str, Any]) -> dict[str, Any]:
    contract = _mapping(card.get("decision_contract"))
    if _has_contract_fields(card, contract):
        return _contract_card(card, contract)
    return _legacy_card(card)


def _contract_card(card: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    decision_tier = _text(_field(card, contract, "decision_tier"), DecisionTier.SKIP.value)
    data_status = _text(_field(card, contract, "data_status"), DataStatus.PARTIAL.value)
    lifecycle_status = _text(
        _field(card, contract, "lifecycle_status"),
        LifecycleStatus.DRAFT.value,
    )
    return {
        **_fixture_fields(card),
        "source": CARD_SOURCE_CONTRACT,
        "decision_tier": decision_tier,
        "data_status": data_status,
        "lifecycle_status": lifecycle_status,
        "outcome_tracked": _bool_or_default(
            _field(card, contract, "outcome_tracked"),
            compute_outcome_tracked(DecisionTier(decision_tier))
            if _is_decision_tier(decision_tier)
            else False,
        ),
        "lock_eligible": _bool_or_default(_field(card, contract, "lock_eligible"), False),
        "recommendation_id": _optional_text(_field(card, contract, "recommendation_id")),
        "reason_code": _optional_text(_field(card, contract, "reason_code")),
        "action": _optional_text(_field(card, contract, "action")),
        "next_eval_at": _format_time(_field(card, contract, "next_eval_at")),
        "provider_budget_status": _optional_text(
            _field(card, contract, "provider_budget_status")
        ),
        "missing_fields": _string_list(_field(card, contract, "missing_fields")),
        "stale_fields": _string_list(_field(card, contract, "stale_fields")),
        "data_readiness": _mapping_copy(_field(card, contract, "data_readiness")),
        "pick": _mapping_copy(_field(card, contract, "pick"))
        if isinstance(_field(card, contract, "pick"), Mapping)
        else None,
        "non_pick": _mapping_copy(_field(card, contract, "non_pick"))
        if isinstance(_field(card, contract, "non_pick"), Mapping)
        else None,
        "one_liner": _optional_text(_field(card, contract, "one_liner")),
        "card_hash": _optional_text(_field(card, contract, "card_hash")),
    }


def _legacy_card(card: Mapping[str, Any]) -> dict[str, Any]:
    recommendation = _mapping(card.get("recommendation"))
    legacy = legacy_decision_view(card, recommendation)
    return {
        **_fixture_fields(card),
        "source": CARD_SOURCE_LEGACY,
        "decision_tier": legacy.decision_tier.value,
        "data_status": _text(card.get("data_status"), DataStatus.PARTIAL.value),
        "lifecycle_status": _text(card.get("lifecycle_status"), LifecycleStatus.DRAFT.value),
        "outcome_tracked": compute_outcome_tracked(legacy.decision_tier),
        "lock_eligible": legacy.lock_eligible,
        "recommendation_id": legacy.recommendation_id,
        "reason_code": _optional_text(card.get("reason_code")),
        "action": _optional_text(card.get("action")),
        "next_eval_at": _format_time(card.get("next_eval_at")),
        "provider_budget_status": _optional_text(card.get("provider_budget_status")),
        "missing_fields": _string_list(card.get("missing_fields")),
        "stale_fields": _string_list(card.get("stale_fields")),
        "data_readiness": _mapping_copy(card.get("data_readiness")),
        "pick": None,
        "non_pick": _mapping_copy(card.get("non_pick"))
        if isinstance(card.get("non_pick"), Mapping)
        else None,
        "one_liner": _optional_text(card.get("one_liner")),
        "card_hash": _optional_text(card.get("card_hash")),
    }


def _fixture_fields(card: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fixture_id": _text(card.get("fixture_id")),
        "kickoff_utc": _format_time(card.get("kickoff_utc")),
        "kickoff_beijing": _optional_text(card.get("kickoff_beijing")),
        "competition_id": _optional_text(card.get("competition_id")),
        "competition_name": _optional_text(card.get("competition_name")),
        "home_team_name": _optional_text(card.get("home_team_name")),
        "away_team_name": _optional_text(card.get("away_team_name")),
        "status": _optional_text(card.get("status")),
    }


def _counts(cards: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_decision_tier = {tier.value: 0 for tier in DecisionTier}
    by_data_status = {status.value: 0 for status in DataStatus}
    by_lifecycle_status = {status.value: 0 for status in LifecycleStatus}
    lock_eligible = 0
    outcome_tracked = 0
    legacy_fallback = 0

    for card in cards:
        decision_tier = _optional_text(card.get("decision_tier"))
        data_status = _optional_text(card.get("data_status"))
        lifecycle_status = _optional_text(card.get("lifecycle_status"))
        if decision_tier in by_decision_tier:
            by_decision_tier[decision_tier] += 1
        if data_status in by_data_status:
            by_data_status[data_status] += 1
        if lifecycle_status in by_lifecycle_status:
            by_lifecycle_status[lifecycle_status] += 1
        if card.get("lock_eligible") is True:
            lock_eligible += 1
        if card.get("outcome_tracked") is True:
            outcome_tracked += 1
        if card.get("source") == CARD_SOURCE_LEGACY:
            legacy_fallback += 1

    return {
        "total": len(cards),
        "lock_eligible": lock_eligible,
        "outcome_tracked": outcome_tracked,
        "legacy_fallback": legacy_fallback,
        "analysis_pick": by_decision_tier[DecisionTier.ANALYSIS_PICK.value],
        "recommend": by_decision_tier[DecisionTier.RECOMMEND.value],
        "watch": by_decision_tier[DecisionTier.WATCH.value],
        "not_ready": by_decision_tier[DecisionTier.NOT_READY.value],
        "skip": by_decision_tier[DecisionTier.SKIP.value],
        "ready": by_data_status[DataStatus.READY.value],
        "partial": by_data_status[DataStatus.PARTIAL.value],
        "stale": by_data_status[DataStatus.STALE.value],
        "blocked": by_data_status[DataStatus.BLOCKED.value],
        "by_decision_tier": by_decision_tier,
        "by_data_status": by_data_status,
        "by_lifecycle_status": by_lifecycle_status,
    }


def _freshness(
    payload: Mapping[str, Any],
    cards: Sequence[Mapping[str, Any]],
    counts: Mapping[str, Any],
) -> dict[str, Any]:
    data_status_summary = _mapping_copy(counts.get("by_data_status"))
    stale = int(data_status_summary.get(DataStatus.STALE.value, 0))
    blocked = int(data_status_summary.get(DataStatus.BLOCKED.value, 0))
    return {
        "last_refresh": _format_time(
            _first(payload.get("last_refresh"), payload.get("generated_at"))
        ),
        "next_refresh_tick": _format_time(
            _first(
                payload.get("next_refresh_tick"),
                _mapping(payload.get("debug")).get("next_refresh_tick"),
                _mapping(payload.get("performance")).get("next_refresh_tick"),
            )
        ),
        "provider_budget_status": _provider_budget_status(payload, cards),
        "staleness": {
            "stale_cards": stale,
            "blocked_cards": blocked,
            "stale_or_blocked_cards": stale + blocked,
        },
        "data_status_summary": data_status_summary,
    }


def _provider_budget_status(
    payload: Mapping[str, Any],
    cards: Sequence[Mapping[str, Any]],
) -> str:
    direct = _optional_text(
        _first(
            payload.get("provider_budget_status"),
            _mapping(payload.get("debug")).get("provider_budget_status"),
            _mapping(payload.get("performance")).get("provider_budget_status"),
        )
    )
    if direct:
        return direct
    statuses = [
        status
        for status in (_optional_text(card.get("provider_budget_status")) for card in cards)
        if status
    ]
    if "EXHAUSTED" in statuses:
        return "EXHAUSTED"
    if statuses:
        return statuses[0]
    return "UNKNOWN"


def _has_contract_fields(card: Mapping[str, Any], contract: Mapping[str, Any]) -> bool:
    return any(
        value is not None
        for value in (
            card.get("decision_tier"),
            card.get("data_status"),
            contract.get("decision_tier"),
            contract.get("data_status"),
        )
    )


def _field(card: Mapping[str, Any], contract: Mapping[str, Any], key: str) -> Any:
    value = contract.get(key)
    if value is not None:
        return value
    return card.get(key)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_copy(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _text(*values: Any) -> str:
    value = _first(*values)
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_time(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [str(item) for item in value if item is not None]
    if value is None:
        return []
    return [str(value)]


def _bool_or_default(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _is_decision_tier(value: str) -> bool:
    try:
        DecisionTier(value)
    except ValueError:
        return False
    return True
