#!/usr/bin/env python3
"""Run and verify the Owner-authorized ten-call XG-PROBE-01."""
# ruff: noqa: E501, S310, S603

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs/review_packages/XG_PROBE_01"
RAW_PATH = PACKAGE / "XG_PROBE_01_RAW_20260824.json"
EVIDENCE_PATH = PACKAGE / "XG_PROBE_01_EVIDENCE_20260824.json"
REPORT_PATH = PACKAGE / "XG_PROBE_01_REPORT_20260824.md"
KICKOFF_CUTOFF = "2026-08-18T00:00:00Z"
SELECTION_SEED = "XG-PROBE-01"
AUTHORIZATION_ID = "XG-PROBE-01_OWNER_10_CALLS"
PROBE_COUNTS = {
    "argentina_primera": 6,
    "eredivisie": 2,
    "ligue_1": 1,
    "bundesliga": 1,
}
HISTORICAL_529 = {
    "argentina_primera": 494,
    "bundesliga": 4,
    "eliteserien": 6,
    "eredivisie": 17,
    "ligue_1": 4,
    "primeira_liga": 4,
}

SELECTION_SQL = rf"""
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
COPY (
WITH league_map AS (
  SELECT DISTINCT competition_id,
         coalesce(payload->>'provider_league_id', payload#>>'{{provider_mapping,league_id}}') AS league_id
  FROM league_season
), fixture_items AS (
  SELECT r.captured_at, item, item#>>'{{fixture,id}}' AS fixture_id
  FROM raw_payload r
  CROSS JOIN LATERAL json_array_elements(r.payload->'response') item
  WHERE r.endpoint='fixtures'
), fixtures AS (
  SELECT DISTINCT ON (fixture_id)
         fixture_id, item#>>'{{league,id}}' AS league_id,
         item#>>'{{fixture,status,short}}' AS status,
         (item#>>'{{fixture,date}}')::timestamptz AS kickoff
  FROM fixture_items
  WHERE fixture_id IS NOT NULL AND fixture_id <> ''
  ORDER BY fixture_id, captured_at DESC
), stat_per_raw AS (
  SELECT r.captured_at, r.payload#>>'{{parameters,fixture}}' AS fixture_id,
         count(DISTINCT item#>>'{{team,id}}') FILTER (WHERE EXISTS (
           SELECT 1 FROM json_array_elements(item->'statistics') s
           WHERE lower(replace(s->>'type',' ','_'))='expected_goals'
         )) AS field_teams,
         count(DISTINCT item#>>'{{team,id}}') FILTER (WHERE EXISTS (
           SELECT 1 FROM json_array_elements(item->'statistics') s
           WHERE lower(replace(s->>'type',' ','_'))='expected_goals'
             AND s->>'value' IS NOT NULL
         )) AS value_teams
  FROM raw_payload r
  LEFT JOIN LATERAL json_array_elements(r.payload->'response') item ON true
  WHERE r.endpoint='statistics'
  GROUP BY r.captured_at, r.payload#>>'{{parameters,fixture}}'
), statistics AS (
  SELECT fixture_id, min(captured_at) AS original_captured_at,
         max(field_teams) AS field_teams, max(value_teams) AS value_teams,
         count(*) AS capture_count
  FROM stat_per_raw
  WHERE fixture_id IS NOT NULL AND fixture_id <> ''
  GROUP BY fixture_id
), missing_statistics AS (
  SELECT s.*
  FROM statistics s
  LEFT JOIN (SELECT DISTINCT fixture_id FROM team_xg_match) x USING (fixture_id)
  WHERE s.value_teams=0 AND x.fixture_id IS NULL
), missing AS (
  SELECT f.fixture_id, l.competition_id, f.kickoff,
         s.original_captured_at, s.field_teams, s.value_teams, s.capture_count
  FROM fixtures f
  JOIN league_map l USING (league_id)
  JOIN missing_statistics s USING (fixture_id)
  WHERE f.status IN ('FT','AET','PEN')
), desired(competition_id, wanted, league_order) AS (
  VALUES ('argentina_primera',6,1),('eredivisie',2,2),('ligue_1',1,3),('bundesliga',1,4)
), ranked AS (
  SELECT m.*, d.wanted, d.league_order,
         row_number() OVER (
           PARTITION BY m.competition_id
           ORDER BY md5(m.fixture_id || ':{SELECTION_SEED}')
         ) AS sample_rank
  FROM missing m JOIN desired d USING (competition_id)
  WHERE m.kickoff < timestamptz '{KICKOFF_CUTOFF}' AND m.field_teams=2
), rows AS (
  SELECT 0 AS sort_group, 0 AS sort_order,
         json_build_object(
           'kind','pool',
           'source_snapshot',transaction_timestamp(),
           'unmaterialized_statistics_null', (SELECT count(*) FROM missing_statistics),
           'joinable_finished', (SELECT count(*) FROM missing),
           'eligible_before_kickoff_cutoff', (SELECT count(*) FROM missing WHERE kickoff < timestamptz '{KICKOFF_CUTOFF}'),
           'eligible_two_sided_null_before_kickoff_cutoff', (SELECT count(*) FROM missing WHERE kickoff < timestamptz '{KICKOFF_CUTOFF}' AND field_teams=2),
           'kickoff_cutoff','{KICKOFF_CUTOFF}',
           'selection_seed','{SELECTION_SEED}'
         )::text AS payload
  UNION ALL
  SELECT 1, league_order * 100 + sample_rank,
         json_build_object(
           'kind','sample','fixture_id',fixture_id,'competition_id',competition_id,
           'kickoff',kickoff,'original_captured_at',original_captured_at,
           'original_expected_goals',json_build_array(NULL,NULL),
           'original_statistics_capture_count',capture_count,
           'sample_rank',sample_rank
         )::text
  FROM ranked WHERE sample_rank <= wanted
)
SELECT payload FROM rows ORDER BY sort_group, sort_order
) TO STDOUT;
ROLLBACK;
"""  # noqa: S608 - constants only; no user input reaches SQL.

PREFLIGHT_SQL = r"""
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
COPY (
WITH latest_quota AS (
  SELECT * FROM provider_quota_observations
  WHERE provider='api_football'
  ORDER BY observed_at DESC LIMIT 1
)
SELECT payload FROM (
  SELECT 1 AS n, json_build_object(
    'kind','runtime','checked_at',now(),
    'schema',(SELECT version_num FROM alembic_version)
  )::text AS payload
  UNION ALL
  SELECT 2, json_build_object(
    'kind','prematch_gate','checked_at',now(),
    'horizon_end',now()+interval '60 minutes',
    'due_count',count(*)
  )::text
  FROM matchday_checkpoint_plans
  WHERE status IN ('PLANNED','DUE') AND window_end > now()
    AND window_start < now()+interval '60 minutes'
    AND checkpoint IN ('T60_ODDS_LINEUPS','T45_ODDS','T45_LINEUPS_RETRY',
                       'T30_LINEUPS_RETRY','T-30m_VALIDATION_LOCK','T15_ODDS')
  UNION ALL
  SELECT 3, json_build_object(
    'kind','quota','provider',provider,'endpoint',endpoint,
    'observed_at',observed_at,'daily_limit',daily_limit,
    'daily_remaining',daily_remaining,'burst_limit',burst_limit,
    'burst_remaining',burst_remaining
  )::text
  FROM latest_quota
) rows ORDER BY n
) TO STDOUT;
ROLLBACK;
"""

REMOTE_PROBE = r'''
import base64, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

manifest = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
expected = {"argentina_primera": 6, "eredivisie": 2, "ligue_1": 1, "bundesliga": 1}
actual = {}
for row in manifest:
    actual[row["competition_id"]] = actual.get(row["competition_id"], 0) + 1
if len(manifest) != 10 or actual != expected or len({r["fixture_id"] for r in manifest}) != 10:
    raise SystemExit("XG_PROBE_MANIFEST_INVALID")
key = os.environ.get("W2_API_FOOTBALL_API_KEY", "").strip()
if not key:
    raise SystemExit("XG_PROBE_PROVIDER_KEY_NOT_VISIBLE")
results = []
for sequence, row in enumerate(manifest, 1):
    fixture_id = str(row["fixture_id"])
    request = urllib.request.Request(
        "https://v3.football.api-sports.io/fixtures/statistics?" + urllib.parse.urlencode({"fixture": fixture_id}),
        headers={"x-apisports-key": key},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
            status = int(response.status)
            headers = {str(k).lower(): str(v) for k, v in dict(response.headers).items()}
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8") or "{}")
        status = int(exc.code)
        headers = {str(k).lower(): str(v) for k, v in dict(exc.headers).items()}
    captured_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    xg = []
    for team in payload.get("response", []) if isinstance(payload, dict) else []:
        if not isinstance(team, dict):
            continue
        value = None
        found = False
        for stat in team.get("statistics", []) if isinstance(team.get("statistics"), list) else []:
            if isinstance(stat, dict) and str(stat.get("type", "")).lower().replace(" ", "_") == "expected_goals":
                value = stat.get("value")
                found = True
                break
        team_obj = team.get("team") if isinstance(team.get("team"), dict) else {}
        xg.append({"team_id": team_obj.get("id"), "team_name": team_obj.get("name"), "field_present": found, "value": value})
    results.append({
        "sequence": sequence,
        "fixture_id": fixture_id,
        "competition_id": row["competition_id"],
        "http_status": status,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "captured_at": captured_at,
        "expected_goals": xg,
        "response_count": len(payload.get("response", [])) if isinstance(payload, dict) and isinstance(payload.get("response"), list) else None,
        "provider_errors": payload.get("errors") if isinstance(payload, dict) else "INVALID_PAYLOAD",
        "quota": {
            "daily_limit": headers.get("x-ratelimit-requests-limit"),
            "daily_remaining": headers.get("x-ratelimit-requests-remaining"),
            "burst_limit": headers.get("x-ratelimit-limit"),
            "burst_remaining": headers.get("x-ratelimit-remaining"),
        },
    })
    if status in (401, 403, 429):
        break
    time.sleep(0.2)
print(json.dumps({"request_count": len(results), "results": results}, ensure_ascii=False, sort_keys=True))
'''


def _ssh_command(args: argparse.Namespace, remote: list[str]) -> list[str]:
    command = ["ssh", "-o", "StrictHostKeyChecking=yes"]
    if args.ssh_key:
        command.extend(("-i", str(args.ssh_key)))
    command.append(args.ssh_host)
    command.extend(remote)
    return command


def _psql(args: argparse.Namespace, sql: str) -> list[dict[str, Any]]:
    command = _ssh_command(
        args,
        ["docker", "exec", "-i", args.postgres_container, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-U", "w2_user", "-d", "w2"],
    )
    result = subprocess.run(command, input=sql, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"XG_PROBE_READ_ONLY_QUERY_FAILED:{result.stderr.strip()}")
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def _one(rows: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    matches = [row for row in rows if row.get("kind") == kind]
    if len(matches) != 1:
        raise ValueError(f"XG_PROBE_KIND_COUNT_INVALID:{kind}:{len(matches)}")
    return matches[0]


def _select(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = _psql(args, SELECTION_SQL)
    pool = _one(rows, "pool")
    manifest = [row for row in rows if row.get("kind") == "sample"]
    counts = Counter(str(row["competition_id"]) for row in manifest)
    if int(pool["unmaterialized_statistics_null"]) != 902:
        raise ValueError("XG_PROBE_SOURCE_902_CHANGED")
    if len(manifest) != 10 or counts != Counter(PROBE_COUNTS):
        raise ValueError(f"XG_PROBE_SAMPLE_INVALID:{len(manifest)}:{dict(counts)}")
    if any(row["original_expected_goals"] != [None, None] for row in manifest):
        raise ValueError("XG_PROBE_ORIGINAL_XG_NOT_NULL")
    return pool, manifest


def _preflight(args: argparse.Namespace) -> dict[str, Any]:
    rows = _psql(args, PREFLIGHT_SQL)
    runtime = _one(rows, "runtime")
    gate = _one(rows, "prematch_gate")
    quota_rows = [row for row in rows if row.get("kind") == "quota"]
    if not quota_rows:
        raise ValueError("XG_PROBE_QUOTA_AUTHORITY_MISSING")
    quota = max(quota_rows, key=lambda row: str(row["observed_at"]))
    if int(gate["due_count"]) != 0:
        raise RuntimeError(f"XG_PROBE_PREMATCH_GATE_CLOSED:{gate['due_count']}")
    remaining = quota.get("daily_remaining")
    burst = quota.get("burst_remaining")
    if remaining is None or int(remaining) - 10 < 1500:
        raise RuntimeError("XG_PROBE_DAILY_RESERVE_UNSAFE")
    if burst is None or int(burst) < 10:
        raise RuntimeError("XG_PROBE_BURST_QUOTA_UNSAFE")
    return {"runtime": runtime, "prematch_gate": gate, "quota_before": quota}


def _call_provider(args: argparse.Namespace, manifest: list[dict[str, Any]]) -> dict[str, Any]:
    encoded = base64.b64encode(json.dumps(manifest, separators=(",", ":")).encode()).decode()
    command = _ssh_command(
        args,
        ["docker", "exec", "-i", args.scheduler_container, "python", "-", encoded],
    )
    result = subprocess.run(command, input=REMOTE_PROBE, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"XG_PROBE_PROVIDER_EXECUTION_FAILED:{result.stderr.strip()}")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("XG_PROBE_PROVIDER_RESULT_NOT_OBJECT")
    if int(payload.get("request_count", -1)) != 10:
        raise RuntimeError(f"XG_PROBE_CALL_COUNT_NOT_10:{payload.get('request_count')}")
    return payload


def _numeric(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return True


def _recovered(call: Mapping[str, Any]) -> bool:
    values = [row.get("value") for row in call["expected_goals"] if row.get("field_present")]
    return len(values) == 2 and all(_numeric(value) for value in values)


def _build_evidence(raw: Mapping[str, Any]) -> dict[str, Any]:
    manifest = raw["sample_selection"]["rows"]
    calls = raw["provider_probe"]["results"]
    if len(manifest) != 10 or len(calls) != 10:
        raise ValueError("XG_PROBE_EVIDENCE_ROW_COUNT_INVALID")
    by_fixture = {str(row["fixture_id"]): row for row in manifest}
    per_league: list[dict[str, Any]] = []
    for league in PROBE_COUNTS:
        league_calls = [row for row in calls if row["competition_id"] == league]
        recovered = sum(_recovered(row) for row in league_calls)
        per_league.append({
            "competition_id": league,
            "sample_n": len(league_calls),
            "numeric_xg_recovered": recovered,
            "recovery_rate": recovered / len(league_calls),
            "historical_529_gap_count": HISTORICAL_529[league],
            "estimated_recovery_in_stratum": HISTORICAL_529[league] * recovered / len(league_calls),
        })
    recovered_total = sum(_recovered(row) for row in calls)
    sampled_gap_count = sum(HISTORICAL_529[row["competition_id"]] for row in per_league)
    unsampled_gap_count = sum(HISTORICAL_529.values()) - sampled_gap_count
    pooled_rate = recovered_total / len(calls)
    estimate = sum(row["estimated_recovery_in_stratum"] for row in per_league) + unsampled_gap_count * pooled_rate
    quota_after = calls[-1]["quota"]
    table = []
    for call in calls:
        original = by_fixture[str(call["fixture_id"])]
        table.append({
            "fixture_id": str(call["fixture_id"]),
            "competition_id": call["competition_id"],
            "kickoff": original["kickoff"],
            "original_captured_at": original["original_captured_at"],
            "original_expected_goals": original["original_expected_goals"],
            "probe_expected_goals": call["expected_goals"],
            "probe_captured_at": call["captured_at"],
            "http_status": call["http_status"],
            "recovered": _recovered(call),
        })
    conclusion = "A_ALL_STILL_NULL_NO_529_ROLLOUT" if recovered_total == 0 else "B_NUMERIC_XG_NOW_AVAILABLE_OWNER_ROLLOUT_DECISION_REQUIRED"
    return {
        "schema_version": "w2.xg_probe_01.evidence.v1",
        "status": conclusion,
        "authorization": raw["authorization"],
        "production": {
            "schema": raw["preflight"]["runtime"]["schema"],
            "provider_calls": 10,
            "database_writes": 0,
            "deployment": False,
            "model_changes": False,
            "ev_se_changes": False,
        },
        "source_pool": raw["sample_selection"]["pool"],
        "prematch_gate": raw["preflight"]["prematch_gate"],
        "quota": {
            "before": raw["preflight"]["quota_before"],
            "after_final_response": quota_after,
        },
        "probe_table": table,
        "per_league_recovery": per_league,
        "historical_529_estimate": {
            "gap_count": 529,
            "sampled_strata_gap_count": sampled_gap_count,
            "unsampled_strata_gap_count": unsampled_gap_count,
            "unsampled_strata": [league for league in HISTORICAL_529 if league not in PROBE_COUNTS],
            "unsampled_extrapolation_rate": pooled_rate,
            "estimated_recoverable": estimate,
            "full_census_provider_calls": 529,
            "estimate_is_sampling_not_authorization": True,
        },
        "conclusion": {
            "classification": conclusion,
            "numeric_xg_recovered": recovered_total,
            "sample_n": 10,
            "owner_decision": "DO_NOT_RETRY_529" if recovered_total == 0 else "OWNER_DECIDES_BOUNDED_ROLLOUT",
        },
    }


def _fmt_xg(rows: list[dict[str, Any]]) -> str:
    return " / ".join(
        f"{row.get('team_name') or row.get('team_id')}="
        f"{'null' if row.get('value') is None else row.get('value')}"
        for row in rows
    )


def _render_report(evidence: Mapping[str, Any]) -> str:
    table = "\n".join(
        f"| `{row['fixture_id']}` | `{row['competition_id']}` | {row['kickoff']} | {row['original_captured_at']} | `null / null` | {_fmt_xg(row['probe_expected_goals'])} | {row['probe_captured_at']} |"
        for row in evidence["probe_table"]
    )
    leagues = "\n".join(
        f"| `{row['competition_id']}` | {row['numeric_xg_recovered']}/{row['sample_n']} | {row['recovery_rate']:.1%} | {row['historical_529_gap_count']} | {row['estimated_recovery_in_stratum']:.2f} |"
        for row in evidence["per_league_recovery"]
    )
    estimate = evidence["historical_529_estimate"]
    quota = evidence["quota"]
    conclusion = evidence["conclusion"]
    if conclusion["numeric_xg_recovered"] == 0:
        decision = "10/10 仍无 numeric xG，按预注册分支 A：不应铺开 529 场重试；这些历史缺口进入 Provider 不可得 / fail-closed 设计。"
    else:
        decision = f"10 场中 {conclusion['numeric_xg_recovered']} 场已恢复 numeric xG，按预注册分支 B：提交 Owner 决定是否铺开；分层加权并对未抽样 10 场使用样本 pooled rate 的估算为 {estimate['estimated_recoverable']:.2f}/529，完整逐场 census 需要 529 次调用。"
    return f"""# XG-PROBE-01 — 有界 Provider 重试探针

Status: `{evidence['status']}`

## 结论

{decision}

这是 Provider 可得性探针，不写 `raw_payload`、`team_xg_match`、Provider ledger 或任何业务表。Provider calls / production writes / deploy / model changes / EV-SE changes = `10 / 0 / 0 / 0 / 0`。

## 执行门与额度

- 临场门：`{evidence['prematch_gate']['checked_at']}` 至 `{evidence['prematch_gate']['horizon_end']}`，正式档位 `{evidence['prematch_gate']['due_count']}`。
- 执行前额度：daily `{quota['before']['daily_remaining']}/{quota['before']['daily_limit']}`，burst `{quota['before']['burst_remaining']}/{quota['before']['burst_limit']}`，authority at `{quota['before']['observed_at']}`。
- 第 10 次响应后额度：daily `{quota['after_final_response']['daily_remaining']}/{quota['after_final_response']['daily_limit']}`，burst `{quota['after_final_response']['burst_remaining']}/{quota['after_final_response']['burst_limit']}`。
- 样本从冻结的 902 场集合中选；先要求 kickoff `< {KICKOFF_CUTOFF}`，再要求原响应两队 xG 都为 null。联赛内按 `md5(fixture_id || ':{SELECTION_SEED}')` 排序，禁止按本次结果挑样。

## 10 行对照

| fixture | league | kickoff | original captured_at | original xG | current xG | probe captured_at |
|---|---|---|---|---|---|---|
{table}

## 按联赛恢复率与 529 场估算

| league | recovered / n | recovery rate | historical gap | estimated recovery |
|---|---:|---:|---:|---:|
{leagues}

529 场中，抽样联赛覆盖历史缺口 `{estimate['sampled_strata_gap_count']}` 场；未抽样的 `{estimate['unsampled_strata_gap_count']}` 场来自 `{', '.join(estimate['unsampled_strata'])}`。后者的估算只能外推本次 pooled recovery rate，不能冒充逐联赛实测。完整铺开额度是逐场一次、共 `{estimate['full_census_provider_calls']}` 次；本报告不授权铺开或生产写入。

## 可复现与失败条件

`python scripts/run_xg_provider_retry_probe.py --check` 只读取冻结 raw probe，不访问生产或 Provider；它重建本 JSON 和本报告并逐字段比较。样本数、联赛配额、902 来源集合、临场门、10 次调用、每行 fixture 绑定、quota header 与表内任一数值漂移都会失败。
"""


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _validate_raw(raw: Mapping[str, Any]) -> None:
    if raw.get("schema_version") != "w2.xg_probe_01.raw.v1":
        raise ValueError("XG_PROBE_RAW_SCHEMA_INVALID")
    auth = raw.get("authorization", {})
    if auth != {"authorization_id": AUTHORIZATION_ID, "approved_calls": 10, "executed_calls": 10}:
        raise ValueError("XG_PROBE_AUTHORIZATION_INVALID")
    if int(raw["preflight"]["prematch_gate"]["due_count"]) != 0:
        raise ValueError("XG_PROBE_FROZEN_PREMATCH_GATE_NOT_ZERO")
    manifest = raw["sample_selection"]["rows"]
    calls = raw["provider_probe"]["results"]
    if len(manifest) != 10 or len(calls) != 10 or int(raw["provider_probe"]["request_count"]) != 10:
        raise ValueError("XG_PROBE_FROZEN_CALL_COUNT_INVALID")
    if Counter(row["competition_id"] for row in manifest) != Counter(PROBE_COUNTS):
        raise ValueError("XG_PROBE_FROZEN_LEAGUE_COUNTS_INVALID")
    if int(raw["sample_selection"]["pool"]["unmaterialized_statistics_null"]) != 902:
        raise ValueError("XG_PROBE_FROZEN_902_INVALID")
    for manifest_row, call in zip(manifest, calls, strict=True):
        if str(manifest_row["fixture_id"]) != str(call["fixture_id"]):
            raise ValueError("XG_PROBE_FIXTURE_BINDING_INVALID")
        if manifest_row["original_expected_goals"] != [None, None]:
            raise ValueError("XG_PROBE_ORIGINAL_XG_INVALID")
        if int(call["http_status"]) != 200 or call.get("provider_errors") not in ({}, [], None):
            raise ValueError("XG_PROBE_PROVIDER_RESPONSE_INVALID")
        if call["quota"].get("daily_remaining") is None:
            raise ValueError("XG_PROBE_QUOTA_HEADER_MISSING")


def _write_outputs(raw: Mapping[str, Any], evidence_path: Path, report_path: Path) -> None:
    evidence = _build_evidence(raw)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(_json_text(evidence), encoding="utf-8")
    report_path.write_text(_render_report(evidence), encoding="utf-8")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"XG_PROBE_JSON_OBJECT_REQUIRED:{path}")
    return value


def _execute(args: argparse.Namespace) -> None:
    if args.raw.exists():
        raise RuntimeError("XG_PROBE_ALREADY_EXECUTED_REFUSING_SECOND_10_CALL_RUN")
    pool, manifest = _select(args)
    preflight = _preflight(args)
    provider = _call_provider(args, manifest)
    raw = {
        "schema_version": "w2.xg_probe_01.raw.v1",
        "authorization": {"authorization_id": AUTHORIZATION_ID, "approved_calls": 10, "executed_calls": provider["request_count"]},
        "sample_selection": {"pool": pool, "rows": manifest},
        "preflight": preflight,
        "provider_probe": provider,
    }
    _validate_raw(raw)
    args.raw.parent.mkdir(parents=True, exist_ok=True)
    args.raw.write_text(_json_text(raw), encoding="utf-8")
    _write_outputs(raw, args.evidence, args.report)
    print(f"XG_PROBE_EXECUTED calls=10 raw={args.raw}")


def _check(args: argparse.Namespace) -> None:
    raw = _load(args.raw)
    _validate_raw(raw)
    expected_evidence = _json_text(_build_evidence(raw))
    actual_evidence = args.evidence.read_text(encoding="utf-8")
    if actual_evidence != expected_evidence:
        raise ValueError("XG_PROBE_EVIDENCE_JSON_DIFF")
    evidence = json.loads(expected_evidence)
    expected_report = _render_report(evidence)
    if args.report.read_text(encoding="utf-8") != expected_report:
        raise ValueError("XG_PROBE_REPORT_DIFF")
    print("XG_PROBE_CHECK_PASS")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--render", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--ssh-host", default="root@45.207.194.97")
    parser.add_argument("--ssh-key", type=Path)
    parser.add_argument("--postgres-container", default="w2-staging-postgres-1")
    parser.add_argument("--scheduler-container", default="w2-staging-scheduler-1")
    parser.add_argument("--raw", type=Path, default=RAW_PATH)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if args.execute:
            _execute(args)
        elif args.preflight:
            pool, manifest = _select(args)
            print(_json_text({"pool": pool, "manifest": manifest, "preflight": _preflight(args)}), end="")
        elif args.render:
            raw = _load(args.raw)
            _validate_raw(raw)
            _write_outputs(raw, args.evidence, args.report)
            print("XG_PROBE_RENDERED")
        else:
            _check(args)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
