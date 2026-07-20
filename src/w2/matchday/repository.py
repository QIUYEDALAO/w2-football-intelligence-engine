from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayEndpointCaptureModel,
    MatchdayEvidenceManifestModel,
    MatchdayMarketObservationModel,
)
from w2.matchday.intake_v2 import CheckpointPlan, parse_utc, stable_hash, validate_manifest_identity


class MatchdayRepositoryError(RuntimeError):
    pass


def _dt(value: Any) -> datetime:
    parsed = parse_utc(value)
    if parsed is None:
        raise MatchdayRepositoryError("INVALID_DATETIME")
    return parsed


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


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
        with Session(self.engine) as session:
            existing = session.get(MatchdayCheckpointPlanModel, plan_id)
            if existing is not None:
                if existing.scheduled_at != _dt(payload["scheduled_at"]):
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
            session.commit()
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
    ) -> None:
        plan_id = stable_hash(
            ":".join([fixture_id, competition_id, season, checkpoint, policy_version])
        )
        with Session(self.engine) as session:
            row = session.get(MatchdayCheckpointPlanModel, plan_id)
            if row is None:
                raise MatchdayRepositoryError("CHECKPOINT_PLAN_NOT_FOUND")
            if row.status == "MISSED" and status == "CAPTURED":
                raise MatchdayRepositoryError("MISSED_CHECKPOINT_IMMUTABLE")
            row.status = _transition_status(row.status, status)
            row.capture_id = capture_id or row.capture_id
            if status == "MISSED":
                row.missed_at = now or datetime.now(UTC)
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

    def claim_due_checkpoint_plans(
        self,
        *,
        now: datetime,
        worker_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        current = normalize_repo_time(now)
        with Session(self.engine) as session:
            self._advance_checkpoint_windows(session, now=current)
            query = (
                select(MatchdayCheckpointPlanModel)
                .where(
                    MatchdayCheckpointPlanModel.status == "DUE",
                    MatchdayCheckpointPlanModel.window_start <= current,
                    MatchdayCheckpointPlanModel.window_end >= current,
                    MatchdayCheckpointPlanModel.claimed_at.is_(None),
                )
                .order_by(
                    MatchdayCheckpointPlanModel.scheduled_at,
                    MatchdayCheckpointPlanModel.kickoff_utc,
                    MatchdayCheckpointPlanModel.fixture_id,
                    MatchdayCheckpointPlanModel.checkpoint,
                )
                .limit(limit)
            )
            if self.engine.dialect.name == "postgresql":
                query = query.with_for_update(skip_locked=True)
            rows = list(session.scalars(query))
            for row in rows:
                row.claimed_at = current
                row.claimed_by = worker_id
                row.attempt_count = int(row.attempt_count or 0) + 1
            result = [self._plan_dict(row) for row in rows]
            session.commit()
        return result

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
                if existing is not None and _capture_payload(existing) == dict(capture):
                    return str(capture["capture_id"])
                raise MatchdayRepositoryError("CAPTURE_IDENTITY_CONFLICT") from None
        return str(capture["capture_id"])

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
                    raise MatchdayRepositoryError("OBSERVATION_IDENTITY_CONFLICT") from None
            session.commit()
        return count

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
            session.add(
                MatchdayEvidenceManifestModel(
                    manifest_id=manifest_hash,
                    fixture_id=fixture_id,
                    competition_id=str(manifest["fixture_identity"]["competition_id"]),
                    as_of=as_of,
                    outcome=str(decision.get("outcome") or "SYSTEM_DEGRADED"),
                    reason_code=str(
                        decision.get("reason") or decision.get("reason_code") or "UNKNOWN"
                    ),
                    manifest_hash=manifest_hash,
                    input_manifest_hash=str(manifest["input_manifest_hash"]),
                    decision_hash=str(decision.get("decision_hash") or "") or None,
                    manifest_integrity_status=str(
                        _manifest_integrity_status(manifest)
                    ),
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

    def _plan_dict(self, row: MatchdayCheckpointPlanModel) -> dict[str, Any]:
        return {
            "id": row.plan_id,
            "fixture_id": row.fixture_id,
            "competition_id": row.competition_id,
            "season": row.season,
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
            if now > window_end:
                row.status = "MISSED"
                row.missed_at = row.missed_at or now
                row.blockers = sorted({*list(row.blockers or []), "CHECKPOINT_MISSING"})
                row.claimed_at = None
                row.claimed_by = None
            elif row.status == "PLANNED" and window_start <= now <= window_end:
                row.status = "DUE"


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


def _manifest_integrity_status(manifest: Mapping[str, Any]) -> str:
    decision = manifest.get("decision")
    if isinstance(decision, Mapping) and decision.get("outcome") == "SYSTEM_DEGRADED":
        return "SYSTEM_DEGRADED"
    market = manifest.get("market_evidence")
    if isinstance(market, Mapping) and market.get("integrity_status") == "CONFLICT":
        return "SYSTEM_DEGRADED"
    return "PASS"
