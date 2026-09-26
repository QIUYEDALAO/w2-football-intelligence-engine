"""One-way shadow evidence binding for newly persisted evaluation rows only."""

from __future__ import annotations

import logging
import math
from dataclasses import replace
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
from w2.domain.odds import settle_total_goals
from w2.domain.profit import (
    FROZEN_FADE_DELTA,
    REBATE_FORMULA_VERSION,
    REBATE_RATE,
    track_d_binary_cashflow,
    track_d_fair_probability,
)
from w2.infrastructure.persistence.forward_evidence_models import (
    ForwardClockModel,
    RecommendationReviewLedgerModel,
)
from w2.infrastructure.persistence.matchday_intake_models import MatchdayMarketObservationModel
from w2.infrastructure.persistence.model_forecast_models import ModelForecastCaptureModel
from w2.infrastructure.persistence.models import ResultModel

TRACK_D_FADE = "TRACK_D_FADE"
VALIDATION_SIGNAL = "VALIDATION_SIGNAL"
VALIDATION_SIGNAL_WATERMARK = "验证期信号 · 非正式推荐 · 不计入档位"
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


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


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


def build_track_d_validation_signal_in_session(
    session: Session, version: Any,
) -> dict[str, Any] | None:
    """Bind an UNDER evaluation to a captured, executable OVER channel quote.

    Pinnacle is the market probability anchor only. Its price can never be
    substituted for the channel price, including when the selected bookmaker
    itself is Pinnacle.
    """
    clock = session.get(ForwardClockModel, CLOCK_ID)
    signal_config = getattr(version, "track_d_validation_signal", None) or {}
    source_selection = str(signal_config.get("source_selection") or version.selection)
    if (
        clock is None
        or version.evaluated_at < clock.started_at
        or version.evaluation_policy_version != clock.model_identity
        or version.market != "TOTALS"
        or source_selection != "UNDER"
        or version.state.value not in {"ANALYSIS_PICK_ACTIVE", "NO_EDGE_CURRENT"}
        or not version.capture_id
        or not version.bookmaker_id
        or version.bookmaker_id == "4"
        or version.exact_line is None
        or not version.quote_identity_hash
    ):
        return None
    capture = (
        session.get(ModelForecastCaptureModel, version.model_forecast_capture_identity_hash)
        if version.model_forecast_capture_identity_hash else None
    )
    if (
        capture is None
        or capture.fixture_id != version.fixture_id
        or capture.captured_at is None
        or capture.kickoff_utc is None
        or capture.captured_at.tzinfo is None
        or capture.kickoff_utc.tzinfo is None
        or not capture.captured_at <= version.evaluated_at < capture.kickoff_utc
    ):
        return None
    observations = session.scalars(
        select(MatchdayMarketObservationModel).where(
            MatchdayMarketObservationModel.provider_fixture_id
            == version.fixture_id.removeprefix("api_football:"),
            MatchdayMarketObservationModel.capture_id == version.capture_id,
            MatchdayMarketObservationModel.canonical_market == "TOTALS",
            MatchdayMarketObservationModel.bookmaker_id.in_((version.bookmaker_id, "4")),
            MatchdayMarketObservationModel.suspended.is_(False),
            MatchdayMarketObservationModel.live.is_(False),
        )
    ).all()
    try:
        line = Decimal(str(version.exact_line))
    except (InvalidOperation, TypeError, ValueError):
        return None

    def quote(bookmaker: str, side: str) -> MatchdayMarketObservationModel | None:
        matches = []
        for row in observations:
            try:
                same_line = row.line is not None and Decimal(str(row.line)) == line
            except (InvalidOperation, TypeError, ValueError):
                same_line = False
            if (
                row.bookmaker_id == bookmaker
                and row.canonical_selection == side
                and same_line
                and (_finite(row.decimal_odds) or 0) > 1
                and row.captured_at is not None
                and row.captured_at <= version.evaluated_at
            ):
                matches.append(row)
        return matches[0] if len(matches) == 1 else None

    channel_under = quote(version.bookmaker_id, "UNDER")
    channel_over = quote(version.bookmaker_id, "OVER")
    pinnacle_over = quote("4", "OVER")
    pinnacle_under = quote("4", "UNDER")
    if not all((channel_under, channel_over, pinnacle_over, pinnacle_under)):
        return None
    assert channel_under and channel_over and pinnacle_over and pinnacle_under
    if (
        channel_under.captured_at != version.capture_at
        or _finite(channel_under.decimal_odds) != _finite(version.decimal_odds)
        or channel_over.captured_at != channel_under.captured_at
        or pinnacle_over.captured_at != pinnacle_under.captured_at
    ):
        return None
    market_odds = {
        "OVER": float(pinnacle_over.decimal_odds),
        "UNDER": float(pinnacle_under.decimal_odds),
    }
    try:
        p_over = track_d_fair_probability(market_odds, "OVER")
        p_fade = min(0.99, max(0.01, p_over + FROZEN_FADE_DELTA))
        channel_odds = float(channel_over.decimal_odds)
        fade_ev = track_d_binary_cashflow(p_fade, channel_odds)
    except (ValueError, KeyError):
        return None
    source_distribution = version.model_settlement_distribution or {}
    probabilities = [_finite(source_distribution.get(state)) for state in (
        "WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS",
    )]
    if (
        any(value is None or not 0.0 <= value <= 1.0 for value in probabilities)
        or abs(sum(value for value in probabilities if value is not None) - 1.0) > 1e-9
    ):
        return None
    loss = _finite(source_distribution.get("LOSS"))
    half_loss = _finite(source_distribution.get("HALF_LOSS"))
    if loss is None or half_loss is None:
        return None
    model_over_probability = loss + 0.5 * half_loss
    _assert_track_d_fade_not_intent_gated(market_odds, p_fade)
    return {
        "selection": "OVER",
        "line": str(line),
        "channel_odds": channel_odds,
        "channel_bookmaker_id": version.bookmaker_id,
        "channel_quote_identity": channel_over.observation_id,
        "channel_quote_captured_at": channel_over.captured_at.isoformat(),
        "pinnacle_odds": market_odds,
        "pinnacle_quote_observation_ids": [
            pinnacle_over.observation_id, pinnacle_under.observation_id,
        ],
        "pinnacle_quote_captured_at": pinnacle_over.captured_at.isoformat(),
        "pinnacle_quote_identity": canonical_sha256(
            {
                "schema_version": "w2.forward_quote_pair.v1",
                "observation_ids": [pinnacle_over.observation_id, pinnacle_under.observation_id],
            },
            domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
        ),
        "model_reference_probability": model_over_probability,
        "fade_probability": p_fade,
        "fade_delta": FROZEN_FADE_DELTA,
        "fade_ev_channel_with_rebate": fade_ev,
    }


def _assert_track_d_fade_not_intent_gated(
    pinnacle_odds: dict[str, float], fade_probability: float,
) -> None:
    """Production-path tripwire (PR-4): the Track D fade is Pinnacle-anchored.

    The fade probability must be the frozen Pinnacle de-vig plus
    ``FROZEN_FADE_DELTA`` formula.  Any other probability source (in particular
    the OU intent gate, which emits zero positive recommendations) is forbidden;
    this keeps the fade path mutually exclusive with the intent gate.
    """
    expected = min(
        0.99,
        max(0.01, track_d_fair_probability(pinnacle_odds, "OVER") + FROZEN_FADE_DELTA),
    )
    if fade_probability != expected:
        raise AssertionError("TRACK_D_FADE_MUST_USE_PINNACLE_ANCHOR_NOT_INTENT_GATE")


def append_forward_evidence_in_session(
    session: Session,
    version: Any,
    *,
    _event_type: str = "EVALUATION_SNAPSHOT",
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
    fade_requested = bool(getattr(version, "track_d_validation_signal", None))
    fade = build_track_d_validation_signal_in_session(session, version) if fade_requested else None
    quotes, pair_error = ([], None) if fade is not None else _pair(session, version)
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
    quote_at = (
        datetime.fromisoformat(fade["channel_quote_captured_at"])
        if fade is not None else quotes[0].captured_at if quotes else None
    )
    market_quote_at = (
        datetime.fromisoformat(fade["pinnacle_quote_captured_at"])
        if fade is not None else quote_at
    )
    times = (forecast_at, quote_at, market_quote_at, kickoff)
    pit_ok = (
        all(value is not None and value.tzinfo is not None for value in times)
        and forecast_at <= version.evaluated_at < kickoff
        and quote_at <= version.evaluated_at
        and market_quote_at <= version.evaluated_at
        and version.evaluated_at >= clock.started_at
    )
    reasons = []
    if not pit_ok:
        reasons.append("PIT_UNPROVABLE")
    if pair_error:
        reasons.append(pair_error)
    if fade_requested and fade is None:
        reasons.append("TRACK_D_CHANNEL_OR_MARKET_QUOTE_UNPROVABLE")
    if any(value is None for value in (lambda_home, lambda_away, rho)) or not input_hash:
        reasons.append("MODEL_PARAMETER_UNPROVABLE")
    if (
        capture is None
        or capture.fixture_id != version.fixture_id
        or not version.calibration_identity
    ):
        reasons.append("MODEL_IDENTITY_UNPROVABLE")
    quote_ids = (
        fade["pinnacle_quote_observation_ids"]
        if fade is not None else [row.observation_id for row in quotes]
    )
    quote_pair_identity = (
        canonical_sha256(
            {"schema_version": "w2.forward_quote_pair.v1", "observation_ids": quote_ids},
            domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
        )
        if quote_ids
        else None
    )
    fade_valid = fade is not None and not reasons
    signal_config = getattr(version, "track_d_validation_signal", None) or {}
    source_selection = str(signal_config.get("source_selection") or version.selection)
    payload = {
        "schema_version": "w2.recommendation_review_ledger.evaluation.v1",
        "event_type": _event_type,
        "evaluation_id": version.evaluation_id,
        "derived_from_evaluation_id": version.evaluation_id,
        "decision_version": version.evaluation_policy_version,
        "calibration_identity": version.calibration_identity,
        "market_quote_identity": (
            fade["pinnacle_quote_identity"]
            if (fade is not None and fade_valid)
            else version.quote_identity_hash
        ),
        "source_quote_identity": version.quote_identity_hash,
        "quote_pair_identity": quote_pair_identity,
        "quote_observation_ids": quote_ids,
        "candidate_kind": (
            TRACK_D_FADE
            if fade_valid
            else
            "OFFICIAL_RECOMMENDATION"
            if version.market != "TOTALS" and version.state.value == "ANALYSIS_PICK_ACTIVE"
            else "NO_EDGE_DISPLAY"
            if version.state.value == "NO_EDGE_CURRENT"
            else "FACTOR_GATE_BLOCKED"
            if version.state.value == "BLOCKED_BY_FACTOR"
            else "EVALUATION_ONLY"
        ),
        "original_selection": source_selection,
        "display_state": (
            VALIDATION_SIGNAL if fade_valid else version.state.value
        ),
        "watermark": (
            VALIDATION_SIGNAL_WATERMARK if fade_valid else None
        ),
        "official_recommendation": False if fade_requested else (
            version.market != "TOTALS" and version.state.value == "ANALYSIS_PICK_ACTIVE"
        ),
        "track_d_validation_signal": fade if fade_valid else None,
        "factor_gate_state": version.factor_decision_status,
        "fixture_id": version.fixture_id,
        "competition_id": getattr(version, "competition_id", None),
        "market": version.market,
        "evaluated_at": version.evaluated_at.isoformat(),
        "captured_at": _iso(quote_at),
        "channel_quote_captured_at": _iso(quote_at) if fade else None,
        "pinnacle_quote_captured_at": _iso(market_quote_at) if fade else None,
        "forecast_captured_at": _iso(forecast_at),
        "first_quote_captured_at": _iso(market_quote_at) if quote_ids else None,
        "second_quote_captured_at": _iso(market_quote_at) if quote_ids else None,
        "first_quote_selection": (
            "OVER" if fade is not None
            else quotes[0].canonical_selection if quotes else None
        ),
        "second_quote_selection": (
            "UNDER" if fade is not None
            else quotes[1].canonical_selection if quotes else None
        ),
        "kickoff_utc": kickoff.isoformat() if kickoff else None,
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "rho": rho,
        "model_input_identity": input_hash,
        "five_state_distribution": version.model_settlement_distribution,
        "forecast_capture_identity": version.model_forecast_capture_identity_hash,
        "model_forecast_manifest_hash": capture.model_input_manifest_hash if capture else None,
        "evaluation_identity_hash": version.identity_hash,
        "selection": "OVER" if fade_valid else version.selection,
        "exact_line": str(version.exact_line) if version.exact_line is not None else None,
        "channel_quote_identity": fade["channel_quote_identity"] if fade else None,
        "pinnacle_quote_identity": fade["pinnacle_quote_identity"] if fade else None,
        "decimal_odds_channel": fade["channel_odds"] if fade else None,
        "decimal_odds_pinnacle": fade["pinnacle_odds"]["OVER"] if fade else None,
        "channel_bookmaker_id": fade["channel_bookmaker_id"] if fade else None,
        "model_reference_probability": (
            fade["model_reference_probability"] if fade else None
        ),
        "fade_probability": fade["fade_probability"] if fade else None,
        "fade_delta": FROZEN_FADE_DELTA if fade else None,
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
        event_type=_event_type,
        evaluated_at=version.evaluated_at,
        pit_status=payload["pit_status"],
        payload=payload,
        payload_sha256=digest,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def record_shadow_evidence_in_session(
    session: Session, version: Any,
) -> RecommendationReviewLedgerModel | None:
    """Keep the shadow writer outside recommendation transaction correctness.

    A savepoint rolls back a writer failure without removing the original
    evaluation. The Dashboard counts missing ledger rows as write gaps, and
    the exception is logged with the evaluation identity for investigation.
    """
    original_written = False
    fade_row: RecommendationReviewLedgerModel | None = None
    try:
        with session.begin_nested():
            append_forward_evidence_in_session(session, version)
            original_written = True
    except Exception:
        _LOG.exception("FORWARD_EVIDENCE_WRITE_FAILED evaluation_id=%s", version.evaluation_id)
    if original_written and (
        version.market == "TOTALS"
        and version.selection == "UNDER"
        and version.state.value in {"ANALYSIS_PICK_ACTIVE", "NO_EDGE_CURRENT"}
    ):
        try:
            with session.begin_nested():
                fade_version = replace(
                    version,
                    selection="OVER",
                    track_d_validation_signal={
                        "candidate_kind": TRACK_D_FADE,
                        "source_selection": "UNDER",
                    },
                )
                fade_row = append_forward_evidence_in_session(
                    session, fade_version, _event_type="DECISION_SNAPSHOT"
                )
        except Exception:
            _LOG.exception("TRACK_D_EVIDENCE_WRITE_FAILED evaluation_id=%s", version.evaluation_id)
    if fade_row is not None and fade_row.payload.get("candidate_kind") == TRACK_D_FADE:
        return fade_row
    return None


def append_validation_signal_settlement_in_session(
    session: Session,
    *,
    evaluation_id: str,
    settlement: str,
    profit_units_channel: float,
    settled_at: datetime,
    home_goals: int | None = None,
    away_goals: int | None = None,
) -> RecommendationReviewLedgerModel:
    """Append settlement facts for a fade signal using channel price + rebate."""
    original = session.scalar(
        select(RecommendationReviewLedgerModel).where(
            RecommendationReviewLedgerModel.evaluation_id == evaluation_id,
            RecommendationReviewLedgerModel.event_type == "DECISION_SNAPSHOT",
        )
    )
    if original is None or (original.payload or {}).get("candidate_kind") != TRACK_D_FADE:
        raise ValueError("TRACK_D_SETTLEMENT_SOURCE_NOT_FOUND")
    source = original.payload or {}
    rebate = abs(float(profit_units_channel)) * float(REBATE_RATE)
    payload = {
        "schema_version": "w2.recommendation_review_ledger.settlement.v1",
        "event_type": "SETTLEMENT_OBSERVED",
        "evaluation_id": evaluation_id,
        "derived_from_evaluation_id": evaluation_id,
        "market_quote_identity": source.get("market_quote_identity"),
        "channel_quote_identity": source.get("channel_quote_identity"),
        "evaluated_at": source.get("evaluated_at"),
        "captured_at": source.get("first_quote_captured_at"),
        "kickoff_utc": source.get("kickoff_utc"),
        "selection": "OVER",
        "market": source.get("market"),
        "exact_line": source.get("exact_line"),
        "decimal_odds_channel": source.get("decimal_odds_channel"),
        "candidate_kind": TRACK_D_FADE,
        "display_state": VALIDATION_SIGNAL,
        "watermark": VALIDATION_SIGNAL_WATERMARK,
        "settlement": settlement,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "profit_units_channel": profit_units_channel,
        "rebate_units_channel": rebate,
        "profit_units_channel_with_rebate": profit_units_channel + rebate,
        "rebate_formula_version": REBATE_FORMULA_VERSION,
        "settlement_observed_at": settled_at.isoformat(),
    }
    digest = canonical_sha256(payload, domain=HashDomain.PREMATCH_READ_MODEL_GENERIC)
    existing = session.get(RecommendationReviewLedgerModel, digest)
    if existing is not None:
        if existing.payload_sha256 != digest or existing.payload != payload:
            raise ValueError("TRACK_D_SETTLEMENT_IDENTITY_CONFLICT")
        return existing
    row = RecommendationReviewLedgerModel(
        review_event_id=digest,
        evaluation_id=evaluation_id,
        event_type="SETTLEMENT_OBSERVED",
        evaluated_at=settled_at,
        pit_status="PROVABLE",
        payload=payload,
        payload_sha256=digest,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def settle_track_d_validation_signals_in_session(
    session: Session, *, now: datetime,
) -> dict[str, int]:
    """Append immutable settlement events once authoritative results exist."""
    snapshots = list(
        session.scalars(
            select(RecommendationReviewLedgerModel).where(
                RecommendationReviewLedgerModel.event_type == "DECISION_SNAPSHOT",
            )
        )
    )
    settled_ids = {
        row.evaluation_id
        for row in session.scalars(
            select(RecommendationReviewLedgerModel).where(
                RecommendationReviewLedgerModel.event_type == "SETTLEMENT_OBSERVED",
                RecommendationReviewLedgerModel.payload["candidate_kind"].as_string()
                == TRACK_D_FADE,
            )
        )
    }
    fixture_ids = {
        str((row.payload or {}).get("fixture_id") or "")
        for row in snapshots
        if (row.payload or {}).get("candidate_kind") == TRACK_D_FADE
        and row.pit_status == "PROVABLE"
        and row.evaluation_id not in settled_ids
    }
    if not fixture_ids:
        return {"signals": 0, "settled": 0}
    canonical_ids = set(fixture_ids) | {f"api_football:{value}" for value in fixture_ids}
    results = {
        str(result.fixture_id): result
        for result in session.scalars(
            select(ResultModel).where(ResultModel.fixture_id.in_(canonical_ids))
        )
    }
    settled = 0
    signals = 0
    units = {"WIN": 1.0, "HALF_WIN": 0.5, "PUSH": 0.0, "HALF_LOSS": -0.5, "LOSS": -1.0}
    for row in snapshots:
        payload = row.payload or {}
        if (
            payload.get("candidate_kind") != TRACK_D_FADE
            or row.pit_status != "PROVABLE"
            or row.evaluation_id in settled_ids
        ):
            continue
        signals += 1
        fixture_id = str(payload.get("fixture_id") or "")
        result = results.get(fixture_id) or results.get(f"api_football:{fixture_id}")
        odds = _finite(payload.get("decimal_odds_channel"))
        line = payload.get("exact_line")
        if result is None or odds is None or line is None:
            continue
        kickoff_text = payload.get("kickoff_utc")
        kickoff = datetime.fromisoformat(str(kickoff_text)) if kickoff_text else None
        confirmed_at = result.confirmed_at
        if (
            kickoff is None
            or kickoff.tzinfo is None
            or confirmed_at is None
            or result.result_status not in {"FT", "AET", "PEN"}
            or confirmed_at.replace(tzinfo=confirmed_at.tzinfo or UTC) > now
            or confirmed_at.replace(tzinfo=confirmed_at.tzinfo or UTC) < kickoff
        ):
            continue
        try:
            outcome = settle_total_goals(
                result.home_goals + result.away_goals, "OVER", Decimal(str(line))
            ).value
            unit = units[outcome]
            profit = unit * (odds - 1.0) if unit > 0 else unit
            append_validation_signal_settlement_in_session(
                session,
                evaluation_id=row.evaluation_id,
                settlement=outcome,
                profit_units_channel=profit,
                settled_at=confirmed_at.replace(tzinfo=confirmed_at.tzinfo or UTC),
                home_goals=result.home_goals,
                away_goals=result.away_goals,
            )
            settled += 1
        except (InvalidOperation, TypeError, ValueError, KeyError):
            _LOG.exception("TRACK_D_SETTLEMENT_WRITE_FAILED evaluation_id=%s", row.evaluation_id)
    return {"signals": signals, "settled": settled}
