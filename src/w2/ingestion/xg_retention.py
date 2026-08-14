from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
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
        backup = canonical_bytes(
            {
                "schema_version": RETENTION_SCHEMA,
                "raw_statistics": raw_rows,
                "fixture_payloads": fixture_rows,
                "rolling_snapshot_identities": snapshot_identities,
            },
            domain=HashDomain.XG_RETENTION_STATE,
        )
        restored_payload = json.loads(backup.decode("utf-8"))
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
            "backup_hash": canonical_sha256(
                {
                    "schema_version": RETENTION_SCHEMA,
                    "raw_statistics": raw_rows,
                    "fixture_payloads": fixture_rows,
                    "rolling_snapshot_identities": snapshot_identities,
                },
                domain=HashDomain.XG_RETENTION_STATE,
            ),
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

    def _plan(
        self,
        repository: Any,
        *,
        snapshot_identities: list[dict[str, Any]],
    ) -> SavedRawXgPlan:
        return XgHistoryBackfillService(
            repository=repository,
            now=self.now,
            config=XgBackfillConfig(
                competition_ids=tuple(sorted(REQUIRED_MATCHDAY_COMPETITIONS)),
            ),
        ).build_saved_raw_plan(snapshot_identities=snapshot_identities)


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
    return canonical_sha256(rows, domain=HashDomain.XG_RETENTION_STATE)


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
