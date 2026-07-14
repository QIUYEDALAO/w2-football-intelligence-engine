from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy import Engine, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.config import Settings
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.forward_ops_models import ForwardResultEventModel
from w2.infrastructure.persistence.future_refresh_models import (
    FutureMarketObservationModel,
    FutureRefreshCheckpointAuditModel,
    FutureRefreshCheckpointPlanModel,
    FutureRefreshRunAuditModel,
    FutureRefreshTaskAuditModel,
    RawPayloadModel,
    TeamXgMatchModel,
    TeamXgRollingSnapshotModel,
)
from w2.infrastructure.persistence.ingestion_models import (
    ProviderRequestLogModel,
    QuotaUsageModel,
)
from w2.tracking.forward_result_source import normalized_finished_results


class FutureRefreshPersistenceError(RuntimeError):
    pass


def parse_db_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value:
        raise FutureRefreshPersistenceError("INVALID_DATETIME")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class DatabaseRawPayloadObjectStore:
    def __init__(self, session: Session) -> None:
        self.session = session

    def put(
        self,
        *,
        sha256: str,
        endpoint: str,
        captured_at: datetime,
        payload: dict[str, Any],
    ) -> str:
        storage_uri = f"db://raw_payload/{sha256}"
        self.session.add(
            RawPayloadModel(
                sha256=sha256,
                endpoint=endpoint,
                captured_at=captured_at,
                storage_uri=storage_uri,
                payload=payload,
            )
        )
        return storage_uri

    def get(self, sha256: str) -> dict[str, Any] | None:
        row = self.session.get(RawPayloadModel, sha256)
        return dict(row.payload) if row is not None else None


class FutureRefreshDbRepository:
    def __init__(self, *, engine: Engine | None = None, settings: Settings | None = None) -> None:
        self.engine = engine or create_engine(settings)

    def save_raw_payload(
        self,
        *,
        sha256: str,
        endpoint: str,
        captured_at: datetime,
        payload: dict[str, Any],
    ) -> str:
        with Session(self.engine) as session:
            store = DatabaseRawPayloadObjectStore(session)
            try:
                storage_uri = store.put(
                    sha256=sha256,
                    endpoint=endpoint,
                    captured_at=captured_at,
                    payload=payload,
                )
                session.commit()
                return storage_uri
            except IntegrityError:
                session.rollback()
                existing = session.get(RawPayloadModel, sha256)
                if existing is None:
                    raise FutureRefreshPersistenceError("RAW_PAYLOAD_CONFLICT") from None
                return existing.storage_uri
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("RAW_PAYLOAD_WRITE_FAILED") from exc

    def append_finished_result_events(
        self,
        *,
        payload: dict[str, Any],
        captured_at: datetime,
        raw_payload_hash: str,
        provider: str = "api_football",
    ) -> int:
        events = normalized_finished_results(
            payload,
            provider=provider,
            confirmed_at=captured_at,
            raw_payload_hash=raw_payload_hash,
        )
        appended = 0
        with Session(self.engine) as session:
            for event in events:
                session.add(ForwardResultEventModel(**event))
                try:
                    session.commit()
                    appended += 1
                except IntegrityError:
                    session.rollback()
                except Exception as exc:
                    session.rollback()
                    raise FutureRefreshPersistenceError("RESULT_EVENT_WRITE_FAILED") from exc
        return appended

    def persist_result_backfill_payload(
        self,
        *,
        payload: dict[str, Any],
        captured_at: datetime,
        provider: str = "api_football",
    ) -> dict[str, Any]:
        """Atomically freeze a result response and append its normalized events."""
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload_hash = sha256(canonical.encode("utf-8")).hexdigest()
        events = normalized_finished_results(
            payload,
            provider=provider,
            confirmed_at=captured_at,
            raw_payload_hash=payload_hash,
        )
        inserted = 0
        with Session(self.engine) as session:
            try:
                if session.get(RawPayloadModel, payload_hash) is None:
                    session.add(
                        RawPayloadModel(
                            sha256=payload_hash,
                            endpoint="fixtures",
                            captured_at=captured_at,
                            storage_uri=f"db://raw_payload/{payload_hash}",
                            payload=payload,
                        )
                    )
                for event in events:
                    exists = session.scalar(
                        select(ForwardResultEventModel.id).where(
                            ForwardResultEventModel.fixture_id == event["fixture_id"],
                            ForwardResultEventModel.provider == event["provider"],
                            ForwardResultEventModel.raw_payload_hash == payload_hash,
                        )
                    )
                    if exists is None:
                        session.add(ForwardResultEventModel(**event))
                        inserted += 1
                session.commit()
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("RESULT_BACKFILL_WRITE_FAILED") from exc
        return {"raw_payload_hash": payload_hash, "events_inserted": inserted}

    def result_events_for_fixture_ids(self, fixture_ids: list[str]) -> list[dict[str, Any]]:
        ids = [fixture_id for fixture_id in dict.fromkeys(fixture_ids) if fixture_id]
        if not ids:
            return []
        latest: dict[str, tuple[datetime, dict[str, Any]]] = {}
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(ForwardResultEventModel)
                    .where(ForwardResultEventModel.fixture_id.in_(ids))
                    .order_by(ForwardResultEventModel.confirmed_at)
                )
            )
            raw_rows = list(
                session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == "fixtures")
                    .order_by(RawPayloadModel.captured_at)
                )
            )
        for row in rows:
            latest[row.fixture_id] = (
                parse_db_datetime(row.confirmed_at),
                dict(row.result_payload),
            )
        wanted = set(ids)
        for raw in raw_rows:
            for event in normalized_finished_results(
                raw.payload,
                provider="api_football",
                confirmed_at=raw.captured_at,
                raw_payload_hash=raw.sha256,
            ):
                fixture_id = str(event["fixture_id"])
                if fixture_id not in wanted:
                    continue
                confirmed_at = parse_db_datetime(event["confirmed_at"])
                current = latest.get(fixture_id)
                if current is None or confirmed_at > current[0]:
                    latest[fixture_id] = (confirmed_at, dict(event["result_payload"]))
        return [latest[fixture_id][1] for fixture_id in ids if fixture_id in latest]

    def append_observations(self, observations: list[dict[str, Any]]) -> int:
        appended = 0
        with Session(self.engine) as session:
            for row in observations:
                session.add(self._observation_model(row))
                try:
                    session.commit()
                    appended += 1
                except IntegrityError:
                    session.rollback()
                except Exception as exc:
                    session.rollback()
                    raise FutureRefreshPersistenceError("OBSERVATION_WRITE_FAILED") from exc
        return appended

    def latest_market_observations(self) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(FutureMarketObservationModel).order_by(
                        FutureMarketObservationModel.fixture_id,
                        FutureMarketObservationModel.captured_at,
                        FutureMarketObservationModel.canonical_market,
                        FutureMarketObservationModel.bookmaker_id,
                        FutureMarketObservationModel.selection,
                    )
                )
            )
        return self._latest_observation_dicts(rows)

    def latest_market_observations_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> list[dict[str, Any]]:
        ids = [fixture_id for fixture_id in dict.fromkeys(fixture_ids) if fixture_id]
        if not ids:
            return []
        partition = (
            FutureMarketObservationModel.fixture_id,
            FutureMarketObservationModel.canonical_market,
            FutureMarketObservationModel.bookmaker_id,
            FutureMarketObservationModel.selection,
            FutureMarketObservationModel.line,
        )
        ranked = (
            select(
                FutureMarketObservationModel.observation_id.label("observation_id"),
                func.row_number()
                .over(
                    partition_by=partition,
                    order_by=FutureMarketObservationModel.captured_at.desc(),
                )
                .label("rank"),
            )
            .where(FutureMarketObservationModel.fixture_id.in_(ids))
            .subquery()
        )
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(FutureMarketObservationModel)
                    .join(
                        ranked,
                        FutureMarketObservationModel.observation_id
                        == ranked.c.observation_id,
                    )
                    .where(ranked.c.rank == 1)
                    .order_by(
                        FutureMarketObservationModel.fixture_id,
                        FutureMarketObservationModel.captured_at,
                        FutureMarketObservationModel.canonical_market,
                        FutureMarketObservationModel.bookmaker_id,
                        FutureMarketObservationModel.selection,
                    )
                )
            )
        return self._latest_observation_dicts(rows)

    def market_observation_history_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> list[dict[str, Any]]:
        ids = [fixture_id for fixture_id in dict.fromkeys(fixture_ids) if fixture_id]
        if not ids:
            return []
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(FutureMarketObservationModel)
                    .where(FutureMarketObservationModel.fixture_id.in_(ids))
                    .order_by(
                        FutureMarketObservationModel.fixture_id,
                        FutureMarketObservationModel.captured_at,
                        FutureMarketObservationModel.canonical_market,
                        FutureMarketObservationModel.bookmaker_id,
                        FutureMarketObservationModel.selection,
                    )
                )
            )
        return [self._observation_dict(row) for row in rows]

    def _latest_observation_dicts(
        self,
        rows: list[FutureMarketObservationModel],
    ) -> list[dict[str, Any]]:
        latest: dict[tuple[str, str, str, str, str | None], dict[str, Any]] = {}
        for model in rows:
            row = self._observation_dict(model)
            key = (
                row["fixture_id"],
                row["canonical_market"],
                row["bookmaker_id"],
                row["selection"],
                row["line"],
            )
            current = latest.get(key)
            if current is None or str(row["captured_at"]) > str(current["captured_at"]):
                latest[key] = row
        return sorted(
            latest.values(),
            key=lambda item: (
                str(item["fixture_id"]),
                str(item["captured_at"]),
                str(item["canonical_market"]),
                str(item["bookmaker_id"]),
                str(item["selection"]),
            ),
        )

    def fixture_payloads(self, *, provider_league_id: str | None = None) -> list[dict[str, Any]]:
        fixtures: dict[str, dict[str, Any]] = {}
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == "fixtures")
                    .order_by(RawPayloadModel.captured_at)
                )
            )
        for row in rows:
            response = row.payload.get("response")
            if not isinstance(response, list):
                continue
            for item in response:
                if not isinstance(item, dict):
                    continue
                if provider_league_id is not None:
                    league_id = str(item.get("league", {}).get("id") or "")
                    if league_id != provider_league_id:
                        continue
                fixture_id = str(item.get("fixture", {}).get("id"))
                if fixture_id and fixture_id != "None":
                    fixtures[fixture_id] = item
        return sorted(fixtures.values(), key=lambda item: item.get("fixture", {}).get("date", ""))

    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == endpoint)
                    .order_by(RawPayloadModel.captured_at)
                )
            )
        return [
            {
                "sha256": row.sha256,
                "endpoint": row.endpoint,
                "captured_at": iso_z(row.captured_at),
                "payload": dict(row.payload),
            }
            for row in rows
        ]

    def upsert_team_xg_matches(self, matches: list[dict[str, Any]]) -> int:
        upserted = 0
        with Session(self.engine) as session:
            for row in matches:
                model = TeamXgMatchModel(
                    id=str(row["id"]),
                    fixture_id=str(row["fixture_id"]),
                    team_id=str(row["team_id"]),
                    opponent_team_id=str(row["opponent_team_id"]),
                    kickoff_at=parse_db_datetime(row["kickoff_at"]),
                    captured_at=parse_db_datetime(row["captured_at"]),
                    xg_for=float(row["xg_for"]),
                    xg_against=float(row["xg_against"]),
                    goals_for=int(row["goals_for"]),
                    goals_against=int(row["goals_against"]),
                    raw_payload_sha256=str(row["raw_payload_sha256"]),
                    source_system=str(row["source_system"]),
                    candidate=False,
                    formal_recommendation=False,
                )
                session.merge(model)
                upserted += 1
            try:
                session.commit()
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("TEAM_XG_MATCH_WRITE_FAILED") from exc
        return upserted

    def team_xg_matches(self) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(TeamXgMatchModel).order_by(
                        TeamXgMatchModel.team_id,
                        TeamXgMatchModel.kickoff_at,
                    )
                )
            )
        return [
            {
                "id": row.id,
                "fixture_id": row.fixture_id,
                "team_id": row.team_id,
                "opponent_team_id": row.opponent_team_id,
                "kickoff_at": iso_z(row.kickoff_at),
                "captured_at": iso_z(row.captured_at),
                "xg_for": row.xg_for,
                "xg_against": row.xg_against,
                "goals_for": row.goals_for,
                "goals_against": row.goals_against,
                "raw_payload_sha256": row.raw_payload_sha256,
                "source_system": row.source_system,
                "candidate": False,
                "formal_recommendation": False,
            }
            for row in rows
        ]

    def upsert_team_xg_rolling_snapshots(self, snapshots: list[dict[str, Any]]) -> int:
        upserted = 0
        with Session(self.engine) as session:
            for row in snapshots:
                session.merge(
                    TeamXgRollingSnapshotModel(
                        snapshot_id=str(row["snapshot_id"]),
                        team_id=str(row["team_id"]),
                        as_of_fixture_id=str(row["as_of_fixture_id"]),
                        as_of_time=parse_db_datetime(row["as_of_time"]),
                        match_count=int(row["match_count"]),
                        rolling_xg_for=float(row["rolling_xg_for"]),
                        rolling_xg_against=float(row["rolling_xg_against"]),
                        rolling_goals_for=float(row["rolling_goals_for"]),
                        rolling_goals_against=float(row["rolling_goals_against"]),
                        regression_index=float(row["regression_index"]),
                        source_system=str(row["source_system"]),
                        candidate=False,
                        formal_recommendation=False,
                    )
                )
                upserted += 1
            try:
                session.commit()
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("TEAM_XG_SNAPSHOT_WRITE_FAILED") from exc
        return upserted

    def team_xg_rolling_snapshots(
        self,
        *,
        fixture_id: str | None = None,
        team_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            query = select(TeamXgRollingSnapshotModel)
            if fixture_id is not None:
                query = query.where(TeamXgRollingSnapshotModel.as_of_fixture_id == fixture_id)
            if team_id is not None:
                query = query.where(TeamXgRollingSnapshotModel.team_id == team_id)
            rows = list(
                session.scalars(
                    query.order_by(
                        TeamXgRollingSnapshotModel.team_id,
                        TeamXgRollingSnapshotModel.as_of_time,
                    )
                )
            )
        return [
            {
                "snapshot_id": row.snapshot_id,
                "team_id": row.team_id,
                "as_of_fixture_id": row.as_of_fixture_id,
                "as_of_time": iso_z(row.as_of_time),
                "match_count": row.match_count,
                "rolling_xg_for": row.rolling_xg_for,
                "rolling_xg_against": row.rolling_xg_against,
                "rolling_goals_for": row.rolling_goals_for,
                "rolling_goals_against": row.rolling_goals_against,
                "regression_index": row.regression_index,
                "source_system": row.source_system,
                "candidate": False,
                "formal_recommendation": False,
            }
            for row in rows
        ]

    def market_snapshots(self) -> list[dict[str, Any]]:
        observations = self.latest_market_observations()
        by_fixture: dict[str, list[dict[str, Any]]] = {}
        for row in observations:
            by_fixture.setdefault(str(row["fixture_id"]), []).append(row)
        snapshots: list[dict[str, Any]] = []
        for fixture_id, rows in sorted(by_fixture.items()):
            captured_at = max(str(row["captured_at"]) for row in rows)
            bookmakers = {str(row["bookmaker_id"]) for row in rows if row.get("bookmaker_id")}
            markets = {str(row["canonical_market"]) for row in rows}
            snapshots.append(
                {
                    "fixture_id": fixture_id,
                    "captured_at": captured_at,
                    "captured_at_utc": captured_at,
                    "snapshot_semantics": "CAPTURED_AT",
                    "bookmaker_count": len(bookmakers),
                    "quality": "READY" if rows else "MARKET_NOT_COMPARABLE",
                    "source": "future_refresh_db",
                    "market_coverage": {market: True for market in sorted(markets)},
                    "candidate": False,
                    "formal_recommendation": False,
                }
            )
        return snapshots

    def provider_status(self) -> dict[str, Any]:
        with Session(self.engine) as session:
            row = session.scalar(
                select(FutureRefreshRunAuditModel).order_by(
                    desc(FutureRefreshRunAuditModel.generated_at)
                )
            )
        if row is None:
            return {}
        last_success = next(
            (
                item
                for item in reversed(row.requests)
                if isinstance(item, dict) and item.get("status_code") == 200
            ),
            {},
        )
        return {
            "provider": "api_football",
            "status": "READY" if not row.blockers else "DEGRADED",
            "remaining_quota": row.remaining_quota,
            "credential_status": "PRESENT",
            "last_request_status": (
                row.requests[-1].get("status_code")
                if row.requests and isinstance(row.requests[-1], dict)
                else None
            ),
            "last_successful_refresh_at": last_success.get("captured_at_utc"),
            "blockers": row.blockers,
        }

    def write_task_audit(self, audit: dict[str, Any]) -> None:
        with Session(self.engine) as session:
            try:
                session.merge(
                    FutureRefreshTaskAuditModel(
                        task_id=str(audit["task_id"]),
                        key=str(audit["key"]),
                        owner=str(audit["owner"]),
                        queued_at=parse_db_datetime(audit["queued_at"]),
                        started_at=parse_db_datetime(audit["started_at"]),
                        finished_at=parse_db_datetime(audit["finished_at"]),
                        status=str(audit["status"]),
                        result=dict(audit["result"]),
                    )
                )
                session.commit()
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("TASK_AUDIT_WRITE_FAILED") from exc

    def task_key_exists(self, key: str) -> bool:
        with Session(self.engine) as session:
            row = session.scalar(
                select(FutureRefreshTaskAuditModel.task_id)
                .where(
                    FutureRefreshTaskAuditModel.key == key,
                    FutureRefreshTaskAuditModel.status == "COMPLETED",
                )
                .limit(1)
            )
        return row is not None

    def upsert_checkpoint_plans(self, plans: list[dict[str, Any]]) -> int:
        if not plans:
            return 0
        upserted = 0
        with Session(self.engine) as session:
            for row in plans:
                plan_id = str(row["id"])
                existing = session.get(FutureRefreshCheckpointPlanModel, plan_id)
                if existing is not None and existing.status == "COMPLETED":
                    continue
                session.merge(
                    FutureRefreshCheckpointPlanModel(
                        id=plan_id,
                        fixture_id=str(row["fixture_id"]),
                        checkpoint=str(row["checkpoint"]),
                        kickoff_utc=parse_db_datetime(row["kickoff_utc"]),
                        due_at=parse_db_datetime(row["due_at"]),
                        endpoints=list(row["endpoints"]),
                        source=str(row["source"]),
                        status=str(row.get("status") or "PENDING"),
                        executed_at=(
                            parse_db_datetime(row["executed_at"])
                            if row.get("executed_at")
                            else None
                        ),
                        last_audit_id=row.get("last_audit_id"),
                    )
                )
                upserted += 1
            try:
                session.commit()
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("CHECKPOINT_PLAN_WRITE_FAILED") from exc
        return upserted

    def due_checkpoint_plans(
        self,
        *,
        now: datetime,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        current = parse_db_datetime(now)
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(FutureRefreshCheckpointPlanModel)
                    .where(
                        FutureRefreshCheckpointPlanModel.status == "PENDING",
                        FutureRefreshCheckpointPlanModel.due_at <= current,
                    )
                    .order_by(
                        FutureRefreshCheckpointPlanModel.due_at,
                        FutureRefreshCheckpointPlanModel.kickoff_utc,
                        FutureRefreshCheckpointPlanModel.fixture_id,
                        FutureRefreshCheckpointPlanModel.checkpoint,
                    )
                    .limit(limit)
                )
            )
        return [self._checkpoint_plan_dict(row) for row in rows]

    def write_checkpoint_audit(
        self,
        *,
        fixture_id: str,
        checkpoint: str,
        as_of: datetime,
        calls_used: int,
        status: str,
        details: dict[str, Any],
    ) -> int:
        with Session(self.engine) as session:
            try:
                audit = FutureRefreshCheckpointAuditModel(
                    fixture_id=str(fixture_id),
                    checkpoint=str(checkpoint),
                    as_of=parse_db_datetime(as_of),
                    calls_used=int(calls_used),
                    status=str(status),
                    details=dict(details),
                )
                session.add(audit)
                plan = session.get(
                    FutureRefreshCheckpointPlanModel,
                    f"{fixture_id}:{checkpoint}",
                )
                if plan is not None and status in {"COMPLETED", "BLOCKED", "PARTIAL_FAILED"}:
                    plan.status = status
                    plan.executed_at = parse_db_datetime(as_of)
                    session.flush()
                    plan.last_audit_id = audit.id
                session.commit()
                return int(audit.id)
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("CHECKPOINT_AUDIT_WRITE_FAILED") from exc

    def _checkpoint_plan_dict(self, row: FutureRefreshCheckpointPlanModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "fixture_id": row.fixture_id,
            "checkpoint": row.checkpoint,
            "kickoff_utc": iso_z(row.kickoff_utc),
            "due_at": iso_z(row.due_at),
            "endpoints": list(row.endpoints),
            "source": row.source,
            "status": row.status,
            "executed_at": iso_z(row.executed_at) if row.executed_at is not None else None,
            "last_audit_id": row.last_audit_id,
        }

    def write_run_audit(self, payload: dict[str, Any]) -> None:
        with Session(self.engine) as session:
            try:
                session.add(
                    FutureRefreshRunAuditModel(
                        generated_at=parse_db_datetime(payload["generated_at_utc"]),
                        competition_id=str(payload["competition_id"]),
                        request_count=int(payload["request_count"]),
                        remaining_quota=payload["remaining_quota"],
                        fixture_count=int(payload["fixture_count"]),
                        mapping_count=int(payload["mapping_count"]),
                        market_snapshot_count=int(payload["market_snapshot_count"]),
                        ledger_appended_count=int(payload["ledger_appended_count"]),
                        selected_market_fixture_ids=list(payload["selected_market_fixture_ids"]),
                        blockers=list(payload["blockers"]),
                        requests=list(payload["requests"]),
                        candidate=False,
                        formal_recommendation=False,
                    )
                )
                session.commit()
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("RUN_AUDIT_WRITE_FAILED") from exc

    def request_count_since(self, since: datetime, *, include_quota_usage: bool = True) -> int:
        since_utc = parse_db_datetime(since)
        day_start = since_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        try:
            with Session(self.engine) as session:
                future_refresh_requests = session.scalar(
                    select(func.coalesce(func.sum(FutureRefreshRunAuditModel.request_count), 0))
                    .where(FutureRefreshRunAuditModel.generated_at >= since_utc)
                )
                provider_request_logs = session.scalar(
                    select(func.count())
                    .select_from(ProviderRequestLogModel)
                    .where(
                        ProviderRequestLogModel.provider == "api_football",
                        ProviderRequestLogModel.requested_at >= since_utc,
                    )
                )
                quota_usage = (
                    session.scalar(
                        select(func.coalesce(func.max(QuotaUsageModel.used), 0)).where(
                            QuotaUsageModel.provider == "api_football",
                            QuotaUsageModel.window_start >= day_start,
                            QuotaUsageModel.window_start < day_end,
                        )
                    )
                    if include_quota_usage
                    else 0
                )
        except Exception as exc:
            raise FutureRefreshPersistenceError("REQUEST_COUNT_READ_FAILED") from exc
        return max(
            int(future_refresh_requests or 0),
            int(provider_request_logs or 0),
            int(quota_usage or 0),
        )

    def _observation_model(self, row: dict[str, Any]) -> FutureMarketObservationModel:
        return FutureMarketObservationModel(
            observation_id=str(row["observation_id"]),
            fixture_id=str(row["fixture_id"]),
            provider=str(row["provider"]),
            bookmaker_id=str(row["bookmaker_id"]),
            bookmaker_name=str(row["bookmaker_name"]),
            provider_bet_id=str(row["provider_bet_id"]),
            raw_market_label=str(row["raw_market_label"]),
            canonical_market=str(row["canonical_market"]),
            selection=str(row["selection"]),
            line=None if row.get("line") is None else str(row["line"]),
            decimal_odds=str(row["decimal_odds"]),
            suspended=bool(row["suspended"]),
            live=bool(row["live"]),
            provider_last_update=str(row["provider_last_update"]),
            captured_at=parse_db_datetime(row["captured_at"]),
            ingested_at=parse_db_datetime(row["ingested_at"]),
            raw_payload_sha256=str(row["raw_payload_sha256"]),
            source_revision=str(row["source_revision"]),
            candidate=False,
            formal_recommendation=False,
        )

    def _observation_dict(self, model: FutureMarketObservationModel) -> dict[str, Any]:
        return {
            "observation_id": model.observation_id,
            "fixture_id": model.fixture_id,
            "provider": model.provider,
            "bookmaker_id": model.bookmaker_id,
            "bookmaker_name": model.bookmaker_name,
            "provider_bet_id": model.provider_bet_id,
            "raw_market_label": model.raw_market_label,
            "canonical_market": model.canonical_market,
            "selection": model.selection,
            "line": model.line,
            "decimal_odds": model.decimal_odds,
            "suspended": model.suspended,
            "live": model.live,
            "provider_last_update": model.provider_last_update,
            "captured_at": iso_z(model.captured_at),
            "ingested_at": iso_z(model.ingested_at),
            "raw_payload_sha256": model.raw_payload_sha256,
            "source_revision": model.source_revision,
            "candidate": False,
            "formal_recommendation": False,
        }
