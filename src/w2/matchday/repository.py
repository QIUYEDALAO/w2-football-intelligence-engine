from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, case, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayCheckpointPlanRescheduleModel,
    MatchdayEndpointCaptureModel,
    MatchdayEndpointCapturePlanModel,
    MatchdayEvidenceManifestModel,
    MatchdayFixtureIdentityModel,
    MatchdayMarketObservationModel,
)
from w2.infrastructure.persistence.model_forecast_models import (
    ModelForecastCaptureModel,
    ModelForecastOutcomeModel,
    canonical_model_forecast_fixture_id_sql,
    model_forecast_fixture_aliases,
)
from w2.matchday.intake_v2 import CheckpointPlan, parse_utc, stable_hash, validate_manifest_identity
from w2.prematch.evaluation_slots import CURRENT_EVALUATION_POLICY, is_evaluation_slot
from w2.prematch.lifecycle import EvaluationOpportunityContext, OpportunityState
from w2.prematch.repository import DynamicPrematchRepository


class MatchdayRepositoryError(RuntimeError):
    pass


def _dt(value: Any) -> datetime:
    parsed = parse_utc(value)
    if parsed is None:
        raise MatchdayRepositoryError("INVALID_DATETIME")
    return parsed


def _iso(value: datetime) -> str:
    normalized = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.isoformat().replace("+00:00", "Z")


def _checkpoint_priority() -> Any:
    unsettled_capture = exists(
        select(ModelForecastCaptureModel.capture_identity_hash)
        .outerjoin(
            ModelForecastOutcomeModel,
            ModelForecastOutcomeModel.capture_identity_hash
            == ModelForecastCaptureModel.capture_identity_hash,
        )
        .where(
            ModelForecastOutcomeModel.capture_identity_hash.is_(None),
            canonical_model_forecast_fixture_id_sql(ModelForecastCaptureModel.fixture_id)
            == canonical_model_forecast_fixture_id_sql(MatchdayCheckpointPlanModel.fixture_id),
        )
        .correlate(MatchdayCheckpointPlanModel)
    )
    return case(
        (
            (MatchdayCheckpointPlanModel.checkpoint == "POSTMATCH_RESULT")
            & unsettled_capture,
            0,
        ),
        (MatchdayCheckpointPlanModel.checkpoint != "POSTMATCH_RESULT", 1),
        else_=2,
    )


class MatchdayRuntimeRepository:
    def __init__(self, *, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine()

    def save_raw_payload(
        self,
        *,
        sha256: str,
        endpoint: str,
        captured_at: datetime,
        payload: Mapping[str, Any],
    ) -> bool:
        with Session(self.engine) as session:
            existing = session.get(RawPayloadModel, sha256)
            if existing is not None:
                return False
            session.add(
                RawPayloadModel(
                    sha256=sha256,
                    endpoint=endpoint,
                    captured_at=captured_at,
                    storage_uri=f"db://raw_payload/{sha256}",
                    payload=dict(payload),
                )
            )
            session.commit()
        return True

    def upsert_checkpoint_plan(self, plan: CheckpointPlan | Mapping[str, Any]) -> str:
        with Session(self.engine) as session:
            try:
                plan_id = self.upsert_checkpoint_plan_in_session(session, plan)
                session.commit()
                return plan_id
            except Exception:
                session.rollback()
                raise

    def upsert_checkpoint_plan_in_session(
        self,
        session: Session,
        plan: CheckpointPlan | Mapping[str, Any],
    ) -> str:
        """Upsert one checkpoint plan without owning the transaction."""
        payload = plan.as_dict() if isinstance(plan, CheckpointPlan) else dict(plan)
        plan_id = stable_hash(
            ":".join(
                [
                    str(payload["fixture_id"]),
                    str(payload["competition_id"]),
                    str(payload["season"]),
                    str(payload["checkpoint"]),
                    str(payload["policy_version"]),
                ]
            )
        )
        incoming_status = str(payload["status"])
        existing = session.get(MatchdayCheckpointPlanModel, plan_id)
        if existing is not None:
            rescheduled = normalize_repo_time(existing.kickoff_utc) != normalize_repo_time(
                _dt(payload["kickoff_utc"])
            )
            # Re-dating is checked ahead of the terminal short-circuit because the
            # stranded plans were all MISSED, which is terminal: deferring the check
            # would leave the exact rows the bug produced untouchable.  plan_id is
            # keyed on fixture x checkpoint x policy and deliberately excludes the
            # kickoff, so a postponed fixture reuses these rows.  Only verdicts that
            # recorded no provider interaction are re-dated; anything that touched
            # the provider stays pinned to the window it describes, which for FAILED
            # has to be decided per row rather than by status alone.
            if rescheduled and _is_redatable(session, existing):
                session.add(
                    _reschedule_audit_row(
                        existing,
                        payload=payload,
                        new_status=incoming_status,
                        recorded_at=normalize_repo_time(datetime.now(UTC)),
                    )
                )
                existing.kickoff_utc = _dt(payload["kickoff_utc"])
                existing.scheduled_at = _dt(payload["scheduled_at"])
                existing.window_start = _dt(payload["window_start"])
                existing.window_end = _dt(payload["window_end"])
                existing.status = incoming_status
                existing.missed_at = (
                    _dt(payload["missed_at"]) if payload.get("missed_at") else None
                )
                existing.endpoints = list(payload.get("endpoints") or existing.endpoints or [])
                existing.blockers = list(payload.get("blockers") or [])
                existing.plan_hash = str(payload.get("plan_hash") or existing.plan_hash)
                # A DUE plan may be claimed by a worker mid-flight.  Its result
                # belongs to the old window, so the claim is released here and
                # that worker's transition fails closed rather than recording a
                # capture against the window it never saw.  All four fields go
                # together: claim_due_checkpoint_plans requires claimed_at and
                # claim_token to both be null, and the lease reaper only runs
                # where claim_expires_at is set, so leaving claimed_at behind
                # would make the re-dated plan permanently unclaimable until its
                # new window elapsed and it was marked MISSED.
                existing.claimed_at = None
                existing.claimed_by = None
                existing.claim_token = None
                existing.claim_expires_at = None
                return plan_id
            if existing.status in {*_TERMINAL_CHECKPOINT_STATUSES, "FAILED"}:
                return plan_id
            if normalize_repo_time(existing.scheduled_at) != normalize_repo_time(
                _dt(payload["scheduled_at"])
            ):
                raise MatchdayRepositoryError("CHECKPOINT_PLAN_CONFLICT")
            if existing.status == "MISSED" and incoming_status == "CAPTURED":
                raise MatchdayRepositoryError("MISSED_CHECKPOINT_IMMUTABLE")
            existing.status = _transition_status(existing.status, incoming_status)
            existing.missed_at = (
                _dt(payload["missed_at"]) if payload.get("missed_at") else existing.missed_at
            )
            existing.capture_id = (
                str(payload.get("capture_id") or existing.capture_id or "") or None
            )
            existing.current_unscheduled_capture_id = (
                str(
                    payload.get("current_unscheduled_capture_id")
                    or existing.current_unscheduled_capture_id
                    or ""
                )
                or None
            )
            existing.endpoints = list(payload.get("endpoints") or existing.endpoints or [])
            existing.blockers = list(payload.get("blockers") or existing.blockers or [])
            existing.plan_hash = str(payload.get("plan_hash") or existing.plan_hash)
        else:
            session.add(
                MatchdayCheckpointPlanModel(
                    plan_id=plan_id,
                    fixture_id=str(payload["fixture_id"]),
                    competition_id=str(payload["competition_id"]),
                    season=str(payload["season"]),
                    policy_version=str(payload["policy_version"]),
                    checkpoint=str(payload["checkpoint"]),
                    kickoff_utc=_dt(payload["kickoff_utc"]),
                    scheduled_at=_dt(payload["scheduled_at"]),
                    window_start=_dt(payload["window_start"]),
                    window_end=_dt(payload["window_end"]),
                    endpoints=list(payload.get("endpoints") or []),
                    status=incoming_status,
                    missed_at=_dt(payload["missed_at"]) if payload.get("missed_at") else None,
                    capture_id=str(payload.get("capture_id") or "") or None,
                    current_unscheduled_capture_id=str(
                        payload.get("current_unscheduled_capture_id") or ""
                    )
                    or None,
                    blockers=list(payload.get("blockers") or []),
                    plan_hash=str(payload["plan_hash"]),
                )
            )
        session.flush()
        return plan_id

    def transition_checkpoint(
        self,
        *,
        fixture_id: str,
        competition_id: str,
        season: str,
        checkpoint: str,
        policy_version: str,
        status: str,
        capture_id: str | None = None,
        now: datetime | None = None,
        claim_token: str | None = None,
    ) -> None:
        plan_id = stable_hash(
            ":".join([fixture_id, competition_id, season, checkpoint, policy_version])
        )
        with Session(self.engine) as session:
            row = session.get(MatchdayCheckpointPlanModel, plan_id)
            if row is None:
                raise MatchdayRepositoryError("CHECKPOINT_PLAN_NOT_FOUND")
            current = normalize_repo_time(now or datetime.now(UTC))
            if claim_token is not None:
                if row.claim_token != claim_token:
                    raise MatchdayRepositoryError("CHECKPOINT_CLAIM_TOKEN_MISMATCH")
                claim_expired = (
                    row.claim_expires_at is None
                    or normalize_repo_time(row.claim_expires_at) < current
                )
                if claim_expired:
                    raise MatchdayRepositoryError("CHECKPOINT_CLAIM_EXPIRED")
            if row.status == "MISSED" and status == "CAPTURED":
                raise MatchdayRepositoryError("MISSED_CHECKPOINT_IMMUTABLE")
            row.status = _transition_status(row.status, status)
            row.capture_id = capture_id or row.capture_id
            if status == "MISSED":
                row.missed_at = current
            if status in _TERMINAL_CHECKPOINT_STATUSES or status == "FAILED":
                row.claimed_at = None
                row.claimed_by = None
                row.claim_token = None
                row.claim_expires_at = None
            session.commit()

    def due_checkpoint_plans(self, *, now: datetime, limit: int = 100) -> list[dict[str, Any]]:
        current = normalize_repo_time(now)
        with Session(self.engine) as session:
            self._advance_checkpoint_windows(session, now=current)
            rows = list(
                session.scalars(
                    select(MatchdayCheckpointPlanModel)
                    .where(
                        MatchdayCheckpointPlanModel.status == "DUE",
                        MatchdayCheckpointPlanModel.window_start <= current,
                        MatchdayCheckpointPlanModel.window_end >= current,
                        MatchdayCheckpointPlanModel.claimed_at.is_(None),
                    )
                    .order_by(
                        _checkpoint_priority(),
                        MatchdayCheckpointPlanModel.scheduled_at,
                        MatchdayCheckpointPlanModel.kickoff_utc,
                        MatchdayCheckpointPlanModel.fixture_id,
                        MatchdayCheckpointPlanModel.checkpoint,
                    )
                    .limit(limit)
                )
            )
            result = [self._plan_dict(row) for row in rows]
            session.commit()
        return result

    def due_checkpoint_competition_ids(
        self,
        *,
        now: datetime,
        competition_ids: Sequence[str],
    ) -> list[str]:
        if not competition_ids:
            return []
        current = normalize_repo_time(now)
        with Session(self.engine) as session:
            self._advance_checkpoint_windows(session, now=current)
            rows = session.execute(
                select(MatchdayCheckpointPlanModel.competition_id)
                .where(
                    MatchdayCheckpointPlanModel.competition_id.in_(competition_ids),
                    MatchdayCheckpointPlanModel.status == "DUE",
                    MatchdayCheckpointPlanModel.window_start <= current,
                    MatchdayCheckpointPlanModel.window_end >= current,
                    MatchdayCheckpointPlanModel.claimed_at.is_(None),
                )
                .order_by(
                    _checkpoint_priority(),
                    MatchdayCheckpointPlanModel.scheduled_at,
                    MatchdayCheckpointPlanModel.kickoff_utc,
                    MatchdayCheckpointPlanModel.fixture_id,
                )
            ).scalars()
            result = list(dict.fromkeys(str(item) for item in rows))
            session.commit()
        return result

    def claim_due_checkpoint_plans(
        self,
        *,
        now: datetime,
        worker_id: str,
        plan_ids: set[str] | None = None,
        limit: int = 100,
        lease_seconds: int = 900,
    ) -> list[dict[str, Any]]:
        if plan_ids is not None and not plan_ids:
            return []
        current = normalize_repo_time(now)
        expires_at = current + timedelta(seconds=lease_seconds)
        with Session(self.engine) as session:
            self._advance_checkpoint_windows(session, now=current)
            query = (
                select(MatchdayCheckpointPlanModel)
                .where(
                    MatchdayCheckpointPlanModel.status == "DUE",
                    MatchdayCheckpointPlanModel.window_start <= current,
                    MatchdayCheckpointPlanModel.window_end >= current,
                    MatchdayCheckpointPlanModel.claimed_at.is_(None),
                    MatchdayCheckpointPlanModel.claim_token.is_(None),
                )
                .order_by(
                    _checkpoint_priority(),
                    MatchdayCheckpointPlanModel.scheduled_at,
                    MatchdayCheckpointPlanModel.kickoff_utc,
                    MatchdayCheckpointPlanModel.fixture_id,
                    MatchdayCheckpointPlanModel.checkpoint,
                )
                .limit(limit)
            )
            if plan_ids is not None:
                query = query.where(MatchdayCheckpointPlanModel.plan_id.in_(plan_ids))
            if self.engine.dialect.name == "postgresql":
                query = query.with_for_update(skip_locked=True)
            rows = list(session.scalars(query))
            for row in rows:
                row.claimed_at = current
                row.claimed_by = worker_id
                row.claim_token = stable_hash(
                    {
                        "plan_id": row.plan_id,
                        "worker_id": worker_id,
                        "claimed_at": _iso(current),
                        "attempt_count": int(row.attempt_count or 0) + 1,
                    }
                )
                row.claim_expires_at = expires_at
                row.attempt_count = int(row.attempt_count or 0) + 1
            result = [self._plan_dict(row) for row in rows]
            session.commit()
        return result

    def release_checkpoint_claim(
        self,
        *,
        plan_id: str,
        claim_token: str,
        reason: str,
        restore_attempt: bool = False,
    ) -> bool:
        with Session(self.engine) as session:
            row = session.get(MatchdayCheckpointPlanModel, plan_id)
            if row is None:
                raise MatchdayRepositoryError("CHECKPOINT_PLAN_NOT_FOUND")
            if row.claim_token != claim_token:
                return False
            if row.status != "DUE":
                return False
            if restore_attempt:
                row.attempt_count = max(int(row.attempt_count or 0) - 1, 0)
            row.claimed_at = None
            row.claimed_by = None
            row.claim_token = None
            row.claim_expires_at = None
            row.blockers = sorted({*list(row.blockers or []), reason})
            session.commit()
        return True

    def validate_checkpoint_claim(
        self,
        *,
        plan_id: str,
        claim_token: str,
        now: datetime,
        fixture_id: str | None = None,
        competition_id: str | None = None,
        season: str | None = None,
    ) -> dict[str, Any]:
        current = normalize_repo_time(now)
        with Session(self.engine) as session:
            self._advance_checkpoint_windows(session, now=current)
            row = session.get(MatchdayCheckpointPlanModel, plan_id)
            if row is None:
                raise MatchdayRepositoryError("CHECKPOINT_PLAN_NOT_FOUND")
            if row.status != "DUE":
                raise MatchdayRepositoryError(f"CHECKPOINT_PLAN_NOT_DUE:{row.status}")
            if row.claim_token != claim_token:
                raise MatchdayRepositoryError("CHECKPOINT_CLAIM_TOKEN_MISMATCH")
            if row.claim_expires_at is None or normalize_repo_time(row.claim_expires_at) < current:
                raise MatchdayRepositoryError("CHECKPOINT_CLAIM_EXPIRED")
            if fixture_id is not None and row.fixture_id != fixture_id:
                raise MatchdayRepositoryError("CHECKPOINT_FIXTURE_MISMATCH")
            if competition_id is not None and row.competition_id != competition_id:
                raise MatchdayRepositoryError("CHECKPOINT_COMPETITION_MISMATCH")
            if season is not None and row.season != season:
                raise MatchdayRepositoryError("CHECKPOINT_SEASON_MISMATCH")
            result = self._plan_dict(row)
            session.commit()
        return result

    def link_endpoint_capture_plans(
        self,
        *,
        capture_id: str,
        plan_ids: Sequence[str],
        endpoint: str,
        linked_at: datetime,
    ) -> list[dict[str, Any]]:
        current = normalize_repo_time(linked_at)
        links: list[dict[str, Any]] = []
        with Session(self.engine) as session:
            capture = session.get(MatchdayEndpointCaptureModel, capture_id)
            if capture is None:
                raise MatchdayRepositoryError("ENDPOINT_CAPTURE_NOT_FOUND")
            for plan_id in plan_ids:
                plan = session.get(MatchdayCheckpointPlanModel, plan_id)
                if plan is None:
                    raise MatchdayRepositoryError("CHECKPOINT_PLAN_NOT_FOUND")
                if capture.fixture_id and plan.fixture_id != capture.fixture_id:
                    raise MatchdayRepositoryError("CAPTURE_PLAN_FIXTURE_MISMATCH")
                if capture.competition_id and plan.competition_id != capture.competition_id:
                    raise MatchdayRepositoryError("CAPTURE_PLAN_COMPETITION_MISMATCH")
                if endpoint not in set(plan.endpoints or []):
                    raise MatchdayRepositoryError("CAPTURE_PLAN_ENDPOINT_MISMATCH")
                if not (
                    normalize_repo_time(plan.window_start)
                    <= current
                    <= normalize_repo_time(plan.window_end)
                ):
                    raise MatchdayRepositoryError("CAPTURE_PLAN_WINDOW_MISMATCH")
                link_hash = stable_hash(
                    {
                        "capture_id": capture_id,
                        "plan_id": plan_id,
                        "endpoint": endpoint,
                    }
                )
                payload = {
                    "link_hash": link_hash,
                    "capture_id": capture_id,
                    "plan_id": plan_id,
                    "endpoint": endpoint,
                    "link_status": "LINKED",
                    "linked_at": _iso(current),
                }
                try:
                    with session.begin_nested():
                        session.add(
                            MatchdayEndpointCapturePlanModel(
                                link_hash=link_hash,
                                capture_id=capture_id,
                                plan_id=plan_id,
                                endpoint=endpoint,
                                link_status="LINKED",
                                linked_at=current,
                            )
                        )
                        session.flush()
                except IntegrityError:
                    existing = session.get(MatchdayEndpointCapturePlanModel, link_hash)
                    if existing is None:
                        raise MatchdayRepositoryError("CAPTURE_PLAN_LINK_CONFLICT") from None
                links.append(payload)
            session.commit()
        return links

    def insert_endpoint_capture(self, capture: Mapping[str, Any]) -> str:
        with Session(self.engine) as session:
            model = MatchdayEndpointCaptureModel(
                capture_id=str(capture["capture_id"]),
                fixture_id=str(capture.get("fixture_id") or "") or None,
                competition_id=str(capture.get("competition_id") or "") or None,
                checkpoint=str(capture.get("checkpoint") or "") or None,
                endpoint=str(capture["endpoint"]),
                sanitized_params=dict(capture["sanitized_params"]),
                params_hash=str(capture["params_hash"]),
                request_task_key=str(capture["request_task_key"]),
                attempt=int(capture.get("attempt") or 1),
                requested_at=_dt(capture["requested_at"]),
                provider_captured_at=_dt(capture["provider_captured_at"]),
                status_code=int(capture["status_code"]),
                elapsed_ms=int(capture["elapsed_ms"]),
                response_count=int(capture["response_count"]),
                quota_values=dict(capture["quota_values"]),
                raw_payload_sha256=str(capture["raw_payload_sha256"]),
                provider_event_time=capture.get("provider_event_time"),
                capture_status=str(capture["capture_status"]),
                error_code=capture.get("error_code"),
            )
            try:
                session.add(model)
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.get(MatchdayEndpointCaptureModel, str(capture["capture_id"]))
                normalized_capture = _normalized_capture_payload(capture)
                if existing is not None and _capture_payload(existing) == normalized_capture:
                    return str(capture["capture_id"])
                raise MatchdayRepositoryError("CAPTURE_IDENTITY_CONFLICT") from None
        return str(capture["capture_id"])

    def latest_endpoint_capture(
        self,
        *,
        request_task_key: str,
        since: datetime,
    ) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            row = session.execute(
                select(MatchdayEndpointCaptureModel, RawPayloadModel)
                .join(
                    RawPayloadModel,
                    RawPayloadModel.sha256 == MatchdayEndpointCaptureModel.raw_payload_sha256,
                )
                .where(
                    MatchdayEndpointCaptureModel.request_task_key == request_task_key,
                    MatchdayEndpointCaptureModel.provider_captured_at
                    >= normalize_repo_time(since),
                    MatchdayEndpointCaptureModel.capture_status.in_(
                        ("CAPTURED", "PROVIDER_EMPTY")
                    ),
                )
                .order_by(MatchdayEndpointCaptureModel.provider_captured_at.desc())
                .limit(1)
            ).first()
        if row is None:
            return None
        capture, raw_payload = row
        return {
            "capture": _capture_payload(capture),
            "payload": dict(raw_payload.payload),
        }

    def insert_market_observations(self, observations: Sequence[Mapping[str, Any]]) -> int:
        count = 0
        with Session(self.engine) as session:
            for row in observations:
                try:
                    with session.begin_nested():
                        session.add(self._observation_model(row))
                        session.flush()
                    count += 1
                except IntegrityError:
                    existing = session.get(
                        MatchdayMarketObservationModel,
                        str(row["observation_id"]),
                    )
                    if existing is not None and _observation_payload(
                        existing,
                    ) == _normalized_observation_payload(row):
                        continue
                    # Observation identity deliberately excludes the release
                    # revision. Replaying the identical provider capture after
                    # a deployment must be idempotent, while the first stored
                    # row retains the provenance of the release that ingested
                    # it. Any business-field change still fails closed.
                    if existing is not None and _observation_identity_payload(
                        _observation_payload(existing)
                    ) == _observation_identity_payload(_normalized_observation_payload(row)):
                        continue
                    raise MatchdayRepositoryError("OBSERVATION_IDENTITY_CONFLICT") from None
            session.commit()
        return count

    def insert_fixture_identities(self, fixtures: Sequence[Mapping[str, Any]]) -> int:
        persisted_count, _changed_fixture_ids = (
            self.upsert_fixture_identities_with_business_changes(fixtures)
        )
        return persisted_count

    def upsert_fixture_identities_with_business_changes(
        self,
        fixtures: Sequence[Mapping[str, Any]],
    ) -> tuple[int, list[str]]:
        count = 0
        changed_fixture_ids: list[str] = []
        with Session(self.engine) as session:
            for row in fixtures:
                normalized = _normalized_fixture_identity_payload(row)
                try:
                    with session.begin_nested():
                        session.add(self._fixture_identity_model(row))
                        session.flush()
                    count += 1
                    changed_fixture_ids.append(str(row["fixture_id"]))
                except IntegrityError:
                    existing = session.get(
                        MatchdayFixtureIdentityModel,
                        str(row["fixture_id"]),
                    )
                    if existing is not None:
                        before = _fixture_projection_business_hash(
                            _fixture_identity_payload(existing)
                        )
                        if _upsert_fixture_identity(existing, normalized):
                            count += 1
                        after = _fixture_projection_business_hash(
                            _fixture_identity_payload(existing)
                        )
                        if before != after:
                            changed_fixture_ids.append(existing.fixture_id)
                        continue
                    provider_existing = session.scalar(
                        select(MatchdayFixtureIdentityModel).where(
                            MatchdayFixtureIdentityModel.provider == str(row["provider"]),
                            MatchdayFixtureIdentityModel.provider_fixture_id
                            == str(row["provider_fixture_id"]),
                        )
                    )
                    if provider_existing is not None:
                        before = _fixture_projection_business_hash(
                            _fixture_identity_payload(provider_existing)
                        )
                        if _upsert_fixture_identity(provider_existing, normalized):
                            count += 1
                        after = _fixture_projection_business_hash(
                            _fixture_identity_payload(provider_existing)
                        )
                        if before != after:
                            changed_fixture_ids.append(provider_existing.fixture_id)
                        continue
                    raise MatchdayRepositoryError("FIXTURE_IDENTITY_CONFLICT") from None
            session.commit()
        return count, list(dict.fromkeys(changed_fixture_ids))

    def insert_manifest(self, manifest: Mapping[str, Any]) -> str:
        manifest_hash = validate_manifest_identity(manifest)
        fixture_id = str(manifest["fixture_identity"]["fixture_id"])
        as_of = _dt(manifest["as_of"])
        natural_key_hash = stable_hash(
            {
                "fixture_id": fixture_id,
                "as_of": _iso(as_of),
                "schema_version": manifest.get("schema_version"),
            }
        )
        with Session(self.engine) as session:
            existing = list(
                session.scalars(
                    select(MatchdayEvidenceManifestModel).where(
                        MatchdayEvidenceManifestModel.fixture_id == fixture_id,
                        MatchdayEvidenceManifestModel.as_of == as_of,
                    )
                )
            )
            if any(row.manifest_hash != manifest_hash for row in existing):
                raise MatchdayRepositoryError("MANIFEST_IDENTITY_CONFLICT")
            if existing:
                return existing[0].manifest_id
            decision = dict(manifest.get("decision") or {})
            reason = decision.get("reason")
            reason_code = (
                str(reason.get("code") or "UNKNOWN")
                if isinstance(reason, Mapping)
                else str(reason or decision.get("reason_code") or "UNKNOWN")
            )
            session.add(
                MatchdayEvidenceManifestModel(
                    manifest_id=manifest_hash,
                    fixture_id=fixture_id,
                    competition_id=str(manifest["fixture_identity"]["competition_id"]),
                    as_of=as_of,
                    outcome=str(decision.get("outcome") or "SYSTEM_DEGRADED"),
                    reason_code=reason_code,
                    manifest_hash=manifest_hash,
                    input_manifest_hash=str(manifest["input_manifest_hash"]),
                    decision_hash=str(decision.get("decision_hash") or "") or None,
                    manifest_integrity_status=str(_manifest_integrity_status(manifest)),
                    natural_key_hash=natural_key_hash,
                    payload=dict(manifest),
                )
            )
            session.commit()
        return manifest_hash

    def latest_manifest(self, fixture_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            row = session.scalar(
                select(MatchdayEvidenceManifestModel)
                .where(MatchdayEvidenceManifestModel.fixture_id == fixture_id)
                .order_by(MatchdayEvidenceManifestModel.as_of.desc())
                .limit(1)
            )
        return dict(row.payload) if row is not None else None

    def manifests_for_fixture(self, fixture_id: str) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(MatchdayEvidenceManifestModel)
                    .where(MatchdayEvidenceManifestModel.fixture_id == fixture_id)
                    .order_by(MatchdayEvidenceManifestModel.as_of)
                )
            )
        return [dict(row.payload) for row in rows]

    def _observation_model(self, row: Mapping[str, Any]) -> MatchdayMarketObservationModel:
        return MatchdayMarketObservationModel(
            observation_id=str(row["observation_id"]),
            fixture_id=str(row["fixture_id"]),
            provider_fixture_id=str(row["provider_fixture_id"]),
            competition_id=str(row["competition_id"]),
            provider=str(row["provider"]),
            bookmaker_id=str(row["bookmaker_id"]),
            bookmaker_name=str(row["bookmaker_name"]),
            capture_id=str(row["capture_id"]),
            provider_bet_id=str(row["provider_bet_id"]),
            raw_market_label=str(row["raw_market_label"]),
            canonical_market=str(row["canonical_market"]),
            canonical_selection=str(row["canonical_selection"]),
            provider_selection=str(row["provider_selection"]),
            line=None if row.get("line") is None else str(row["line"]),
            decimal_odds=str(row["decimal_odds"]),
            suspended=bool(row["suspended"]),
            live=bool(row["live"]),
            provider_updated_at=str(row["provider_updated_at"]),
            captured_at=_dt(row["captured_at"]),
            ingested_at=_dt(row["ingested_at"]),
            raw_payload_sha256=str(row["raw_payload_sha256"]),
            source_revision=str(row["source_revision"]),
        )

    def _fixture_identity_model(self, row: Mapping[str, Any]) -> MatchdayFixtureIdentityModel:
        normalized = _normalized_fixture_identity_payload(row)
        return MatchdayFixtureIdentityModel(
            fixture_id=str(row["fixture_id"]),
            provider=str(row["provider"]),
            provider_fixture_id=str(row["provider_fixture_id"]),
            competition_id=str(row["competition_id"]),
            provider_league_id=str(row["provider_league_id"]),
            season=str(row["season"]),
            kickoff_utc=_dt(row["kickoff_utc"]),
            fixture_status=str(row["fixture_status"]),
            home_provider_team_id=str(row["home_provider_team_id"]),
            away_provider_team_id=str(row["away_provider_team_id"]),
            home_w2_team_id=str(row.get("home_w2_team_id") or "") or None,
            away_w2_team_id=str(row.get("away_w2_team_id") or "") or None,
            team_identity_status=str(row["team_identity_status"]),
            raw_payload_sha256=str(row["raw_payload_sha256"]),
            endpoint_capture_id=str(row.get("endpoint_capture_id") or "") or None,
            captured_at=_dt(row["captured_at"]),
            identity_hash=_fixture_identity_semantic_hash_from_payload(normalized),
            payload=dict(row["payload"]),
        )

    def _plan_dict(self, row: MatchdayCheckpointPlanModel) -> dict[str, Any]:
        return {
            "id": row.plan_id,
            "fixture_id": row.fixture_id,
            "competition_id": row.competition_id,
            "season": row.season,
            "policy_version": row.policy_version,
            "checkpoint": row.checkpoint,
            "kickoff_utc": _iso(row.kickoff_utc),
            "due_at": _iso(row.scheduled_at),
            "scheduled_at": _iso(row.scheduled_at),
            "endpoints": list(row.endpoints or []),
            "source": "matchday_intake.v2",
            "status": row.status,
            "window_start": _iso(row.window_start),
            "window_end": _iso(row.window_end),
            "claimed_at": _iso(row.claimed_at) if row.claimed_at else None,
            "claimed_by": row.claimed_by,
            "claim_token": row.claim_token,
            "claim_expires_at": _iso(row.claim_expires_at) if row.claim_expires_at else None,
            "attempt_count": int(row.attempt_count or 0),
            "test_only": bool(row.test_only),
            "namespace": row.namespace,
        }

    def _advance_checkpoint_windows(self, session: Session, *, now: datetime) -> None:
        rows = list(
            session.scalars(
                select(MatchdayCheckpointPlanModel).where(
                    MatchdayCheckpointPlanModel.status.in_(("PLANNED", "DUE"))
                )
            )
        )
        for row in rows:
            window_end = normalize_repo_time(row.window_end)
            window_start = normalize_repo_time(row.window_start)
            claim_expires = (
                normalize_repo_time(row.claim_expires_at) if row.claim_expires_at else None
            )
            if now > window_end:
                row.status = "MISSED"
                row.missed_at = row.missed_at or now
                missed_blocker = (
                    "RESULT_WINDOW_MISSED"
                    if row.checkpoint == "POSTMATCH_RESULT"
                    else "CHECKPOINT_MISSING"
                )
                row.blockers = sorted({*list(row.blockers or []), missed_blocker})
                row.claimed_at = None
                row.claimed_by = None
                row.claim_token = None
                row.claim_expires_at = None
                self._record_missed_opportunities_in_session(session, row=row, recorded_at=now)
            elif row.status == "DUE" and claim_expires is not None and claim_expires < now:
                row.claimed_at = None
                row.claimed_by = None
                row.claim_token = None
                row.claim_expires_at = None
            elif row.status == "PLANNED" and window_start <= now <= window_end:
                row.status = "DUE"

    def _record_missed_opportunities_in_session(
        self,
        session: Session,
        *,
        row: MatchdayCheckpointPlanModel,
        recorded_at: datetime,
    ) -> None:
        if "odds" not in set(row.endpoints or ()) or not is_evaluation_slot(row.checkpoint):
            return
        tracks = session.execute(
            select(
                ModelForecastCaptureModel.capture_identity_hash,
                ModelForecastCaptureModel.model_input_manifest_hash,
            )
            .where(
                ModelForecastCaptureModel.fixture_id.in_(
                    model_forecast_fixture_aliases(row.fixture_id)
                )
            )
            .order_by(ModelForecastCaptureModel.capture_identity_hash)
        )
        repository = DynamicPrematchRepository(self.engine)
        for capture_hash, model_input_hash in tracks:
            context = EvaluationOpportunityContext(
                model_forecast_capture_identity_hash=str(capture_hash),
                model_input_hash=str(model_input_hash),
                evaluation_policy_version=CURRENT_EVALUATION_POLICY,
                evaluation_slot_id=row.checkpoint,
                scheduled_checkpoint_at=normalize_repo_time(row.scheduled_at),
                checkpoint_plan_identity=row.plan_id,
                source_event_identity=f"checkpoint-missed:{row.plan_id}:{_iso(recorded_at)}",
            )
            for market in ("ASIAN_HANDICAP", "TOTALS"):
                repository.record_opportunity_without_attempt_in_session(
                    session,
                    fixture_id=row.fixture_id.removeprefix("api_football:"),
                    market=market,
                    context=context,
                    state=OpportunityState.MISSED_CHECKPOINT,
                    recorded_at=recorded_at,
                    blocker="CHECKPOINT_WINDOW_MISSED",
                )


# Statuses a moved kickoff may rewrite.  None of them recorded a provider
# interaction, so the row holds only a verdict about a window the fixture no
# longer has.  CAPTURED, PROVIDER_EMPTY, FAILED and CONFLICT are excluded: each
# describes something that actually happened against the old window.
_REDATABLE_CHECKPOINT_STATUSES = frozenset(
    {"PLANNED", "DUE", "MISSED", "SKIPPED_POLICY", "SKIPPED_BUDGET"}
)


def _is_redatable(session: Session, row: MatchdayCheckpointPlanModel) -> bool:
    """Whether a moved kickoff may rewrite this plan row.

    Status alone is not sufficient for FAILED.  A FAILED row may record either
    a plan that never reached the provider or one whose request was actually
    sent and errored; the second kind describes a real interaction with the old
    window and must stay pinned to it, exactly as CAPTURED and PROVIDER_EMPTY
    do.  The distinguishing evidence is a capture on the row or a link row
    joining it to an endpoint capture.
    """

    if row.status in _REDATABLE_CHECKPOINT_STATUSES:
        return True
    if row.status != "FAILED":
        return False
    if row.capture_id or row.current_unscheduled_capture_id:
        return False
    linked = session.scalar(
        select(MatchdayEndpointCapturePlanModel.link_hash)
        .where(MatchdayEndpointCapturePlanModel.plan_id == row.plan_id)
        .limit(1)
    )
    return linked is None


def _reschedule_audit_row(
    row: MatchdayCheckpointPlanModel,
    *,
    payload: Mapping[str, Any],
    new_status: str,
    recorded_at: datetime,
) -> MatchdayCheckpointPlanRescheduleModel:
    """Capture the window a re-date is about to overwrite.

    The re-date writes the new kickoff, window, status, blockers and missed_at
    over the same row, and no other table records what the plan looked like
    before: endpoint captures and the checkpoint audit describe attempts, not
    the plan they were scheduled against.  attempt_count is carried forward
    rather than reset -- plan_id spans windows by design, so the count is the
    plan identity's history, not this window's -- and is recorded here so the
    accumulated value stays interpretable.
    """

    previous_kickoff = normalize_repo_time(row.kickoff_utc)
    return MatchdayCheckpointPlanRescheduleModel(
        reschedule_id=stable_hash(
            ":".join([row.plan_id, _iso(previous_kickoff), _iso(recorded_at)])
        ),
        plan_id=row.plan_id,
        fixture_id=row.fixture_id,
        checkpoint=row.checkpoint,
        recorded_at=recorded_at,
        previous_status=row.status,
        previous_kickoff_utc=previous_kickoff,
        previous_scheduled_at=normalize_repo_time(row.scheduled_at),
        previous_window_start=normalize_repo_time(row.window_start),
        previous_window_end=normalize_repo_time(row.window_end),
        previous_attempt_count=int(row.attempt_count or 0),
        previous_blockers=list(row.blockers or []),
        previous_missed_at=normalize_repo_time(row.missed_at) if row.missed_at else None,
        new_status=new_status,
        new_kickoff_utc=_dt(payload["kickoff_utc"]),
        new_scheduled_at=_dt(payload["scheduled_at"]),
        new_window_start=_dt(payload["window_start"]),
        new_window_end=_dt(payload["window_end"]),
    )


def _transition_status(current: str, incoming: str) -> str:
    if current == incoming:
        return current
    if incoming == "CONFLICT":
        return incoming
    allowed = {
        "PLANNED": {"DUE", "MISSED", "SKIPPED_POLICY", "SKIPPED_BUDGET", "CONFLICT"},
        "DUE": {
            "CAPTURED",
            "PROVIDER_EMPTY",
            "FAILED",
            "MISSED",
            "SKIPPED_POLICY",
            "SKIPPED_BUDGET",
            "CONFLICT",
        },
        "CAPTURED": {"CONFLICT"},
        "PROVIDER_EMPTY": {"CONFLICT"},
        "FAILED": {"DUE", "CONFLICT"},
        "MISSED": {"CONFLICT"},
        "SKIPPED_POLICY": {"CONFLICT"},
        "SKIPPED_BUDGET": {"CONFLICT"},
        "CONFLICT": set(),
    }
    if incoming in allowed.get(current, set()):
        return incoming
    raise MatchdayRepositoryError(f"CHECKPOINT_STATUS_TRANSITION_INVALID:{current}->{incoming}")


_TERMINAL_CHECKPOINT_STATUSES = frozenset(
    {
        "CAPTURED",
        "PROVIDER_EMPTY",
        "MISSED",
        "SKIPPED_POLICY",
        "SKIPPED_BUDGET",
        "CONFLICT",
    }
)


def normalize_repo_time(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _capture_payload(row: MatchdayEndpointCaptureModel) -> dict[str, Any]:
    return {
        "capture_id": row.capture_id,
        "fixture_id": row.fixture_id,
        "competition_id": row.competition_id,
        "checkpoint": row.checkpoint,
        "endpoint": row.endpoint,
        "sanitized_params": dict(row.sanitized_params),
        "params_hash": row.params_hash,
        "request_task_key": row.request_task_key,
        "attempt": int(row.attempt or 1),
        "requested_at": _iso(row.requested_at),
        "provider_captured_at": _iso(row.provider_captured_at),
        "status_code": int(row.status_code),
        "elapsed_ms": int(row.elapsed_ms),
        "response_count": int(row.response_count),
        "quota_values": dict(row.quota_values),
        "raw_payload_sha256": row.raw_payload_sha256,
        "provider_event_time": row.provider_event_time,
        "capture_status": row.capture_status,
        "error_code": row.error_code,
        "schema_version": "MatchdayEndpointCaptureV1",
    }


def _normalized_capture_payload(capture: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "capture_id": str(capture["capture_id"]),
        "fixture_id": str(capture.get("fixture_id") or "") or None,
        "competition_id": str(capture.get("competition_id") or "") or None,
        "checkpoint": str(capture.get("checkpoint") or "") or None,
        "endpoint": str(capture["endpoint"]),
        "sanitized_params": dict(capture["sanitized_params"]),
        "params_hash": str(capture["params_hash"]),
        "request_task_key": str(capture["request_task_key"]),
        "attempt": int(capture.get("attempt") or 1),
        "requested_at": _iso(_dt(capture["requested_at"])),
        "provider_captured_at": _iso(_dt(capture["provider_captured_at"])),
        "status_code": int(capture["status_code"]),
        "elapsed_ms": int(capture["elapsed_ms"]),
        "response_count": int(capture["response_count"]),
        "quota_values": dict(capture["quota_values"]),
        "raw_payload_sha256": str(capture["raw_payload_sha256"]),
        "provider_event_time": capture.get("provider_event_time"),
        "capture_status": str(capture["capture_status"]),
        "error_code": capture.get("error_code"),
        "schema_version": "MatchdayEndpointCaptureV1",
    }


def _observation_payload(row: MatchdayMarketObservationModel) -> dict[str, Any]:
    return {
        "observation_id": row.observation_id,
        "fixture_id": row.fixture_id,
        "provider_fixture_id": row.provider_fixture_id,
        "competition_id": row.competition_id,
        "provider": row.provider,
        "bookmaker_id": row.bookmaker_id,
        "bookmaker_name": row.bookmaker_name,
        "capture_id": row.capture_id,
        "provider_bet_id": row.provider_bet_id,
        "raw_market_label": row.raw_market_label,
        "canonical_market": row.canonical_market,
        "canonical_selection": row.canonical_selection,
        "provider_selection": row.provider_selection,
        "line": row.line,
        "decimal_odds": row.decimal_odds,
        "suspended": bool(row.suspended),
        "live": bool(row.live),
        "provider_updated_at": row.provider_updated_at,
        "captured_at": _iso(row.captured_at),
        "ingested_at": _iso(row.ingested_at),
        "raw_payload_sha256": row.raw_payload_sha256,
        "source_revision": row.source_revision,
    }


def _normalized_observation_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "observation_id": str(row["observation_id"]),
        "fixture_id": str(row["fixture_id"]),
        "provider_fixture_id": str(row["provider_fixture_id"]),
        "competition_id": str(row["competition_id"]),
        "provider": str(row["provider"]),
        "bookmaker_id": str(row["bookmaker_id"]),
        "bookmaker_name": str(row["bookmaker_name"]),
        "capture_id": str(row["capture_id"]),
        "provider_bet_id": str(row["provider_bet_id"]),
        "raw_market_label": str(row["raw_market_label"]),
        "canonical_market": str(row["canonical_market"]),
        "canonical_selection": str(row["canonical_selection"]),
        "provider_selection": str(row["provider_selection"]),
        "line": None if row.get("line") is None else str(row["line"]),
        "decimal_odds": str(row["decimal_odds"]),
        "suspended": bool(row["suspended"]),
        "live": bool(row["live"]),
        "provider_updated_at": str(row["provider_updated_at"]),
        "captured_at": _iso(_dt(row["captured_at"])),
        "ingested_at": _iso(_dt(row["ingested_at"])),
        "raw_payload_sha256": str(row["raw_payload_sha256"]),
        "source_revision": str(row["source_revision"]),
    }


def _observation_identity_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    """Stable provider-observation identity, independent of code release."""
    return {
        key: value for key, value in row.items() if key not in {"source_revision", "ingested_at"}
    }


def _fixture_identity_payload(row: MatchdayFixtureIdentityModel) -> dict[str, Any]:
    return {
        "fixture_id": row.fixture_id,
        "provider": row.provider,
        "provider_fixture_id": row.provider_fixture_id,
        "competition_id": row.competition_id,
        "provider_league_id": row.provider_league_id,
        "season": row.season,
        "kickoff_utc": _iso(row.kickoff_utc),
        "fixture_status": row.fixture_status,
        "home_provider_team_id": row.home_provider_team_id,
        "away_provider_team_id": row.away_provider_team_id,
        "home_w2_team_id": row.home_w2_team_id,
        "away_w2_team_id": row.away_w2_team_id,
        "team_identity_status": row.team_identity_status,
        "raw_payload_sha256": row.raw_payload_sha256,
        "endpoint_capture_id": row.endpoint_capture_id,
        "captured_at": _iso(row.captured_at),
        "identity_hash": row.identity_hash,
        "payload": dict(row.payload),
        "schema_version": "MatchdayFixtureIdentityV1",
    }


def _normalized_fixture_identity_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fixture_id": str(row["fixture_id"]),
        "provider": str(row["provider"]),
        "provider_fixture_id": str(row["provider_fixture_id"]),
        "competition_id": str(row["competition_id"]),
        "provider_league_id": str(row["provider_league_id"]),
        "season": str(row["season"]),
        "kickoff_utc": _iso(_dt(row["kickoff_utc"])),
        "fixture_status": str(row["fixture_status"]),
        "home_provider_team_id": str(row["home_provider_team_id"]),
        "away_provider_team_id": str(row["away_provider_team_id"]),
        "home_w2_team_id": str(row.get("home_w2_team_id") or "") or None,
        "away_w2_team_id": str(row.get("away_w2_team_id") or "") or None,
        "team_identity_status": str(row["team_identity_status"]),
        "raw_payload_sha256": str(row["raw_payload_sha256"]),
        "endpoint_capture_id": str(row.get("endpoint_capture_id") or "") or None,
        "captured_at": _iso(_dt(row["captured_at"])),
        "identity_hash": str(row["identity_hash"]),
        "payload": dict(row["payload"]),
        "schema_version": "MatchdayFixtureIdentityV1",
    }


_FIXTURE_IDENTITY_STABLE_FIELDS = (
    "provider",
    "provider_fixture_id",
    "competition_id",
    "provider_league_id",
    "season",
    "home_provider_team_id",
    "away_provider_team_id",
)

_FIXTURE_IDENTITY_MUTABLE_FIELDS = (
    "kickoff_utc",
    "fixture_status",
    "raw_payload_sha256",
    "endpoint_capture_id",
    "captured_at",
    "payload",
)

_TEAM_IDENTITY_STATUS_RANK = {
    "REVIEW_REQUIRED": 0,
    "PARTIAL": 1,
    "READY": 2,
    "PROVIDER_PRIMARY_READY": 3,
}


def _upsert_fixture_identity(
    existing: MatchdayFixtureIdentityModel,
    incoming: Mapping[str, Any],
) -> bool:
    current = _fixture_identity_payload(existing)
    for field in _FIXTURE_IDENTITY_STABLE_FIELDS:
        if current[field] != incoming[field]:
            raise MatchdayRepositoryError("FIXTURE_IDENTITY_CONFLICT")
    changed = False
    current_captured_at = _dt(current["captured_at"])
    incoming_captured_at = _dt(incoming["captured_at"])
    if incoming_captured_at > current_captured_at:
        for field in _FIXTURE_IDENTITY_MUTABLE_FIELDS:
            if current[field] == incoming[field]:
                continue
            setattr(existing, field, _fixture_identity_model_value(field, incoming[field]))
            changed = True
    elif incoming_captured_at == current_captured_at:
        for field in _FIXTURE_IDENTITY_MUTABLE_FIELDS:
            if current[field] != incoming[field]:
                raise MatchdayRepositoryError("CAPTURE_PROVENANCE_CONFLICT")
    for field in ("home_w2_team_id", "away_w2_team_id"):
        incoming_value = incoming.get(field)
        current_value = getattr(existing, field)
        if current_value and incoming_value and current_value != incoming_value:
            raise MatchdayRepositoryError("FIXTURE_IDENTITY_CONFLICT")
        if not current_value and incoming_value:
            setattr(existing, field, str(incoming_value))
            changed = True
    incoming_status = str(incoming["team_identity_status"])
    current_status = str(existing.team_identity_status)
    if _team_identity_status_rank(incoming_status) > _team_identity_status_rank(current_status):
        existing.team_identity_status = incoming_status
        changed = True
    semantic_hash = _fixture_identity_semantic_hash(existing)
    if existing.identity_hash != semantic_hash:
        existing.identity_hash = semantic_hash
        changed = True
    return changed


def _fixture_identity_model_value(field: str, value: Any) -> Any:
    if field in {"captured_at", "kickoff_utc"}:
        return _dt(value)
    if field == "payload":
        return dict(value)
    if field == "endpoint_capture_id":
        return str(value or "") or None
    return str(value)


def _team_identity_status_rank(status: str) -> int:
    return _TEAM_IDENTITY_STATUS_RANK.get(status, -1)


def _fixture_identity_semantic_hash(row: MatchdayFixtureIdentityModel) -> str:
    return _fixture_identity_semantic_hash_from_payload(_fixture_identity_payload(row))


def _fixture_identity_semantic_hash_from_payload(row: Mapping[str, Any]) -> str:
    return stable_hash(
        {
            "schema_version": "MatchdayFixtureIdentitySemanticHashV1",
            "fixture_id": str(row["fixture_id"]),
            "provider": str(row["provider"]),
            "provider_fixture_id": str(row["provider_fixture_id"]),
            "competition_id": str(row["competition_id"]),
            "provider_league_id": str(row["provider_league_id"]),
            "season": str(row["season"]),
            "kickoff_utc": _iso(_dt(row["kickoff_utc"])),
            "fixture_status": str(row["fixture_status"]),
            "home_provider_team_id": str(row["home_provider_team_id"]),
            "away_provider_team_id": str(row["away_provider_team_id"]),
            "home_w2_team_id": str(row.get("home_w2_team_id") or "") or None,
            "away_w2_team_id": str(row.get("away_w2_team_id") or "") or None,
            "team_identity_status": str(row["team_identity_status"]),
        }
    )


def _fixture_projection_business_hash(row: Mapping[str, Any]) -> str:
    """Only fields that can change fixture projection semantics."""
    return stable_hash(
        {
            "fixture_id": str(row["fixture_id"]),
            "competition_id": str(row["competition_id"]),
            "season": str(row["season"]),
            "kickoff_utc": _iso(_dt(row["kickoff_utc"])),
            "fixture_status": str(row["fixture_status"]),
            "home_provider_team_id": str(row["home_provider_team_id"]),
            "away_provider_team_id": str(row["away_provider_team_id"]),
            "home_w2_team_id": str(row.get("home_w2_team_id") or "") or None,
            "away_w2_team_id": str(row.get("away_w2_team_id") or "") or None,
            "team_identity_status": str(row["team_identity_status"]),
        }
    )


def _manifest_integrity_status(manifest: Mapping[str, Any]) -> str:
    decision = manifest.get("decision")
    if isinstance(decision, Mapping) and decision.get("outcome") == "SYSTEM_DEGRADED":
        return "SYSTEM_DEGRADED"
    market = manifest.get("market_evidence")
    if isinstance(market, Mapping) and market.get("integrity_status") == "CONFLICT":
        return "SYSTEM_DEGRADED"
    return "PASS"
