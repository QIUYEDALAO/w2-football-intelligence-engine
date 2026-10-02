#!/usr/bin/env python3
"""重新物化目标 6 场 F9 快照（覆盖旧 pit=false 遗留），零 Provider 调用。

生产部署后执行：
  python scripts/reprove_f9_snapshots.py

原理：只物化目标 6 场（build_saved_raw_plan 的 snapshot_identities 参数限制范围，
避免 materialize_saved_xg 全量物化所有 future fixtures 导致 OOM），再用 upsert 对
已存在的 pit=false 旧快照 DELETE + INSERT 覆盖重证（first_captured_at=组件真实采集
时刻、decision_at=真实决策点、first_committed_at=确认事务 clock_timestamp()，绝不
回填伪造时间）。
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.future_refresh_models import TeamXgRollingSnapshotModel
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.ingestion.xg_backfill import XgBackfillConfig, XgHistoryBackfillService
from w2.matchday.intake_v2 import required_matchday_competition_ids

TARGET_FIXTURES = (
    "1569953",
    "1551819",
    "1493161",
    "1492318",
    "1493155",
    "1493162",
)


def _snapshot_state(engine: Any, fixture_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    with Session(engine) as session:
        rows = list(session.scalars(select(TeamXgRollingSnapshotModel).where(
            TeamXgRollingSnapshotModel.as_of_fixture_id.in_(fixture_ids)
        )))
    return [
        {
            "snapshot_id": row.snapshot_id,
            "team_id": row.team_id,
            "as_of_fixture_id": row.as_of_fixture_id,
            "pit_proven": bool(row.pit_proven),
            "first_captured_at": (
                row.first_captured_at.isoformat() if row.first_captured_at else None
            ),
            "first_committed_at": (
                row.first_committed_at.isoformat() if row.first_committed_at else None
            ),
            "decision_at": row.decision_at.isoformat() if row.decision_at else None,
        }
        for row in rows
    ]


def main() -> int:
    now = datetime.now(UTC)
    repo = FutureRefreshDbRepository()

    # 目标 6 场的现有快照 identity（含旧 pit=false 遗留）。
    current = _snapshot_state(repo.engine, TARGET_FIXTURES)
    identities = [
        {"snapshot_id": row["snapshot_id"], "team_id": row["team_id"],
         "as_of_fixture_id": row["as_of_fixture_id"]}
        for row in current
    ]
    if not identities:
        print(json.dumps({"status": "FAIL", "reason": "NO_TARGET_SNAPSHOTS"}))
        return 1

    service = XgHistoryBackfillService(
        repository=repo,
        now=now,
        config=XgBackfillConfig(
            competition_ids=tuple(sorted(required_matchday_competition_ids())),
            min_rolling_matches=3,
            max_rolling_matches=5,
        ),
    )
    plan = service.build_saved_raw_plan(snapshot_identities=identities)
    if plan.blockers:
        print(json.dumps({"status": "FAIL", "blockers": list(plan.blockers)}))
        return 1

    upserted = repo.upsert_team_xg_rolling_snapshots(list(plan.rolling_snapshots))

    after = _snapshot_state(repo.engine, TARGET_FIXTURES)
    failures: list[str] = []
    for row in after:
        if not row["pit_proven"]:
            failures.append(f"{row['snapshot_id']}:not_pit_proven")
        elif not row["first_captured_at"] or not row["decision_at"]:
            failures.append(f"{row['snapshot_id']}:missing_pit_time")
        elif (
            datetime.fromisoformat(row["first_captured_at"])
            > datetime.fromisoformat(row["decision_at"])
        ):
            failures.append(f"{row['snapshot_id']}:first_capture_after_decision")
        elif (
            row["first_committed_at"]
            and datetime.fromisoformat(row["first_committed_at"])
            > datetime.fromisoformat(row["decision_at"])
        ):
            failures.append(f"{row['snapshot_id']}:first_commit_after_decision")

    report = {
        "schema_version": "w2.f9_snapshot_reprove.v1",
        "target_fixtures": list(TARGET_FIXTURES),
        "upserted": upserted,
        "snapshot_count": len(after),
        "snapshots": after,
        "failures": failures,
        "status": "PASS" if not failures and len(after) == len(TARGET_FIXTURES) * 2 else "FAIL",
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
