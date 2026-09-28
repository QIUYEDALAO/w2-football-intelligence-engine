"""AH/OU v3 forward cohort preregistration (S4).

The scheduler calls ``preregister_cohort`` at ``decision_at = kickoff - 2h`` for
every fixture that passes the admission gates. The preregistration records the
*real* home/away ids, the quote capture identity, the model version and the
source id, keyed by a canonical identity so repeated runs are idempotent.

Results are deliberately out of scope here: the preregistration is written by the
pre-match role (``quant_asof_reader_role``) which cannot see result/settlement
tables, and any post-event enrichment is a separate ``POST_EVENT_ENRICHMENT``
step.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from w2.domain.canonical_serialization import HashDomain, canonical_sha256

COHORT_SCHEMA = "w2.ah_ou_forward_cohort.v3"
_DOMAIN = HashDomain.RECOMMENDATION_DECISION_V4


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def build_cohort_identity(
    *,
    fixture_id: str,
    decision_at: datetime,
    home_team_id: str,
    away_team_id: str,
    model_version: str,
    source_id: str,
    capture_id: str,
) -> str:
    """Identity of the preregistration: real team ids + quote capture + model + source."""
    body = {
        "contract": COHORT_SCHEMA,
        "fixture_id": fixture_id,
        "decision_at": _iso(decision_at),
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "model_version": model_version,
        "source_id": source_id,
        "capture_id": capture_id,
    }
    return canonical_sha256(body, domain=_DOMAIN)


def preregister_cohort(
    *,
    fixture_id: str,
    decision_at: datetime,
    home_team_id: str,
    away_team_id: str,
    model_version: str,
    source_id: str,
    capture_id: str,
    quote_identity_hash: str,
    source_capture_sha256: str,
) -> dict[str, Any]:
    """Return the preregistration payload keyed by its canonical identity.

    The payload is what the scheduler persists. Re-running with the same inputs
    yields the same identity, so persistence by ``cohort_id`` is idempotent.
    """
    cohort_id = build_cohort_identity(
        fixture_id=fixture_id,
        decision_at=decision_at,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        model_version=model_version,
        source_id=source_id,
        capture_id=capture_id,
    )
    return {
        "cohort_id": cohort_id,
        "fixture_id": fixture_id,
        "decision_at": _iso(decision_at),
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "model_version": model_version,
        "source_id": source_id,
        "capture_id": capture_id,
        "quote_identity_hash": quote_identity_hash,
        "source_capture_sha256": source_capture_sha256,
    }
