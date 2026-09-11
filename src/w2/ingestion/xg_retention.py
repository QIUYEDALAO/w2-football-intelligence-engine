from __future__ import annotations

import json
import struct
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import (
    HashDomain,
    canonical_bytes,
    canonical_sha256,
)
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.future_refresh_models import (
    RawStatisticsRetentionModel,
    TeamXgMatchModel,
    TeamXgRollingSnapshotModel,
)
from w2.ingestion.future_refresh import sha256_payload
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.ingestion.xg_backfill import (
    SavedRawXgPlan,
    XgBackfillConfig,
    XgHistoryBackfillService,
)
from w2.matchday.intake_v2 import REQUIRED_MATCHDAY_COMPETITIONS

RETENTION_SCHEMA = "w2.xg_retention_hardening.v1"
XG_RETENTION_HASH_DOMAIN = HashDomain.FUTURE_REFRESH_EVIDENCE


class XgRetentionError(ValueError):
    pass


class XgRetentionHardeningService:
    def __init__(self, engine: Engine | None = None, *, now: datetime | None = None) -> None:
        self.engine = engine or create_engine()
        self.now = (now or datetime.now(UTC)).astimezone(UTC)
        self.repository = FutureRefreshDbRepository(engine=self.engine)

    def audit(self) -> dict[str, Any]:
        raw = self.repository.raw_payloads("statistics")
        raw_rows = sorted(raw, key=lambda item: str(item.get("sha256") or ""))
        fixture_rows = self.repository.fixture_payloads()
        current_snapshot_rows = sorted(
            self.repository.team_xg_rolling_snapshots(),
            key=lambda row: str(row.get("snapshot_id") or ""),
        )
        snapshot_identities = [
            {
                "snapshot_id": str(row.get("snapshot_id") or ""),
                "team_id": str(row.get("team_id") or ""),
                "as_of_fixture_id": str(row.get("as_of_fixture_id") or ""),
            }
            for row in current_snapshot_rows
        ]
        invalid_raw_hashes = [
            str(row.get("sha256") or "")
            for row in raw_rows
            if sha256_payload(
                _dict(row.get("payload")),
                domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
            )
            != str(row.get("sha256") or "")
        ]
        if invalid_raw_hashes:
            raise XgRetentionError("RAW_STATISTICS_HASH_MISMATCH")
        plan = self._plan(self.repository, snapshot_identities=snapshot_identities)
        backup_state = {
            "schema_version": RETENTION_SCHEMA,
            "raw_statistics": raw_rows,
            "fixture_payloads": fixture_rows,
            "rolling_snapshot_identities": snapshot_identities,
        }
        backup = canonical_bytes(backup_state, domain=XG_RETENTION_HASH_DOMAIN)
        restored_payload = _restore_canonical_json(json.loads(backup.decode("utf-8")))
        restored_rows = restored_payload.get("raw_statistics")
        restored_fixtures = restored_payload.get("fixture_payloads")
        restored_identities = restored_payload.get("rolling_snapshot_identities")
        if not all(
            isinstance(value, list)
            for value in (restored_rows, restored_fixtures, restored_identities)
        ):
            raise XgRetentionError("RAW_STATISTICS_BACKUP_INVALID")
        restored_repository = _RestoredRawRepository(
            self.repository,
            statistics=restored_rows,
            fixtures=restored_fixtures,
        )
        restored_plan = self._plan(
            restored_repository,
            snapshot_identities=restored_identities,
        )
        expected_match_rows = list(plan.team_xg_matches)
        expected_snapshot_rows = list(plan.rolling_snapshots)
        current_match_rows = sorted(
            self.repository.team_xg_matches(),
            key=lambda row: str(row.get("id") or ""),
        )
        expected_match_hash = _state_hash(expected_match_rows)
        expected_snapshot_hash = _state_hash(expected_snapshot_rows)
        current_match_hash = _state_hash(current_match_rows)
        current_snapshot_hash = _state_hash(current_snapshot_rows)
        restored_match_hash = _state_hash(list(restored_plan.team_xg_matches))
        restored_snapshot_hash = _state_hash(list(restored_plan.rolling_snapshots))
        with Session(self.engine) as session:
            retained_hashes = sorted(
                session.scalars(
                    select(RawStatisticsRetentionModel.raw_payload_sha256).order_by(
                        RawStatisticsRetentionModel.raw_payload_sha256
                    )
                )
            )
        raw_hashes = sorted(str(row["sha256"]) for row in raw_rows)
        raw_aggregate_hash = _state_hash(raw_hashes)
        restored_raw_hash = _state_hash(
            sorted(str(row["sha256"]) for row in restored_rows if isinstance(row, Mapping))
        )
        manifest_match = retained_hashes == raw_hashes
        count_guard = len(current_match_rows) == len(expected_match_rows) and len(
            current_snapshot_rows
        ) == len(expected_snapshot_rows)
        hash_guard = (
            current_match_hash == expected_match_hash
            and current_snapshot_hash == expected_snapshot_hash
        )
        restore_hash_match = (
            raw_aggregate_hash == restored_raw_hash
            and expected_match_hash == restored_match_hash
            and expected_snapshot_hash == restored_snapshot_hash
        )
        raw_nonempty = bool(raw_rows)
        plan_ready = not plan.blockers
        status = (
            "PASS"
            if raw_nonempty
            and plan_ready
            and manifest_match
            and count_guard
            and hash_guard
            and restore_hash_match
            else "BLOCKED"
        )
        return {
            "schema_version": RETENTION_SCHEMA,
            "status": status,
            "dry_run": True,
            "provider_calls": 0,
            "db_writes": 0,
            "raw_statistics_count": len(raw_rows),
            "raw_statistics_nonempty": raw_nonempty,
            "raw_statistics_aggregate_hash": raw_aggregate_hash,
            "raw_statistics_retention_manifest_count": len(retained_hashes),
            "raw_statistics_retention_manifest_match": manifest_match,
            "team_xg_match_expected_count": len(expected_match_rows),
            "team_xg_match_current_scoped_count": len(current_match_rows),
            "team_xg_match_expected_hash": expected_match_hash,
            "team_xg_match_current_scoped_hash": current_match_hash,
            "rolling_snapshot_expected_count": len(expected_snapshot_rows),
            "rolling_snapshot_current_scoped_count": len(current_snapshot_rows),
            "rolling_snapshot_expected_hash": expected_snapshot_hash,
            "rolling_snapshot_current_scoped_hash": current_snapshot_hash,
            "count_guard_match": count_guard,
            "hash_guard_match": hash_guard,
            "backup_bytes": len(backup),
            "backup_hash": _state_hash(backup_state),
            "raw_statistics_restore_hash_match": restore_hash_match,
            "rebuild_from_raw_match_hash": restored_match_hash,
            "rebuild_from_raw_snapshot_hash": restored_snapshot_hash,
            "blockers": [
                reason
                for reason, ok in (
                    ("RAW_STATISTICS_ABSENT", raw_nonempty),
                    ("XG_RAW_REBUILD_PLAN_BLOCKED", plan_ready),
                    ("RAW_STATISTICS_RETENTION_MANIFEST_MISMATCH", manifest_match),
                    ("XG_REBUILD_COUNT_GUARD_MISMATCH", count_guard),
                    ("XG_REBUILD_HASH_GUARD_MISMATCH", hash_guard),
                    ("RAW_STATISTICS_RESTORE_HASH_MISMATCH", restore_hash_match),
                )
                if not ok
            ]
            + list(plan.blockers),
        }

    def repair_derived_lineage(
        self,
        *,
        dry_run: bool = True,
        write_db: bool = False,
        backup_path: Path | None = None,
    ) -> dict[str, Any]:
        if dry_run and write_db:
            raise XgRetentionError("write_db requires dry_run=false")
        if write_db and backup_path is None:
            raise XgRetentionError("XG_RETENTION_REPAIR_BACKUP_REQUIRED")
        repository = self.repository
        current_matches = sorted(
            repository.team_xg_matches(), key=lambda row: str(row.get("id") or "")
        )
        current_snapshots = sorted(
            repository.team_xg_rolling_snapshots(),
            key=lambda row: str(row.get("snapshot_id") or ""),
        )
        future_plan = self._service(repository).build_saved_raw_plan()
        identity_by_id = {
            str(row.get("snapshot_id") or ""): {
                "snapshot_id": str(row.get("snapshot_id") or ""),
                "team_id": str(row.get("team_id") or ""),
                "as_of_fixture_id": str(row.get("as_of_fixture_id") or ""),
            }
            for row in [*current_snapshots, *future_plan.rolling_snapshots]
        }
        plan = self._service(repository).build_saved_raw_plan(
            snapshot_identities=[identity_by_id[key] for key in sorted(identity_by_id)]
        )
        if plan.blockers:
            raise XgRetentionError("XG_RETENTION_REPAIR_PLAN_BLOCKED")
        expected_matches = list(plan.team_xg_matches)
        expected_snapshots = list(plan.rolling_snapshots)
        current_match_by_id = {str(row["id"]): row for row in current_matches}
        expected_match_by_id = {str(row["id"]): row for row in expected_matches}
        current_snapshot_by_id = {str(row["snapshot_id"]): row for row in current_snapshots}
        expected_snapshot_by_id = {str(row["snapshot_id"]): row for row in expected_snapshots}
        if set(current_match_by_id) != set(expected_match_by_id):
            raise XgRetentionError("XG_RETENTION_REPAIR_MATCH_ID_GUARD_MISMATCH")
        if not set(current_snapshot_by_id) <= set(expected_snapshot_by_id):
            raise XgRetentionError("XG_RETENTION_REPAIR_SNAPSHOT_ID_GUARD_MISMATCH")
        match_updates = _guarded_timestamp_updates(
            current_match_by_id,
            expected_match_by_id,
            allowed_field="captured_at",
        )
        snapshot_updates = _guarded_timestamp_updates(
            current_snapshot_by_id,
            expected_snapshot_by_id,
            allowed_field="as_of_time",
        )
        new_snapshot_ids = sorted(set(expected_snapshot_by_id) - set(current_snapshot_by_id))
        backup_state = {
            "schema_version": "w2.xg_retention_derived_backup.v1",
            "team_xg_match": current_matches,
            "rolling_snapshots": current_snapshots,
        }
        backup = canonical_bytes(backup_state, domain=XG_RETENTION_HASH_DOMAIN)
        backup_hash = _state_hash(backup_state)
        restored_backup = _restore_canonical_json(json.loads(backup.decode("utf-8")))
        backup_restore_match = (
            canonical_sha256(restored_backup, domain=XG_RETENTION_HASH_DOMAIN) == backup_hash
        )
        if not backup_restore_match:
            raise XgRetentionError("XG_RETENTION_REPAIR_BACKUP_RESTORE_HASH_MISMATCH")
        db_writes = 0
        if write_db:
            assert backup_path is not None
            if backup_path.exists():
                raise XgRetentionError("XG_RETENTION_REPAIR_BACKUP_ALREADY_EXISTS")
            with Session(self.engine) as session:
                locked_matches = list(
                    session.scalars(
                        select(TeamXgMatchModel).order_by(TeamXgMatchModel.id).with_for_update()
                    )
                )
                locked_snapshots = list(
                    session.scalars(
                        select(TeamXgRollingSnapshotModel)
                        .order_by(TeamXgRollingSnapshotModel.snapshot_id)
                        .with_for_update()
                    )
                )
                locked_match_state = [
                    FutureRefreshDbRepository._team_xg_match_dict(row) for row in locked_matches
                ]
                locked_snapshot_state = [
                    FutureRefreshDbRepository._team_xg_rolling_snapshot_dict(row)
                    for row in locked_snapshots
                ]
                if _state_hash(locked_match_state) != _state_hash(current_matches):
                    raise XgRetentionError("XG_RETENTION_REPAIR_CURRENT_MATCH_HASH_CHANGED")
                if _state_hash(locked_snapshot_state) != _state_hash(current_snapshots):
                    raise XgRetentionError("XG_RETENTION_REPAIR_CURRENT_SNAPSHOT_HASH_CHANGED")
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                backup_path.write_bytes(backup)
                if backup_path.stat().st_size != len(backup):
                    raise XgRetentionError("XG_RETENTION_REPAIR_BACKUP_WRITE_MISMATCH")
                locked_match_by_id = {row.id: row for row in locked_matches}
                locked_snapshot_by_id = {row.snapshot_id: row for row in locked_snapshots}
                for identity in match_updates:
                    match_model = locked_match_by_id[identity]
                    match_model.captured_at = _parse_time(
                        expected_match_by_id[identity]["captured_at"]
                    )
                    db_writes += 1
                for identity in snapshot_updates:
                    snapshot_model = locked_snapshot_by_id[identity]
                    snapshot_model.as_of_time = _parse_time(
                        expected_snapshot_by_id[identity]["as_of_time"]
                    )
                    db_writes += 1
                for identity in new_snapshot_ids:
                    snapshot_payload = expected_snapshot_by_id[identity]
                    session.add(_snapshot_model(snapshot_payload))
                    db_writes += 1
                session.commit()
        post_audit = self.audit() if write_db else None
        if post_audit is not None and post_audit["status"] != "PASS":
            raise XgRetentionError("XG_RETENTION_REPAIR_POST_AUDIT_FAILED")
        return {
            "schema_version": "w2.xg_retention_derived_repair.v1",
            "status": "PASS" if post_audit is not None else "DRY_RUN_PASS",
            "dry_run": dry_run,
            "write_db": write_db,
            "provider_calls": 0,
            "db_writes": db_writes,
            "team_xg_match_id_guard_match": True,
            "rolling_snapshot_id_guard_match": True,
            "team_xg_match_timestamp_update_count": len(match_updates),
            "rolling_snapshot_timestamp_update_count": len(snapshot_updates),
            "rolling_snapshot_insert_count": len(new_snapshot_ids),
            "backup_bytes": len(backup),
            "backup_hash": backup_hash,
            "backup_restore_hash_match": backup_restore_match,
            "backup_path": str(backup_path) if write_db else None,
            "expected_team_xg_match_hash": _state_hash(expected_matches),
            "expected_rolling_snapshot_hash": _state_hash(expected_snapshots),
            "post_audit": post_audit,
        }

    def _plan(
        self,
        repository: Any,
        *,
        snapshot_identities: list[dict[str, Any]],
    ) -> SavedRawXgPlan:
        return self._service(repository).build_saved_raw_plan(
            snapshot_identities=snapshot_identities
        )

    def _service(self, repository: Any) -> XgHistoryBackfillService:
        return XgHistoryBackfillService(
            repository=repository,
            now=self.now,
            config=XgBackfillConfig(
                competition_ids=tuple(sorted(REQUIRED_MATCHDAY_COMPETITIONS)),
            ),
        )


class _RestoredRawRepository:
    def __init__(
        self,
        delegate: FutureRefreshDbRepository,
        *,
        statistics: list[Any],
        fixtures: list[Any],
    ) -> None:
        self.delegate = delegate
        self.statistics = [dict(row) for row in statistics if isinstance(row, Mapping)]
        self.fixtures = [dict(row) for row in fixtures if isinstance(row, Mapping)]

    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        return (
            list(self.statistics)
            if endpoint == "statistics"
            else self.delegate.raw_payloads(endpoint)
        )

    def fixture_payloads(self) -> list[dict[str, Any]]:
        return list(self.fixtures)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)


def _state_hash(rows: Any) -> str:
    return canonical_sha256(rows, domain=XG_RETENTION_HASH_DOMAIN)


def _restore_canonical_json(value: Any) -> Any:
    if isinstance(value, list):
        return [_restore_canonical_json(item) for item in value]
    if not isinstance(value, Mapping):
        return value
    if set(value) == {"$w2_float"}:
        return struct.unpack(">d", bytes.fromhex(str(value["$w2_float"])))[0]
    return {key: _restore_canonical_json(item) for key, item in value.items()}


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _guarded_timestamp_updates(
    current: Mapping[str, Mapping[str, Any]],
    expected: Mapping[str, Mapping[str, Any]],
    *,
    allowed_field: str,
) -> list[str]:
    updates: list[str] = []
    for identity in sorted(current):
        left = current[identity]
        right = expected[identity]
        differences = {
            field for field in set(left) | set(right) if left.get(field) != right.get(field)
        }
        if differences - {allowed_field}:
            raise XgRetentionError(
                f"XG_RETENTION_NON_TIMESTAMP_DRIFT:{identity}:{','.join(sorted(differences))}"
            )
        if allowed_field in differences:
            updates.append(identity)
    return updates


def _parse_time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _snapshot_model(row: Mapping[str, Any]) -> TeamXgRollingSnapshotModel:
    return TeamXgRollingSnapshotModel(
        snapshot_id=str(row["snapshot_id"]),
        team_id=str(row["team_id"]),
        as_of_fixture_id=str(row["as_of_fixture_id"]),
        as_of_time=_parse_time(row["as_of_time"]),
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
