"""One-way shadow evidence binding for newly persisted evaluation rows only."""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import (
    CURRENT_SERIALIZER_VERSION,
    HashDomain,
    canonical_sha256,
)
from w2.infrastructure.persistence.forward_evidence_models import (
    ForwardClockModel,
    RecommendationReviewLedgerModel,
)
from w2.infrastructure.persistence.matchday_intake_models import MatchdayMarketObservationModel
from w2.infrastructure.persistence.model_forecast_models import ModelForecastCaptureModel

CLOCK_ID = "candidate-c-r0-forward-v1"
T0 = datetime(2026, 9, 25, 8, 46, 32, tzinfo=UTC)
PREREG_SHA256 = "13b897871a37011b3647f860b819a9299a76f81d5af00be5eb2acf2142671a0f"
INPUT_VERSION = "w2.forward_evidence_input.v1"
_LOG = logging.getLogger(__name__)


def register_forward_clock(
    session: Session,
    *,
    started_at: datetime,
    code_revision: str,
    model_identity: str = "candidate-eval.v2",
) -> ForwardClockModel:
    """Explicit one-time registration; a repeat may only confirm identical fields."""
    if started_at.tzinfo is None or started_at.astimezone(UTC) < T0:
        raise ValueError("FORWARD_CLOCK_BEFORE_T0")
    if len(code_revision) != 40 or any(c not in "0123456789abcdef" for c in code_revision):
        raise ValueError("FORWARD_CLOCK_REVISION_INVALID")
    proposed = {
        "started_at": started_at.astimezone(UTC),
        "code_revision": code_revision,
        "model_identity": model_identity,
        "preregistration_sha256": PREREG_SHA256,
        "input_version": INPUT_VERSION,
    }
    existing = session.get(ForwardClockModel, CLOCK_ID)
    if existing is not None:
        if any(getattr(existing, key) != value for key, value in proposed.items()):
            raise ValueError("FORWARD_CLOCK_ALREADY_STARTED")
        return existing
    row = ForwardClockModel(clock_id=CLOCK_ID, **proposed)
    session.add(row)
    session.flush()
    return row


def _finite(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _pair(
    session: Session,
    version: Any,
) -> tuple[list[MatchdayMarketObservationModel], str | None]:
    if not version.capture_id or version.exact_line is None:
        return [], "QUOTE_PAIR_MISSING"
    rows = session.scalars(
        select(MatchdayMarketObservationModel).where(
            MatchdayMarketObservationModel.provider_fixture_id
            == version.fixture_id.removeprefix("api_football:"),
            MatchdayMarketObservationModel.capture_id == version.capture_id,
            MatchdayMarketObservationModel.canonical_market == version.market,
            MatchdayMarketObservationModel.bookmaker_id == "4",
            MatchdayMarketObservationModel.suspended.is_(False),
            MatchdayMarketObservationModel.live.is_(False),
        )
    ).all()
    wanted = ("HOME", "AWAY") if version.market == "ASIAN_HANDICAP" else ("OVER", "UNDER")
    try:
        line = Decimal(str(version.exact_line))
    except (InvalidOperation, TypeError, ValueError):
        return [], "QUOTE_PAIR_MISSING"
    selected: list[MatchdayMarketObservationModel] = []
    for side in wanted:
        expected = (
            -line if version.market == "ASIAN_HANDICAP" and side != version.selection else line
        )
        matches = []
        for row in rows:
            try:
                matches_line = row.line is not None and abs(
                    Decimal(row.line) - expected
                ) <= Decimal("0.01")
            except (InvalidOperation, TypeError, ValueError):
                matches_line = False
            if (
                row.canonical_selection == side
                and matches_line
                and (_finite(row.decimal_odds) or 0) > 1
            ):
                matches.append(row)
        if len(matches) != 1:
            return [], "QUOTE_PAIR_MISMATCH"
        selected.append(matches[0])
    if (
        selected[0].bookmaker_id != selected[1].bookmaker_id
        or selected[0].captured_at != selected[1].captured_at
    ):
        return [], "QUOTE_PAIR_MISMATCH"
    selected_quote = next(
        (row for row in selected if row.canonical_selection == version.selection), None
    )
    if (
        selected_quote is None
        or not version.quote_identity_hash
        or version.capture_at != selected_quote.captured_at
        or _finite(version.decimal_odds) != _finite(selected_quote.decimal_odds)
    ):
        return [], "QUOTE_PAIR_MISMATCH"
    return selected, None


def append_forward_evidence_in_session(
    session: Session,
    version: Any,
) -> RecommendationReviewLedgerModel | None:
    """Append an evaluation event iff an explicit clock exists and the row is new.

    Missing/invalid provenance becomes PIT_UNPROVABLE evidence, never a fabricated
    time or coefficient. This function has no recommendation output.
    """
    clock = session.get(ForwardClockModel, CLOCK_ID)
    if clock is None or version.evaluated_at < clock.started_at:
        return None
    if version.evaluation_policy_version != clock.model_identity:
        return None
    capture = (
        session.get(ModelForecastCaptureModel, version.model_forecast_capture_identity_hash)
        if version.model_forecast_capture_identity_hash
        else None
    )
    quotes, pair_error = _pair(session, version)
    simulation = (
        ((capture.payload.get("simulation_replay") or {}).get("simulation") or {})
        if capture and isinstance(capture.payload, dict)
        else {}
    )
    calibration = simulation.get("calibration") if isinstance(simulation, dict) else None
    params = calibration.get("params") if isinstance(calibration, dict) else None
    lambda_home = _finite(simulation.get("lambda_home")) if isinstance(simulation, dict) else None
    lambda_away = _finite(simulation.get("lambda_away")) if isinstance(simulation, dict) else None
    rho = _finite(params.get("dixon_coles_rho")) if isinstance(params, dict) else None
    input_hash = calibration.get("simulation_input_hash") if isinstance(calibration, dict) else None
    kickoff = capture.kickoff_utc if capture else None
    forecast_at = capture.captured_at if capture else None
    quote_at = quotes[0].captured_at if quotes else None
    times = (forecast_at, quote_at, kickoff)
    pit_ok = (
        all(value is not None and value.tzinfo is not None for value in times)
        and forecast_at <= version.evaluated_at < kickoff
        and quote_at <= version.evaluated_at
        and version.evaluated_at >= clock.started_at
    )
    reasons = []
    if not pit_ok:
        reasons.append("PIT_UNPROVABLE")
    if pair_error:
        reasons.append(pair_error)
    if any(value is None for value in (lambda_home, lambda_away, rho)) or not input_hash:
        reasons.append("MODEL_PARAMETER_UNPROVABLE")
    if (
        capture is None
        or capture.fixture_id != version.fixture_id
        or not version.calibration_identity
    ):
        reasons.append("MODEL_IDENTITY_UNPROVABLE")
    quote_ids = [row.observation_id for row in quotes]
    quote_pair_identity = (
        canonical_sha256(
            {"schema_version": "w2.forward_quote_pair.v1", "observation_ids": quote_ids},
            domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
        )
        if quotes
        else None
    )
    payload = {
        "schema_version": "w2.recommendation_review_ledger.evaluation.v1",
        "event_type": "EVALUATION_SNAPSHOT",
        "evaluation_id": version.evaluation_id,
        "derived_from_evaluation_id": version.evaluation_id,
        "decision_version": version.evaluation_policy_version,
        "calibration_identity": version.calibration_identity,
        "market_quote_identity": version.quote_identity_hash,
        "quote_pair_identity": quote_pair_identity,
        "quote_observation_ids": quote_ids,
        "candidate_kind": (
            "OFFICIAL_RECOMMENDATION"
            if version.state.value == "ANALYSIS_PICK_ACTIVE"
            else "NO_EDGE_DISPLAY"
            if version.state.value == "NO_EDGE_CURRENT"
            else "FACTOR_GATE_BLOCKED"
            if version.state.value == "BLOCKED_BY_FACTOR"
            else "EVALUATION_ONLY"
        ),
        "original_selection": version.selection,
        "display_state": version.state.value,
        "factor_gate_state": version.factor_decision_status,
        "fixture_id": version.fixture_id,
        "market": version.market,
        "evaluated_at": version.evaluated_at.isoformat(),
        "forecast_captured_at": forecast_at.isoformat() if forecast_at else None,
        "first_quote_captured_at": quotes[0].captured_at.isoformat() if quotes else None,
        "second_quote_captured_at": quotes[1].captured_at.isoformat() if quotes else None,
        "first_quote_selection": quotes[0].canonical_selection if quotes else None,
        "second_quote_selection": quotes[1].canonical_selection if quotes else None,
        "kickoff_utc": kickoff.isoformat() if kickoff else None,
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "rho": rho,
        "model_input_identity": input_hash,
        "five_state_distribution": version.model_settlement_distribution,
        "forecast_capture_identity": version.model_forecast_capture_identity_hash,
        "model_forecast_manifest_hash": capture.model_input_manifest_hash if capture else None,
        "evaluation_identity_hash": version.identity_hash,
        "pit_status": "PROVABLE" if not reasons else "PIT_UNPROVABLE",
        "exclusion_reasons": reasons,
        "code_revision": clock.code_revision,
        "input_version": clock.input_version,
        "preregistration_sha256": clock.preregistration_sha256,
        "serialization_version": CURRENT_SERIALIZER_VERSION.value,
    }
    digest = canonical_sha256(payload, domain=HashDomain.PREMATCH_READ_MODEL_GENERIC)
    existing = session.get(RecommendationReviewLedgerModel, digest)
    if existing is not None:
        if existing.payload_sha256 != digest or existing.payload != payload:
            raise ValueError("FORWARD_EVIDENCE_IDENTITY_CONFLICT")
        return existing
    row = RecommendationReviewLedgerModel(
        review_event_id=digest,
        evaluation_id=version.evaluation_id,
        event_type="EVALUATION_SNAPSHOT",
        evaluated_at=version.evaluated_at,
        pit_status=payload["pit_status"],
        payload=payload,
        payload_sha256=digest,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def record_shadow_evidence_in_session(session: Session, version: Any) -> None:
    """Keep the shadow writer outside recommendation transaction correctness.

    A savepoint rolls back a writer failure without removing the original
    evaluation. The Dashboard counts missing ledger rows as write gaps, and
    the exception is logged with the evaluation identity for investigation.
    """
    try:
        with session.begin_nested():
            append_forward_evidence_in_session(session, version)
    except Exception:
        _LOG.exception("FORWARD_EVIDENCE_WRITE_FAILED evaluation_id=%s", version.evaluation_id)
