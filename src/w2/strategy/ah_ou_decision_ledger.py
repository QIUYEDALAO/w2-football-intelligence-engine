"""AH/OU v3 decision ledger writer (S3/S4).

Four-step idempotency, each step keyed on the immutable content of the step
before it, so retries never produce a duplicate and a changed input becomes a
new identity instead of a silent edit:

1. capture  -- the quote's ``capture_id``/``source_capture_sha256`` (same capture
   is addressed once).
2. freeze   -- ``input_hash`` = canonical digest of the frozen F9/F6 input.
3. evaluate -- ``decision_id`` = canonical digest of (input_hash, model version,
   calibration version, quote identity, direction, score, skip).
4. write    -- insert by ``decision_id``; an identical re-run is a no-op, a
   conflicting ``(fixture_id, market, decision_at)`` slot refuses the batch.

The writer never falls back to the old weighted ``factor_score`` / pure
``bookmaker_intent``: a refusal is persisted (via ``skip_reason``) and stops the
rest of the batch.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
    AH_OU_DECISION_LEDGER_SCHEMA,
    AhOuDecisionLedgerModel,
)

_DECISION_HASH_DOMAIN = HashDomain.RECOMMENDATION_DECISION_V4


def _decimal_text(value: Any) -> str:
    if value is None:
        return "0"
    if isinstance(value, Decimal):
        return str(value)
    return format(float(value), ".8f")


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


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
    return canonical_sha256(body, domain=_DECISION_HASH_DOMAIN)


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
) -> str:
    """Evaluate step: identity of the decision, not the inputs."""
    body = {
        "contract": AH_OU_DECISION_LEDGER_SCHEMA,
        "fixture_id": fixture_id,
        "market": market,
        "decision_at": _iso(decision_at),
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
    return canonical_sha256(body, domain=_DECISION_HASH_DOMAIN)


def write_ah_ou_decision(
    session: Session,
    *,
    fixture_id: str,
    market: str,
    decision_at: datetime,
    model_version: str,
    calibration_version: str,
    input_hash: str,
    full_distribution: dict[str, Any],
    quote_identity_hash: str,
    source_capture_sha256: str,
    capture_id: str,
    source_id: str,
    home_team_id: str,
    away_team_id: str,
    selected: bool,
    direction: str | None,
    score: float | Decimal,
    skip_reason: str | None,
    created_at: datetime,
) -> AhOuDecisionLedgerModel:
    """Idempotent write: identical re-run is a no-op; slot conflict raises."""
    score_text = _decimal_text(score)
    decision_id = build_ah_ou_decision_id(
        fixture_id=fixture_id,
        market=market,
        decision_at=decision_at,
        model_version=model_version,
        calibration_version=calibration_version,
        input_hash=input_hash,
        quote_identity_hash=quote_identity_hash,
        source_capture_sha256=source_capture_sha256,
        direction=direction,
        score=score_text,
        skip_reason=skip_reason,
        selected=selected,
    )

    existing = session.get(AhOuDecisionLedgerModel, decision_id)
    if existing is not None:
        # Four-step idempotency: the same identity was already written; nothing
        # changed, so this is a successful no-op rather than a duplicate.
        return existing

    slot_row = session.scalar(
        select(AhOuDecisionLedgerModel).where(
            AhOuDecisionLedgerModel.fixture_id == fixture_id,
            AhOuDecisionLedgerModel.market == market,
            AhOuDecisionLedgerModel.decision_at == decision_at,
        )
    )
    if slot_row is not None:
        raise ValueError(
            "AH_OU_DECISION_SLOT_CONFLICT:"
            f"{fixture_id}/{market}/{_iso(decision_at)} already has {slot_row.decision_id}"
        )

    row = AhOuDecisionLedgerModel(
        decision_id=decision_id,
        fixture_id=fixture_id,
        market=market,
        decision_at=decision_at,
        model_version=model_version,
        calibration_version=calibration_version,
        input_hash=input_hash,
        full_distribution=full_distribution,
        quote_identity_hash=quote_identity_hash,
        source_capture_sha256=source_capture_sha256,
        capture_id=capture_id,
        source_id=source_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        selected=selected,
        direction=direction,
        score=score_text,
        skip_reason=skip_reason,
        created_at=created_at,
    )
    session.add(row)
    return row
