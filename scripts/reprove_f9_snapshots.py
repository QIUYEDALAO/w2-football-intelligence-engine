#!/usr/bin/env python3
"""重新物化未来比赛 F9 快照（覆盖旧 pit=false 遗留），并验证目标 6 场。

生产部署新代码（含 upsert 覆盖未证明遗留快照的修复）后执行，零 Provider 调用：
  python scripts/reprove_f9_snapshots.py

原理：
- materialize_saved_xg 用已入库的 fixture/statistics raw evidence 重新物化所有
  未来比赛快照（captured_before_cutoff=True 口径），对已存在的 pit=false 旧快照
  DELETE + INSERT 覆盖重证（first_captured_at=组件真实采集时刻、decision_at=真实
  决策点、first_committed_at=确认事务 clock_timestamp()，绝不回填伪造时间）。
- 验证目标 6 场快照 pit=true、first_captured_at ≤ decision_at、
  first_committed_at ≤ decision_at。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import Any

from w2.infrastructure.database import create_engine
from w2.ingestion.xg_backfill import materialize_saved_xg

TARGET_FIXTURES = (
    "1569953",
    "1551819",
    "1493161",
    "1492318",
    "1493155",
    "1493162",
)


def _snapshot_state(engine: Any, fixture_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from w2.infrastructure.persistence.future_refresh_models import TeamXgRollingSnapshotModel

    rows: list[dict[str, Any]] = []
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        for row in session.scalars(
            select(TeamXgRollingSnapshotModel).where(
                TeamXgRollingSnapshotModel.as_of_fixture_id.in_(fixture_ids)
            )
        ):
            rows.append(
                {
                    "snapshot_id": row.snapshot_id,
                    "as_of_fixture_id": row.as_of_fixture_id,
                    "pit_proven": bool(row.pit_proven),
                    "first_captured_at": row.first_captured_at.isoformat()
                    if row.first_captured_at
                    else None,
                    "first_committed_at": row.first_committed_at.isoformat()
                    if row.first_committed_at
                    else None,
                    "decision_at": row.decision_at.isoformat() if row.decision_at else None,
                }
            )
    return rows


def main() -> int:
    result = materialize_saved_xg()
    payload = result.as_dict()
    print(json.dumps({"materialization": payload}, ensure_ascii=False, sort_keys=True))

    engine = create_engine()
    snapshots = _snapshot_state(engine, TARGET_FIXTURES)
    failures: list[str] = []
    for row in snapshots:
        if not row["pit_proven"]:
            failures.append(f"{row['snapshot_id']}:not_pit_proven")
            continue
        if not row["first_captured_at"] or not row["decision_at"]:
            failures.append(f"{row['snapshot_id']}:missing_pit_time")
            continue
        first_captured = datetime.fromisoformat(row["first_captured_at"])
        first_committed = datetime.fromisoformat(row["first_committed_at"])
        decision = datetime.fromisoformat(row["decision_at"])
        if first_captured > decision:
            failures.append(f"{row['snapshot_id']}:first_capture_after_decision")
        if first_committed > decision:
            failures.append(f"{row['snapshot_id']}:first_commit_after_decision")

    report = {
        "schema_version": "w2.f9_snapshot_reprove.v1",
        "target_fixtures": list(TARGET_FIXTURES),
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
        "failures": failures,
        "status": "PASS" if not failures and len(snapshots) == len(TARGET_FIXTURES) * 2 else "FAIL",
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    if report["status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
