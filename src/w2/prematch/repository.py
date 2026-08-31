from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.domain import calibration_authority
from w2.domain.canonical_serialization import (
    CURRENT_SERIALIZER_VERSION,
    HashDomain,
    canonical_sha256,
)
from w2.domain.enums import MarketType
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
    DynamicPrematchOpportunityModel,
    DynamicPrematchSupersessionModel,
    LineupConfirmedEventModel,
    T30ValidationSnapshotModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayFixtureIdentityModel,
)
from w2.prematch.candidate_notifications import (
    enqueue_attempt_notification_in_session,
    enqueue_closeout_withdrawal_in_session,
)
from w2.prematch.lifecycle import (
    CHECKPOINT_OPPORTUNITY_SCOPE,
    DYNAMIC_EVALUATION_V2_SCHEMA,
    EVAL_02B_DISTRIBUTION_TOLERANCE,
    MODEL_FORECAST_DENOMINATOR_SCOPE,
    SETTLEMENT_STATE_ORDER,
    DynamicEvaluationState,
    DynamicEvaluationVersion,
    EvaluationOpportunityContext,
    LineupConfirmedEvent,
    LockSnapshotResult,
    OpportunityState,
    opportunity_identity_hash,
)

PAIR_PROJECTOR_SCHEMA = "w2.eval_02b_exact_pair_projection.v2"
_PAIR_MARKETS = {MarketType.ASIAN_HANDICAP.value, MarketType.TOTALS.value}
_PAIR_ELIGIBLE_STATES = {
    DynamicEvaluationState.ANALYSIS_PICK_ACTIVE.value,
    DynamicEvaluationState.NO_EDGE_CURRENT.value,
}


class DynamicPrematchRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine()

    def append_evaluation(
        self,
        version: DynamicEvaluationVersion,
        *,
        supersession_reason: str = "NEW_CAPTURE_OR_MODEL_INPUT",
    ) -> tuple[DynamicEvaluationVersion, bool]:
        with Session(self.engine) as session:
            try:
                result = self.append_evaluation_in_session(
                    session,
                    version,
                    supersession_reason=supersession_reason,
                )
                session.commit()
                return result
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(DynamicPrematchEvaluationModel).where(
                        DynamicPrematchEvaluationModel.identity_hash == version.identity_hash
                    )
                )
                if existing is None:
                    raise
                return _version_from_payload(existing.payload), False

    def denominator_covered_fixture_ids(self) -> set[str]:
        """Return canonical bare fixture ids with both current market rows."""
        with Session(self.engine) as session:
            rows = session.execute(
                select(
                    DynamicPrematchEvaluationModel.fixture_id,
                    DynamicPrematchEvaluationModel.market,
                ).where(
                    DynamicPrematchEvaluationModel.denominator_scope
                    == MODEL_FORECAST_DENOMINATOR_SCOPE,
                    ~DynamicPrematchEvaluationModel.evaluation_id.in_(
                        select(DynamicPrematchSupersessionModel.superseded_evaluation_id)
                    ),
                )
            )
        markets: dict[str, set[str]] = {}
        for fixture_id, market in rows:
            canonical = str(fixture_id).removeprefix("api_football:")
            markets.setdefault(canonical, set()).add(str(market))
        return {
            fixture_id
            for fixture_id, values in markets.items()
            if {MarketType.ASIAN_HANDICAP.value, MarketType.TOTALS.value} <= values
        }

    def append_evaluation_in_session(
        self,
        session: Session,
        version: DynamicEvaluationVersion,
        *,
        supersession_reason: str = "NEW_CAPTURE_OR_MODEL_INPUT",
    ) -> tuple[DynamicEvaluationVersion, bool]:
        """Append evaluation and supersession without owning the transaction."""
        existing = session.scalar(
            select(DynamicPrematchEvaluationModel).where(
                DynamicPrematchEvaluationModel.identity_hash == version.identity_hash
            )
        )
        if existing is not None:
            return _version_from_payload(existing.payload), False
        persisted = replace(version, recorded_at=datetime.now(UTC))
        payload = persisted.as_dict()
        # Supersession is scoped to one evaluation slot.  Keyed on fixture x market
        # alone, the T-15m record would retire T-30m, which retired T-45m, and so
        # on -- five distinct opportunities collapsing into the last one, so a
        # fixture evaluated at five checkpoints would report two.  A retry within
        # the same slot still supersedes, which is the behaviour we do want.
        previous = session.scalar(
            select(DynamicPrematchEvaluationModel)
            .where(
                DynamicPrematchEvaluationModel.fixture_id == version.fixture_id,
                DynamicPrematchEvaluationModel.market == version.market,
                DynamicPrematchEvaluationModel.checkpoint == version.checkpoint,
                DynamicPrematchEvaluationModel.model_forecast_capture_identity_hash
                == version.model_forecast_capture_identity_hash,
                DynamicPrematchEvaluationModel.evaluation_policy_version
                == version.evaluation_policy_version,
                DynamicPrematchEvaluationModel.official_funnel_eligible.is_(
                    version.official_funnel_eligible
                ),
                ~DynamicPrematchEvaluationModel.evaluation_id.in_(
                    select(DynamicPrematchSupersessionModel.superseded_evaluation_id)
                ),
            )
            .order_by(DynamicPrematchEvaluationModel.evaluated_at.desc())
            .limit(1)
        )
        session.add(
            DynamicPrematchEvaluationModel(
                evaluation_id=persisted.evaluation_id,
                identity_hash=persisted.identity_hash,
                fixture_id=persisted.fixture_id,
                market=persisted.market,
                selection=persisted.selection,
                checkpoint=persisted.checkpoint,
                capture_id=persisted.capture_id,
                quote_identity_hash=persisted.quote_identity_hash,
                model_input_hash=persisted.model_input_hash,
                lineup_input_hash=persisted.lineup_input_hash,
                evaluated_at=persisted.evaluated_at,
                capture_at=persisted.capture_at,
                original_state=persisted.state.value,
                recorded_at=persisted.recorded_at,
                denominator_scope=persisted.denominator_scope,
                measurement_semantics=persisted.measurement_semantics,
                official_funnel_eligible=persisted.official_funnel_eligible,
                exclusion_reason=persisted.exclusion_reason,
                evaluation_policy_version=persisted.evaluation_policy_version,
                evaluation_slot_id=persisted.evaluation_slot_id,
                model_forecast_capture_identity_hash=(
                    persisted.model_forecast_capture_identity_hash
                ),
                opportunity_identity_hash=persisted.opportunity_identity_hash,
                attempt_identity_hash=persisted.attempt_identity_hash,
                scheduled_checkpoint_at=persisted.scheduled_checkpoint_at,
                checkpoint_plan_identity=persisted.checkpoint_plan_identity,
                source_event_identity=persisted.source_event_identity,
                bookmaker_count=persisted.bookmaker_count,
                first_failed_gate=persisted.first_failed_gate,
                all_failed_gates=list(persisted.all_failed_gates),
                gate_results=persisted.gate_results,
                payload=payload,
            )
        )
        session.flush()
        if persisted.denominator_scope == CHECKPOINT_OPPORTUNITY_SCOPE:
            self._upsert_opportunity_in_session(session, persisted)
            enqueue_attempt_notification_in_session(session, persisted)
        if previous is not None:
            session.add(
                DynamicPrematchSupersessionModel(
                    superseded_evaluation_id=previous.evaluation_id,
                    superseded_by_evaluation_id=version.evaluation_id,
                    fixture_id=version.fixture_id,
                    market=version.market,
                    reason=supersession_reason,
                    created_at=version.evaluated_at,
                )
            )
            session.flush()
        return persisted, True

    def _upsert_opportunity_in_session(
        self,
        session: Session,
        version: DynamicEvaluationVersion,
    ) -> None:
        if not all(
            (
                version.opportunity_identity_hash,
                version.attempt_identity_hash,
                version.model_forecast_capture_identity_hash,
                version.evaluation_policy_version,
                version.evaluation_slot_id,
                version.scheduled_checkpoint_at,
                version.checkpoint_plan_identity,
                version.source_event_identity,
                version.opportunity_state,
                version.recorded_at,
            )
        ):
            raise ValueError("OFFICIAL_OPPORTUNITY_IDENTITY_INCOMPLETE")
        assert version.scheduled_checkpoint_at is not None
        assert version.opportunity_state is not None
        row = session.get(
            DynamicPrematchOpportunityModel,
            version.opportunity_identity_hash,
        )
        payload = {
            "opportunity_identity_hash": version.opportunity_identity_hash,
            "model_forecast_capture_identity_hash": (
                version.model_forecast_capture_identity_hash
            ),
            "evaluation_policy_version": version.evaluation_policy_version,
            "evaluation_slot_id": version.evaluation_slot_id,
            "market": version.market,
            "checkpoint_plan_identity": version.checkpoint_plan_identity,
            "scheduled_checkpoint_at": version.scheduled_checkpoint_at.isoformat(),
            "state": version.opportunity_state.value,
            "immutable_identity": True,
        }
        if row is None:
            session.add(
                DynamicPrematchOpportunityModel(
                    opportunity_identity_hash=version.opportunity_identity_hash,
                    fixture_id=version.fixture_id,
                    market=version.market,
                    model_forecast_capture_identity_hash=(
                        version.model_forecast_capture_identity_hash
                    ),
                    evaluation_policy_version=version.evaluation_policy_version,
                    evaluation_slot_id=version.evaluation_slot_id,
                    scheduled_checkpoint_at=version.scheduled_checkpoint_at,
                    checkpoint_plan_identity=version.checkpoint_plan_identity,
                    state=version.opportunity_state.value,
                    recorded_at=version.recorded_at,
                    evaluated_at=version.evaluated_at,
                    latest_attempt_identity_hash=version.attempt_identity_hash,
                    payload=payload,
                )
            )
            session.flush()
            return
        identity = (
            row.fixture_id,
            row.market,
            row.model_forecast_capture_identity_hash,
            row.evaluation_policy_version,
            row.evaluation_slot_id,
            _plan_time(row.scheduled_checkpoint_at),
            row.checkpoint_plan_identity,
        )
        expected = (
            version.fixture_id,
            version.market,
            version.model_forecast_capture_identity_hash,
            version.evaluation_policy_version,
            version.evaluation_slot_id,
            _plan_time(version.scheduled_checkpoint_at),
            version.checkpoint_plan_identity,
        )
        if identity != expected:
            raise ValueError("OPPORTUNITY_IDENTITY_CONFLICT")
        row.state = version.opportunity_state.value
        row.evaluated_at = version.evaluated_at
        row.latest_attempt_identity_hash = version.attempt_identity_hash
        row.payload = payload
        session.flush()

    def record_opportunity_without_attempt(
        self,
        *,
        fixture_id: str,
        market: str,
        context: EvaluationOpportunityContext,
        state: OpportunityState,
        recorded_at: datetime,
        blocker: str,
    ) -> bool:
        with Session(self.engine) as session:
            inserted = self.record_opportunity_without_attempt_in_session(
                session,
                fixture_id=fixture_id,
                market=market,
                context=context,
                state=state,
                recorded_at=recorded_at,
                blocker=blocker,
            )
            session.commit()
        return inserted

    def record_opportunity_without_attempt_in_session(
        self,
        session: Session,
        *,
        fixture_id: str,
        market: str,
        context: EvaluationOpportunityContext,
        state: OpportunityState,
        recorded_at: datetime,
        blocker: str,
    ) -> bool:
        if state not in {
            OpportunityState.MISSED_CHECKPOINT,
            OpportunityState.EVALUATION_ERROR,
        }:
            raise ValueError("OPPORTUNITY_STATE_REQUIRES_ATTEMPT")
        identity = opportunity_identity_hash(context, market=market)
        existing = session.get(DynamicPrematchOpportunityModel, identity)
        if existing is not None:
            return False
        session.add(
            DynamicPrematchOpportunityModel(
                opportunity_identity_hash=identity,
                fixture_id=fixture_id,
                market=market,
                model_forecast_capture_identity_hash=(
                    context.model_forecast_capture_identity_hash
                ),
                evaluation_policy_version=context.evaluation_policy_version,
                evaluation_slot_id=context.evaluation_slot_id,
                scheduled_checkpoint_at=context.scheduled_checkpoint_at,
                checkpoint_plan_identity=context.checkpoint_plan_identity,
                state=state.value,
                recorded_at=recorded_at,
                evaluated_at=None,
                latest_attempt_identity_hash=None,
                payload={
                    "opportunity_identity_hash": identity,
                    "state": state.value,
                    "scheduled_checkpoint_at": context.scheduled_checkpoint_at.isoformat(),
                    "recorded_at": recorded_at.isoformat(),
                    "evaluated_at": None,
                    "blocker": blocker,
                    "source_event_identity": context.source_event_identity,
                    "immutable_identity": True,
                },
            )
        )
        session.flush()
        enqueue_closeout_withdrawal_in_session(
            session,
            fixture_id=fixture_id,
            market=market,
            opportunity_identity_hash=identity,
            model_forecast_capture_identity_hash=(
                context.model_forecast_capture_identity_hash
            ),
            evaluation_policy_version=context.evaluation_policy_version,
            evaluation_slot_id=context.evaluation_slot_id,
            scheduled_checkpoint_at=context.scheduled_checkpoint_at,
            current_state=state,
            recorded_at=recorded_at,
            blocker=blocker,
        )
        return True

    def append_lineup_event(
        self,
        event: LineupConfirmedEvent,
    ) -> tuple[LineupConfirmedEvent, bool]:
        with Session(self.engine) as session:
            try:
                result = self.append_lineup_event_in_session(session, event)
                session.commit()
                return result
            except Exception:
                session.rollback()
                raise

    def append_lineup_event_in_session(
        self,
        session: Session,
        event: LineupConfirmedEvent,
    ) -> tuple[LineupConfirmedEvent, bool]:
        existing = list(
            session.scalars(
                select(LineupConfirmedEventModel)
                .where(LineupConfirmedEventModel.fixture_id == event.fixture_id)
                .order_by(LineupConfirmedEventModel.captured_at, LineupConfirmedEventModel.event_id)
                .limit(2)
            )
        )
        if len(existing) > 1:
            raise ValueError("LINEUP_CONFIRMATION_CONFLICT")
        if existing:
            row = existing[0]
            if row.lineup_input_hash != event.lineup_input_hash:
                raise ValueError("LINEUP_CONFIRMATION_CONFLICT")
            original = _lineup_event_from_payload(row.payload)
            if _lineup_event_business_fields(original) != _lineup_event_business_fields(event):
                raise ValueError("LINEUP_EVENT_PAYLOAD_CONFLICT")
            return original, False

        session.add(
            LineupConfirmedEventModel(
                event_id=f"lineup:{event.lineup_input_hash}",
                fixture_id=event.fixture_id,
                lineup_input_hash=event.lineup_input_hash,
                captured_at=event.captured_at,
                checkpoint=event.checkpoint,
                payload=event.as_dict(),
            )
        )
        session.flush()
        return event, True

    def ensure_lineup_confirmed_odds_plan_in_session(
        self,
        session: Session,
        plan: Mapping[str, Any],
    ) -> tuple[str, bool]:
        plan_id = _checkpoint_plan_id(plan)
        existing = session.get(MatchdayCheckpointPlanModel, plan_id)
        if existing is not None:
            if not _same_checkpoint_plan_spec(existing, plan):
                raise RuntimeError("CHECKPOINT_PLAN_CONFLICT")
            return existing.plan_id, False
        session.add(
            MatchdayCheckpointPlanModel(
                plan_id=plan_id,
                fixture_id=str(plan["fixture_id"]),
                competition_id=str(plan["competition_id"]),
                season=str(plan["season"]),
                policy_version=str(plan["policy_version"]),
                checkpoint=str(plan["checkpoint"]),
                kickoff_utc=_plan_time(plan["kickoff_utc"]),
                scheduled_at=_plan_time(plan["scheduled_at"]),
                window_start=_plan_time(plan["window_start"]),
                window_end=_plan_time(plan["window_end"]),
                endpoints=list(plan.get("endpoints") or []),
                status=str(plan["status"]),
                missed_at=_plan_optional_time(plan.get("missed_at")),
                capture_id=str(plan.get("capture_id") or "") or None,
                current_unscheduled_capture_id=str(plan.get("current_unscheduled_capture_id") or "")
                or None,
                blockers=list(plan.get("blockers") or []),
                plan_hash=str(plan["plan_hash"]),
            )
        )
        session.flush()
        return plan_id, True

    def freeze_t30_snapshot(self, fixture_id: str, result: LockSnapshotResult) -> bool:
        if result.status != "READY" or result.snapshot is None:
            return False
        capture_id = str(result.snapshot.get("capture_id") or "")
        capture_at = _parse_utc(
            result.snapshot.get("capture_at") or result.snapshot.get("captured_at")
        )
        if not capture_id or capture_at is None:
            raise ValueError("LOCK_SNAPSHOT_IDENTITY_INCOMPLETE")
        validation_id = f"t30-{fixture_id}-{capture_id}"
        with Session(self.engine) as session:
            session.add(
                T30ValidationSnapshotModel(
                    validation_id=validation_id,
                    fixture_id=fixture_id,
                    capture_id=capture_id,
                    capture_at=capture_at,
                    checkpoint=result.checkpoint,
                    status=result.status,
                    payload=json.loads(
                        json.dumps(
                            result.snapshot,
                            default=lambda value: (
                                value.astimezone(UTC).isoformat()
                                if isinstance(value, datetime)
                                else str(value)
                            ),
                        )
                    ),
                )
            )
            try:
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(T30ValidationSnapshotModel).where(
                        T30ValidationSnapshotModel.fixture_id == fixture_id
                    )
                )
                if existing is not None and existing.capture_id == capture_id:
                    return False
                raise ValueError("T30_VALIDATION_SNAPSHOT_ALREADY_FROZEN") from None

    def lifecycle(self, fixture_id: str) -> dict[str, Any]:
        with Session(self.engine) as session:
            return self.lifecycle_in_session(session, fixture_id)

    @staticmethod
    def lifecycle_in_session(
        session: Session,
        fixture_id: str,
    ) -> dict[str, Any]:
        """Read the lifecycle visible to an existing projection unit-of-work."""
        rows = list(
            session.scalars(
                select(DynamicPrematchEvaluationModel)
                .where(DynamicPrematchEvaluationModel.fixture_id == fixture_id)
                .order_by(DynamicPrematchEvaluationModel.evaluated_at)
            )
        )
        supersessions = {
            row.superseded_evaluation_id: row
            for row in session.scalars(
                select(DynamicPrematchSupersessionModel).where(
                    DynamicPrematchSupersessionModel.fixture_id == fixture_id
                )
            )
        }
        versions: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row.payload)
            payload["original_state"] = row.original_state
            supersession = supersessions.get(row.evaluation_id)
            if supersession is not None:
                payload["state"] = DynamicEvaluationState.SUPERSEDED.value
                payload["superseded_by_evaluation_id"] = supersession.superseded_by_evaluation_id
                payload["supersession_reason"] = supersession.reason
            versions.append(payload)
        return {
            "schema_version": "w2.dynamic_quote_ev_lifecycle.v1",
            "fixture_id": fixture_id,
            "versions": versions,
            "current": [row for row in versions if row.get("state") != "SUPERSEDED"],
        }


def _version_from_payload(payload: dict[str, Any]) -> DynamicEvaluationVersion:
    # Rebuilt rather than defaulted: without this the four calibration fields came
    # back None on every existing-record return, so a caller that read them off a
    # duplicate append saw nothing and could not tell an unvalidated record from a
    # validated one. Legacy payloads reconstruct as UNRECORDED and inadmissible.
    calibration = calibration_authority.reconstruct_from_payload(payload)
    return DynamicEvaluationVersion(
        evaluation_id=str(payload["evaluation_id"]),
        identity_hash=str(payload["identity_hash"]),
        calibration_status_raw=calibration["calibration_status_raw"],
        calibration_status=calibration["calibration_status"],
        calibration_recommendation_admissible=(
            calibration["calibration_recommendation_admissible"]
        ),
        calibration_authority=calibration["calibration_authority"],
        fixture_id=str(payload["fixture_id"]),
        market=str(payload["market"]),
        selection=str(payload["selection"]),
        exact_line=float(payload["exact_line"]) if payload.get("exact_line") is not None else None,
        bookmaker_id=str(payload["bookmaker_id"]) if payload.get("bookmaker_id") else None,
        capture_id=str(payload["capture_id"]) if payload.get("capture_id") else None,
        quote_identity_hash=str(payload["quote_identity_hash"])
        if payload.get("quote_identity_hash")
        else None,
        model_input_hash=str(payload["model_input_hash"])
        if payload.get("model_input_hash")
        else None,
        lineup_input_hash=str(payload["lineup_input_hash"])
        if payload.get("lineup_input_hash")
        else None,
        checkpoint=str(payload["checkpoint"]),
        evaluated_at=_parse_utc(payload["evaluated_at"]) or datetime.now(UTC),
        capture_at=_parse_utc(payload.get("capture_at")),
        state=DynamicEvaluationState(str(payload["state"])),
        current_ev=float(payload["current_ev"]) if payload.get("current_ev") is not None else None,
        current_delta=float(payload["current_delta"])
        if payload.get("current_delta") is not None
        else None,
        current_ev_minus_se=float(payload["current_ev_minus_se"])
        if payload.get("current_ev_minus_se") is not None
        else None,
        current_cashflow_price_edge=(
            float(payload["current_cashflow_price_edge"])
            if payload.get("current_cashflow_price_edge") is not None
            else None
        ),
        decimal_odds=float(payload["decimal_odds"])
        if payload.get("decimal_odds") is not None
        else None,
        required_ev=float(payload["required_ev"]),
        required_delta=float(payload["required_delta"]),
        required_cashflow_price_edge=float(payload.get("required_cashflow_price_edge", 0.05)),
        probability_delta_admission_gate=bool(
            payload.get("probability_delta_admission_gate", False)
        ),
        required_ev_minus_se=float(payload["required_ev_minus_se"]),
        shortfall={str(key): float(value) for key, value in payload["shortfall"].items()},
        blockers=tuple(str(item) for item in payload.get("blockers", [])),
        user_message=str(payload["user_message"]) if payload.get("user_message") else None,
        next_action=str(payload["next_action"]) if payload.get("next_action") else None,
        supersedes_evaluation_id=str(payload["supersedes_evaluation_id"])
        if payload.get("supersedes_evaluation_id")
        else None,
        supersession_reason=str(payload["supersession_reason"])
        if payload.get("supersession_reason")
        else None,
        schema_version=str(payload.get("schema_version") or "w2.dynamic_quote_evaluation.v1"),
        competition_id=str(payload["competition_id"]) if payload.get("competition_id") else None,
        season=str(payload["season"]) if payload.get("season") else None,
        provider=str(payload["provider"]) if payload.get("provider") else None,
        model_settlement_distribution={
            str(key): float(value)
            for key, value in payload["model_settlement_distribution"].items()
        }
        if isinstance(payload.get("model_settlement_distribution"), dict)
        else None,
        scoreline_reference=dict(payload["scoreline_reference"])
        if isinstance(payload.get("scoreline_reference"), dict)
        else None,
        bookmaker_count=max(0, int(payload.get("bookmaker_count") or 0)),
        denominator_scope=str(payload["denominator_scope"])
        if payload.get("denominator_scope")
        else None,
        first_failed_gate=str(payload["first_failed_gate"])
        if payload.get("first_failed_gate")
        else None,
        all_failed_gates=tuple(str(item) for item in payload.get("all_failed_gates", [])),
        gate_results={str(key): bool(value) for key, value in payload["gate_results"].items()}
        if isinstance(payload.get("gate_results"), dict)
        else None,
        recorded_at=_parse_utc(payload.get("recorded_at")),
        measurement_semantics=str(payload["measurement_semantics"])
        if payload.get("measurement_semantics")
        else None,
        official_funnel_eligible=(
            bool(payload["official_funnel_eligible"])
            if payload.get("official_funnel_eligible") is not None
            else None
        ),
        exclusion_reason=str(payload["exclusion_reason"])
        if payload.get("exclusion_reason")
        else None,
        evaluation_policy_version=str(payload["evaluation_policy_version"])
        if payload.get("evaluation_policy_version")
        else None,
        evaluation_slot_id=str(payload["evaluation_slot_id"])
        if payload.get("evaluation_slot_id")
        else None,
        model_forecast_capture_identity_hash=str(
            payload["model_forecast_capture_identity_hash"]
        )
        if payload.get("model_forecast_capture_identity_hash")
        else None,
        opportunity_identity_hash=str(payload["opportunity_identity_hash"])
        if payload.get("opportunity_identity_hash")
        else None,
        attempt_identity_hash=str(payload["attempt_identity_hash"])
        if payload.get("attempt_identity_hash")
        else None,
        scheduled_checkpoint_at=_parse_utc(payload.get("scheduled_checkpoint_at")),
        checkpoint_plan_identity=str(payload["checkpoint_plan_identity"])
        if payload.get("checkpoint_plan_identity")
        else None,
        source_event_identity=str(payload["source_event_identity"])
        if payload.get("source_event_identity")
        else None,
        opportunity_state=(
            OpportunityState(str(payload["opportunity_state"]))
            if payload.get("opportunity_state")
            else None
        ),
    )


def _lineup_event_from_payload(payload: dict[str, Any]) -> LineupConfirmedEvent:
    if payload.get("schema_version") != "w2.lineup_confirmed_event.v2":
        raise ValueError("LINEUP_EVENT_PAYLOAD_CONFLICT")
    captured_at = _parse_utc(payload.get("captured_at"))
    if captured_at is None:
        raise ValueError("LINEUP_EVENT_PAYLOAD_CONFLICT")
    try:
        return LineupConfirmedEvent(
            fixture_id=str(payload["fixture_id"]),
            competition_id=str(payload["competition_id"]),
            season=str(payload["season"]),
            captured_at=captured_at,
            checkpoint=str(payload["checkpoint"]),
            lineup_input_hash=str(payload["lineup_input_hash"]),
            home_lineup_identity_hash=str(payload["home_lineup_identity_hash"]),
            away_lineup_identity_hash=str(payload["away_lineup_identity_hash"]),
            home_starters=int(payload["home_starters"]),
            away_starters=int(payload["away_starters"]),
            source_capture_id=str(payload["source_capture_id"]),
            raw_sha256=str(payload["raw_sha256"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("LINEUP_EVENT_PAYLOAD_CONFLICT") from exc


def _lineup_event_business_fields(event: LineupConfirmedEvent) -> tuple[object, ...]:
    return (
        event.fixture_id,
        event.competition_id,
        event.season,
        event.lineup_input_hash,
        event.home_lineup_identity_hash,
        event.away_lineup_identity_hash,
        event.home_starters,
        event.away_starters,
        event.checkpoint,
    )


def _checkpoint_plan_id(plan: Mapping[str, Any]) -> str:
    identity = ":".join(
        str(plan[key])
        for key in (
            "fixture_id",
            "competition_id",
            "season",
            "checkpoint",
            "policy_version",
        )
    )
    return hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()


def _same_checkpoint_plan_spec(
    existing: MatchdayCheckpointPlanModel,
    plan: Mapping[str, Any],
) -> bool:
    return (
        existing.fixture_id == str(plan["fixture_id"])
        and existing.competition_id == str(plan["competition_id"])
        and existing.season == str(plan["season"])
        and existing.policy_version == str(plan["policy_version"])
        and existing.checkpoint == str(plan["checkpoint"])
        and _plan_time(existing.kickoff_utc) == _plan_time(plan["kickoff_utc"])
        and _plan_time(existing.scheduled_at) == _plan_time(plan["scheduled_at"])
        and _plan_time(existing.window_start) == _plan_time(plan["window_start"])
        and _plan_time(existing.window_end) == _plan_time(plan["window_end"])
        and list(existing.endpoints or []) == list(plan.get("endpoints") or [])
    )


def _plan_optional_time(value: object) -> datetime | None:
    return None if value is None else _plan_time(value)


def _plan_time(value: object) -> datetime:
    parsed = _parse_utc(value)
    if parsed is None:
        raise ValueError("INVALID_DATETIME")
    return parsed


def _parse_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


@dataclass(frozen=True, kw_only=True)
class ExactPairIdentity:
    canonical_fixture_id: str
    competition_id: str
    season_id: str
    provider_id: str
    bookmaker_id: str
    market: str
    selection: str
    exact_line: float
    pre_evaluation_id: str
    post_evaluation_id: str

    def as_dict(self) -> dict[str, object]:
        return {
            "canonical_fixture_id": self.canonical_fixture_id,
            "competition_id": self.competition_id,
            "season_id": self.season_id,
            "provider_id": self.provider_id,
            "bookmaker_id": self.bookmaker_id,
            "market": self.market,
            "selection": self.selection,
            "exact_line": self.exact_line,
            "pre_evaluation_id": self.pre_evaluation_id,
            "post_evaluation_id": self.post_evaluation_id,
        }

    @property
    def identity_hash(self) -> str:
        return _pair_sha256(self.as_dict())


@dataclass(frozen=True, kw_only=True)
class ExactPrePostPair:
    identity: ExactPairIdentity
    identity_hash: str
    hash_domain: str
    serializer_version: str
    kickoff_at: datetime
    lineup_confirmed_at: datetime
    pre_evaluated_at: datetime
    pre_capture_at: datetime
    post_evaluated_at: datetime
    post_capture_at: datetime
    lineup_input_hash: str
    pre_capture_id: str
    post_capture_id: str
    pre_quote_identity_hash: str
    post_quote_identity_hash: str
    pre_superseded_by_evaluation_id: str | None
    post_superseded_by_evaluation_id: str | None
    baseline_distribution: dict[str, float]
    candidate_distribution: dict[str, float]


@dataclass(frozen=True, kw_only=True)
class PairProjectionExclusion:
    fixture_id: str
    market: str | None
    reason: str


@dataclass(frozen=True, kw_only=True)
class ExactPairProjection:
    schema_version: str
    pairs: tuple[ExactPrePostPair, ...]
    exclusions: tuple[PairProjectionExclusion, ...]


@dataclass(frozen=True, kw_only=True)
class _EligiblePairEvaluation:
    evaluation_id: str
    provider_id: str
    bookmaker_id: str
    market: str
    selection: str
    exact_line: float
    capture_id: str
    quote_identity_hash: str
    lineup_input_hash: str | None
    evaluated_at: datetime
    capture_at: datetime
    distribution: dict[str, float]

    @property
    def quote_scope(self) -> tuple[str, str, str, str, float]:
        return (
            self.provider_id,
            self.bookmaker_id,
            self.market,
            self.selection,
            self.exact_line,
        )


def project_exact_eval_02b_pairs(engine: Engine) -> ExactPairProjection:
    """Derive exact immutable Pre/Post pairs without writing or running the gate."""
    with Session(engine) as session:
        fixtures = {
            row.fixture_id: row
            for row in session.scalars(
                select(MatchdayFixtureIdentityModel).order_by(
                    MatchdayFixtureIdentityModel.fixture_id
                )
            )
        }
        alias_index = _fixture_alias_index(fixtures.values())
        identity_exclusions: set[tuple[str, str]] = set()
        events: dict[str, list[LineupConfirmedEventModel]] = {}
        for event in session.scalars(
            select(LineupConfirmedEventModel).order_by(
                LineupConfirmedEventModel.fixture_id,
                LineupConfirmedEventModel.captured_at,
                LineupConfirmedEventModel.event_id,
            )
        ):
            fixture_id, blocker = _resolve_fixture_alias(event.fixture_id, alias_index)
            if fixture_id is None:
                identity_exclusions.add((event.fixture_id, blocker))
            else:
                events.setdefault(fixture_id, []).append(event)
        evaluations: dict[str, list[DynamicPrematchEvaluationModel]] = {}
        for evaluation_row in session.scalars(
            select(DynamicPrematchEvaluationModel).order_by(
                DynamicPrematchEvaluationModel.fixture_id,
                DynamicPrematchEvaluationModel.market,
                DynamicPrematchEvaluationModel.evaluated_at,
                DynamicPrematchEvaluationModel.evaluation_id,
            )
        ):
            fixture_id, blocker = _resolve_fixture_alias(
                evaluation_row.fixture_id,
                alias_index,
            )
            if fixture_id is None:
                identity_exclusions.add((evaluation_row.fixture_id, blocker))
            else:
                evaluations.setdefault(fixture_id, []).append(evaluation_row)
        superseded_by = {
            row.superseded_evaluation_id: row.superseded_by_evaluation_id
            for row in session.scalars(select(DynamicPrematchSupersessionModel))
        }

    pairs: list[ExactPrePostPair] = []
    exclusions = [
        PairProjectionExclusion(fixture_id=fixture_id, market=None, reason=reason)
        for fixture_id, reason in sorted(identity_exclusions)
    ]
    for fixture_id in sorted(set(events) | set(evaluations)):
        fixture = fixtures.get(fixture_id)
        if fixture is None:
            exclusions.append(
                PairProjectionExclusion(
                    fixture_id=fixture_id,
                    market=None,
                    reason="BLOCKED_FIXTURE_IDENTITY_MISSING",
                )
            )
            continue
        fixture_events = events.get(fixture_id, [])
        if not fixture_events:
            exclusions.append(
                PairProjectionExclusion(
                    fixture_id=fixture_id,
                    market=None,
                    reason="BLOCKED_LINEUP_EVENT_MISSING",
                )
            )
            continue
        if len(fixture_events) != 1 or not _event_matches_fixture(
            fixture_events[0],
            fixture,
            alias_index,
        ):
            exclusions.append(
                PairProjectionExclusion(
                    fixture_id=fixture_id,
                    market=None,
                    reason="BLOCKED_LINEUP_EVENT_CONFLICT",
                )
            )
            continue
        event = fixture_events[0]
        by_market: dict[str, list[_EligiblePairEvaluation]] = {}
        fixture_evaluations = evaluations.get(fixture_id, [])
        for row in fixture_evaluations:
            eligible_evaluation = _eligible_pair_evaluation(row, fixture, alias_index)
            if eligible_evaluation is not None:
                by_market.setdefault(eligible_evaluation.market, []).append(eligible_evaluation)
        for market in sorted({row.market for row in fixture_evaluations}):
            pair = _pair_market(
                fixture,
                event,
                by_market.get(market, []),
                superseded_by,
            )
            if pair is None:
                exclusions.append(
                    PairProjectionExclusion(
                        fixture_id=fixture_id,
                        market=market,
                        reason="BLOCKED_EXACT_PRE_POST_PAIR_MISSING_OR_AMBIGUOUS",
                    )
                )
            else:
                pairs.append(pair)
    return ExactPairProjection(
        schema_version=PAIR_PROJECTOR_SCHEMA,
        pairs=tuple(
            sorted(
                pairs,
                key=lambda pair: (
                    pair.kickoff_at,
                    pair.identity.canonical_fixture_id,
                    pair.identity.market,
                ),
            )
        ),
        exclusions=tuple(exclusions),
    )


def _fixture_alias_index(
    fixtures: Iterable[MatchdayFixtureIdentityModel],
) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for fixture in fixtures:
        aliases = {
            fixture.fixture_id,
            fixture.provider_fixture_id,
            f"api_football:{fixture.provider_fixture_id}",
        }
        if fixture.fixture_id.startswith("api_football:"):
            aliases.add(fixture.fixture_id.removeprefix("api_football:"))
        for alias in aliases:
            if alias:
                index.setdefault(alias, set()).add(fixture.fixture_id)
    return index


def _resolve_fixture_alias(
    fixture_id: str,
    alias_index: dict[str, set[str]],
) -> tuple[str | None, str]:
    matches = alias_index.get(fixture_id, set())
    if not matches:
        return None, "BLOCKED_FIXTURE_IDENTITY_MISSING"
    if len(matches) != 1:
        return None, "BLOCKED_FIXTURE_IDENTITY_CONFLICT"
    return next(iter(matches)), ""


def _event_matches_fixture(
    event: LineupConfirmedEventModel,
    fixture: MatchdayFixtureIdentityModel,
    alias_index: dict[str, set[str]],
) -> bool:
    payload = event.payload
    event_fixture_id, _ = _resolve_fixture_alias(event.fixture_id, alias_index)
    payload_fixture_id, _ = _resolve_fixture_alias(
        str(payload.get("fixture_id") or ""),
        alias_index,
    )
    captured_at = _pair_time(payload.get("captured_at"))
    return bool(
        payload.get("schema_version") == "w2.lineup_confirmed_event.v2"
        and event_fixture_id == fixture.fixture_id
        and payload_fixture_id == fixture.fixture_id
        and payload.get("competition_id") == fixture.competition_id
        and payload.get("season") == fixture.season
        and payload.get("lineup_input_hash") == event.lineup_input_hash
        and payload.get("checkpoint") == event.checkpoint == "LINEUP_CONFIRMED"
        and captured_at == _pair_utc(event.captured_at)
        and _pair_utc(event.captured_at) < _pair_utc(fixture.kickoff_utc)
    )


def _eligible_pair_evaluation(
    row: DynamicPrematchEvaluationModel,
    fixture: MatchdayFixtureIdentityModel,
    alias_index: dict[str, set[str]],
) -> _EligiblePairEvaluation | None:
    payload = row.payload
    row_fixture_id, _ = _resolve_fixture_alias(row.fixture_id, alias_index)
    payload_fixture_id, _ = _resolve_fixture_alias(
        str(payload.get("fixture_id") or ""),
        alias_index,
    )
    if (
        payload.get("schema_version") != DYNAMIC_EVALUATION_V2_SCHEMA
        or row.original_state not in _PAIR_ELIGIBLE_STATES
        or row.market not in _PAIR_MARKETS
        or row_fixture_id != fixture.fixture_id
        or payload_fixture_id != fixture.fixture_id
        or payload.get("market") != row.market
        or payload.get("selection") != row.selection
        or payload.get("capture_id") != row.capture_id
        or payload.get("quote_identity_hash") != row.quote_identity_hash
        or payload.get("lineup_input_hash") != row.lineup_input_hash
        or payload.get("competition_id") != fixture.competition_id
        or payload.get("season") != fixture.season
        or payload.get("provider") != fixture.provider
    ):
        return None
    if any(
        value is None or not str(value).strip()
        for value in (
            payload.get("bookmaker_id"),
            payload.get("capture_id"),
            payload.get("quote_identity_hash"),
            payload.get("market"),
            payload.get("selection"),
        )
    ):
        return None
    exact_line = _pair_float(payload.get("exact_line"))
    capture_at = _pair_time(payload.get("capture_at"))
    evaluated_at = _pair_time(payload.get("evaluated_at"))
    distribution = _pair_distribution(payload.get("model_settlement_distribution"))
    if (
        exact_line is None
        or capture_at is None
        or evaluated_at is None
        or distribution is None
        or row.capture_at is None
        or capture_at != _pair_utc(row.capture_at)
        or evaluated_at != _pair_utc(row.evaluated_at)
    ):
        return None
    return _EligiblePairEvaluation(
        evaluation_id=row.evaluation_id,
        provider_id=fixture.provider,
        bookmaker_id=str(payload["bookmaker_id"]),
        market=str(payload["market"]),
        selection=str(payload["selection"]),
        exact_line=exact_line,
        capture_id=str(payload["capture_id"]),
        quote_identity_hash=str(payload["quote_identity_hash"]),
        lineup_input_hash=(
            str(payload["lineup_input_hash"]) if payload.get("lineup_input_hash") else None
        ),
        evaluated_at=evaluated_at,
        capture_at=capture_at,
        distribution=distribution,
    )


def _pair_market(
    fixture: MatchdayFixtureIdentityModel,
    event: LineupConfirmedEventModel,
    evaluations: list[_EligiblePairEvaluation],
    superseded_by: dict[str, str],
) -> ExactPrePostPair | None:
    event_at = _pair_utc(event.captured_at)
    groups: dict[tuple[str, str, str, str, float], list[_EligiblePairEvaluation]] = {}
    for evaluation in evaluations:
        groups.setdefault(evaluation.quote_scope, []).append(evaluation)
    candidates: list[tuple[_EligiblePairEvaluation, _EligiblePairEvaluation]] = []
    for rows in groups.values():
        pre_rows = [
            row for row in rows if row.lineup_input_hash is None and row.capture_at < event_at
        ]
        post_rows = [
            row
            for row in rows
            if row.lineup_input_hash == event.lineup_input_hash and row.capture_at >= event_at
        ]
        if pre_rows and post_rows:
            candidates.append(
                (
                    max(
                        pre_rows,
                        key=lambda row: (
                            row.capture_at,
                            row.evaluated_at,
                            row.evaluation_id,
                        ),
                    ),
                    min(
                        post_rows,
                        key=lambda row: (
                            row.capture_at,
                            row.evaluated_at,
                            row.evaluation_id,
                        ),
                    ),
                )
            )
    if len(candidates) != 1:
        return None
    pre_evaluation, post_evaluation = candidates[0]
    identity = ExactPairIdentity(
        canonical_fixture_id=fixture.fixture_id,
        competition_id=fixture.competition_id,
        season_id=fixture.season,
        provider_id=pre_evaluation.provider_id,
        bookmaker_id=pre_evaluation.bookmaker_id,
        market=pre_evaluation.market,
        selection=pre_evaluation.selection,
        exact_line=pre_evaluation.exact_line,
        pre_evaluation_id=pre_evaluation.evaluation_id,
        post_evaluation_id=post_evaluation.evaluation_id,
    )
    return ExactPrePostPair(
        identity=identity,
        identity_hash=identity.identity_hash,
        hash_domain=HashDomain.EVAL_02B_PAIR_IDENTITY.value,
        serializer_version=CURRENT_SERIALIZER_VERSION.value,
        kickoff_at=_pair_utc(fixture.kickoff_utc),
        lineup_confirmed_at=event_at,
        pre_evaluated_at=pre_evaluation.evaluated_at,
        pre_capture_at=pre_evaluation.capture_at,
        post_evaluated_at=post_evaluation.evaluated_at,
        post_capture_at=post_evaluation.capture_at,
        lineup_input_hash=event.lineup_input_hash,
        pre_capture_id=pre_evaluation.capture_id,
        post_capture_id=post_evaluation.capture_id,
        pre_quote_identity_hash=pre_evaluation.quote_identity_hash,
        post_quote_identity_hash=post_evaluation.quote_identity_hash,
        pre_superseded_by_evaluation_id=superseded_by.get(pre_evaluation.evaluation_id),
        post_superseded_by_evaluation_id=superseded_by.get(post_evaluation.evaluation_id),
        baseline_distribution=pre_evaluation.distribution,
        candidate_distribution=post_evaluation.distribution,
    )


def _pair_distribution(value: object) -> dict[str, float] | None:
    if not isinstance(value, dict) or set(value) != set(SETTLEMENT_STATE_ORDER):
        return None
    try:
        result = {state: float(value[state]) for state in SETTLEMENT_STATE_ORDER}
    except (TypeError, ValueError):
        return None
    if any(not math.isfinite(item) or item < 0 for item in result.values()):
        return None
    if abs(sum(result.values()) - 1.0) > EVAL_02B_DISTRIBUTION_TOLERANCE:
        return None
    return result


def _pair_float(value: object) -> float | None:
    if not isinstance(value, (str, int, float)):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _pair_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _pair_utc(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except (TypeError, ValueError):
        return None


def _pair_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _pair_sha256(value: object) -> str:
    return canonical_sha256(value, domain=HashDomain.EVAL_02B_PAIR_IDENTITY)
