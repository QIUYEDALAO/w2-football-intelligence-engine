#!/usr/bin/env python3
"""C2：matchday_checkpoint_plans 里 fixture 已完赛的 FAILED 处置——标记「已过期」（附 FT 证据）。

背景：T168_OPEN_ODDS 等赛前 checkpoints 的 FAILED 在 fixture 完赛后即失去意义，但监控
checkpoint_health 曾用 window_end>now-1h 过滤（T168 窗口=7 天），导致「fixture 已 FT 但
window_end 仍未来」的历史 FAILED 持续误报 CHECKPOINT_FAILED（如 8 月 16 日 14 条 T168）。
监控 SQL 已修为只对 GRACE 内真实 FAILED 上浮；本脚本把已完赛的 FAILED 逐条标记「已过期」，
附 FT 证据，用于数据留痕。

边界（铁律，adjudicated 模式）：
  - 对象：matchday_checkpoint_plans 里 status='FAILED' 且 fixture 已完赛
    （matchday_fixture_identities.fixture_status IN FT/AET/PEN）的行；
  - 处置动作：仅 UPDATE blockers 追加 "EXPIRED_FIXTURE_FT:{fixture_status}" 标记，
    不改 status / 不删行 / 不覆盖原 blockers；
  - fail-closed：无 FT 证据（fixture 未完赛或不存在）的 FAILED 一律 skipped。

用法：
  python scripts/adjudicate_checkpoint_failed_expired.py --dry-run   # 只输出统计 + UPDATE SQL
  python scripts/adjudicate_checkpoint_failed_expired.py --apply     # 执行 UPDATE + 写留痕 JSON
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

SSH_HOST = "w2-hk"
PG = "docker exec w2-staging-postgres-1 psql -XqAt -v ON_ERROR_STOP=1 -U w2_user -d w2"


def ssh(command: str) -> str:
    result = subprocess.run(["ssh", SSH_HOST, command], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"SSH_FAILED: {result.stderr.strip()}")
    return result.stdout.strip()


def sql(query: str) -> str:
    return ssh(f"{PG} -c {shlex.quote(query)}")


def _json_rows(raw: str) -> list[dict]:
    return json.loads(raw) if raw else []


def fetch_expired_failed() -> list[dict]:
    """查所有 fixture 已完赛的 FAILED 行（含 FT 证据）。"""
    raw = sql(
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) FROM ("
        "SELECT mcp.plan_id, mcp.fixture_id, mcp.checkpoint, mcp.status, "
        "mcp.scheduled_at::text AS scheduled_at, mcp.blockers::text AS blockers_text, "
        "mfi.fixture_status, mfi.kickoff_utc::text AS kickoff_utc "
        "FROM matchday_checkpoint_plans mcp "
        "JOIN matchday_fixture_identities mfi ON mfi.fixture_id = mcp.fixture_id "
        "WHERE mcp.status='FAILED' AND mfi.fixture_status IN ('FT','AET','PEN') "
        "ORDER BY mcp.scheduled_at) t"
    )
    return _json_rows(raw)


def build_updates(rows: list[dict], adjudicator: str) -> tuple[list[str], list[dict]]:
    statements: list[str] = []
    records: list[dict] = []
    now = datetime.now(UTC).isoformat()
    for row in rows:
        fixture_status = str(row.get("fixture_status") or "")
        plan_id = row["plan_id"]
        record = {
            "adjudicator": adjudicator,
            "adjudicated_at": now,
            "plan_id": plan_id,
            "fixture_id": row.get("fixture_id"),
            "checkpoint": row.get("checkpoint"),
            "verdict": f"已过期：fixture 已完赛（{fixture_status}），采集窗口失去意义",
            "fixture_status": fixture_status,
            "kickoff_utc": row.get("kickoff_utc"),
            "scheduled_at": row.get("scheduled_at"),
            "skipped": False,
        }
        mark = (
            f"EXPIRED_FIXTURE_FT:{fixture_status}:"
            f"adjudicator={adjudicator}:at={now}"
        )
        statements.append(
            "UPDATE matchday_checkpoint_plans SET blockers = "  # noqa: S608 -- 逐条主键精确更新
            f"(blockers || '{json.dumps([mark], ensure_ascii=False)}'::jsonb) "
            f"WHERE plan_id='{plan_id}' AND status='FAILED';"
        )
        records.append(record)
    return statements, records


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--dry-run"
    if mode not in ("--dry-run", "--apply"):
        raise SystemExit("用法: adjudicate_checkpoint_failed_expired.py [--dry-run|--apply]")
    adjudicator = os.environ.get("W2_FENCE_ADJUDICATOR", "codex-agent")

    rows = fetch_expired_failed()
    if not rows:
        print("NO_EXPIRED_FAILED_ROWS（无 fixture 已完赛的 FAILED）")
        return

    by_checkpoint = Counter(r.get("checkpoint") for r in rows)
    by_month = Counter((r.get("scheduled_at") or "")[:7] for r in rows)

    statements, records = build_updates(rows, adjudicator)

    print(f"== matchday_checkpoint_plans 已完赛 FAILED 只读核对（{len(rows)} 条）==")
    print("按 checkpoint 分布：", dict(by_checkpoint))
    print("按 scheduled 月份分布：", dict(by_month))
    print(f"可处置（追加 EXPIRED_FIXTURE_FT 标记）：{len(records)} 条；skipped：0 条")

    if mode == "--dry-run":
        print("\n== 处置 UPDATE SQL（--apply 才执行）==")
        for statement in statements:
            print(statement)
        return

    failed: list[str] = []
    for statement in statements:
        try:
            sql(statement)
        except RuntimeError as exc:
            failed.append(f"{statement[:120]}... -> {exc}")
    if failed:
        print("APPLY_FAILED：")
        for line in failed:
            print(f"  {line}")
        raise SystemExit(1)

    stamp = datetime.now(UTC).strftime("%Y%m%d")
    record_path = (
        Path(__file__).resolve().parent / f"checkpoint_failed_expired_{stamp}.json"
    )
    with open(record_path, "w", encoding="utf-8") as handle:
        json.dump(
            {"adjudicated_at": datetime.now(UTC).isoformat(), "records": records},
            handle,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\nAPPLY_OK：{len(statements)} 条已追加 EXPIRED_FIXTURE_FT，留痕写入 {record_path}")


if __name__ == "__main__":
    main()
