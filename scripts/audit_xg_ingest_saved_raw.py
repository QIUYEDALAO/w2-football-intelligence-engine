#!/usr/bin/env python3
"""Reproduce XG-INGEST-01 from persisted evidence without Provider calls or writes."""
# ruff: noqa: E501, S608

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OBSERVED_AT = "2026-08-23T15:40:00Z"
POST_BACKFILL_KICKOFF = "2026-08-18T00:00:00Z"
RELEASE_ID = "d05ab74217e37af2e85732ac3a63ee4d9e214aa1"
SCHEMA = "0070_notification_delivery_routing"
DEFAULT_JSON = ROOT / "docs/review_packages/XG_INGEST_01/XG_INGEST_01_EVIDENCE_20260823.json"
DEFAULT_MARKDOWN = ROOT / "docs/review_packages/XG_INGEST_01/XG_INGEST_01_REPORT_20260823.md"

SQL = rf"""
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
COPY (
WITH enabled AS (
  SELECT competition_id,
         coalesce(payload->>'provider_league_id', payload#>>'{{provider_mapping,league_id}}') AS league_id
  FROM league_season
  WHERE (payload->>'enabled')::boolean IS TRUE
), fixture_items AS (
  SELECT r.captured_at, item, item#>>'{{fixture,id}}' AS fixture_id
  FROM raw_payload r
  CROSS JOIN LATERAL json_array_elements(r.payload->'response') item
  WHERE r.endpoint = 'fixtures'
    AND r.captured_at <= timestamptz '{OBSERVED_AT}'
), fixtures AS (
  SELECT DISTINCT ON (fixture_id)
         fixture_id, item#>>'{{league,id}}' AS league_id,
         item#>>'{{fixture,status,short}}' AS status,
         (item#>>'{{fixture,date}}')::timestamptz AS kickoff
  FROM fixture_items
  WHERE fixture_id IS NOT NULL AND fixture_id <> ''
  ORDER BY fixture_id, captured_at DESC
), stat_per_raw AS (
  SELECT r.sha256, r.captured_at,
         r.payload#>>'{{parameters,fixture}}' AS fixture_id,
         count(DISTINCT item#>>'{{team,id}}') FILTER (WHERE EXISTS (
           SELECT 1 FROM json_array_elements(item->'statistics') s
           WHERE lower(replace(s->>'type', ' ', '_')) = 'expected_goals'
         )) AS field_teams,
         count(DISTINCT item#>>'{{team,id}}') FILTER (WHERE EXISTS (
           SELECT 1 FROM json_array_elements(item->'statistics') s
           WHERE lower(replace(s->>'type', ' ', '_')) = 'expected_goals'
             AND s->>'value' IS NOT NULL
         )) AS value_teams
  FROM raw_payload r
  LEFT JOIN LATERAL json_array_elements(r.payload->'response') item ON true
  WHERE r.endpoint = 'statistics'
    AND r.captured_at <= timestamptz '{OBSERVED_AT}'
  GROUP BY r.sha256, r.captured_at, r.payload#>>'{{parameters,fixture}}'
), statistics AS (
  SELECT fixture_id, max(field_teams) AS field_teams,
         max(value_teams) AS value_teams, min(captured_at) AS first_captured_at,
         max(captured_at) AS last_captured_at
  FROM stat_per_raw
  WHERE fixture_id IS NOT NULL AND fixture_id <> ''
  GROUP BY fixture_id
), persisted AS (
  SELECT fixture_id, count(*) AS row_count, count(DISTINCT team_id) AS team_count,
         count(*) FILTER (WHERE xg_for IS NULL OR xg_against IS NULL) AS null_row_count,
         min(captured_at) AS first_materialized_at
  FROM team_xg_match
  WHERE captured_at <= timestamptz '{OBSERVED_AT}'
  GROUP BY fixture_id
), universe AS (
  SELECT f.fixture_id, e.competition_id, f.status, f.kickoff,
         coalesce(s.field_teams, 0) AS field_teams,
         coalesce(s.value_teams, 0) AS value_teams,
         s.first_captured_at, s.last_captured_at,
         coalesce(p.row_count, 0) AS persisted_rows,
         coalesce(p.team_count, 0) AS persisted_teams,
         coalesce(p.null_row_count, 0) AS persisted_null_rows,
         p.first_materialized_at
  FROM fixtures f
  JOIN enabled e USING (league_id)
  LEFT JOIN statistics s USING (fixture_id)
  LEFT JOIN persisted p USING (fixture_id)
  WHERE f.status IN ('FT', 'AET', 'PEN')
    AND f.kickoff >= timestamptz '2025-01-01T00:00:00Z'
    AND f.kickoff < timestamptz '{OBSERVED_AT}'
), by_competition AS (
  SELECT competition_id, count(*) AS finished_fixtures,
         count(*) FILTER (WHERE persisted_teams = 2 AND persisted_rows = 2) AS persisted_fixtures,
         count(*) FILTER (WHERE value_teams = 2 AND persisted_teams = 0) AS numeric_raw_not_persisted,
         count(*) FILTER (
           WHERE kickoff < timestamptz '{POST_BACKFILL_KICKOFF}'
             AND field_teams = 2 AND value_teams = 0 AND persisted_teams = 0
         ) AS null_cached_retry_required,
         count(*) FILTER (
           WHERE kickoff < timestamptz '{POST_BACKFILL_KICKOFF}'
             AND field_teams = 0 AND value_teams = 0 AND persisted_teams = 0
         ) AS source_absent_not_replayable,
         count(*) FILTER (
           WHERE kickoff >= timestamptz '{POST_BACKFILL_KICKOFF}'
             AND persisted_teams = 0
         ) AS provider_pending,
         count(*) FILTER (
           WHERE kickoff >= timestamptz '{POST_BACKFILL_KICKOFF}'
             AND persisted_teams = 2 AND persisted_rows = 2
         ) AS post_backfill_published
  FROM universe GROUP BY competition_id
), daily AS (
  SELECT captured_at::date AS captured_date, count(*) AS statistics_payloads,
         count(*) FILTER (WHERE field_teams = 2) AS expected_goals_field_two_sides,
         count(*) FILTER (WHERE value_teams = 2) AS numeric_xg_two_sides,
         count(*) FILTER (WHERE value_teams = 2 AND p.fixture_id IS NOT NULL) AS materialized_fixtures
  FROM stat_per_raw r
  LEFT JOIN persisted p USING (fixture_id)
  GROUP BY captured_at::date
), xg_latency_rows AS (
  SELECT fixture_id, min(kickoff_at) AS kickoff, min(captured_at) AS captured_at
  FROM team_xg_match
  WHERE captured_at <= timestamptz '{OBSERVED_AT}'
  GROUP BY fixture_id
), latency AS (
  SELECT count(*) AS n,
         percentile_cont(0.5) WITHIN GROUP (
           ORDER BY extract(epoch FROM (captured_at - kickoff)) / 3600.0
         ) AS p50_hours,
         percentile_cont(0.9) WITHIN GROUP (
           ORDER BY extract(epoch FROM (captured_at - kickoff)) / 3600.0
         ) AS p90_hours,
         max(extract(epoch FROM (captured_at - kickoff)) / 3600.0) AS max_hours
  FROM xg_latency_rows
  WHERE kickoff >= timestamptz '{POST_BACKFILL_KICKOFF}'
), samples AS (
  SELECT fixture_id, competition_id, kickoff, first_captured_at, last_captured_at,
         field_teams, value_teams, persisted_rows
  FROM universe
  WHERE kickoff < timestamptz '{POST_BACKFILL_KICKOFF}'
    AND field_teams = 2 AND value_teams = 0 AND persisted_teams = 0
  ORDER BY competition_id, kickoff, fixture_id LIMIT 20
), source_counts AS (
  SELECT
    (SELECT count(*) FROM raw_payload WHERE endpoint='statistics' AND captured_at <= timestamptz '{OBSERVED_AT}') AS raw_statistics_payloads,
    (SELECT count(*) FROM team_xg_match WHERE captured_at <= timestamptz '{OBSERVED_AT}') AS team_xg_match_rows,
    (SELECT count(DISTINCT fixture_id) FROM team_xg_match WHERE captured_at <= timestamptz '{OBSERVED_AT}') AS team_xg_match_fixtures,
    (SELECT count(*) FROM enabled) AS enabled_competitions
)
SELECT payload FROM (
SELECT 10 AS sort_group, competition_id AS sort_key,
       json_build_object(
         'kind','competition', 'competition_id',competition_id,
         'finished_fixtures',finished_fixtures,
         'persisted_fixtures',persisted_fixtures,
         'numeric_raw_not_persisted',numeric_raw_not_persisted,
         'null_cached_retry_required',null_cached_retry_required,
         'source_absent_not_replayable',source_absent_not_replayable,
         'provider_pending',provider_pending,
         'post_backfill_published',post_backfill_published,
         'coverage_before',round(persisted_fixtures::numeric / nullif(finished_fixtures,0), 6),
         'provider_zero_replay_additions',numeric_raw_not_persisted,
         'coverage_after_provider_zero_replay',round((persisted_fixtures + numeric_raw_not_persisted)::numeric / nullif(finished_fixtures,0), 6)
       )::text AS payload
FROM by_competition
UNION ALL
SELECT 20, captured_date::text,
       json_build_object(
         'kind','daily_capture','captured_date',captured_date,
         'statistics_payloads',statistics_payloads,
         'expected_goals_field_two_sides',expected_goals_field_two_sides,
         'numeric_xg_two_sides',numeric_xg_two_sides,
         'materialized_fixtures',materialized_fixtures,
         'null_value_responses',expected_goals_field_two_sides - numeric_xg_two_sides
       )::text
FROM daily
UNION ALL
SELECT 30, 'latency', json_build_object(
  'kind','provider_publication_latency','kickoff_from','{POST_BACKFILL_KICKOFF}',
  'n',n,'p50_hours',round(p50_hours::numeric,1),
  'p90_hours',round(p90_hours::numeric,1),'max_hours',round(max_hours::numeric,1)
)::text FROM latency
UNION ALL
SELECT 40, fixture_id, json_build_object(
  'kind','null_cached_sample','fixture_id',fixture_id,'competition_id',competition_id,
  'kickoff',kickoff,'first_captured_at',first_captured_at,'last_captured_at',last_captured_at,
  'field_teams',field_teams,'value_teams',value_teams,'persisted_rows',persisted_rows
)::text FROM samples
UNION ALL
SELECT 50, 'source_counts', json_build_object(
  'kind','source_counts','raw_statistics_payloads',raw_statistics_payloads,
  'team_xg_match_rows',team_xg_match_rows,'team_xg_match_fixtures',team_xg_match_fixtures,
  'enabled_competitions',enabled_competitions
)::text FROM source_counts
) evidence_rows
ORDER BY sort_group, sort_key
) TO STDOUT;
ROLLBACK;
"""


def _load_rows(lines: Iterable[str]) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in lines if line.strip()]
    if any(not isinstance(row, dict) or "kind" not in row for row in rows):
        raise ValueError("XG_INGEST_SOURCE_ROW_INVALID")
    return rows


def _run_read_only(args: argparse.Namespace) -> list[dict[str, Any]]:
    command = ["ssh", "-o", "StrictHostKeyChecking=yes"]
    if args.ssh_key:
        command.extend(("-i", str(args.ssh_key)))
    command.extend(
        (
            args.ssh_host,
            "docker exec -i w2-staging-postgres-1 psql -X -qAt -v ON_ERROR_STOP=1 -U w2_user -d w2",
        )
    )
    result = subprocess.run(command, input=SQL, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"XG_INGEST_READ_ONLY_QUERY_FAILED:{result.stderr.strip()}")
    return _load_rows(result.stdout.splitlines())


def _one(rows: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    matches = [row for row in rows if row["kind"] == kind]
    if len(matches) != 1:
        raise ValueError(f"XG_INGEST_SOURCE_KIND_COUNT_INVALID:{kind}:{len(matches)}")
    return matches[0]


def build_evidence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    competitions = [row for row in rows if row["kind"] == "competition"]
    daily = [row for row in rows if row["kind"] == "daily_capture"]
    latency = _one(rows, "provider_publication_latency")
    source = _one(rows, "source_counts")
    null_samples = [row for row in rows if row["kind"] == "null_cached_sample"]
    totals = {
        field: sum(int(row[field]) for row in competitions)
        for field in (
            "numeric_raw_not_persisted",
            "null_cached_retry_required",
            "source_absent_not_replayable",
            "provider_pending",
            "post_backfill_published",
            "provider_zero_replay_additions",
        )
    }
    if totals != {
        "numeric_raw_not_persisted": 0,
        "null_cached_retry_required": 529,
        "source_absent_not_replayable": 11,
        "provider_pending": 15,
        "post_backfill_published": 54,
        "provider_zero_replay_additions": 0,
    }:
        raise ValueError(f"XG_INGEST_FROZEN_CLASSIFICATION_CHANGED:{totals}")
    if int(source["team_xg_match_fixtures"]) != 9423 or int(source["team_xg_match_rows"]) != 18846:
        raise ValueError("XG_INGEST_VERIFIER_WHOLE_FIXTURE_INVARIANT_CHANGED")
    if (
        int(latency["n"]) != 56
        or float(latency["p50_hours"]) != 18.2
        or float(latency["p90_hours"]) != 80.8
        or float(latency["max_hours"]) != 127.8
    ):
        raise ValueError("XG_INGEST_PROVIDER_LATENCY_LINEAGE_CHANGED")
    return {
        "schema_version": "w2.xg_ingest_01.evidence.v1",
        "status": "ROOT_CAUSE_CONFIRMED_PROVIDER_ZERO_REPLAY_BLOCKED_NO_NUMERIC_RAW_PRODUCTION_CHANGE_NOT_AUTHORIZED",
        "observed_at": OBSERVED_AT,
        "production": {
            "release_id": RELEASE_ID,
            "schema": SCHEMA,
            "provider_calls": 0,
            "database_writes": 0,
            "outcomes_read": 0,
        },
        "scope": {
            "source": "league_season.payload.enabled",
            "enabled_competition_count_observed": int(source["enabled_competitions"]),
            "kickoff_from": "2025-01-01T00:00:00Z",
            "post_backfill_kickoff_from": POST_BACKFILL_KICKOFF,
            "coverage_average_computed": False,
        },
        "root_cause": {
            "classification": "NULL_STATISTICS_CAPTURE_TREATED_AS_TERMINAL_CACHE_HIT",
            "reproducible_predicate": [
                "finished fixture in enabled league",
                "both Provider team blocks contain expected_goals field",
                "both expected_goals values are JSON null",
                "no later numeric saved-raw capture exists",
                "raw_statistics_fixture_ids nevertheless marks fixture cached by parameters.fixture",
                "parse_team_xg_matches returns zero rows before persistence",
            ],
            "null_cached_retry_required_fixtures": totals["null_cached_retry_required"],
            "numeric_saved_raw_not_materialized_fixtures": totals["numeric_raw_not_persisted"],
            "identity_filter_or_transaction_rollback": False,
            "write_path_reached_for_529": False,
            "production_release_source_code_chain": [
                "src/w2/features/xg_materialization.py:_stat_value rejects null",
                "src/w2/features/xg_materialization.py:parse_team_xg_matches requires both teams",
                "production release d05ab742 raw_statistics_fixture_ids ignores xG completeness",
                "src/w2/ingestion/xg_backfill.py skips every fixture in that cache set",
            ],
            "samples": null_samples,
        },
        "whole_fixture_invariant": {
            "source": "VERIFIER_CONFIRMED_SKIP_RECOMPUTE_PER_OWNER_PATCH",
            "team_xg_match_fixtures": 9423,
            "team_xg_match_rows": 18846,
            "rows_per_fixture": 2,
            "partial_fixture_count": 0,
            "null_xg_for_rows": 0,
            "null_xg_against_rows": 0,
            "original_869_is_exact_not_lower_bound": True,
        },
        "capture_day_lineage": daily,
        "provider_publication_latency": {
            **latency,
            "scope": "ALL_MATERIALIZED_MATCHES_NOT_ENABLED_COVERAGE_SCOPE",
            "enabled_post_backfill_published_fixtures": totals["post_backfill_published"],
            "outside_current_enabled_scope_fixtures": int(latency["n"])
            - totals["post_backfill_published"],
        },
        "per_competition": competitions,
        "classification_totals_without_coverage_average": totals,
        "provider_zero_replay": {
            "status": "BLOCKED_NO_NUMERIC_SAVED_RAW_FOR_THE_529",
            "recoverable_fixtures": totals["provider_zero_replay_additions"],
            "reason": "THE_529_SAVED_RESPONSES_CONTAIN_EXPECTED_GOALS_KEYS_WITH_JSON_NULL_VALUES;_TEAM_XG_MATCH_REQUIRES_NUMERIC_NON_NULL_VALUES",
            "production_write_executed": False,
            "provider_call_executed": False,
            "next_decision_required": "OWNER_MUST_SEPARATELY_AUTHORIZE_BOUNDED_PROVIDER_RETRY_AND_PRODUCTION_WRITE",
        },
        "prevention": {
            "collector_change": "ONLY_TWO_SIDED_NUMERIC_XG_MAY_SATISFY_THE_STATISTICS_CACHE;_NULL_OR_ABSENT_XG_REMAINS_RETRYABLE",
            "implementation_state": "LOCAL_ONLY_NOT_DEPLOYED",
            "alarm": "FAIL_WHEN_TWO_SIDED_NUMERIC_SAVED_RAW_LACKS_EXACTLY_TWO_NON_NULL_TEAM_XG_MATCH_ROWS",
            "provider_pending_separate": True,
            "no_age_or_model_threshold": True,
            "deployment_executed": False,
        },
    }


def _render_markdown(evidence: Mapping[str, Any]) -> str:
    totals = evidence["classification_totals_without_coverage_average"]
    latency = evidence["provider_publication_latency"]
    competition_rows = "\n".join(
        f"| `{row['competition_id']}` | {row['finished_fixtures']} | {row['persisted_fixtures']} | "
        f"{row['null_cached_retry_required']} | {row['source_absent_not_replayable']} | "
        f"{row['provider_pending']} | {row['provider_zero_replay_additions']} | "
        f"{float(row['coverage_before']):.6f} | {float(row['coverage_after_provider_zero_replay']):.6f} |"
        for row in evidence["per_competition"]
    )
    daily_rows = "\n".join(
        f"| {row['captured_date']} | {row['statistics_payloads']} | "
        f"{row['expected_goals_field_two_sides']} | {row['numeric_xg_two_sides']} | "
        f"{row['materialized_fixtures']} | {row['null_value_responses']} |"
        for row in evidence["capture_day_lineage"]
    )
    return f"""# XG-INGEST-01 — saved-raw 入库缺口复核

Status: `{evidence["status"]}`

## 结论

根因已确定：缺口不是 numeric xG 在写入事务里丢失，而是 **两队 `expected_goals` 字段存在、值却为 JSON `null` 的 statistics 响应被错误当成永久 cache hit**。解析器对这类 payload 正确地产出 0 行；错误发生在其后续状态语义——`raw_statistics_fixture_ids()` 只凭 `parameters.fixture` 判定“已缓存”，后续采集从此不再请求。529 场均未到达 `upsert_team_xg_matches()`，因此球队身份解析、批次写入和事务回滚不是这 529 场的原因。

冻结口径下，真正的“numeric saved raw 已存在但未物化”是 `{totals["numeric_raw_not_persisted"]}`。所以现存 raw 的 Provider 0 重放可新增 `{totals["provider_zero_replay_additions"]}` 场，不能把 529 个 `null` 变成数值。执行虚假的数据库回补会违反非空数值契约；实际补齐需要 Owner 另行批准有界 Provider 重试及生产写入，本轮均未执行。

Provider calls / production writes / outcomes reads: `0 / 0 / 0`。

## 精确分类

- null 响应被终态缓存、需要重新采集：`{totals["null_cached_retry_required"]}` 场。
- 历史 payload 原本无 `expected_goals` 字段：`{totals["source_absent_not_replayable"]}` 场，不是入库缺陷。
- 2026-08-18 后仍在 Provider 发布窗内：`{totals["provider_pending"]}` 场，单列，不算残余丢失。
- 当前启用集合内，2026-08-18 后已经发布并落库：`{totals["post_backfill_published"]}` 场。
- Provider 落库滞后统计沿用核验方的全体已物化口径：p50 / p90 / max = `{latency["p50_hours"]}h / {latency["p90_hours"]}h / {latency["max_hours"]}h`（n=`{latency["n"]}`）。该 n 比当前启用集合的 54 场多 2 场，二者不是同一分母，绝不混算覆盖率。
- 核验方已确认 `9,423` 场每场恰好 2 行、单边和空字段均为 0；按 Owner 补丁不重复投入。原 869 是精确值，不是下界。

## 逐联赛回补前后

不计算整体覆盖均值。`Provider 0 后` 是真实可重放结果，不是假设 Provider 已发布；因此本冻结样本中与回补前相同。`null cached` 是需要重新请求 Provider 的历史缺口，`provider pending` 是尚在正常发布窗内的比赛，`source absent` 是历史 payload 根本没有 xG 字段；三者不得合并为残余入库丢失。

| competition | finished | persisted | null cached | source absent | provider pending | Provider 0 additions | coverage before | coverage after Provider 0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{competition_rows}

## 采集日血缘

“含 expected_goals”必须区分字段存在与数值存在。原交接数字对应前者；只有后者能进入非空 Float 列。

| captured date | statistics raw | field on both sides | numeric on both sides | materialized | field present but null |
|---|---:|---:|---:|---:|---:|
{daily_rows}

## 防复发

1. cache 命中条件改为“两队 numeric xG 完整”，null/缺字段保持 retryable；该代码变更只在本地验证，未部署。
2. 独立 guard 只在“numeric saved raw 已存在但 team_xg_match 不是恰好两条非空行”时报警；Provider pending 不混入该报警。
3. 529 场历史补齐需要新的 Provider 权限与生产写入决策。没有授权前，报告保持 blocked，不自行执行。

## 可复现边界

- production release: `{RELEASE_ID}`; schema: `{SCHEMA}`; observed at: `{OBSERVED_AT}`。
- scope 动态读取 `league_season.payload.enabled`，没有固定联赛数量。
- SQL 是 `REPEATABLE READ READ ONLY`；不读取 outcomes。
- `--check` 逐字比较 JSON 与 Markdown，单字段 1e-6 变异会失败。
"""


def _self_check() -> None:
    required = {
        "src/w2/features/xg_materialization.py": (
            "def statistics_xg_by_team(",
            "if value is None:",
            "if home_id not in xg_by_team or away_id not in xg_by_team:",
        ),
        "src/w2/ingestion/future_refresh_repository.py": (
            "def raw_statistics_fixture_ids(self) -> set[str]:",
            "Return only fixtures with complete, numeric two-sided xG evidence.",
            "len(statistics_xg_by_team(payload)) == 2",
        ),
        "src/w2/ingestion/xg_backfill.py": (
            "cached_statistics = self.repository.raw_statistics_fixture_ids()",
            "if fixture_id in cached_statistics:",
        ),
    }
    for relative, fragments in required.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        if any(fragment not in text for fragment in fragments):
            raise AssertionError(f"XG_INGEST_SOURCE_CONTRACT_CHANGED:{relative}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ssh-host", default="root@45.207.194.97")
    parser.add_argument("--ssh-key", type=Path)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    _self_check()
    if args.self_check:
        print(json.dumps({"self_check": "PASS"}, sort_keys=True))
        return
    evidence = build_evidence(_run_read_only(args))
    rendered_json = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    rendered_markdown = _render_markdown(evidence)
    if args.check:
        if args.output_json.read_text(encoding="utf-8") != rendered_json:
            raise SystemExit("XG_INGEST_EVIDENCE_JSON_DIFF")
        if args.output_markdown.read_text(encoding="utf-8") != rendered_markdown:
            raise SystemExit("XG_INGEST_REPORT_MARKDOWN_DIFF")
        print(json.dumps({"reproduction": "PASS"}, sort_keys=True))
        return
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(rendered_json, encoding="utf-8")
    args.output_markdown.write_text(rendered_markdown, encoding="utf-8")
    print(json.dumps({"provider_calls": 0, "production_database_writes": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
