"""Canonical identity for immutable AH/OU decisions across write and read paths."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from w2.domain.canonical_serialization import HashDomain, canonical_sha256

AH_OU_DECISION_LEDGER_SCHEMA = "w2.ah_ou_decision_ledger.v3"


def canonical_decision_score_text(value: Any) -> str:
    if value is None:
        return "0"
    if isinstance(value, Decimal):
        return str(value)
    return format(float(value), ".8f")


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


def build_ah_ou_input_hash(
    *,
    features: dict[str, Any],
    home_snapshot: dict[str, Any],
    away_snapshot: dict[str, Any],
    meetings: list[dict[str, Any]],
    quote: dict[str, Any],
) -> str:
    """Freeze step: canonical digest of everything the softmax consumed."""
    body = {
        "contract": AH_OU_DECISION_LEDGER_SCHEMA,
        "features": features,
        "home_snapshot_id": home_snapshot.get("snapshot_id"),
        "away_snapshot_id": away_snapshot.get("snapshot_id"),
        "meetings": [
            {
                "fixture_id": m.get("fixture_id"),
                "goals_for": m.get("goals_for"),
                "goals_against": m.get("goals_against"),
            }
            for m in meetings
        ],
        "quote_capture_id": quote.get("capture_id"),
        "quote_line": str(quote.get("line")),
        "quote_side_prices": quote.get("side_prices"),
    }
    return canonical_sha256(body, domain=HashDomain.RECOMMENDATION_DECISION_V4)
