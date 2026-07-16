from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from w2.models.fair_market_estimate import (
    SNAPSHOT_SCHEMA_V2,
    verify_estimate_semantics,
    verify_estimate_snapshot,
)

AUDIT_CAPTURE_IDENTITY_SCHEMA_VERSION = "w2.audit_capture_identity.v1"
AUDIT_IDENTITY_VALID_STATUS = "PASS"
AUDIT_ESTIMATE_IDENTITY_MISSING = "AUDIT_ESTIMATE_IDENTITY_MISSING"
AUDIT_ESTIMATE_IDENTITY_MISMATCH = "AUDIT_ESTIMATE_IDENTITY_MISMATCH"
AUDIT_ESTIMATE_IDENTITY_AMBIGUOUS = "AUDIT_ESTIMATE_IDENTITY_AMBIGUOUS"


@dataclass(frozen=True)
class CaptureEstimateIdentity:
    estimate_id: str | None
    status: str
    blocker: str | None


def capture_content_hash(record: Mapping[str, Any]) -> str | None:
    for field in ("capture_hash", "evidence_hash", "card_hash"):
        value = _text(record.get(field))
        if value:
            return value
    return None


def audit_capture_id(record: Mapping[str, Any]) -> str | None:
    fixture_id = _text(record.get("fixture_id"))
    captured_at = _text(record.get("captured_at"))
    content_hash = capture_content_hash(record)
    if not fixture_id or not captured_at or not content_hash:
        return None
    payload = {
        "schema_version": AUDIT_CAPTURE_IDENTITY_SCHEMA_VERSION,
        "fixture_id": fixture_id,
        "football_day": _optional_text(record.get("football_day")),
        "environment": _optional_text(record.get("environment")),
        "captured_at": captured_at,
        "capture_checkpoint": _optional_text(record.get("capture_checkpoint")),
        "capture_hash": content_hash,
        "record_type": _text(record.get("record_type")) or "capture",
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"aci_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def capture_estimate_identity(record: Mapping[str, Any]) -> CaptureEstimateIdentity:
    eligible = {
        estimate_id: snapshot
        for snapshot in _snapshots(record)
        if (estimate_id := _optional_text(snapshot.get("estimate_id")))
        and _eligible_snapshot(snapshot)
    }

    pick = _mapping(record.get("pick"))
    gate = _mapping(record.get("analysis_gate"))
    for value in (
        pick.get("estimate_id"),
        record.get("estimate_id"),
        gate.get("estimate_id"),
    ):
        candidate = _optional_text(value)
        if not candidate:
            continue
        if candidate in eligible:
            return CaptureEstimateIdentity(candidate, AUDIT_IDENTITY_VALID_STATUS, None)
        return CaptureEstimateIdentity(None, "BLOCKED", AUDIT_ESTIMATE_IDENTITY_MISMATCH)

    identity_candidates = _matching_audit_identity_estimates(record, pick=pick, gate=gate)
    if identity_candidates:
        valid = identity_candidates & eligible.keys()
        if len(valid) == 1:
            return CaptureEstimateIdentity(next(iter(valid)), AUDIT_IDENTITY_VALID_STATUS, None)
        if not valid:
            return CaptureEstimateIdentity(None, "BLOCKED", AUDIT_ESTIMATE_IDENTITY_MISMATCH)
        return CaptureEstimateIdentity(None, "BLOCKED", AUDIT_ESTIMATE_IDENTITY_AMBIGUOUS)

    if len(eligible) == 1:
        return CaptureEstimateIdentity(next(iter(eligible)), AUDIT_IDENTITY_VALID_STATUS, None)
    if len(eligible) > 1:
        return CaptureEstimateIdentity(None, "BLOCKED", AUDIT_ESTIMATE_IDENTITY_AMBIGUOUS)
    return CaptureEstimateIdentity(None, "BLOCKED", AUDIT_ESTIMATE_IDENTITY_MISSING)


def _eligible_snapshot(snapshot: Mapping[str, Any]) -> bool:
    return bool(
        snapshot.get("schema_version") == SNAPSHOT_SCHEMA_V2
        and snapshot.get("semantic_status") == "VERIFIED"
        and snapshot.get("evidence_eligible") is True
        and verify_estimate_snapshot(snapshot)
        and verify_estimate_semantics(snapshot)
    )


def _matching_audit_identity_estimates(
    record: Mapping[str, Any],
    *,
    pick: Mapping[str, Any],
    gate: Mapping[str, Any],
) -> set[str]:
    market = _optional_text(pick.get("market") or gate.get("market"))
    strategy = _optional_text(
        pick.get("strategy_version")
        or gate.get("strategy_version")
        or record.get("strategy_version")
    )
    rows = record.get("audit_capture_identities")
    if not isinstance(rows, Sequence) or isinstance(rows, str | bytes | bytearray):
        return set()
    candidates: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if market and _optional_text(row.get("market")) != market:
            continue
        row_strategy = _optional_text(row.get("strategy_version") or row.get("strategy"))
        if strategy and row_strategy != strategy:
            continue
        estimate_id = _optional_text(row.get("estimate_id"))
        if estimate_id:
            candidates.add(estimate_id)
    return candidates


def _snapshots(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = record.get("fair_market_estimate_snapshots")
    if not isinstance(rows, Sequence) or isinstance(rows, str | bytes | bytearray):
        return []
    return [row for row in rows if isinstance(row, Mapping)]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None
