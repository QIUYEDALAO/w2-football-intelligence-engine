"""短期数据修复：补 results.source_capture_id（1493157/1493166）。

根因：``materialize_results`` 曾按 captured_at 选最早 FT raw 作 source，可能选中
future_refresh 单独采集的 fixtures raw（无 matchday capture），source_capture_id 解析不到
→ 结算 sweep 抛 V3_RESULT_CAPTURE_MISSING → BLOCKED。根本修复（``_authoritative_result``
优先选有 matchday capture 的 raw）已让新完赛场不再复发；本脚本补已空的 1493157/1493166，
让这两场结算落库。

流程（可回滚）：
  1. 建备份表 results_backup_<stamp>（COPY 目标 fixture 的 results 行）。
  2. 原生 SQL 删除旧行（ResultModel 是 SQLAlchemy ORM append-only，原生 SQL 绕过 ORM 触发器）。
  3. 用修复后的 ``OutcomeLedgerRepository.materialize_results`` 重物化，正确填 source_capture_id。

用法：
  python scripts/fix_result_source_capture_id.py --dry-run        # 只备份不删不写，打印计划
  python scripts/fix_result_source_capture_id.py                  # 实际执行
  python scripts/fix_result_source_capture_id.py --fixture-ids 1493157,1493166
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime

from sqlalchemy import text

from w2.infrastructure.database import create_engine
from w2.tracking.outcome_ledger_repository import OutcomeLedgerRepository


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-ids", default="1493157,1493166")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ids = tuple(
        f"api_football:{raw.strip()}"
        for raw in args.fixture_ids.split(",")
        if raw.strip()
    )
    if not ids:
        print("NO_FIXTURE_IDS")
        return 2

    engine = create_engine()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = f"results_backup_{stamp}"

    with engine.begin() as conn:
        before = conn.execute(
            text("SELECT fixture_id, source_capture_id FROM results WHERE fixture_id = ANY(:ids)"),
            {"ids": list(ids)},
        ).fetchall()
        print(f"BEFORE ({len(before)} rows):")
        for row in before:
            print(f"  {row.fixture_id} source_capture_id={row.source_capture_id}")
        # 1. 备份（总是执行，即使 dry-run，保证可回滚）。
        conn.execute(
            text(f"CREATE TABLE {backup} AS SELECT * FROM results WHERE fixture_id = ANY(:ids)"),
            {"ids": list(ids)},
        )
        print(f"BACKUP_TABLE {backup} (rows={len(before)})")
        if args.dry_run:
            print("DRY_RUN: 不删除不重物化。")
            return 0
        # 2. 删除旧行（原生 SQL，绕过 ResultModel ORM append-only 触发器）。
        conn.execute(text("DELETE FROM results WHERE fixture_id = ANY(:ids)"), {"ids": list(ids)})

    # 3. 重物化（修复后正确填 source_capture_id）。
    repo = OutcomeLedgerRepository(engine)
    result = repo.materialize_results(fixture_ids=ids, dry_run=False, write_db=True)
    print("MATERIALIZE_RESULT:", result)

    with engine.connect() as conn:
        after = conn.execute(
            text("SELECT fixture_id, source_payload_sha256, source_capture_id FROM results WHERE fixture_id = ANY(:ids)"),
            {"ids": list(ids)},
        ).fetchall()
    print("AFTER:")
    ok = True
    for row in after:
        print(f"  {row.fixture_id} source_capture_id={row.source_capture_id}")
        if not row.source_capture_id:
            ok = False
    if not ok:
        print(f"FIX_INCOMPLETE: 仍有 source_capture_id 为空，回滚可用 {backup}")
        return 1
    print(f"FIX_OK backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
