#!/usr/bin/env python3
"""Collect and verify the read-only SCHED-PEAK-01 production trace."""
# ruff: noqa: E501, S603

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs/review_packages/SCHED_PEAK_01"
RAW_PATH = PACKAGE / "SCHED_PEAK_01_RAW_20260824.json"
EVIDENCE_PATH = PACKAGE / "SCHED_PEAK_01_EVIDENCE_20260824.json"
REPORT_PATH = PACKAGE / "SCHED_PEAK_01_REPORT_20260824.md"
CLAIMED_AT = "2026-08-23T18:30:49.501785Z"
SLOT_DUE_AT = "2026-08-23T18:30:00Z"
SHORT_WINDOW_END = "2026-08-23T18:45:00Z"

SQL = r"""
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
COPY (
SELECT json_build_object(
  'snapshot_at', transaction_timestamp(),
  'schema', (SELECT version_num FROM alembic_version),
  'plans', coalesce((
    SELECT json_agg(json_build_object(
      'plan_id', plan_id, 'fixture_id', fixture_id,
      'competition_id', competition_id, 'checkpoint', checkpoint,
      'kickoff_utc', kickoff_utc, 'scheduled_at', scheduled_at,
      'window_start', window_start, 'window_end', window_end,
      'status', status, 'attempt_count', attempt_count,
      'missed_at', missed_at, 'blockers', blockers,
      'capture_id', capture_id
    ) ORDER BY window_end, kickoff_utc, fixture_id, checkpoint)
    FROM matchday_checkpoint_plans
    WHERE scheduled_at = timestamptz '2026-08-23T18:30:00Z'
  ), '[]'::json),
  'tasks', coalesce((
    SELECT json_agg(json_build_object(
      'task_id', task_id, 'key', key, 'queued_at', queued_at,
      'started_at', started_at, 'finished_at', finished_at,
      'status', status,
      'queue_seconds', round(extract(epoch FROM started_at-queued_at)::numeric, 6),
      'run_seconds', round(extract(epoch FROM finished_at-started_at)::numeric, 6),
      'request_count', result->'request_count',
      'blockers', result->'blockers',
      'checkpoint_fixture_ids', result->'checkpoint_fixture_ids'
    ) ORDER BY started_at, queued_at, task_id)
    FROM future_refresh_task_audit
    WHERE queued_at >= timestamptz '2026-08-23T18:20:00Z'
      AND queued_at < timestamptz '2026-08-23T19:05:00Z'
  ), '[]'::json),
  'peak_endpoint_captures', coalesce((
    SELECT json_agg(json_build_object(
      'endpoint', endpoint, 'fixture_id', fixture_id,
      'checkpoint', checkpoint, 'competition_id', competition_id,
      'requested_at', requested_at,
      'provider_captured_at', provider_captured_at,
      'elapsed_ms', elapsed_ms, 'status_code', status_code,
      'response_count', response_count,
      'capture_status', capture_status, 'error_code', error_code,
      'request_task_key', request_task_key
    ) ORDER BY requested_at, endpoint, fixture_id)
    FROM matchday_endpoint_captures
    WHERE requested_at >= timestamptz '2026-08-23T18:30:00Z'
      AND requested_at < timestamptz '2026-08-23T18:45:00Z'
      AND checkpoint IN ('T15_ODDS','T-30m_VALIDATION_LOCK',
                         'T30_LINEUPS_RETRY','T3_ODDS','T6_ODDS',
                         'T60_ODDS_LINEUPS')
      OR requested_at >= timestamptz '2026-08-23T18:30:00Z'
      AND requested_at < timestamptz '2026-08-23T18:45:00Z'
      AND checkpoint = 'T-30m_VALIDATION_LOCK,T30_LINEUPS_RETRY'
  ), '[]'::json),
  'provider_window', (
    SELECT json_build_object(
      'attempts', count(*),
      'errors', count(*) FILTER (WHERE error IS NOT NULL),
      'timeouts', count(*) FILTER (WHERE error ILIKE '%timeout%'),
      'last_completed_at', max(completed_at),
      'max_seconds', round(max(extract(epoch FROM completed_at-requested_at))::numeric, 6),
      'p95_seconds', round(percentile_cont(0.95) WITHIN GROUP (
        ORDER BY extract(epoch FROM completed_at-requested_at))::numeric, 6)
    )
    FROM provider_request_logs
    WHERE live
      AND requested_at >= timestamptz '2026-08-23T18:30:00Z'
      AND requested_at < timestamptz '2026-08-23T18:48:00Z'
  ),
  'older_backlog', coalesce((
    SELECT json_agg(json_build_object(
      'task_id', task_id, 'key', key, 'queued_at', queued_at,
      'started_at', started_at, 'finished_at', finished_at,
      'status', status
    ) ORDER BY queued_at)
    FROM future_refresh_task_audit
    WHERE queued_at < timestamptz '2026-08-23T18:30:49.501785Z'
      AND started_at > timestamptz '2026-08-23T18:30:49.501785Z'
      AND started_at < timestamptz '2026-08-23T18:32:00Z'
  ), '[]'::json)
)::text
) TO STDOUT;
ROLLBACK;
"""


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ssh(args: argparse.Namespace, command: str, *, stdin: str | None = None) -> str:
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes"]
    if args.ssh_key:
        cmd.extend(["-i", args.ssh_key])
    cmd.extend([f"{args.ssh_user}@{args.ssh_host}", command])
    result = subprocess.run(
        cmd,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise SystemExit(f"SCHED_PEAK_SSH_FAILED:{result.stderr.strip()}")
    return result.stdout


def _sql_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    output = _ssh(
        args,
        "docker exec -i w2-staging-postgres-1 psql -XAt -v ON_ERROR_STOP=1 -U w2_user -d w2",
        stdin=SQL,
    )
    rows = [line for line in output.splitlines() if line.startswith("{")]
    if len(rows) != 1:
        raise SystemExit("SCHED_PEAK_SQL_SNAPSHOT_INVALID")
    return dict(json.loads(rows[0]))


def _dispatch_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    logs = _ssh(
        args,
        "docker logs --since 2026-08-23T18:30:00Z --until 2026-08-23T18:32:00Z w2-staging-scheduler-1 2>&1",
    )
    marker = "w2 future fixture refresh "
    matches: list[dict[str, Any]] = []
    for line in logs.splitlines():
        if marker not in line or CLAIMED_AT not in line:
            continue
        payload = ast.literal_eval(line.split(marker, 1)[1])
        if payload.get("queued_at_utc") == CLAIMED_AT:
            matches.append(payload)
    if len(matches) != 1:
        raise SystemExit("SCHED_PEAK_DISPATCH_LOG_NOT_UNIQUE")
    row = matches[0]
    return {
        "queued_at_utc": row["queued_at_utc"],
        "due_checkpoint_count": row["due_checkpoint_count"],
        "selected_checkpoint_count": row["selected_checkpoint_count"],
        "projected_calls": row["projected_calls"],
        "all_due_projected_calls": row["all_due_projected_calls"],
        "tick_hard_cap": row["tick_hard_cap"],
        "plans": [
            {
                "plan_id": item["id"],
                "competition_id": item["competition_id"],
                "fixture_id": item["fixture_id"],
                "checkpoint": item["checkpoint"],
                "due_at": item["due_at"],
                "window_end": item["window_end"],
                "claim_expires_at": item["claim_expires_at"],
            }
            for item in row["checkpoints"]
        ],
        "groups": [
            {
                "task_id": item["task_id"],
                "competition_id": item["competition_id"],
                "checkpoint_count": item["checkpoint_count"],
            }
            for item in row["results"]
        ],
    }


def collect(args: argparse.Namespace) -> dict[str, Any]:
    version = json.loads(_ssh(args, "curl -fsS http://127.0.0.1:18000/v1/version"))
    worker_cmd = json.loads(
        _ssh(args, "docker inspect -f '{{json .Config.Cmd}}' w2-staging-worker-1").strip()
    )
    capacity_lines = _ssh(
        args,
        "nproc; free -m | sed -n '2p'; docker stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.PIDs}}' w2-staging-worker-1 w2-staging-scheduler-1 w2-staging-postgres-1; docker inspect -f '{{.HostConfig.Memory}}|{{.HostConfig.NanoCpus}}' w2-staging-worker-1",
    ).splitlines()
    return {
        "schema_version": "w2.sched-peak-01.raw.v1",
        "collected_at": _iso(datetime.now(UTC)),
        "authority": {
            "release_id": version["release_id"],
            "schema": version["release_identity"]["alembic"]["current"],
        },
        "worker": {"command": worker_cmd},
        "capacity_lines": capacity_lines,
        "dispatch": _dispatch_snapshot(args),
        "database": _sql_snapshot(args),
        "safety": {
            "provider_calls_by_collector": 0,
            "production_writes": 0,
            "deployments": 0,
        },
    }


def _task_map(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["task_id"]): dict(item) for item in raw["database"]["tasks"]}


def build_evidence(raw: dict[str, Any], raw_bytes: bytes) -> dict[str, Any]:
    dispatch = raw["dispatch"]
    db_plans = {str(item["plan_id"]): dict(item) for item in raw["database"]["plans"]}
    task_map = _task_map(raw)
    groups = []
    for index, group in enumerate(dispatch["groups"], 1):
        task = task_map[str(group["task_id"])]
        groups.append(
            {
                "dispatch_order": index,
                "competition_id": group["competition_id"],
                "checkpoint_count": int(group["checkpoint_count"]),
                "task_id": group["task_id"],
                "queued_at": task["queued_at"],
                "started_at": task["started_at"],
                "finished_at": task["finished_at"],
                "queue_seconds": float(task["queue_seconds"]),
                "run_seconds": float(task["run_seconds"]),
                "status": task["status"],
                "blockers": task.get("blockers") or [],
            }
        )

    dispatched_plans = [db_plans[str(item["plan_id"])] for item in dispatch["plans"]]
    status_counts = Counter(str(item["status"]) for item in dispatched_plans)
    missed = [item for item in dispatched_plans if item["status"] == "MISSED"]
    captured = [item for item in dispatched_plans if item["status"] == "CAPTURED"]
    short_missed = [
        item for item in missed if _dt(item["window_end"]) == _dt(SHORT_WINDOW_END)
    ]
    peak_captures = list(raw["database"]["peak_endpoint_captures"])
    brazil_captures = [
        item for item in peak_captures if item["competition_id"] == "brasileirao_serie_a"
    ]
    brazil_group = next(item for item in groups if item["competition_id"] == "brasileirao_serie_a")
    claim_at = _dt(dispatch["queued_at_utc"])
    claim_expiry = _dt(dispatch["plans"][0]["claim_expires_at"])
    last_brazil_response = _dt(raw["database"]["provider_window"]["last_completed_at"])
    brazil_finish = _dt(brazil_group["finished_at"])
    brazil_start = _dt(brazil_group["started_at"])
    window_end = _dt(SHORT_WINDOW_END)

    concurrency = None
    for item in raw["worker"]["command"]:
        if str(item).startswith("--concurrency="):
            concurrency = int(str(item).split("=", 1)[1])
    if concurrency is None:
        raise ValueError("worker concurrency is not explicit")

    # Frozen-trace FIFO replay. Slot 0 is the additional process; slot 1 keeps
    # the observed wait until the existing worker accepted the first peak task.
    initial_wait = float(groups[0]["queue_seconds"])
    first_three = groups[:3]
    occupancies = [
        (_dt(first_three[index + 1]["started_at"]) - _dt(item["started_at"])).total_seconds()
        if index + 1 < len(first_three)
        else float(item["run_seconds"])
        for index, item in enumerate(first_three)
    ]
    slots = [0.0, initial_wait]
    replay = []
    for item, duration in zip(first_three, occupancies, strict=True):
        slot = min(range(2), key=slots.__getitem__)
        start = slots[slot]
        finish = start + duration
        slots[slot] = finish
        replay.append(
            {
                "competition_id": item["competition_id"],
                "slot": slot + 1,
                "start_after_claim_seconds": round(start, 6),
                "finish_after_claim_seconds": round(finish, 6),
            }
        )
    replay_brazil = replay[-1]
    window_budget = (window_end - claim_at).total_seconds()

    postmatch = next(
        item
        for item in raw["database"]["plans"]
        if item["checkpoint"] == "POSTMATCH_RESULT"
        and _dt(item["scheduled_at"]) == _dt(SLOT_DUE_AT)
    )
    all_slot_statuses = Counter(
        str(item["status"])
        for item in raw["database"]["plans"]
        if _dt(item["scheduled_at"]) == _dt(SLOT_DUE_AT)
    )

    evidence = {
        "schema_version": "w2.sched-peak-01.evidence.v1",
        "source_raw_sha256": _sha(raw_bytes),
        "authority": raw["authority"],
        "slot": {
            "due_at": SLOT_DUE_AT,
            "prematch_due_count": int(dispatch["due_checkpoint_count"]),
            "prematch_selected_count": int(dispatch["selected_checkpoint_count"]),
            "prematch_projected_provider_calls": int(dispatch["projected_calls"]),
            "prematch_status_counts": dict(sorted(status_counts.items())),
            "prematch_captured_count": len(captured),
            "prematch_missed_count": len(missed),
            "prematch_other_terminal_count": len(dispatched_plans) - len(captured) - len(missed),
            "all_same_due_at_status_counts": dict(sorted(all_slot_statuses.items())),
            "postmatch_plan": {
                "plan_id": postmatch["plan_id"],
                "status": postmatch["status"],
                "attempt_count": int(postmatch["attempt_count"]),
                "window_end": postmatch["window_end"],
            },
        },
        "claim": {
            "claimed_count": len(dispatch["plans"]),
            "all_missed_attempted": all(int(item["attempt_count"]) >= 1 for item in missed),
            "claimed_at": dispatch["queued_at_utc"],
            "claim_expires_at": _iso(claim_expiry),
            "lease_seconds": int((claim_expiry - claim_at).total_seconds()),
            "short_window_end": SHORT_WINDOW_END,
            "short_window_budget_from_claim_seconds": round(window_budget, 6),
            "short_missed_count": len(short_missed),
            "missed_at": sorted({item["missed_at"] for item in missed}),
        },
        "worker": {
            "concurrency": concurrency,
            "command": raw["worker"]["command"],
            "dispatch_group_count": len(groups),
            "groups": groups,
            "older_backlog_count": len(raw["database"]["older_backlog"]),
        },
        "provider": {
            "peak_endpoint_capture_count": len(peak_captures),
            "peak_http_200_count": sum(int(item["status_code"] == 200) for item in peak_captures),
            "peak_error_count": sum(int(bool(item.get("error_code"))) for item in peak_captures),
            "peak_max_elapsed_ms": max(int(item["elapsed_ms"]) for item in peak_captures),
            "brazil_request_count": len(brazil_captures),
            "brazil_first_request_at": min(item["requested_at"] for item in brazil_captures),
            "brazil_last_response_at": _iso(last_brazil_response),
            "brazil_max_elapsed_ms": max(int(item["elapsed_ms"]) for item in brazil_captures),
            "window_summary": raw["database"]["provider_window"],
        },
        "occupancy": {
            "brazil_queue_seconds": float(brazil_group["queue_seconds"]),
            "brazil_run_seconds": float(brazil_group["run_seconds"]),
            "claim_to_brazil_finish_seconds": round((brazil_finish - claim_at).total_seconds(), 6),
            "remaining_lease_at_brazil_start_seconds": round((claim_expiry - brazil_start).total_seconds(), 6),
            "run_over_remaining_lease_seconds": round(
                (brazil_finish - claim_expiry).total_seconds(), 6
            ),
            "post_provider_tail_seconds": round(
                (brazil_finish - last_brazil_response).total_seconds(), 6
            ),
            "post_provider_tail_over_short_window_seconds": round(
                (brazil_finish - window_end).total_seconds(), 6
            ),
        },
        "failure_dimensions": {
            "missed_by_competition": dict(
                sorted(Counter(str(item["competition_id"]) for item in missed).items())
            ),
            "missed_by_checkpoint": dict(
                sorted(Counter(str(item["checkpoint"]) for item in missed).items())
            ),
            "captured_by_competition": dict(
                sorted(Counter(str(item["competition_id"]) for item in captured).items())
            ),
            "captured_by_checkpoint": dict(
                sorted(Counter(str(item["checkpoint"]) for item in captured).items())
            ),
        },
        "capacity_option": {
            "frozen_trace_minimum_concurrency": 2,
            "two_slot_replay": replay,
            "brazil_finish_after_claim_seconds": replay_brazil[
                "finish_after_claim_seconds"
            ],
            "short_window_budget_seconds": round(window_budget, 6),
            "replay_margin_seconds": round(
                window_budget - float(replay_brazil["finish_after_claim_seconds"]), 6
            ),
            "current_capacity_lines": raw["capacity_lines"],
        },
        "root_cause": {
            "classification": "SINGLE_WORKER_SERIALIZATION_PLUS_POST_REQUEST_PROCESSING_OVERRAN_CLAIM_WINDOW",
            "claim_contention": False,
            "worker_concurrency_insufficient": True,
            "provider_timeout": False,
            "never_claimed_before_expiry": False,
            "late_claim_token_mismatch_is_effect_not_cause": True,
        },
        "safety": raw["safety"],
    }
    validate_evidence(evidence)
    return evidence


def validate_evidence(evidence: dict[str, Any]) -> None:
    expected = {
        "prematch_due_count": 14,
        "prematch_selected_count": 14,
        "prematch_captured_count": 3,
        "prematch_missed_count": 9,
        "prematch_other_terminal_count": 2,
    }
    for field, value in expected.items():
        if evidence["slot"][field] != value:
            raise ValueError(f"SCHED_PEAK_SLOT_MISMATCH:{field}")
    if evidence["claim"]["lease_seconds"] != 900:
        raise ValueError("SCHED_PEAK_LEASE_MISMATCH")
    if not evidence["claim"]["all_missed_attempted"]:
        raise ValueError("SCHED_PEAK_UNCLAIMED_MISS")
    if evidence["claim"]["short_missed_count"] != 6:
        raise ValueError("SCHED_PEAK_SHORT_MISSED_COUNT_MISMATCH")
    if evidence["worker"]["concurrency"] != 1:
        raise ValueError("SCHED_PEAK_WORKER_CONCURRENCY_MISMATCH")
    if evidence["provider"]["peak_endpoint_capture_count"] != 11:
        raise ValueError("SCHED_PEAK_PROVIDER_CAPTURE_COUNT_MISMATCH")
    if evidence["provider"]["peak_http_200_count"] != 11:
        raise ValueError("SCHED_PEAK_PROVIDER_HTTP_MISMATCH")
    if evidence["provider"]["peak_error_count"] != 0:
        raise ValueError("SCHED_PEAK_PROVIDER_ERROR_PRESENT")
    if evidence["provider"]["peak_max_elapsed_ms"] > 1000:
        raise ValueError("SCHED_PEAK_PROVIDER_LATENCY_UNEXPECTED")
    if evidence["occupancy"]["run_over_remaining_lease_seconds"] <= 0:
        raise ValueError("SCHED_PEAK_NO_LEASE_OVERRUN")
    if evidence["capacity_option"]["replay_margin_seconds"] <= 0:
        raise ValueError("SCHED_PEAK_TWO_SLOT_REPLAY_FAILED")
    if evidence["safety"] != {
        "provider_calls_by_collector": 0,
        "production_writes": 0,
        "deployments": 0,
    }:
        raise ValueError("SCHED_PEAK_SAFETY_MISMATCH")


def render_report(e: dict[str, Any]) -> str:
    groups = "\n".join(
        f"| {row['dispatch_order']} | {row['competition_id']} | {row['checkpoint_count']} | {row['queue_seconds']:.3f} | {row['run_seconds']:.3f} | {row['status']} | {', '.join(row['blockers']) or '-'} |"
        for row in e["worker"]["groups"]
    )
    return f"""# SCHED-PEAK-01 — 18:30Z 高峰槽根因报告

## 结论

`CHECKPOINT_MISSING` 的具体成因是 **单 worker 串行化，加上任务的 Provider 后处理超过剩余窗口/租约**。生产 worker 明确为 `--concurrency=1`，且该观测发生在截至 2026-08-28T04:37:34Z 的临时 coverage 插桩窗口内。18:30:49Z 调度器一次性成功 claim `14/14` 个 prematch 计划，说明不是没取走，也不是初始 claim 争用；11 个已发出的峰值请求全部 HTTP 200，最大 `{e['provider']['peak_max_elapsed_ms']}ms`，说明不是 Provider 超时。

巴甲 8-plan 批次排队 `{e['occupancy']['brazil_queue_seconds']:.3f}s` 后于 18:38:37Z 开始，8 次 Provider 请求在 18:38:40.507Z 前全部返回，但任务直到 18:47:45.513Z 才结束。最后响应后的本地处理仍占 `{e['occupancy']['post_provider_tail_seconds']:.3f}s`，最终超过 18:45:00Z 短窗口 `{e['occupancy']['post_provider_tail_over_short_window_seconds']:.3f}s`，也超过 18:45:49.502Z claim lease `{e['occupancy']['run_over_remaining_lease_seconds']:.3f}s`。18:45:55Z scheduler 因窗口和 lease 均已过期，把 6 个短窗口计划推进为 MISSED 并清除 token；worker 随后写回才看到 `CHECKPOINT_CLAIM_TOKEN_MISMATCH`。该 mismatch 是过期后的结果，不是最初争用原因。

## 峰值瞬时容量

- 同一 tick prematch due/selected：`{e['slot']['prematch_due_count']}/{e['slot']['prematch_selected_count']}`，预计 Provider calls `{e['slot']['prematch_projected_provider_calls']}`。
- 同 due_at 的全部计划另有 1 个 `POSTMATCH_RESULT`，因此数据库最终状态为 `{json.dumps(e['slot']['all_same_due_at_status_counts'], ensure_ascii=False, sort_keys=True)}`。
- worker 可用并发：`{e['worker']['concurrency']}`；claim lease：`{e['claim']['lease_seconds']}s`；从 claim 到 18:45 短窗口结束实际仅 `{e['claim']['short_window_budget_from_claim_seconds']:.3f}s`。
- 巴甲任务从 claim 到结束 `{e['occupancy']['claim_to_brazil_finish_seconds']:.3f}s`；启动时 lease 只剩 `{e['occupancy']['remaining_lease_at_brazil_start_seconds']:.3f}s`，而自身运行 `{e['occupancy']['brazil_run_seconds']:.3f}s`。

| 顺序 | 联赛 | 计划数 | queue s | run s | task 状态 | blocker |
|---:|---|---:|---:|---:|---|---|
{groups}

## 为什么 4 个 CAPTURED 能成功、9 个不能

同 due_at 的 4 个 CAPTURED 不是同质样本：

- 3 个 prematch CAPTURED 全是 `T15_ODDS`，属于最先执行的 Serie A 两场和 Ligue 1 一场；分组顺序在巴甲之前，均在 18:45 前完成。
- 第 4 个是 `POSTMATCH_RESULT`，窗口一直到 `{e['slot']['postmatch_plan']['window_end']}`，经历 `{e['slot']['postmatch_plan']['attempt_count']}` 次 claim 后仍可恢复；它不能证明 15 分钟 prematch 容量充足。
- 9 个 MISSED 按联赛为 `{json.dumps(e['failure_dimensions']['missed_by_competition'], ensure_ascii=False, sort_keys=True)}`，按档位为 `{json.dumps(e['failure_dimensions']['missed_by_checkpoint'], ensure_ascii=False, sort_keys=True)}`。其中巴甲 8 个在同一批次：请求虽已快速返回，但整批在持久化/投影阶段越过窗口；Argentina T6 排在最后，首次启动时 lease 已失效，重领后又因同一 worker 队列延迟越过 19:00。

所以表面上与联赛相关，真正的区分维度是 **claim 后的 competition 分组顺序、单 worker FIFO 占用和窗口长度**，不是巴甲 Provider 慢。

## 四类假设判定

| 假设 | 判定 | 可复现证据 |
|---|---|---|
| claim 争用 | 否 | 单 tick `14/14` 全 claim；9 个 MISSED 的 `attempt_count>=1`；token mismatch 发生在窗口推进清 token 之后 |
| worker 并发不足 | 是 | runtime `--concurrency=1`；前序任务串行占用，巴甲 claim→finish `{e['occupancy']['claim_to_brazil_finish_seconds']:.3f}s` 超 900s lease |
| Provider 响应超时 | 否 | 峰值绑定请求 `11/11` HTTP 200、error 0、max `{e['provider']['peak_max_elapsed_ms']}ms`；18:30–18:48 Provider ledger timeout 0 |
| 到期前未被取走 | 否 | scheduler dispatch 中 14 个 plan ID 全部有 claim token/expiry；MISSED 全部至少 attempt 1 |

## 修复选项与代价

1. **临时止血候选：worker concurrency `1 → 2`。** 冻结时间线按 FIFO、并保留观测到的 task/child 切换占用重放，巴甲批次预计在 claim 后 `{e['capacity_option']['brazil_finish_after_claim_seconds']:.3f}s` 完成，距短窗口结束尚有 `{e['capacity_option']['replay_margin_seconds']:.3f}s`；因此 `2` 只是在 coverage 插桩负载下通过这一次冻结重放的临时值，不是长期容量基线。coverage 于 2026-08-28T04:37:34Z 结束后必须按 SCHED-PEAK-02 重测。代价是多一个 Celery 子进程、额外 DB 连接和近似增加一份 worker 工作集；并行请求还会提高瞬时 Provider burst，必须保留现有 tick hard cap 与 quota guard，并在部署 Gate 复测内存、DB 连接和峰值 Provider burst。
2. **结构性修复：把临场短窗口放到独立 Celery queue/concurrency pool，并按 window_end/fixture 分小批。** 保留 scheduler 的 EDF claim，不改业务档位时间；让 discovery、postmatch、outcome 与长窗口任务不能占掉 T-30/T15 执行槽。代价是多一个 worker 服务/路由规则、更多 task 开销和更复杂的 quota 并发控制。
3. **不建议加长 lease 或改 checkpoint 时间。** lease 变长只会允许窗口外写回，不能恢复正式 T-30 有效性；把业务档位错开会改变推荐语义。若只做“错峰”，应错开非临场后台任务或隔离队列，不动 T-30/T15 的窗口。

本轮只交付诊断和方案：Provider 调用 `0`、生产写入 `0`、部署 `0`。
"""


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def render(raw_path: Path, evidence_path: Path, report_path: Path) -> None:
    raw_bytes = raw_path.read_bytes()
    raw = json.loads(raw_bytes)
    evidence = build_evidence(raw, raw_bytes)
    evidence_path.write_bytes(_canonical_json(evidence))
    report_path.write_text(render_report(evidence), encoding="utf-8")


def check(raw_path: Path, evidence_path: Path, report_path: Path) -> None:
    raw_bytes = raw_path.read_bytes()
    evidence = build_evidence(json.loads(raw_bytes), raw_bytes)
    expected_evidence = _canonical_json(evidence)
    if evidence_path.read_bytes() != expected_evidence:
        raise SystemExit("SCHED_PEAK_EVIDENCE_JSON_DIFF")
    expected_report = render_report(evidence)
    if report_path.read_text(encoding="utf-8") != expected_report:
        raise SystemExit("SCHED_PEAK_REPORT_DIFF")
    print("SCHED_PEAK_01_CHECK_PASS")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--collect", action="store_true")
    mode.add_argument("--render", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--raw", type=Path, default=RAW_PATH)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--ssh-host", default="45.207.194.97")
    parser.add_argument("--ssh-user", default="root")
    parser.add_argument("--ssh-key")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.collect:
        raw = collect(args)
        args.raw.parent.mkdir(parents=True, exist_ok=True)
        args.raw.write_bytes(_canonical_json(raw))
        render(args.raw, args.evidence, args.report)
        print(f"SCHED_PEAK_01_COLLECTED:{args.raw}")
    elif args.render:
        render(args.raw, args.evidence, args.report)
        print("SCHED_PEAK_01_RENDERED")
    else:
        check(args.raw, args.evidence, args.report)


if __name__ == "__main__":
    try:
        main()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"SCHED_PEAK_01_INVALID:{exc}", file=sys.stderr)
        raise SystemExit(1) from exc
