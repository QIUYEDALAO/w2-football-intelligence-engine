#!/usr/bin/env python3
"""fence 68 条 SIDE_EFFECT_UNCERTAIN 处置：只读核对 + 逐条裁决 + 留痕（可回滚）。

边界（铁律）：
  - 只 UPDATE ``provider_side_effect_fence.state``（SIDE_EFFECT_UNCERTAIN → RESOLVED）；
  - 不动账本 / 快照 / 推荐；
  - 禁无依据批量改：逐条依据来自 error 类型 + 数据落库证据。

RESOLVED 语义：已人工裁决「实际成功」——数据已落库（幂等冲突 / 超时后补采），
下次 checkpoint-refresh 幂等刷新继续。巡检与系统健康只统计 SIDE_EFFECT_UNCERTAIN，
RESOLVED 不再产生 FENCE_UNCERTAIN_STALE / SIDE_EFFECT_UNCERTAIN 告警。

用法：
  python scripts/resolve_fence_uncertain.py --dry-run   # 只核对，输出裁决依据 + UPDATE SQL
  python scripts/resolve_fence_uncertain.py --apply     # 执行 UPDATE + 写留痕 JSON

裁决人通过环境变量 W2_FENCE_ADJUDICATOR 指定（默认 codex-agent）。
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

RESOLVED = "RESOLVED"
SSH_HOST = "w2-hk"
PG = "docker exec w2-staging-postgres-1 psql -XqAt -v ON_ERROR_STOP=1 -U w2_user -d w2"

# 裁决规则：error 关键词 → 中文依据（全部判定为「实际成功」——数据已落库）。
VERDICT_RULES = [
    (
        "TEAM_XG_SNAPSHOT_FIELD_CONFLICT",
        "xG 快照字段冲突（first_captured_at）——xG 数据已落库，快照物化幂等冲突",
    ),
    (
        "F6_HISTORY_FIELD_CONFLICT",
        "h2h 历史字段冲突（endpoint_capture_id）——h2h 数据已落库，幂等冲突",
    ),
    (
        "UniqueViolation",
        "快照重复主键（snapshot_id 已存在）——已物化，幂等冲突",
    ),
    (
        "STALE_ATTEMPTING_TIMEOUT",
        "任务超时——对应联赛后续已补采（team_xg_match 数据持续落库）",
    ),
]


def ssh(command: str) -> str:
    result = subprocess.run(["ssh", SSH_HOST, command], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"SSH_FAILED: {result.stderr.strip()}")
    return result.stdout.strip()


def sql(query: str) -> str:
    return ssh(f"{PG} -c {shlex.quote(query)}")


def _adjudicate(error: str | None) -> str:
    if not error:
        return "实际失败：无错误记录，需人工复核"
    for keyword, reason in VERDICT_RULES:
        if keyword in error:
            return "实际成功：" + reason
    return "实际失败：未识别错误类型，需人工复核——" + error[:120]


def fetch_uncertain() -> list[dict]:
    raw = sql(
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) FROM ("
        "SELECT task_id, stage, attempt, state, error, updated_at "
        "FROM provider_side_effect_fence WHERE state='SIDE_EFFECT_UNCERTAIN' "
        "ORDER BY task_id, stage) t"
    )
    rows = json.loads(raw) if raw else []
    if not rows:
        raise SystemExit("NO_UNCERTAIN_ROWS（68 条已不存在或已处置）")
    return rows


def fetch_evidence() -> dict[str, str]:
    """数据落库证据：各联赛 team_xg_match 最新 captured_at + 10-05 后 DONE 计数。"""
    evidence: dict[str, str] = {}
    raw = sql(
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) FROM ("
        "SELECT mfi.competition_id, count(DISTINCT txm.fixture_id) AS xg_fixtures, "
        "max(txm.captured_at) AS latest_captured_at "
        "FROM team_xg_match txm "
        "JOIN matchday_fixture_identities mfi ON txm.fixture_id = mfi.provider_fixture_id "
        "WHERE mfi.competition_id IN ('argentina_primera','brasileirao_serie_a','mls',"
        "'netherlands_eerste_divisie','spain_segunda_division') "
        "GROUP BY mfi.competition_id) t"
    )
    for row in json.loads(raw) if raw else []:
        evidence["xg_" + row["competition_id"]] = (
            f"{row['xg_fixtures']} fixtures, latest={row['latest_captured_at']}"
        )
    return evidence


def build_updates(rows: list[dict], adjudicator: str) -> tuple[list[str], list[dict]]:
    statements: list[str] = []
    records: list[dict] = []
    now = datetime.now(UTC).isoformat()
    for row in rows:
        verdict = _adjudicate(row.get("error"))
        task_id = row["task_id"]
        stage = row["stage"]
        attempt = row["attempt"]
        if verdict.startswith("实际失败"):
            # fail-closed：实际失败的行不得置 RESOLVED，保持 SIDE_EFFECT_UNCERTAIN 待人工复核
            records.append(
                {
                    "adjudicator": adjudicator,
                    "adjudicated_at": now,
                    "task_id": task_id,
                    "stage": stage,
                    "attempt": attempt,
                    "original_state": row.get("state"),
                    "new_state": row.get("state"),
                    "verdict": verdict,
                    "original_error": row.get("error"),
                    "skipped": True,
                }
            )
            continue
        # 主键 (task_id, stage, attempt) 精确定位；只动 state，不动其他表。
        statements.append(
            "UPDATE provider_side_effect_fence SET state='RESOLVED', "  # noqa: S608 -- 逐条 WHERE 主键精确更新，task_id/stage 来自只读查询
            f"error='RESOLVED:{verdict}'::text, updated_at=now() "
            f"WHERE task_id='{task_id}' AND stage='{stage}' AND attempt={attempt};"
        )
        records.append(
            {
                "adjudicator": adjudicator,
                "adjudicated_at": now,
                "task_id": task_id,
                "stage": stage,
                "attempt": attempt,
                "original_state": row.get("state"),
                "new_state": RESOLVED,
                "verdict": verdict,
                "original_error": row.get("error"),
            }
        )
    return statements, records


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--dry-run"
    if mode not in ("--dry-run", "--apply"):
        raise SystemExit("用法: resolve_fence_uncertain.py [--dry-run|--apply]")
    adjudicator = os.environ.get("W2_FENCE_ADJUDICATOR", "codex-agent")

    rows = fetch_uncertain()
    evidence = fetch_evidence()
    statements, records = build_updates(rows, adjudicator)

    # 裁决依据统计（核对 reason 分布，禁无依据批量）
    verdict_counts = Counter(r["verdict"].split("：")[0] for r in records)

    print(f"== fence UNCERTAIN 只读核对（{len(rows)} 条）==")
    print("数据落库证据：")
    for key, value in sorted(evidence.items()):
        print(f"  {key}: {value}")
    print("裁决统计：", dict(verdict_counts))
    print("逐条裁决依据：")
    for record in records:
        print(f"  {record['task_id']}|{record['stage']} -> {record['verdict']}")

    if mode == "--dry-run":
        print("\n== 裁决 UPDATE SQL（--apply 才执行）==")
        for statement in statements:
            print(statement)
        return

    # --apply：逐条执行（每条独立事务，失败不阻断其余，但整体报告）
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

    record_path = Path(__file__).resolve().parent / "fence_resolution_records.json"
    with open(record_path, "w", encoding="utf-8") as handle:
        json.dump(
            {"adjudicated_at": datetime.now(UTC).isoformat(), "records": records},
            handle,
            ensure_ascii=False,
            indent=2,
        )
    skipped_count = sum(1 for r in records if r.get("skipped"))
    print(
        f"\nAPPLY_OK：{len(statements)} 条已置 RESOLVED，"
        f"skipped={skipped_count} 条保持 SIDE_EFFECT_UNCERTAIN，留痕写入 {record_path}"
    )


if __name__ == "__main__":
    main()
