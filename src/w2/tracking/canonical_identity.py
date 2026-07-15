from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from w2.models.fair_market_estimate import (
    verify_estimate_semantics,
    verify_estimate_snapshot,
)
from w2.models.market_quote import verify_market_quote

SCOPES = {"OFFICIAL", "VALIDATION", "SHADOW"}


def canonical_capture_candidates(
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return one last, valid, prematch evidence candidate per performance key."""
    candidates = [item for record in records for item in _capture_candidates(record)]
    valid = [item for item in candidates if item["exclusion_reason"] is None]
    winners: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for item in valid:
        key = performance_key(item)
        if not all(key):
            continue
        current = winners.get(key)
        order = (_time(item.get("captured_at")), str(item.get("capture_hash") or ""))
        if current is None or order > (
            _time(current.get("captured_at")),
            str(current.get("capture_hash") or ""),
        ):
            winners[key] = item
    for item in candidates:
        item["canonical_candidate"] = winners.get(performance_key(item)) is item
        item["audit_only"] = not item["canonical_candidate"]
    return candidates


def performance_key(record: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(record.get("fixture_id") or ""),
        str(record.get("market") or ""),
        str(record.get("recommendation_scope") or ""),
        str(record.get("strategy_version") or ""),
    )


def capture_identity(record: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        *performance_key(record),
        str(record.get("selection") or ""),
        str(record.get("estimate_id") or ""),
        str(record.get("quote_id") or ""),
        str(record.get("capture_hash") or ""),
    )


def candidate_for_outcome(
    candidates: Sequence[Mapping[str, Any]], outcome: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    source_hash = str(outcome.get("source_capture_hash") or "")
    eligible = [item for item in candidates if item.get("canonical_candidate") is True]
    if source_hash:
        exact = [item for item in eligible if item.get("capture_hash") == source_hash]
        exact = [item for item in exact if _outcome_matches(item, outcome)]
        return exact[0] if len(exact) == 1 else None
    # Compatibility is intentionally limited to a complete audit identity. A fixture-only
    # match can cross markets, scopes, or strategy versions and is never authoritative.
    identity_fields = (
        "market",
        "selection",
        "recommendation_scope",
        "strategy_version",
        "estimate_id",
        "quote_id",
    )
    if not all(outcome.get(field) for field in identity_fields):
        return None
    exact = [item for item in eligible if _outcome_matches(item, outcome)]
    return exact[0] if len(exact) == 1 else None


def _capture_candidates(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    if str(record.get("record_type") or "capture") != "capture":
        return []
    declared = record.get("audit_capture_identities")
    if isinstance(declared, Sequence) and not isinstance(declared, (str, bytes, bytearray)):
        return [
            _candidate(record, item)
            for item in declared
            if isinstance(item, Mapping)
        ]
    items: list[Mapping[str, Any]] = []
    pick = record.get("pick")
    if isinstance(pick, Mapping):
        items.append(
            {
                **pick,
                "recommendation_scope": _scope(record),
                "strategy_version": str(record.get("strategy_version") or "DECISION_CONTRACT_V2"),
            }
        )
    shadows = record.get("shadow_picks")
    if isinstance(shadows, Sequence) and not isinstance(shadows, (str, bytes, bytearray)):
        items.extend(
            {
                **item,
                "recommendation_scope": "SHADOW",
                "strategy_version": str(item.get("strategy_version") or "WIDE_SHADOW_V1"),
            }
            for item in shadows
            if isinstance(item, Mapping)
        )
    gates = record.get("analysis_gate_v2_shadows")
    if isinstance(gates, Sequence) and not isinstance(gates, (str, bytes, bytearray)):
        items.extend(
            {
                **item,
                "recommendation_scope": "SHADOW",
                "strategy_version": str(
                    item.get("strategy_version")
                    or item.get("schema_version")
                    or "STRICT_SHADOW_V1"
                ),
            }
            for item in gates
            if isinstance(item, Mapping)
        )
    return [_candidate(record, item) for item in items]


def _candidate(record: Mapping[str, Any], item: Mapping[str, Any]) -> dict[str, Any]:
    estimate_id = str(item.get("estimate_id") or record.get("estimate_id") or "")
    quote_id = str(item.get("quote_id") or record.get("quote_id") or "")
    estimates = record.get("fair_market_estimate_snapshots")
    snapshot = next(
        (
            value
            for value in estimates or ()
            if isinstance(value, Mapping) and value.get("estimate_id") == estimate_id
        ),
        None,
    )
    quote = item.get("market_quote") or record.get("market_quote")
    output = {
        **dict(record),
        "market": str(item.get("market") or ""),
        "selection": str(item.get("selection") or ""),
        "recommendation_scope": str(item.get("recommendation_scope") or _scope(record)),
        "strategy_version": str(item.get("strategy_version") or ""),
        "estimate_id": estimate_id,
        "quote_id": quote_id,
        "capture_hash": str(record.get("capture_hash") or record.get("evidence_hash") or ""),
        "evidence_eligible": item.get("evidence_eligible", record.get("evidence_eligible", True)),
    }
    output["exclusion_reason"] = _exclusion_reason(output, snapshot, quote)
    return output


def _exclusion_reason(
    candidate: Mapping[str, Any],
    snapshot: Mapping[str, Any] | None,
    quote: Any,
) -> str | None:
    captured = _parse_time(candidate.get("captured_at"))
    kickoff = _parse_time(candidate.get("kickoff_utc"))
    if captured is None or kickoff is None or captured >= kickoff:
        return "NOT_PREMATCH"
    if candidate.get("live") is True or str(candidate.get("fixture_status") or "").upper() in {
        "LIVE", "1H", "HT", "2H", "ET", "P", "BT",
    }:
        return "LIVE_CAPTURE"
    if snapshot is None or not verify_estimate_snapshot(snapshot):
        return "INVALID_SNAPSHOT"
    if not verify_estimate_semantics(snapshot):
        return "SEMANTIC_FAIL"
    if not isinstance(quote, Mapping) or not verify_market_quote(quote):
        return "INVALID_QUOTE"
    if quote.get("quote_id") != candidate.get("quote_id"):
        return "INVALID_QUOTE"
    if snapshot.get("estimate_id") != candidate.get("estimate_id"):
        return "INVALID_SNAPSHOT"
    if candidate.get("evidence_eligible") is not True:
        return "EVIDENCE_INELIGIBLE"
    return None


def _outcome_matches(candidate: Mapping[str, Any], outcome: Mapping[str, Any]) -> bool:
    return all(
        str(candidate.get(field) or "") == str(outcome.get(field) or "")
        for field in (
            "fixture_id",
            "market",
            "selection",
            "recommendation_scope",
            "strategy_version",
            "estimate_id",
            "quote_id",
        )
    )


def _scope(record: Mapping[str, Any]) -> str:
    explicit = str(record.get("recommendation_scope") or "").upper()
    if explicit in SCOPES:
        return explicit
    if str(record.get("decision_tier") or "").upper() == "ANALYSIS_PICK":
        return "VALIDATION"
    return "OFFICIAL"


def _time(value: Any) -> datetime:
    return _parse_time(value) or datetime.min.replace(tzinfo=UTC)


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
