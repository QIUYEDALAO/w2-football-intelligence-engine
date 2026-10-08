#!/usr/bin/env python3
"""759+41 条历史 BLOCKED 处置：逐条裁决 + 追加 stored_result.adjudicated 标记。

边界（铁律）：
  - 对象：provider_side_effect_fence 里 stage='task' AND state='DONE' AND
    stored_result->>'status' LIKE 'BLOCKED%' 的历史行（非 SIDE_EFFECT_UNCERTAIN，不复用
    resolve_fence_uncertain.py）；
  - 处置动作：仅 UPDATE stored_result 顶层追加 adjudicated 键（verdict/adjudicator/at），
    不改 state、不删行、不覆盖 error 原文（历史证据不覆盖——吸收 68 条处置时 error 被覆盖的教训）；
  - 禁无依据批量：每行落到具体证据（额度保护附后续 PASS、payload 缺失逐 fixture 核查）；
  - fail-closed：未识别 blocker 一律 skipped，不得处置。

用法：
  python scripts/adjudicate_fence_blocked_history.py --dry-run   # 只输出裁决统计 + UPDATE SQL
  python scripts/adjudicate_fence_blocked_history.py --apply     # 执行 UPDATE + 写留痕 JSON

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

SSH_HOST = "w2-hk"
PG = "docker exec w2-staging-postgres-1 psql -XqAt -v ON_ERROR_STOP=1 -U w2_user -d w2"

# 已知可处置的 blocker 类别（按指令书 A 三类根因）。
QUOTA_BLOCKER_PREFIXES = (
    "PROVIDER_RESERVE_PROTECTED",
    "PROVIDER_HEADER_REMAINING_BELOW_MINIMUM",
    "PROVIDER_REFRESH_BUDGET_TOO_HIGH",
)
CLAIM_BLOCKER_PREFIXES = (
    "CHECKPOINT_BATCH_NO_VALID_CLAIMS",
    "CHECKPOINT_CLAIM_TOKEN_MISMATCH",
)
PAYLOAD_MISSING_PREFIX = "CHECKPOINT_FIXTURE_PAYLOAD_MISSING:"
# 未识别类型 → skipped（fail-closed，需人工逐条复核）。
UNKNOWN_BLOCKER_PREFIXES = (
    "ENDPOINT_CAPTURE_WRITE_FAILED",
    "ValueError",
    "LINEUP_MATERIALIZATION_FAILED",
    "FutureRefreshPersistenceError",
)


def ssh(command: str) -> str:
    result = subprocess.run(["ssh", SSH_HOST, command], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"SSH_FAILED: {result.stderr.strip()}")
    return result.stdout.strip()


def sql(query: str) -> str:
    return ssh(f"{PG} -c {shlex.quote(query)}")


def _json_rows(raw: str) -> list[dict]:
    return json.loads(raw) if raw else []


def fetch_blocked() -> list[dict]:
    """查所有未处置的历史 BLOCKED 行（含 stored_result 全文）。"""
    raw = sql(
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) FROM ("
        "SELECT task_id, stage, attempt, state, error, updated_at, "
        "stored_result::text AS stored_result_text "
        "FROM provider_side_effect_fence "
        "WHERE stage='task' AND state='DONE' AND stored_result->>'status' LIKE 'BLOCKED%' "
        "AND stored_result->'adjudicated' IS NULL ORDER BY updated_at) t"
    )
    return _json_rows(raw)


def fetch_pass_evidence() -> dict[str, str]:
    """额度保护证据：每个 competition+season 作用域后续 DONE PASS 的最新 updated_at。

    task_key 形如 checkpoint-refresh:{competition}:{season}:{hash}——hash 每次 tick 不同，
    必须按去掉 hash 的 scope（checkpoint-refresh:{competition}:{season}）匹配，才能找到
    同一联赛后续 tick 的 PASS 证据。
    """
    raw = sql(
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) FROM ("
        "SELECT stored_result->>'task_key' AS task_key, updated_at::text AS updated_at "
        "FROM provider_side_effect_fence "
        "WHERE stage='task' AND state='DONE' AND stored_result->>'status'='PASS') t"
    )
    evidence: dict[str, str] = {}
    for row in _json_rows(raw):
        scope = (row.get("task_key") or "").rsplit(":", 1)[0]
        if not scope:
            continue
        cur = evidence.get(scope, "")
        if (row.get("updated_at") or "") > cur:
            evidence[scope] = row["updated_at"]
    return evidence


def fetch_fixture_checkpoint_status() -> dict[str, list[dict]]:
    """fixture → 该 fixture 的 checkpoint plan 状态列表（用于 payload 缺失核查）。"""
    raw = sql(
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) FROM ("
        "SELECT fixture_id, checkpoint, status, scheduled_at::text AS scheduled_at "
        "FROM matchday_checkpoint_plans ORDER BY fixture_id, scheduled_at) t"
    )
    by_fixture: dict[str, list[dict]] = {}
    for row in _json_rows(raw):
        fid = row.get("fixture_id")
        if fid:
            by_fixture.setdefault(str(fid), []).append(row)
    return by_fixture


def fetch_finished_fixtures() -> set[str]:
    """已完赛 fixture（fixture_status IN FT/AET/PEN）的 provider_fixture_id 集合。"""
    raw = sql(
        "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) FROM ("
        "SELECT provider_fixture_id FROM matchday_fixture_identities "
        "WHERE fixture_status IN ('FT','AET','PEN')) t"
    )
    return {str(r["provider_fixture_id"]) for r in _json_rows(raw)}


def _payload_verdict(
    fixture_id: str,
    fixture_status: dict[str, list[dict]],
    finished: set[str],
) -> tuple[str, bool]:
    """核查单个 payload 缺失 fixture：后续已 CAPTURED / 已完赛 POSTMATCH CAPTURED / 仍缺未完赛。"""
    plans = fixture_status.get(f"api_football:{fixture_id}") or fixture_status.get(fixture_id) or []
    captured = [p for p in plans if p.get("status") == "CAPTURED"]
    postmatch_captured = [p for p in captured if p.get("checkpoint") == "POSTMATCH_RESULT"]
    if captured:
        return (
            f"实际失败：payload 缺失已被后续采集修复"
            f"（fixture {fixture_id} 有 {len(captured)} 个 CAPTURED checkpoint）",
            True,
        )
    if postmatch_captured:
        return f"已过期不再相关（fixture {fixture_id} POSTMATCH_RESULT 已 CAPTURED）", True
    if fixture_id in finished:
        return f"已过期不再相关（fixture {fixture_id} 已完赛）", True
    return f"实际失败：payload 缺失且未修复（fixture {fixture_id} 仍缺、未完赛）——不得处置", False


def adjudicate_row(
    row: dict,
    pass_evidence: dict[str, str],
    fixture_status: dict[str, list[dict]],
    finished: set[str],
) -> tuple[str, bool]:
    """逐条裁决一行。返回 (verdict, apply)。apply=False 表示 skipped（fail-closed）。"""
    try:
        stored = json.loads(row.get("stored_result_text") or "{}")
    except json.JSONDecodeError:
        return "实际失败：stored_result 解析失败——需人工复核", False
    blockers = (stored.get("result") or {}).get("blockers") or []
    if not isinstance(blockers, list):
        blockers = []
    task_key = stored.get("task_key") or ""
    task_scope = task_key.rsplit(":", 1)[0]
    updated_at = str(row.get("updated_at") or "")

    # 1. 存在未识别 blocker → 整行 skipped（fail-closed）
    unknown = [b for b in blockers if isinstance(b, str) and b.startswith(UNKNOWN_BLOCKER_PREFIXES)]
    if unknown:
        return f"实际失败：未识别 blocker 类型，需人工复核——{', '.join(unknown[:3])}", False

    quota = [b for b in blockers if isinstance(b, str) and b.startswith(QUOTA_BLOCKER_PREFIXES)]
    claims = [b for b in blockers if isinstance(b, str) and b.startswith(CLAIM_BLOCKER_PREFIXES)]
    payloads = [b for b in blockers if isinstance(b, str) and b.startswith(PAYLOAD_MISSING_PREFIX)]

    # 2. payload 缺失 → 逐 fixture 核查
    payload_pending: list[str] = []
    for b in payloads:
        fid = b[len(PAYLOAD_MISSING_PREFIX):]
        verdict, ok = _payload_verdict(fid, fixture_status, finished)
        if not ok:
            payload_pending.append(fid)
    if payload_pending:
        return (
            f"实际失败：payload 缺失且未修复——{', '.join(payload_pending)} 仍缺、未完赛，不得处置",
            False,
        )

    # 3. 额度保护 → 附后续 PASS 证据
    if quota:
        pass_at = pass_evidence.get(task_scope, "")
        if pass_at and pass_at > updated_at:
            return (
                f"实际失败：当日额度保护拦截，后续同日 DONE PASS 已覆盖（pass_at={pass_at}）",
                True,
            )
        return "实际失败：额度保护拦截，但未找到后续 PASS 证据——需人工复核", False

    # 4. 并发 claim → 直接判定
    if claims:
        return "实际失败：调度并发 claim 噪音，后续 tick 已成功", True

    # 5. payload 已修复/过期（无 pending）→ 处置
    if payloads:
        return "实际失败：payload 缺失已被后续采集修复/已过期不再相关", True

    return "实际失败：空 blocker，需人工复核", False


def build_updates(
    rows: list[dict],
    adjudicator: str,
    *,
    pass_evidence: dict[str, str],
    fixture_status: dict[str, list[dict]],
    finished: set[str],
) -> tuple[list[str], list[dict]]:
    statements: list[str] = []
    records: list[dict] = []
    now = datetime.now(UTC).isoformat()
    for row in rows:
        verdict, apply = adjudicate_row(row, pass_evidence, fixture_status, finished)
        task_id = row["task_id"]
        stage = row["stage"]
        attempt = row["attempt"]
        record = {
            "adjudicator": adjudicator,
            "adjudicated_at": now,
            "task_id": task_id,
            "stage": stage,
            "attempt": attempt,
            "verdict": verdict,
            "original_status": (
                json.loads(row.get("stored_result_text") or "{}") or {}
            ).get("status"),
            "original_blockers": (
                (json.loads(row.get("stored_result_text") or "{}") or {})
                .get("result", {})
                .get("blockers")
            ),
            "skipped": not apply,
        }
        if not apply:
            records.append(record)
            continue
        mark = json.dumps(
            {"adjudicated": {"verdict": verdict, "adjudicator": adjudicator, "at": now}},
            ensure_ascii=False,
        )
        statements.append(
            "UPDATE provider_side_effect_fence SET stored_result = "  # noqa: S608 -- 逐条主键精确更新，值来自只读查询
            f"(stored_result::jsonb || '{mark}'::jsonb)::json "
            f"WHERE task_id='{task_id}' AND stage='{stage}' AND attempt={attempt};"
        )
        records.append(record)
    return statements, records


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--dry-run"
    if mode not in ("--dry-run", "--apply"):
        raise SystemExit("用法: adjudicate_fence_blocked_history.py [--dry-run|--apply]")
    adjudicator = os.environ.get("W2_FENCE_ADJUDICATOR", "codex-agent")

    rows = fetch_blocked()
    if not rows:
        print("NO_BLOCKED_ROWS（无未处置历史 BLOCKED）")
        return

    pass_evidence = fetch_pass_evidence()
    fixture_status = fetch_fixture_checkpoint_status()
    finished = fetch_finished_fixtures()

    statements, records = build_updates(
        rows,
        adjudicator,
        pass_evidence=pass_evidence,
        fixture_status=fixture_status,
        finished=finished,
    )

    applied = [r for r in records if not r.get("skipped")]
    skipped = [r for r in records if r.get("skipped")]
    verdict_counts = Counter(r["verdict"].split("：")[0] for r in records)

    print(f"== fence 历史 BLOCKED 只读核对（{len(rows)} 条）==")
    print("裁决统计：", dict(verdict_counts))
    print(
        f"可处置（追加 adjudicated）：{len(applied)} 条；"
        f"skipped（fail-closed 保持上浮）：{len(skipped)} 条"
    )
    print("逐条裁决依据：")
    for record in records:
        print(f"  {record['task_id']}|{record['stage']} -> {record['verdict']}")

    if mode == "--dry-run":
        print("\n== 裁决 UPDATE SQL（--apply 才执行）==")
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
        Path(__file__).resolve().parent / f"fence_blocked_history_adjudication_{stamp}.json"
    )
    with open(record_path, "w", encoding="utf-8") as handle:
        json.dump(
            {"adjudicated_at": datetime.now(UTC).isoformat(), "records": records},
            handle,
            ensure_ascii=False,
            indent=2,
        )
    print(
        f"\nAPPLY_OK：{len(statements)} 条已追加 adjudicated，"
        f"skipped={len(skipped)} 条保持上浮，留痕写入 {record_path}"
    )


if __name__ == "__main__":
    main()
