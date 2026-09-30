"""Canonical identity for immutable AH/OU decisions across write and read paths."""

from __future__ import annotations

from datetime import UTC, datetime

from w2.domain.canonical_serialization import HashDomain, canonical_sha256

AH_OU_DECISION_LEDGER_SCHEMA = "w2.ah_ou_decision_ledger.v3"


def canonical_decision_time(value: datetime) -> str:
    """Normalize SQLite and PostgreSQL readback to the original UTC identity."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def build_ah_ou_decision_id(
    *,
    fixture_id: str,
    market: str,
    decision_at: datetime,
    model_version: str,
    calibration_version: str,
    input_hash: str,
    quote_identity_hash: str,
    source_capture_sha256: str,
    direction: str | None,
    score: str,
    skip_reason: str | None,
    selected: bool,
    terms_hash: str | None = None,
) -> str:
    """The single v3/v3.1 decision identity algorithm shared by writer and reader."""
    body = {
        "contract": "w2.ah_ou_decision_ledger.v3.1" if terms_hash else AH_OU_DECISION_LEDGER_SCHEMA,
        "fixture_id": fixture_id,
        "market": market,
        "decision_at": canonical_decision_time(decision_at),
        "model_version": model_version,
        "calibration_version": calibration_version,
        "input_hash": input_hash,
        "quote_identity_hash": quote_identity_hash,
        "source_capture_sha256": source_capture_sha256,
        "direction": direction,
        "score": score,
        "skip_reason": skip_reason,
        "selected": selected,
    }
    if terms_hash:
        body["terms_hash"] = terms_hash
    return canonical_sha256(body, domain=HashDomain.RECOMMENDATION_DECISION_V4)
