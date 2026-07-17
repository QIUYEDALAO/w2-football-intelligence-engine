from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from w2.domain.environment_policy import build_environment_policy_stamp

SOURCE = "w2.replay.front_door.v1"


def build_replay_front_door(
    *,
    football_day: str,
    environment: str,
    day_view: Mapping[str, Any] | None = None,
    audit_manifest: Mapping[str, Any] | None = None,
    audit_tables: Mapping[str, Any] | None = None,
    outcomes: Sequence[Mapping[str, Any]] | None = None,
    as_of: str | datetime | None = None,
) -> dict[str, Any]:
    """Build a read-only replay envelope from explicit local inputs."""
    cards = [_replay_card(card, outcomes=outcomes) for card in _day_view_cards(day_view)]
    replay_gaps = _replay_gaps(
        day_view=day_view,
        audit_manifest=audit_manifest,
        audit_tables=audit_tables,
        outcomes=outcomes,
    )
    return {
        "football_day": football_day,
        "environment": environment,
        "environment_policy": _environment_policy(day_view, environment),
        "replay_status": _replay_status(
            day_view=day_view,
            audit_tables=audit_tables,
            outcomes=outcomes,
        ),
        "as_of": _as_of(as_of),
        "source": SOURCE,
        "known_at_summary": _known_at_summary(day_view),
        "decision_summary": _decision_summary(cards),
        "reason_summary": _reason_summary(cards),
        "outcome_tracking_summary": _outcome_tracking_summary(cards),
        "card_hash_checks": [verify_replay_card_hash(card) for card in cards],
        "replay_gaps": replay_gaps,
        "cards": cards,
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
        "checkpoint_write": False,
        "lock_snapshot_write": False,
        "settlement_write": False,
    }


def verify_replay_card_hash(card: Mapping[str, Any]) -> dict[str, Any]:
    fixture_id = _text(card.get("fixture_id"))
    card_hash = _optional_text(card.get("card_hash"))
    expected = _optional_text(card.get("expected_card_hash"))
    if card_hash is None:
        status = "MISSING"
    elif expected is None:
        status = "PRESENT_UNVERIFIED"
    elif expected == card_hash:
        status = "PASS"
    else:
        status = "MISMATCH"
    return {
        "fixture_id": fixture_id,
        "card_hash": card_hash,
        "expected_card_hash": expected,
        "hash_status": status,
        "source": SOURCE,
    }


def _replay_status(
    *,
    day_view: Mapping[str, Any] | None,
    audit_tables: Mapping[str, Any] | None,
    outcomes: Sequence[Mapping[str, Any]] | None,
) -> str:
    if not day_view and not audit_tables:
        return "NO_REPLAY_INPUTS"
    if not day_view:
        return "MISSING_DAYVIEW"
    if outcomes is None:
        return "MISSING_OUTCOMES"
    return "READY"


def _replay_gaps(
    *,
    day_view: Mapping[str, Any] | None,
    audit_manifest: Mapping[str, Any] | None,
    audit_tables: Mapping[str, Any] | None,
    outcomes: Sequence[Mapping[str, Any]] | None,
) -> list[str]:
    gaps: list[str] = []
    if not day_view:
        gaps.append("MISSING_DAYVIEW")
    if not audit_manifest:
        gaps.append("MISSING_AUDIT_MANIFEST")
    if not audit_tables:
        gaps.append("MISSING_AUDIT_TABLES")
    if outcomes is None:
        gaps.append("MISSING_OUTCOMES")
    return gaps


def _replay_card(
    card: Mapping[str, Any],
    *,
    outcomes: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    outcome = _outcome_for(card, outcomes)
    output = {
        "fixture_id": _text(card.get("fixture_id")),
        "kickoff_utc": _optional_text(card.get("kickoff_utc")),
        "decision_tier": _optional_text(card.get("decision_tier")),
        "data_status": _optional_text(card.get("data_status")),
        "lock_eligible": card.get("lock_eligible") is True,
        "outcome_tracked": card.get("outcome_tracked") is True,
        "recommendation_id": _optional_text(card.get("recommendation_id")),
        "reason_code": _optional_text(card.get("reason_code")),
        "action": _optional_text(card.get("action")),
        "one_liner": _optional_text(card.get("one_liner")),
        "card_hash": _optional_text(card.get("card_hash")),
        "expected_card_hash": _optional_text(card.get("expected_card_hash")),
        "outcome": outcome,
        "outcome_status": _outcome_status(card, outcome, outcomes),
        "replay_source": _optional_text(card.get("source")) or "day_view",
    }
    output["hash_status"] = verify_replay_card_hash(output)["hash_status"]
    return output


def _outcome_for(
    card: Mapping[str, Any],
    outcomes: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any] | None:
    if outcomes is None:
        return None
    fixture_id = _text(card.get("fixture_id"))
    for outcome in outcomes:
        if _text(outcome.get("fixture_id")) == fixture_id:
            return {
                "fixture_id": fixture_id,
                "result_status": _optional_text(outcome.get("result_status")),
                "settlement_status": _optional_text(outcome.get("settlement_status")),
                "score": _optional_text(outcome.get("score")),
                "pnl": outcome.get("pnl"),
                "unit_result": outcome.get("unit_result"),
            }
    return None


def _outcome_status(
    card: Mapping[str, Any],
    outcome: Mapping[str, Any] | None,
    outcomes: Sequence[Mapping[str, Any]] | None,
) -> str:
    if outcomes is None:
        return "OUTCOMES_NOT_PROVIDED"
    if outcome is not None:
        return "MATCHED"
    if card.get("outcome_tracked") is True:
        return "MISSING_OUTCOME"
    return "NOT_TRACKED"


def _outcome_tracking_summary(cards: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    tracked = [card for card in cards if card.get("outcome_tracked") is True]
    missing = [
        _text(card.get("fixture_id"))
        for card in tracked
        if card.get("outcome_status") == "MISSING_OUTCOME"
    ]
    matched = [
        _text(card.get("fixture_id")) for card in tracked if card.get("outcome_status") == "MATCHED"
    ]
    return {
        "tracked_count": len(tracked),
        "matched_outcome_count": len(matched),
        "missing_outcome_count": len(missing),
        "tracked_fixture_ids": [_text(card.get("fixture_id")) for card in tracked],
        "matched_fixture_ids": matched,
        "missing_outcome_fixture_ids": missing,
    }


def _decision_summary(cards: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    decision_tiers = Counter(
        _text(card.get("decision_tier"))
        for card in cards
        if _optional_text(card.get("decision_tier"))
    )
    data_statuses = Counter(
        _text(card.get("data_status")) for card in cards if _optional_text(card.get("data_status"))
    )
    return {
        "total_cards": len(cards),
        "lock_eligible_count": sum(1 for card in cards if card.get("lock_eligible") is True),
        "by_decision_tier": dict(sorted(decision_tiers.items())),
        "by_data_status": dict(sorted(data_statuses.items())),
    }


def _reason_summary(cards: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    reasons = Counter(
        _text(card.get("reason_code")) for card in cards if _optional_text(card.get("reason_code"))
    )
    return [
        {"reason_code": reason_code, "count": count}
        for reason_code, count in sorted(reasons.items(), key=lambda item: (-item[1], item[0]))
    ]


def _known_at_summary(day_view: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = _mapping(day_view)
    return {
        "has_day_view": bool(payload),
        "generated_at": _optional_text(payload.get("generated_at")),
        "source": _optional_text(payload.get("source")),
        "checkpoint_key": _optional_text(payload.get("checkpoint_key")),
        "counts": dict(_mapping(payload.get("counts"))),
        "freshness": dict(_mapping(payload.get("freshness"))),
        "degradation": dict(_mapping(payload.get("degradation"))),
        "navigation": dict(_mapping(payload.get("navigation"))),
    }


def _day_view_cards(day_view: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    value = _mapping(day_view).get("cards")
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _environment_policy(day_view: Mapping[str, Any] | None, environment: str) -> dict[str, Any]:
    policy = _mapping(_mapping(day_view).get("environment_policy"))
    return dict(policy) if policy else build_environment_policy_stamp(environment)


def _as_of(value: str | datetime | None) -> str:
    if value is None:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, datetime):
        actual = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        return actual.isoformat().replace("+00:00", "Z")
    return str(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _optional_text(value: Any) -> str | None:
    text = _text(value).strip()
    return text or None
