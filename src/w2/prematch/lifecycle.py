from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from w2.domain import calibration_authority
from w2.domain.admission_contract import (
    MIN_CASHFLOW_PRICE_EDGE_FLOAT,
    economic_admission_pass,
)

ACTIVE_DELTA_THRESHOLD = 0.05
ACTIVE_EV_THRESHOLD = 0.0
ACTIVE_EV_MINUS_SE_THRESHOLD = 0.0
LINEUP_CONFIRMED_CHECKPOINT = "LINEUP_CONFIRMED"
T30_VALIDATION_CHECKPOINT = "T-30m_VALIDATION_LOCK"
DYNAMIC_EVALUATION_V1_SCHEMA = "w2.dynamic_quote_evaluation.v1"
DYNAMIC_EVALUATION_V2_SCHEMA = "w2.dynamic_quote_evaluation.v2"
DYNAMIC_EVALUATION_V3_SCHEMA = "w2.dynamic_quote_evaluation.v3"
MODEL_FORECAST_DENOMINATOR_SCOPE = "MODEL_FORECAST_CAPTURE_MARKET_V1"
CHECKPOINT_OPPORTUNITY_SCOPE = "CHECKPOINT_EVALUATION_OPPORTUNITY_V2"
CHECKPOINT_OPPORTUNITY_SEMANTICS = "CHECKPOINT_EVALUATION_OPPORTUNITY"
MIN_DYNAMIC_BOOKMAKER_DEPTH = 3
SETTLEMENT_STATE_ORDER = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")
# Calibration decides admission, so it belongs in the identity that append-only
# dedup keys on. Adding a key changes every future hash, so the payloads carry an
# explicit version: an old and a new hash then differ for a reason a reader can see.
EVALUATION_IDENTITY_VERSION = "w2.dynamic_quote_evaluation.identity.v2"
LEGACY_EVALUATION_IDENTITY_VERSION = "w2.dynamic_quote_evaluation.identity.v1"
ATTEMPT_IDENTITY_VERSION = "w2.dynamic_quote_evaluation.attempt_identity.v2"
EVAL_02B_DISTRIBUTION_TOLERANCE = 1e-9
SOURCE_ABSENT_USER_MESSAGE = "当前采集窗口尚未取得完整盘口"
SOURCE_ABSENT_NEXT_ACTION = "等待下一次受控采集"


class DynamicEvaluationState(StrEnum):
    ANALYSIS_PICK_ACTIVE = "ANALYSIS_PICK_ACTIVE"
    NO_EDGE_CURRENT = "NO_EDGE_CURRENT"
    STALE_PENDING_REFRESH = "STALE_PENDING_REFRESH"
    LINEUP_READY_MARKET_REFRESH_PENDING = "LINEUP_READY_MARKET_REFRESH_PENDING"
    NOT_READY_SOURCE_ABSENT = "NOT_READY_SOURCE_ABSENT"
    NOT_READY_QUOTE_INCOMPLETE = "NOT_READY_QUOTE_INCOMPLETE"
    NOT_READY_MODEL_INPUT = "NOT_READY_MODEL_INPUT"
    SUPERSEDED = "SUPERSEDED"


class OpportunityState(StrEnum):
    EVALUATED_NO_EDGE = "EVALUATED_NO_EDGE"
    EVALUATED_CANDIDATE = "EVALUATED_CANDIDATE"
    BLOCKED_BY_GATE = "BLOCKED_BY_GATE"
    MISSED_CHECKPOINT = "MISSED_CHECKPOINT"
    EVALUATION_ERROR = "EVALUATION_ERROR"


EVALUATED_OPPORTUNITY_STATES = frozenset(
    {
        OpportunityState.EVALUATED_CANDIDATE.value,
        OpportunityState.EVALUATED_NO_EDGE.value,
        OpportunityState.BLOCKED_BY_GATE.value,
    }
)


def evaluated_attempt_identities(rows: Sequence[Any]) -> set[tuple[str, str]]:
    return {
        (str(row.opportunity_identity_hash), str(row.attempt_identity_hash))
        for row in rows
        if getattr(row, "official_funnel_eligible", None) is True
        and getattr(row, "opportunity_identity_hash", None)
        and getattr(row, "attempt_identity_hash", None)
    }


def final_official_opportunities(
    rows: Sequence[Any],
    *,
    evaluated_attempts: set[tuple[str, str]],
) -> dict[tuple[str, str], Any]:
    final: dict[tuple[str, str], Any] = {}
    for row in rows:
        if (
            str(row.state) not in EVALUATED_OPPORTUNITY_STATES
            or (
                str(row.opportunity_identity_hash),
                str(row.latest_attempt_identity_hash),
            )
            not in evaluated_attempts
        ):
            continue
        key = (str(row.fixture_id).removeprefix("api_football:"), str(row.market))
        previous = final.get(key)
        if previous is None or (
            row.scheduled_checkpoint_at,
            row.recorded_at,
            row.opportunity_identity_hash,
        ) > (
            previous.scheduled_checkpoint_at,
            previous.recorded_at,
            previous.opportunity_identity_hash,
        ):
            final[key] = row
    return final


@dataclass(frozen=True, kw_only=True)
class EvaluationOpportunityContext:
    model_forecast_capture_identity_hash: str
    model_input_hash: str
    evaluation_policy_version: str
    evaluation_slot_id: str
    scheduled_checkpoint_at: datetime
    checkpoint_plan_identity: str
    source_event_identity: str

    def __post_init__(self) -> None:
        from w2.prematch.evaluation_slots import require_evaluation_slot

        if not self.model_forecast_capture_identity_hash or not self.model_input_hash:
            raise ValueError("MODEL_FORECAST_CAPTURE_IDENTITY_MISSING")
        if not self.checkpoint_plan_identity or not self.source_event_identity:
            raise ValueError("OPPORTUNITY_SOURCE_IDENTITY_MISSING")
        require_evaluation_slot(
            self.evaluation_slot_id,
            policy_version=self.evaluation_policy_version,
        )
        _aware_utc(self.scheduled_checkpoint_at, field="scheduled_checkpoint_at")


@dataclass(frozen=True, kw_only=True)
class DynamicEvaluationInput:
    fixture_id: str
    market: str
    selection: str
    exact_line: float | None
    bookmaker_id: str | None
    capture_id: str | None
    quote_identity_hash: str | None
    model_input_hash: str | None
    evaluated_at: datetime
    checkpoint: str
    capture_at: datetime | None = None
    source_observations_present: bool = True
    exact_quote_complete: bool = True
    quote_fresh: bool = True
    model_ready: bool = True
    market_probability_ready: bool = True
    # Absent means unvalidated: an evaluation that never carried a calibration
    # status is exactly the case this gate exists to catch, so it fails closed.
    calibration_status: str | None = None
    identity_conflict: bool = False
    model_probability: float | None = None
    market_probability: float | None = None
    expected_value: float | None = None
    ev_se: float | None = None
    cashflow_price_edge: float | None = None
    decimal_odds: float | None = None
    lineup_input_hash: str | None = None
    lineup_confirmed_at: datetime | None = None
    post_lineup_quote: bool = False
    schema_version: str = DYNAMIC_EVALUATION_V1_SCHEMA
    competition_id: str | None = None
    season: str | None = None
    provider: str | None = None
    model_settlement_distribution: Mapping[str, Any] | None = None
    bookmaker_count: int = 0
    mainline_parsed: bool = False
    denominator_scope: str | None = None
    calibration_identity: str | None = None
    one_x_two_probabilities: Mapping[str, Any] | None = None


@dataclass(frozen=True, kw_only=True)
class DynamicEvaluationVersion:
    evaluation_id: str
    identity_hash: str
    fixture_id: str
    market: str
    selection: str
    exact_line: float | None
    bookmaker_id: str | None
    capture_id: str | None
    quote_identity_hash: str | None
    model_input_hash: str | None
    lineup_input_hash: str | None
    checkpoint: str
    evaluated_at: datetime
    capture_at: datetime | None
    state: DynamicEvaluationState
    current_ev: float | None
    current_delta: float | None
    current_ev_minus_se: float | None
    decimal_odds: float | None
    required_ev: float
    required_delta: float
    required_ev_minus_se: float
    shortfall: dict[str, float]
    blockers: tuple[str, ...]
    user_message: str | None
    next_action: str | None
    current_cashflow_price_edge: float | None = None
    required_cashflow_price_edge: float = MIN_CASHFLOW_PRICE_EDGE_FLOAT
    probability_delta_admission_gate: bool = False
    supersedes_evaluation_id: str | None = None
    supersession_reason: str | None = None
    schema_version: str = DYNAMIC_EVALUATION_V1_SCHEMA
    competition_id: str | None = None
    season: str | None = None
    provider: str | None = None
    model_settlement_distribution: dict[str, float] | None = None
    scoreline_reference: dict[str, Any] | None = None
    bookmaker_count: int = 0
    denominator_scope: str | None = None
    first_failed_gate: str | None = None
    all_failed_gates: tuple[str, ...] = ()
    gate_results: dict[str, bool] | None = None
    recorded_at: datetime | None = None
    measurement_semantics: str | None = None
    official_funnel_eligible: bool | None = None
    exclusion_reason: str | None = None
    evaluation_policy_version: str | None = None
    evaluation_slot_id: str | None = None
    model_forecast_capture_identity_hash: str | None = None
    opportunity_identity_hash: str | None = None
    attempt_identity_hash: str | None = None
    scheduled_checkpoint_at: datetime | None = None
    checkpoint_plan_identity: str | None = None
    source_event_identity: str | None = None
    opportunity_state: OpportunityState | None = None
    # The calibration behind the decision, kept on the record rather than only in
    # gate_results. gate_results says whether the gate passed; these say what the
    # gate was looking at, under which authority, and what it concluded.
    calibration_status_raw: str | None = None
    calibration_status: str | None = None
    calibration_recommendation_admissible: bool | None = None
    calibration_authority: str | None = None
    # Evidence-only payload additions. They deliberately do not participate in
    # identity_payload so existing frozen evaluation identities remain stable.
    calibration_identity: str | None = None
    one_x_two_probabilities: dict[str, float] | None = None

    def as_dict(
        self,
        *,
        projected_state: DynamicEvaluationState | None = None,
        superseded_by_evaluation_id: str | None = None,
    ) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = (projected_state or self.state).value
        payload["evaluated_at"] = _iso(self.evaluated_at)
        payload["capture_at"] = _iso(self.capture_at) if self.capture_at else None
        payload["blockers"] = list(self.blockers)
        payload["all_failed_gates"] = list(self.all_failed_gates)
        payload["recorded_at"] = _iso(self.recorded_at) if self.recorded_at else None
        payload["scheduled_checkpoint_at"] = (
            _iso(self.scheduled_checkpoint_at) if self.scheduled_checkpoint_at else None
        )
        payload["opportunity_state"] = (
            self.opportunity_state.value if self.opportunity_state else None
        )
        payload["superseded_by_evaluation_id"] = superseded_by_evaluation_id
        payload["immutable"] = True
        payload["schema_version"] = self.schema_version
        return payload


def bind_evaluation_opportunity(
    version: DynamicEvaluationVersion,
    context: EvaluationOpportunityContext,
) -> DynamicEvaluationVersion:
    """Bind a classified attempt to its pre-registered orchestration event."""

    opportunity_hash = opportunity_identity_hash(context, market=version.market)
    attempt_hash = _hash(
        {
            "attempt_identity_version": ATTEMPT_IDENTITY_VERSION,
            "opportunity_identity_hash": opportunity_hash,
            "quote_identity_hash": version.quote_identity_hash,
            "model_input_hash": context.model_input_hash,
            "lineup_input_hash": version.lineup_input_hash,
            "source_event_identity": context.source_event_identity,
            # Same quote, same model input, different calibration is a different
            # attempt: it reached its conclusion on a different basis. Without this
            # the append-only first-write-wins swallows the second conclusion, so a
            # downgrade from validated to unvalidated would never be recorded.
            "calibration_status": version.calibration_status,
            "calibration_recommendation_admissible": (
                version.calibration_recommendation_admissible
            ),
        }
    )
    if version.state == DynamicEvaluationState.ANALYSIS_PICK_ACTIVE:
        state = OpportunityState.EVALUATED_CANDIDATE
    elif version.state == DynamicEvaluationState.NO_EDGE_CURRENT:
        state = OpportunityState.EVALUATED_NO_EDGE
    else:
        state = OpportunityState.BLOCKED_BY_GATE
    return replace(
        version,
        evaluation_id=f"dqe-{attempt_hash}",
        identity_hash=attempt_hash,
        model_input_hash=context.model_input_hash,
        checkpoint=context.evaluation_slot_id,
        denominator_scope=CHECKPOINT_OPPORTUNITY_SCOPE,
        measurement_semantics=CHECKPOINT_OPPORTUNITY_SEMANTICS,
        official_funnel_eligible=True,
        evaluation_policy_version=context.evaluation_policy_version,
        evaluation_slot_id=context.evaluation_slot_id,
        model_forecast_capture_identity_hash=(
            context.model_forecast_capture_identity_hash
        ),
        opportunity_identity_hash=opportunity_hash,
        attempt_identity_hash=attempt_hash,
        scheduled_checkpoint_at=context.scheduled_checkpoint_at,
        checkpoint_plan_identity=context.checkpoint_plan_identity,
        source_event_identity=context.source_event_identity,
        opportunity_state=state,
    )


def opportunity_identity_hash(
    context: EvaluationOpportunityContext,
    *,
    market: str,
) -> str:
    return _hash(
        {
            "model_forecast_capture_identity_hash": (
                context.model_forecast_capture_identity_hash
            ),
            "evaluation_policy_version": context.evaluation_policy_version,
            "evaluation_slot_id": context.evaluation_slot_id,
            "market": market,
        }
    )


@dataclass(frozen=True, kw_only=True)
class LineupConfirmedEvent:
    fixture_id: str
    competition_id: str
    season: str
    captured_at: datetime
    lineup_input_hash: str
    home_starters: int
    away_starters: int
    home_lineup_identity_hash: str
    away_lineup_identity_hash: str
    source_capture_id: str
    raw_sha256: str
    checkpoint: str = LINEUP_CONFIRMED_CHECKPOINT

    def __post_init__(self) -> None:
        if not self.fixture_id or not self.competition_id or not self.season:
            raise ValueError("LINEUP_EVENT_IDENTITY_MISSING")
        _aware_utc(self.captured_at, field="captured_at")
        if self.checkpoint != LINEUP_CONFIRMED_CHECKPOINT:
            raise ValueError("LINEUP_EVENT_CHECKPOINT_INVALID")
        if self.home_starters != 11 or self.away_starters != 11:
            raise ValueError("STARTING_XI_INCOMPLETE")
        if not self.lineup_input_hash:
            raise ValueError("LINEUP_INPUT_HASH_MISSING")
        if not self.home_lineup_identity_hash or not self.away_lineup_identity_hash:
            raise ValueError("LINEUP_IDENTITY_HASH_MISSING")
        if not self.source_capture_id or not self.raw_sha256:
            raise ValueError("LINEUP_EVENT_PROVENANCE_MISSING")

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "competition_id": self.competition_id,
            "season": self.season,
            "captured_at": _iso(self.captured_at),
            "checkpoint": self.checkpoint,
            "lineup_input_hash": self.lineup_input_hash,
            "home_lineup_identity_hash": self.home_lineup_identity_hash,
            "away_lineup_identity_hash": self.away_lineup_identity_hash,
            "home_starters": self.home_starters,
            "away_starters": self.away_starters,
            "source_capture_id": self.source_capture_id,
            "raw_sha256": self.raw_sha256,
            "schema_version": "w2.lineup_confirmed_event.v2",
            "numeric_adjustment_enabled": False,
            "lineup_ah_adjustment": 0.0,
            "lineup_totals_adjustment": 0.0,
            "lambda_adjustment": 0.0,
        }


def lineup_confirmed_refresh_plan(
    *,
    fixture_id: str,
    competition_id: str,
    season: str,
    kickoff_utc: datetime,
    captured_at_utc: datetime,
    home_starters: int,
    away_starters: int,
    lineup_input_hash: str,
) -> dict[str, Any]:
    kickoff = _aware_utc(kickoff_utc, field="kickoff_utc")
    captured_at = _aware_utc(captured_at_utc, field="captured_at_utc")
    if home_starters != 11 or away_starters != 11:
        raise ValueError("STARTING_XI_INCOMPLETE")
    if not lineup_input_hash:
        raise ValueError("LINEUP_INPUT_HASH_MISSING")
    if captured_at >= kickoff:
        raise ValueError("POST_KICKOFF_LINEUP_REJECTED")
    payload: dict[str, Any] = {
        "fixture_id": fixture_id,
        "competition_id": competition_id,
        "season": season,
        "policy_version": "w2.matchday_intake_policy.v2",
        "checkpoint": LINEUP_CONFIRMED_CHECKPOINT,
        "kickoff_utc": _iso(kickoff),
        "scheduled_at": _iso(captured_at),
        "window_start": _iso(captured_at),
        "window_end": _iso(kickoff),
        "endpoints": ["odds"],
        "status": "DUE",
        "missed_at": None,
        "capture_id": None,
        "current_unscheduled_capture_id": None,
        "blockers": [],
    }
    payload["plan_hash"] = _hash(payload)
    return payload


@dataclass(frozen=True, kw_only=True)
class LockSnapshotResult:
    status: str
    snapshot: dict[str, Any] | None
    eligible_count: int
    rejected: tuple[dict[str, str], ...]
    checkpoint: str = T30_VALIDATION_CHECKPOINT


def classify_evaluation(
    value: DynamicEvaluationInput,
    *,
    identity_version: str = EVALUATION_IDENTITY_VERSION,
) -> DynamicEvaluationVersion:
    calibration_record = calibration_authority.evidence_record(value.calibration_status)
    calibration_normalised = str(calibration_record["calibration_status"])
    calibration_admissible = bool(
        calibration_record["calibration_recommendation_admissible"]
    )
    evaluated_at = _aware_utc(value.evaluated_at, field="evaluated_at")
    capture_at = (
        _aware_utc(value.capture_at, field="capture_at") if value.capture_at is not None else None
    )
    lineup_confirmed_at = (
        _aware_utc(value.lineup_confirmed_at, field="lineup_confirmed_at")
        if value.lineup_confirmed_at is not None
        else None
    )
    distribution = _v2_distribution(value)
    blockers: list[str] = []
    user_message: str | None = None
    next_action: str | None = None

    delta = (
        float(value.model_probability) - float(value.market_probability)
        if value.model_probability is not None and value.market_probability is not None
        else None
    )
    ev = float(value.expected_value) if value.expected_value is not None else None
    ev_se = float(value.ev_se) if value.ev_se is not None else None
    ev_minus_se = ev - ev_se if ev is not None and ev_se is not None else None

    denominator_scoped = value.denominator_scope in {
        MODEL_FORECAST_DENOMINATOR_SCOPE,
        CHECKPOINT_OPPORTUNITY_SCOPE,
    }
    if not value.source_observations_present:
        state = DynamicEvaluationState.NOT_READY_SOURCE_ABSENT
        blockers.append("SOURCE_OBSERVATIONS_ABSENT")
        user_message = SOURCE_ABSENT_USER_MESSAGE
        next_action = SOURCE_ABSENT_NEXT_ACTION
    elif value.identity_conflict:
        state = DynamicEvaluationState.NOT_READY_QUOTE_INCOMPLETE
        blockers.append("QUOTE_IDENTITY_CONFLICT")
    elif not value.mainline_parsed and denominator_scoped:
        state = DynamicEvaluationState.NOT_READY_QUOTE_INCOMPLETE
        blockers.append("MAINLINE_NOT_PARSED")
    elif not value.exact_quote_complete or not value.quote_identity_hash:
        state = DynamicEvaluationState.NOT_READY_QUOTE_INCOMPLETE
        blockers.append("PAIR_INCOMPLETE")
    elif denominator_scoped and value.bookmaker_count < MIN_DYNAMIC_BOOKMAKER_DEPTH:
        state = DynamicEvaluationState.NOT_READY_QUOTE_INCOMPLETE
        blockers.append("INSUFFICIENT_BOOKMAKER_DEPTH")
    elif lineup_confirmed_at is not None and (
        capture_at is None
        or capture_at < lineup_confirmed_at
        or not value.post_lineup_quote
        or not value.lineup_input_hash
    ):
        state = DynamicEvaluationState.LINEUP_READY_MARKET_REFRESH_PENDING
        blockers.append("POST_LINEUP_FRESH_QUOTE_PENDING")
    elif not value.quote_fresh:
        state = DynamicEvaluationState.STALE_PENDING_REFRESH
        blockers.append("CURRENT_QUOTE_STALE")
    elif not value.model_ready or not value.market_probability_ready or not value.model_input_hash:
        state = DynamicEvaluationState.NOT_READY_MODEL_INPUT
        blockers.append("MODEL_OR_DEVIG_NOT_READY")
    elif not calibration_admissible:
        # The distribution, EV and EV_SE are still computed, stored and shown; only
        # the authority to become a candidate is withheld. An unvalidated
        # probability is analysis evidence, not a recommendation.
        state = DynamicEvaluationState.NOT_READY_MODEL_INPUT
        blockers.append(calibration_authority.RECOMMENDATION_BLOCKER)
    elif ev is None or delta is None or ev_minus_se is None or value.cashflow_price_edge is None:
        state = DynamicEvaluationState.NOT_READY_MODEL_INPUT
        blockers.append("EV_EVIDENCE_INCOMPLETE")
    elif economic_admission_pass(
        expected_value=ev,
        ev_minus_se=ev_minus_se,
        cashflow_price_edge=value.cashflow_price_edge,
    ):
        state = DynamicEvaluationState.ANALYSIS_PICK_ACTIVE
    else:
        state = DynamicEvaluationState.NO_EDGE_CURRENT
        if ev <= ACTIVE_EV_THRESHOLD:
            blockers.append("EV_NOT_POSITIVE")
        if value.cashflow_price_edge < MIN_CASHFLOW_PRICE_EDGE_FLOAT:
            blockers.append("CASHFLOW_EDGE_BELOW_THRESHOLD")
        if ev_minus_se <= ACTIVE_EV_MINUS_SE_THRESHOLD:
            blockers.append("EV_MINUS_SE_NOT_POSITIVE")

    shortfall = {
        "ev": round(max(ACTIVE_EV_THRESHOLD - ev, 0.0), 6) if ev is not None else 0.0,
        "delta": 0.0,
        "cashflow_price_edge": round(
            max(MIN_CASHFLOW_PRICE_EDGE_FLOAT - value.cashflow_price_edge, 0.0), 6
        )
        if value.cashflow_price_edge is not None
        else 0.0,
        "ev_minus_se": round(max(ACTIVE_EV_MINUS_SE_THRESHOLD - ev_minus_se, 0.0), 6)
        if ev_minus_se is not None
        else 0.0,
    }
    if identity_version not in {
        EVALUATION_IDENTITY_VERSION,
        LEGACY_EVALUATION_IDENTITY_VERSION,
    }:
        raise ValueError("EVALUATION_IDENTITY_VERSION_INVALID")
    identity_payload: dict[str, Any] = {
        "fixture_id": value.fixture_id,
        "market": value.market,
        "selection": value.selection,
        "exact_line": value.exact_line,
        "bookmaker_id": value.bookmaker_id,
        "capture_id": value.capture_id,
        "quote_identity_hash": value.quote_identity_hash,
        "model_input_hash": value.model_input_hash,
        "lineup_input_hash": value.lineup_input_hash,
        "checkpoint": value.checkpoint,
        "capture_at": _iso(capture_at) if capture_at else None,
    }
    if identity_version == EVALUATION_IDENTITY_VERSION:
        identity_payload.update(
            {
                "identity_version": EVALUATION_IDENTITY_VERSION,
                "calibration_status": calibration_normalised,
                "calibration_recommendation_admissible": calibration_admissible,
            }
        )
    if denominator_scoped:
        identity_payload.update(
            {
                "denominator_scope": value.denominator_scope,
                "bookmaker_count": value.bookmaker_count,
                "mainline_parsed": value.mainline_parsed,
                "source_observations_present": value.source_observations_present,
                "exact_quote_complete": value.exact_quote_complete,
                "quote_fresh": value.quote_fresh,
                "model_ready": value.model_ready,
                "market_probability_ready": value.market_probability_ready,
            }
        )
    if value.schema_version in {DYNAMIC_EVALUATION_V2_SCHEMA, DYNAMIC_EVALUATION_V3_SCHEMA}:
        identity_payload.update(
            {
                "schema_version": value.schema_version,
                "competition_id": value.competition_id,
                "season": value.season,
                "provider": value.provider,
                "model_settlement_distribution": distribution,
            }
        )
    identity_hash = _hash(identity_payload)
    evaluation_complete = bool(
        value.model_ready
        and value.mainline_parsed
        and value.exact_quote_complete
        and value.bookmaker_count >= MIN_DYNAMIC_BOOKMAKER_DEPTH
        and value.quote_fresh
        and value.market_probability_ready
        and value.model_input_hash
        and ev is not None
        and delta is not None
        and ev_minus_se is not None
        and value.cashflow_price_edge is not None
    )
    gate_results = (
        {
            "model_ready": bool(value.model_ready),
            "mainline_parsed": bool(value.mainline_parsed),
            "bookmaker_depth": value.bookmaker_count >= MIN_DYNAMIC_BOOKMAKER_DEPTH,
            "quote_fresh": bool(value.quote_fresh),
            "evaluated": evaluation_complete,
            "calibration_validated": calibration_admissible,
            "no_edge": evaluation_complete and state == DynamicEvaluationState.NO_EDGE_CURRENT,
            "candidate": evaluation_complete
            and state == DynamicEvaluationState.ANALYSIS_PICK_ACTIVE,
        }
        if denominator_scoped
        else None
    )
    failed_gates = (
        tuple(
            gate
            for gate in (
                "MODEL_READY",
                "MAINLINE_PARSED",
                "BOOKMAKER_DEPTH",
                "QUOTE_FRESH",
                "CALIBRATION_VALIDATED",
                "EVALUATION_COMPLETE",
            )
            if not bool(
                gate_results[
                    {
                        "MODEL_READY": "model_ready",
                        "MAINLINE_PARSED": "mainline_parsed",
                        "BOOKMAKER_DEPTH": "bookmaker_depth",
                        "QUOTE_FRESH": "quote_fresh",
                        "CALIBRATION_VALIDATED": "calibration_validated",
                        "EVALUATION_COMPLETE": "evaluated",
                    }[gate]
                ]
            )
        )
        if gate_results is not None
        else ()
    )
    return DynamicEvaluationVersion(
        evaluation_id=f"dqe-{identity_hash}",
        identity_hash=identity_hash,
        calibration_status_raw=calibration_record["calibration_status_raw"],
        calibration_status=calibration_record["calibration_status"],
        calibration_recommendation_admissible=calibration_admissible,
        calibration_authority=calibration_record["calibration_authority"],
        calibration_identity=value.calibration_identity,
        one_x_two_probabilities=_one_x_two_probabilities(value.one_x_two_probabilities),
        fixture_id=str(value.fixture_id),
        market=str(value.market),
        selection=str(value.selection),
        exact_line=float(value.exact_line) if value.exact_line is not None else None,
        bookmaker_id=str(value.bookmaker_id) if value.bookmaker_id else None,
        capture_id=str(value.capture_id) if value.capture_id else None,
        quote_identity_hash=str(value.quote_identity_hash) if value.quote_identity_hash else None,
        model_input_hash=str(value.model_input_hash) if value.model_input_hash else None,
        lineup_input_hash=str(value.lineup_input_hash) if value.lineup_input_hash else None,
        checkpoint=str(value.checkpoint),
        evaluated_at=evaluated_at,
        capture_at=capture_at,
        state=state,
        current_ev=round(ev, 6) if ev is not None else None,
        current_delta=round(delta, 6) if delta is not None else None,
        current_ev_minus_se=round(ev_minus_se, 6) if ev_minus_se is not None else None,
        current_cashflow_price_edge=(
            round(value.cashflow_price_edge, 6) if value.cashflow_price_edge is not None else None
        ),
        decimal_odds=(
            round(float(value.decimal_odds), 6) if value.decimal_odds is not None else None
        ),
        required_ev=ACTIVE_EV_THRESHOLD,
        required_delta=0.0,
        required_cashflow_price_edge=MIN_CASHFLOW_PRICE_EDGE_FLOAT,
        probability_delta_admission_gate=False,
        required_ev_minus_se=ACTIVE_EV_MINUS_SE_THRESHOLD,
        shortfall=shortfall,
        blockers=tuple(blockers),
        user_message=user_message,
        next_action=next_action,
        schema_version=value.schema_version,
        competition_id=str(value.competition_id) if value.competition_id else None,
        season=str(value.season) if value.season else None,
        provider=str(value.provider) if value.provider else None,
        model_settlement_distribution=distribution,
        bookmaker_count=max(0, int(value.bookmaker_count)),
        denominator_scope=value.denominator_scope,
        first_failed_gate=failed_gates[0] if failed_gates else None,
        all_failed_gates=failed_gates,
        gate_results=gate_results,
    )


def _one_x_two_probabilities(raw: Mapping[str, Any] | None) -> dict[str, float] | None:
    if raw is None:
        return None
    if set(raw) != {"home", "draw", "away"}:
        raise ValueError("DYNAMIC_EVALUATION_1X2_INVALID")
    try:
        probabilities = {side: float(raw[side]) for side in ("home", "draw", "away")}
    except (TypeError, ValueError):
        raise ValueError("DYNAMIC_EVALUATION_1X2_INVALID") from None
    if any(not math.isfinite(value) or value < 0 for value in probabilities.values()):
        raise ValueError("DYNAMIC_EVALUATION_1X2_INVALID")
    # Simulation public probabilities are rounded to six decimals; the three
    # rounded values can differ from one by at most 1.5e-6.
    if abs(sum(probabilities.values()) - 1.0) > 2e-6:
        raise ValueError("DYNAMIC_EVALUATION_1X2_INVALID")
    return probabilities


def _v2_distribution(value: DynamicEvaluationInput) -> dict[str, float] | None:
    if value.schema_version == DYNAMIC_EVALUATION_V1_SCHEMA:
        return None
    if value.schema_version == DYNAMIC_EVALUATION_V3_SCHEMA:
        raw = value.model_settlement_distribution
        if raw is None:
            return None
        return _validated_distribution(raw)
    if value.schema_version != DYNAMIC_EVALUATION_V2_SCHEMA:
        raise ValueError("DYNAMIC_EVALUATION_SCHEMA_UNSUPPORTED")
    required_identity = (
        value.fixture_id,
        value.competition_id,
        value.season,
        value.provider,
        value.market,
        value.selection,
        value.bookmaker_id,
        value.capture_id,
        value.quote_identity_hash,
        value.model_input_hash,
        value.checkpoint,
    )
    if any(item is None or not str(item).strip() for item in required_identity):
        raise ValueError("DYNAMIC_EVALUATION_V2_IDENTITY_INCOMPLETE")
    if value.exact_line is None or value.capture_at is None:
        raise ValueError("DYNAMIC_EVALUATION_V2_IDENTITY_INCOMPLETE")
    raw = value.model_settlement_distribution
    return _validated_distribution(raw)


def _validated_distribution(raw: Mapping[str, Any] | None) -> dict[str, float]:
    if not isinstance(raw, Mapping) or set(raw) != set(SETTLEMENT_STATE_ORDER):
        raise ValueError("DYNAMIC_EVALUATION_V2_DISTRIBUTION_INVALID")
    try:
        distribution = {state: float(raw[state]) for state in SETTLEMENT_STATE_ORDER}
    except (TypeError, ValueError):
        raise ValueError("DYNAMIC_EVALUATION_V2_DISTRIBUTION_INVALID") from None
    if any(not math.isfinite(item) or item < 0 for item in distribution.values()):
        raise ValueError("DYNAMIC_EVALUATION_V2_DISTRIBUTION_INVALID")
    if abs(sum(distribution.values()) - 1.0) > EVAL_02B_DISTRIBUTION_TOLERANCE:
        raise ValueError("DYNAMIC_EVALUATION_V2_DISTRIBUTION_INVALID")
    return distribution


class DynamicEvaluationLedger:
    """In-memory append-only projection used by DB and artifact adapters.

    Evaluation rows never change. Supersession is a separate relation projected
    at read time, so old business conclusions become ``SUPERSEDED`` without
    rewriting their original evidence.
    """

    def __init__(self, versions: Sequence[DynamicEvaluationVersion] = ()) -> None:
        self._versions: list[DynamicEvaluationVersion] = []
        self._by_identity: dict[str, DynamicEvaluationVersion] = {}
        self._superseded_by: dict[str, str] = {}
        self._supersession_reason: dict[str, str] = {}
        for version in versions:
            self.append(version)

    def append(
        self,
        value: DynamicEvaluationInput | DynamicEvaluationVersion,
        *,
        supersession_reason: str = "NEW_CAPTURE_OR_MODEL_INPUT",
    ) -> DynamicEvaluationVersion:
        candidate = (
            classify_evaluation(value) if isinstance(value, DynamicEvaluationInput) else value
        )
        existing = self._by_identity.get(candidate.identity_hash)
        if existing is not None:
            return existing
        previous = self.current_for(candidate.fixture_id, candidate.market)
        if previous is not None:
            candidate = DynamicEvaluationVersion(
                **{
                    **asdict(candidate),
                    "supersedes_evaluation_id": previous.evaluation_id,
                    "supersession_reason": supersession_reason,
                }
            )
            self._superseded_by[previous.evaluation_id] = candidate.evaluation_id
            self._supersession_reason[previous.evaluation_id] = supersession_reason
        self._versions.append(candidate)
        self._by_identity[candidate.identity_hash] = candidate
        return candidate

    def confirm_lineup(self, event: LineupConfirmedEvent) -> None:
        for version in list(self._versions):
            if (
                version.fixture_id != event.fixture_id
                or version.evaluation_id in self._superseded_by
            ):
                continue
            marker_hash = _hash(
                {
                    "event": LINEUP_CONFIRMED_CHECKPOINT,
                    "fixture_id": event.fixture_id,
                    "lineup_input_hash": event.lineup_input_hash,
                    "market": version.market,
                }
            )
            marker = DynamicEvaluationVersion(
                evaluation_id=f"dqe-{marker_hash}",
                identity_hash=marker_hash,
                fixture_id=version.fixture_id,
                market=version.market,
                selection=version.selection,
                exact_line=version.exact_line,
                bookmaker_id=None,
                capture_id=None,
                quote_identity_hash=None,
                model_input_hash=None,
                lineup_input_hash=event.lineup_input_hash,
                checkpoint=LINEUP_CONFIRMED_CHECKPOINT,
                evaluated_at=_aware_utc(event.captured_at, field="captured_at"),
                capture_at=None,
                state=DynamicEvaluationState.LINEUP_READY_MARKET_REFRESH_PENDING,
                current_ev=None,
                current_delta=None,
                current_ev_minus_se=None,
                decimal_odds=None,
                required_ev=ACTIVE_EV_THRESHOLD,
                required_delta=ACTIVE_DELTA_THRESHOLD,
                required_ev_minus_se=ACTIVE_EV_MINUS_SE_THRESHOLD,
                shortfall={"ev": 0.0, "delta": 0.0, "ev_minus_se": 0.0},
                blockers=("POST_LINEUP_FRESH_QUOTE_PENDING",),
                user_message=None,
                next_action="立即执行首发后的受控赔率刷新",
            )
            self.append(marker, supersession_reason="LINEUP_INPUT_SUPERSEDED")

    def current_for(self, fixture_id: str, market: str) -> DynamicEvaluationVersion | None:
        for version in reversed(self._versions):
            if (
                version.fixture_id == fixture_id
                and version.market == market
                and version.evaluation_id not in self._superseded_by
            ):
                return version
        return None

    def as_dict(self) -> dict[str, Any]:
        versions = []
        for version in self._versions:
            superseded_by = self._superseded_by.get(version.evaluation_id)
            payload = version.as_dict(
                projected_state=(DynamicEvaluationState.SUPERSEDED if superseded_by else None),
                superseded_by_evaluation_id=superseded_by,
            )
            if superseded_by:
                payload["supersession_reason"] = self._supersession_reason[version.evaluation_id]
            versions.append(payload)
        return {
            "schema_version": "w2.dynamic_quote_ev_lifecycle.v1",
            "versions": versions,
            "current_evaluation_ids": [
                version.evaluation_id
                for version in self._versions
                if version.evaluation_id not in self._superseded_by
            ],
        }


def select_t30_validation_snapshot(
    snapshots: Sequence[Mapping[str, Any]],
    *,
    kickoff: datetime,
    tolerance_minutes: int = 5,
) -> LockSnapshotResult:
    kickoff_utc = _aware_utc(kickoff, field="kickoff")
    target = kickoff_utc - timedelta(minutes=30)
    tolerance = timedelta(minutes=max(int(tolerance_minutes), 0))
    eligible: list[tuple[float, datetime, dict[str, Any]]] = []
    rejected: list[dict[str, str]] = []
    for raw in snapshots:
        snapshot = dict(raw)
        capture_at = _parse_datetime(snapshot.get("capture_at") or snapshot.get("captured_at"))
        reason: str | None = None
        if capture_at is None:
            reason = "CAPTURE_TIME_MISSING"
        elif capture_at > kickoff_utc:
            reason = "POST_KICKOFF_REJECTED"
        elif abs(capture_at - target) > tolerance:
            reason = "OUTSIDE_T30_WINDOW"
        elif not bool(snapshot.get("exact_quote_complete", snapshot.get("quote_complete", False))):
            reason = "PAIR_INCOMPLETE"
        elif not bool(snapshot.get("quote_fresh", snapshot.get("fresh", False))):
            reason = "QUOTE_NOT_FRESH"
        elif not bool(snapshot.get("model_inputs_frozen", False)):
            reason = "MODEL_INPUTS_NOT_FROZEN"
        if reason is not None:
            rejected.append(
                {
                    "capture_id": str(snapshot.get("capture_id") or ""),
                    "reason": reason,
                }
            )
            continue
        assert capture_at is not None
        eligible.append((abs((capture_at - target).total_seconds()), capture_at, snapshot))
    if not eligible:
        return LockSnapshotResult(
            status="LOCK_SNAPSHOT_UNAVAILABLE",
            snapshot=None,
            eligible_count=0,
            rejected=tuple(rejected),
        )
    # Time proximity is the only selector. EV and price are deliberately absent
    # from the ordering, preventing retrospective best-price selection.
    eligible.sort(key=lambda item: (item[0], item[1], str(item[2].get("capture_id") or "")))
    selected = dict(eligible[0][2])
    selected["checkpoint"] = T30_VALIDATION_CHECKPOINT
    selected["validation_target_at"] = _iso(target)
    selected["validation_window_minutes"] = tolerance_minutes
    selected["validation_active"] = True
    return LockSnapshotResult(
        status="READY",
        snapshot=selected,
        eligible_count=len(eligible),
        rejected=tuple(rejected),
    )


def _hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=lambda value: _iso(value) if isinstance(value, datetime) else str(value),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _aware_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field.upper()}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(UTC)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _aware_utc(value, field="capture_at")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return _aware_utc(parsed, field="capture_at")
