"""T4 测试数据污染清理：删除绕过四步写入器手插的 fx1/fx2 + snap-H/A。

只删明确测试行，不动任何真实数据：
- 账本 ``ah_ou_decision_ledger``：``fixture_id IN ('fx1','fx2')``
  （input_hash='hhhh…'、model_version='m1'、decision_contract='' 的手插测试行）。
- 快照 ``team_xg_rolling_snapshot``：``team_id IN ('H','A') AND source_system='sys'``
  （snapshot_id='snap-H'/'snap-A' 的手插测试行）。

账本表有 append-only trigger ``w2_ahou_terms_immutable`` 拦住 selected=true 的 DELETE，
清理前临时 DISABLE、清理后 ENABLE，整段在单事务内完成（dry-run 不落盘）。

用法：
    W2_DATABASE_URL=... .venv/bin/python scripts/cleanup_t4_test_pollution.py
    W2_DATABASE_URL=... .venv/bin/python scripts/cleanup_t4_test_pollution.py --dry-run
"""
from __future__ import annotations

import argparse

from sqlalchemy import text

from w2.infrastructure.database import create_engine

_LEDGER_TRIGGER = "w2_ahou_terms_immutable"


def cleanup(engine, *, dry_run: bool) -> dict[str, int]:
    """Delete the test-pollution rows; return per-table deleted row counts."""
    deleted: dict[str, int] = {"ah_ou_decision_ledger": 0, "team_xg_rolling_snapshot": 0}
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text(
                f"ALTER TABLE ah_ou_decision_ledger DISABLE TRIGGER {_LEDGER_TRIGGER}"
            ))
        try:
            result = conn.execute(text(
                "DELETE FROM ah_ou_decision_ledger WHERE fixture_id IN ('fx1', 'fx2')"
            ))
            deleted["ah_ou_decision_ledger"] = result.rowcount or 0
            result = conn.execute(text(
                "DELETE FROM team_xg_rolling_snapshot "
                "WHERE team_id IN ('H', 'A') AND source_system = 'sys'"
            ))
            deleted["team_xg_rolling_snapshot"] = result.rowcount or 0
            if dry_run:
                conn.rollback()
        finally:
            if engine.dialect.name == "postgresql" and not dry_run:
                conn.execute(text(
                    f"ALTER TABLE ah_ou_decision_ledger ENABLE TRIGGER {_LEDGER_TRIGGER}"
                ))
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description="T4 测试数据污染清理")
    parser.add_argument("--dry-run", action="store_true", help="只统计不落盘")
    args = parser.parse_args()

    engine = create_engine()
    deleted = cleanup(engine, dry_run=args.dry_run)
    verb = "would delete" if args.dry_run else "deleted"
    for table, count in deleted.items():
        print(f"{verb} {count} row(s) from {table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
