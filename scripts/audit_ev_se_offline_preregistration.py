#!/usr/bin/env python3
"""Reproduce the frozen EV-SE preregistration evidence without production writes."""
# ruff: noqa: E501, S608

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from w2.domain.canonical_serialization import HashDomain, canonical_sha256

OBSERVED_AT = "2026-08-23T12:00:50Z"
RELEASE_ID = "d05ab74217e37af2e85732ac3a63ee4d9e214aa1"
SCHEMA = "0070_notification_delivery_routing"
CORPUS_SHA256 = "d19b217afe159c87dbf8d0dea87c260374ac9d18ffd8bb97581cfffe858cedc5"
CORPUS_FILE_SHA256 = "80e49d1a32b5dd9653d41826e87415acff0d32a6804dea408f3b99737a6ab5e2"
CORPUS_SNAPSHOT = "2026-08-22T05:50:41.929427Z"
CORPUS_ROWS = 38_706
FLOAT_TOLERANCE = 0.000001
ACTIVE_COMPETITIONS = frozenset(
    {
        "argentina_primera",
        "brasileirao_serie_a",
        "bundesliga",
        "eliteserien",
        "eredivisie",
        "la_liga",
        "ligue_1",
        "mls",
        "premier_league",
        "primeira_liga",
        "serie_a",
    }
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = ROOT / (
    "docs/review_packages/EV_SE_OFFLINE_VALIDATION/"
    "EV_SE_OFFLINE_PREREGISTRATION_EVIDENCE_20260823.json"
)
DEFAULT_MARKDOWN = ROOT / (
    "docs/review_packages/EV_SE_OFFLINE_VALIDATION/"
    "EV_SE_OFFLINE_PREREGISTRATION_BASELINE_20260823.md"
)

SQL = r"""
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

COPY (
WITH frozen_evaluations AS (
  SELECT e.evaluation_id, e.fixture_id, e.market, e.selection, e.evaluated_at,
         coalesce(e.recorded_at, e.evaluated_at) AS frozen_at,
         (e.payload->>'current_ev')::float8
           - (e.payload->>'current_ev_minus_se')::float8 AS ev_se
  FROM dynamic_prematch_evaluations e
  WHERE e.payload->>'current_ev' IS NOT NULL
    AND e.payload->>'current_ev_minus_se' IS NOT NULL
    AND (e.payload->>'current_ev')::float8
          - (e.payload->>'current_ev_minus_se')::float8 >= 0
    AND coalesce(e.recorded_at, e.evaluated_at)
          <= timestamptz '2026-08-23T12:00:50Z'
), identities AS (
  SELECT DISTINCT ON (provider_fixture_id)
         provider_fixture_id, home_provider_team_id, away_provider_team_id,
         competition_id, kickoff_utc
  FROM matchday_fixture_identities
  WHERE provider = 'api_football'
    AND captured_at <= timestamptz '2026-08-23T12:00:50Z'
  ORDER BY provider_fixture_id, captured_at DESC
), sides AS (
  SELECT e.*, i.competition_id, i.kickoff_utc, side.name AS side,
         side.team_id
  FROM frozen_evaluations e
  JOIN identities i ON i.provider_fixture_id = e.fixture_id
  CROSS JOIN LATERAL (
    VALUES ('HOME', i.home_provider_team_id),
           ('AWAY', i.away_provider_team_id)
  ) AS side(name, team_id)
), ranked_xg AS (
  SELECT s.evaluation_id, s.side, x.*,
         row_number() OVER (
           PARTITION BY s.evaluation_id, s.side
           ORDER BY x.kickoff_at DESC, x.id DESC
         ) AS rank
  FROM sides s
  JOIN team_xg_match x
    ON x.team_id = s.team_id
   AND x.kickoff_at < s.evaluated_at
   AND x.captured_at <= s.evaluated_at
   AND x.source_system = 'api_football_statistics'
   AND x.raw_payload_sha256 IS NOT NULL
   AND x.xg_for IS NOT NULL
   AND x.xg_against IS NOT NULL
), visible_xg AS (
  SELECT * FROM ranked_xg WHERE rank <= 20
), side_stats AS (
  SELECT s.evaluation_id, s.side, count(x.id) AS n,
         extract(epoch FROM (s.kickoff_utc - max(x.kickoff_at))) / 86400.0 AS age,
         stddev_samp(x.xg_for) / sqrt(count(x.id)) AS se_for,
         stddev_samp(x.xg_against) / sqrt(count(x.id)) AS se_against
  FROM sides s
  LEFT JOIN visible_xg x
    ON x.evaluation_id = s.evaluation_id AND x.side = s.side
  GROUP BY s.evaluation_id, s.side, s.kickoff_utc
), reconstructed AS (
  SELECT e.*, i.competition_id, i.kickoff_utc,
         home.n AS home_n, away.n AS away_n,
         (home.age + away.age) / 2.0 AS age,
         0.5 * sqrt(home.se_for ^ 2 + away.se_against ^ 2) AS sigma_home,
         0.5 * sqrt(away.se_for ^ 2 + home.se_against ^ 2) AS sigma_away
  FROM frozen_evaluations e
  JOIN identities i ON i.provider_fixture_id = e.fixture_id
  JOIN side_stats home
    ON home.evaluation_id = e.evaluation_id AND home.side = 'HOME'
  JOIN side_stats away
    ON away.evaluation_id = e.evaluation_id AND away.side = 'AWAY'
), usable AS (
  SELECT *
  FROM reconstructed
  WHERE home_n >= 3 AND away_n >= 3
    AND age IS NOT NULL
    AND sigma_home IS NOT NULL AND sigma_away IS NOT NULL
), residuals AS (
  SELECT *,
         count(*) OVER (
           PARTITION BY home_n, away_n, market, selection
         ) AS stratum_n,
         age - avg(age) OVER (
           PARTITION BY home_n, away_n, market, selection
         ) AS age_residual,
         ev_se - avg(ev_se) OVER (
           PARTITION BY home_n, away_n, market, selection
         ) AS ev_se_residual
  FROM usable
), fixed_effect AS (
  SELECT * FROM residuals WHERE stratum_n >= 4
), n20 AS (
  SELECT * FROM usable WHERE home_n = 20 AND away_n = 20
), median_age AS (
  SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY age) AS value FROM n20
)
SELECT json_build_object(
  'kind', 'age_metrics',
  'payload', json_build_object(
    'frozen_numeric_rows', (SELECT count(*) FROM frozen_evaluations),
    'usable_rows', (SELECT count(*) FROM usable),
    'distinct_fixtures', (SELECT count(DISTINCT fixture_id) FROM usable),
    'ev_se_min', (SELECT min(ev_se) FROM usable),
    'ev_se_mean', (SELECT avg(ev_se) FROM usable),
    'ev_se_max', (SELECT max(ev_se) FROM usable),
    'raw_age_correlation', (SELECT corr(age, ev_se) FROM usable),
    'raw_min_n_correlation',
      (SELECT corr(least(home_n, away_n), ev_se) FROM usable),
    'fixed_effect_correlation',
      (SELECT corr(age_residual, ev_se_residual) FROM fixed_effect),
    'fixed_effect_rows', (SELECT count(*) FROM fixed_effect),
    'n20_rows', (SELECT count(*) FROM n20),
    'n20_fixtures', (SELECT count(DISTINCT fixture_id) FROM n20),
    'n20_age_median', (SELECT value FROM median_age),
    'n20_age_correlation', (SELECT corr(age, ev_se) FROM n20),
    'fresh_age_mean',
      (SELECT avg(age) FROM n20, median_age WHERE age <= median_age.value),
    'fresh_ev_se_mean',
      (SELECT avg(ev_se) FROM n20, median_age WHERE age <= median_age.value),
    'old_age_mean',
      (SELECT avg(age) FROM n20, median_age WHERE age > median_age.value),
    'old_ev_se_mean',
      (SELECT avg(ev_se) FROM n20, median_age WHERE age > median_age.value)
  )
)::text
) TO STDOUT;

COPY (
WITH numeric_rows AS (
  SELECT evaluation_id, evaluated_at, recorded_at,
         coalesce(recorded_at, evaluated_at) AS frozen_at,
         (payload->>'current_ev')::float8
           - (payload->>'current_ev_minus_se')::float8 AS ev_se
  FROM dynamic_prematch_evaluations
  WHERE payload->>'current_ev' IS NOT NULL
    AND payload->>'current_ev_minus_se' IS NOT NULL
    AND (payload->>'current_ev')::float8
          - (payload->>'current_ev_minus_se')::float8 >= 0
), ranked AS (
  SELECT *, row_number() OVER (ORDER BY frozen_at, evaluation_id) AS rank
  FROM numeric_rows
), frozen_min AS (
  SELECT *
  FROM numeric_rows
  WHERE frozen_at <= timestamptz '2026-08-23T12:00:50Z'
  ORDER BY ev_se, evaluation_id
  LIMIT 1
)
SELECT json_build_object(
  'kind', 'lineage',
  'frozen_count',
    (SELECT count(*) FROM numeric_rows
     WHERE frozen_at <= timestamptz '2026-08-23T12:00:50Z'),
  'handoff_min', (SELECT min(ev_se) FROM ranked WHERE rank <= 2564),
  'row_2603_at', (SELECT frozen_at FROM ranked WHERE rank = 2603),
  'row_2604_at', (SELECT frozen_at FROM ranked WHERE rank = 2604),
  'row_2653_at', (SELECT frozen_at FROM ranked WHERE rank = 2653),
  'frozen_min', (SELECT ev_se FROM frozen_min),
  'frozen_min_evaluated_at', (SELECT evaluated_at FROM frozen_min),
  'frozen_min_recorded_at', (SELECT recorded_at FROM frozen_min)
)::text
) TO STDOUT;

COPY (
WITH identities AS (
  SELECT DISTINCT ON (provider_fixture_id)
         provider_fixture_id, home_provider_team_id, away_provider_team_id,
         competition_id, provider_league_id, kickoff_utc
  FROM matchday_fixture_identities
  WHERE provider = 'api_football'
    AND captured_at <= timestamptz '2026-08-23T12:00:50Z'
  ORDER BY provider_fixture_id, captured_at DESC
)
SELECT json_build_object(
  'kind', 'coverage_evaluation',
  'evaluation_id', e.evaluation_id,
  'fixture_id', e.fixture_id,
  'evaluated_at', e.evaluated_at,
  'frozen_at', coalesce(e.recorded_at, e.evaluated_at),
  'competition_id', i.competition_id,
  'provider_league_id', i.provider_league_id,
  'kickoff_utc', i.kickoff_utc,
  'home_team_id', i.home_provider_team_id,
  'away_team_id', i.away_provider_team_id
)::text
FROM dynamic_prematch_evaluations e
JOIN identities i ON i.provider_fixture_id = e.fixture_id
WHERE coalesce(e.recorded_at, e.evaluated_at)
        <= timestamptz '2026-08-23T12:00:50Z'
ORDER BY e.evaluation_id
) TO STDOUT;

COPY (
WITH totals AS (
  SELECT ((payload->'four_field_xg_identity'->'home'->>'xg_for')::float8
          + (payload->'four_field_xg_identity'->'away'->>'xg_against')::float8) / 2.0
       + ((payload->'four_field_xg_identity'->'away'->>'xg_for')::float8
          + (payload->'four_field_xg_identity'->'home'->>'xg_against')::float8) / 2.0
         AS base_total
  FROM model_forecast_capture
  WHERE coalesce(inserted_at, captured_at)
        <= timestamptz '2026-08-23T12:00:50Z'
)
SELECT json_build_object(
  'kind', 'capture_totals',
  'count', count(*),
  'inside', count(*) FILTER (WHERE base_total BETWEEN 1.35 AND 4.40),
  'above', count(*) FILTER (WHERE base_total > 4.40),
  'below', count(*) FILTER (WHERE base_total < 1.35)
)::text
FROM totals
) TO STDOUT;

COPY (
SELECT json_build_object(
  'kind', 'canonical_history',
  'total', count(*),
  'competitions', array_agg(DISTINCT competition_id ORDER BY competition_id),
  'active', count(*) FILTER (WHERE competition_id IN (
    'argentina_primera', 'brasileirao_serie_a', 'bundesliga', 'eliteserien',
    'eredivisie', 'la_liga', 'ligue_1', 'mls', 'premier_league',
    'primeira_liga', 'serie_a'
  ))
)::text
FROM canonical_team_match_history
WHERE captured_at <= timestamptz '2026-08-23T12:00:50Z'
) TO STDOUT;

COPY (
WITH identities AS (
  SELECT DISTINCT ON (provider_fixture_id) provider_fixture_id
  FROM matchday_fixture_identities
  WHERE provider = 'api_football'
    AND captured_at <= timestamptz '2026-08-23T12:00:50Z'
  ORDER BY provider_fixture_id, captured_at DESC
)
SELECT json_build_object(
  'kind', 'source_counts',
  'coverage_evaluations', (
    SELECT count(*)
    FROM dynamic_prematch_evaluations e
    JOIN identities i ON i.provider_fixture_id = e.fixture_id
    WHERE coalesce(e.recorded_at, e.evaluated_at)
          <= timestamptz '2026-08-23T12:00:50Z'
  ),
  'xg', (
    SELECT count(*)
    FROM team_xg_match
    WHERE source_system = 'api_football_statistics'
      AND raw_payload_sha256 IS NOT NULL
      AND xg_for IS NOT NULL AND xg_against IS NOT NULL
      AND captured_at <= timestamptz '2026-08-23T12:00:50Z'
  )
)::text
) TO STDOUT;

ROLLBACK;
"""

XG_SQL = r"""
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
COPY (
SELECT json_build_object(
  'kind', 'xg',
  'id', id,
  'fixture_id', fixture_id,
  'team_id', team_id,
  'kickoff_at', kickoff_at,
  'captured_at', captured_at
)::text
FROM team_xg_match
WHERE source_system = 'api_football_statistics'
  AND raw_payload_sha256 IS NOT NULL
  AND xg_for IS NOT NULL AND xg_against IS NOT NULL
  AND captured_at <= timestamptz '2026-08-23T12:00:50Z'
ORDER BY team_id, kickoff_at, id
) TO STDOUT;
ROLLBACK;
"""


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("DATETIME_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(UTC)


def _round(value: Any, digits: int = 6) -> float:
    return round(float(value), digits)


def _iso_z(value: Any) -> str:
    return _utc(str(value)).isoformat().replace("+00:00", "Z")


def _load_rows(lines: Iterable[str]) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in lines if line.strip()]
    if any(not isinstance(row, dict) or "kind" not in row for row in rows):
        raise ValueError("EV_SE_SOURCE_ROW_INVALID")
    return rows


def _run_read_only_sql(args: argparse.Namespace, sql: str) -> list[dict[str, Any]]:
    command = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=yes",
    ]
    if args.ssh_key:
        command.extend(("-i", str(args.ssh_key)))
    command.extend(
        (
            args.ssh_host,
            "docker exec -i w2-staging-postgres-1 "
            "psql -X -qAt -v ON_ERROR_STOP=1 -U w2_user -d w2",
        )
    )
    result = subprocess.run(
        command,
        input=sql,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"EV_SE_READ_ONLY_QUERY_FAILED:{result.stderr.strip()}")
    return _load_rows(result.stdout.splitlines())


def _read_production(args: argparse.Namespace) -> list[dict[str, Any]]:
    return _run_read_only_sql(args, SQL) + _run_read_only_sql(args, XG_SQL)


def _canonical_corpus(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["snapshot_as_of"] = _utc(str(payload["snapshot_as_of"]))
    normalized["kickoff_from"] = _utc(str(payload["kickoff_from"]))
    normalized["kickoff_to"] = _utc(str(payload["kickoff_to"]))
    normalized_rows: list[dict[str, Any]] = []
    for raw in payload["history_rows"]:
        row = dict(raw)
        for field in ("kickoff_utc", "raw_captured_at", "result_first_captured_at"):
            row[field] = _utc(str(row[field]))
        normalized_rows.append(row)
    normalized["history_rows"] = normalized_rows
    body = {key: value for key, value in normalized.items() if key != "corpus_sha256"}
    actual = canonical_sha256(
        {"identity_type": "FACTOR_MODEL_GATE1_RAW_HISTORY_CORPUS", **body},
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
    )
    if actual != CORPUS_SHA256 or payload.get("corpus_sha256") != CORPUS_SHA256:
        raise ValueError("EV_SE_CORPUS_CANONICAL_HASH_MISMATCH")
    if len(normalized_rows) != CORPUS_ROWS:
        raise ValueError("EV_SE_CORPUS_ROW_COUNT_MISMATCH")
    if str(payload["snapshot_as_of"]) != CORPUS_SNAPSHOT:
        raise ValueError("EV_SE_CORPUS_SNAPSHOT_MISMATCH")
    return normalized


def _load_corpus(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CORPUS_FILE_SHA256:
        raise ValueError("EV_SE_CORPUS_FILE_HASH_MISMATCH")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("EV_SE_CORPUS_INVALID")
    return _canonical_corpus(payload)


def _visible_xg_count(
    rows: list[dict[str, Any]], *, before: datetime, limit: int = 20
) -> int:
    visible = [
        row
        for row in rows
        if row["kickoff_at"] < before and row["captured_at"] <= before
    ]
    return min(len(visible), limit)


def _coverage_metrics(
    source_rows: list[dict[str, Any]], corpus: Mapping[str, Any]
) -> dict[str, Any]:
    xg_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    xg_fixture_times: dict[tuple[str, str], list[datetime]] = defaultdict(list)
    for row in source_rows:
        if row["kind"] != "xg":
            continue
        normalized = {
            **row,
            "kickoff_at": _utc(str(row["kickoff_at"])),
            "captured_at": _utc(str(row["captured_at"])),
        }
        team_id = str(row["team_id"])
        fixture_id = str(row["fixture_id"])
        xg_by_team[team_id].append(normalized)
        xg_fixture_times[(team_id, fixture_id)].append(normalized["captured_at"])
    for team_rows in xg_by_team.values():
        team_rows.sort(key=lambda row: (row["kickoff_at"], str(row["id"])), reverse=True)

    history_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in corpus["history_rows"]:
        history_by_team[str(row["team_id"])].append(row)
    for team_rows in history_by_team.values():
        team_rows.sort(
            key=lambda row: (row["kickoff_utc"], str(row["provider_fixture_id"])),
            reverse=True,
        )

    evaluations = 0
    full = 0
    false_full = 0
    missing_sides = 0
    coverages: list[float] = []
    for row in source_rows:
        if (
            row["kind"] != "coverage_evaluation"
            or row["competition_id"] not in ACTIVE_COMPETITIONS
        ):
            continue
        evaluated_at = _utc(str(row["evaluated_at"]))
        kickoff = _utc(str(row["kickoff_utc"]))
        if evaluated_at >= kickoff:
            continue
        side_coverages: list[float] = []
        legacy_counts: list[int] = []
        for field in ("home_team_id", "away_team_id"):
            team_id = str(row[field])
            expected = [
                history
                for history in history_by_team[team_id]
                if history["kickoff_utc"] < kickoff
                and str(history["provider_league_id"])
                == str(row["provider_league_id"])
            ][:20]
            if len(expected) < 3:
                side_coverages = []
                break
            observed = sum(
                any(
                    captured_at <= evaluated_at
                    for captured_at in xg_fixture_times[
                        (team_id, str(history["provider_fixture_id"]))
                    ]
                )
                for history in expected
            )
            coverage = observed / len(expected)
            side_coverages.append(coverage)
            legacy_counts.append(
                _visible_xg_count(xg_by_team[team_id], before=evaluated_at)
            )
        if len(side_coverages) != 2:
            continue
        evaluations += 1
        coverages.extend(side_coverages)
        side_full = [math.isclose(value, 1.0) for value in side_coverages]
        full += int(all(side_full))
        missing_sides += sum(not value for value in side_full)
        false_full += int(all(value == 20 for value in legacy_counts) and not all(side_full))

    denominator = full + false_full
    return {
        "evaluations": evaluations,
        "both_sides_full_expected_latest20_coverage": full,
        "legacy_n20_both_evaluations": denominator,
        "legacy_n20_both_but_expected_latest20_missing": false_full,
        "false_full_share_at_legacy_n20_both": _round(false_full / denominator),
        "side_rows_with_missing_expected_xg": missing_sides,
        "side_coverage_min": _round(min(coverages)),
        "side_coverage_median": _round(statistics.median(coverages)),
        "side_coverage_mean": _round(statistics.fmean(coverages)),
    }


def _one(rows: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    matches = [row for row in rows if row["kind"] == kind]
    if len(matches) != 1:
        raise ValueError(f"EV_SE_SOURCE_KIND_COUNT_INVALID:{kind}:{len(matches)}")
    return matches[0]


def build_evidence(source_rows: list[dict[str, Any]], corpus: Mapping[str, Any]) -> dict[str, Any]:
    age = _one(source_rows, "age_metrics")["payload"]
    lineage_source = _one(source_rows, "lineage")
    captures = _one(source_rows, "capture_totals")
    canonical = _one(source_rows, "canonical_history")
    source_counts = _one(source_rows, "source_counts")
    observed_counts = {
        kind: sum(row["kind"] == kind for row in source_rows)
        for kind in ("coverage_evaluation", "xg")
    }
    expected_counts = {
        "coverage_evaluation": int(source_counts["coverage_evaluations"]),
        "xg": int(source_counts["xg"]),
    }
    if observed_counts != expected_counts:
        raise ValueError(
            f"EV_SE_SOURCE_ROWS_INCOMPLETE:{observed_counts}:{expected_counts}"
        )
    if int(lineage_source["frozen_count"]) != int(age["usable_rows"]):
        raise ValueError("EV_SE_FROZEN_LINEAGE_COUNT_MISMATCH")
    ev_multiplier = math.sqrt(0.25 + 0.25)
    simulation_multiplier = math.sqrt(0.158655 + 0.158655)
    return {
        "schema_version": "w2.ev_se.offline_preregistration_evidence.v2",
        "status": "PRE_MODEL_DIAGNOSTIC_PASS_REPRODUCIBLE_PARAMETER_GATE_REVIEW_READY",
        "observed_at": OBSERVED_AT,
        "production": {
            "release_id": RELEASE_ID,
            "schema": SCHEMA,
            "provider_calls": 0,
            "database_writes": 0,
            "outcomes_read": 0,
        },
        "reproducibility": {
            "float_tolerance": FLOAT_TOLERANCE,
            "frozen_row_time_expression": "COALESCE(recorded_at, evaluated_at)",
            "frozen_row_cutoff_inclusive": OBSERVED_AT,
            "usable_predicate": [
                "current_ev IS NOT NULL",
                "current_ev_minus_se IS NOT NULL",
                "current_ev - current_ev_minus_se >= 0",
                "COALESCE(recorded_at, evaluated_at) <= 2026-08-23T12:00:50Z",
                "api_football fixture identity resolves",
                "kickoff_at < evaluated_at",
                "captured_at <= evaluated_at",
                "latest visible xG rows per side capped at 20",
                "home_n >= 3 AND away_n >= 3",
                "age, sigma_home, and sigma_away are non-null",
            ],
            "row_count_lineage": {
                "handoff_ev_se_values": 2564,
                "handoff_age_correlation_subset": 2528,
                "frozen_baseline_usable": int(age["usable_rows"]),
                "owner_live_recount": 2653,
                "owner_live_recount_added_after_frozen_cutoff": 50,
                "frozen_row_2603_max_recorded_at": _iso_z(
                    lineage_source["row_2603_at"]
                ),
                "first_post_cutoff_row_recorded_at": _iso_z(
                    lineage_source["row_2604_at"]
                ),
                "owner_live_row_2653_recorded_at": _iso_z(
                    lineage_source["row_2653_at"]
                ),
            },
            "minimum_lineage": {
                "handoff_min_exact": _round(lineage_source["handoff_min"]),
                "handoff_min_reported_4dp": 0.0296,
                "frozen_min_exact": _round(lineage_source["frozen_min"]),
                "new_min_evaluated_at": _iso_z(
                    lineage_source["frozen_min_evaluated_at"]
                ),
                "new_min_recorded_at": _iso_z(
                    lineage_source["frozen_min_recorded_at"]
                ),
                "cause": "NEW_EVALUATION_ENTERED_AFTER_HANDOFF_SNAPSHOT",
            },
        },
        "age_falsification": {
            "usable_evaluations": int(age["usable_rows"]),
            "distinct_fixtures": int(age["distinct_fixtures"]),
            "ev_se": {
                "min": _round(age["ev_se_min"]),
                "mean": _round(age["ev_se_mean"]),
                "max": _round(age["ev_se_max"]),
            },
            "raw_latest_age_ev_se_correlation": _round(age["raw_age_correlation"]),
            "raw_min_n_ev_se_correlation": _round(age["raw_min_n_correlation"]),
            "fixed_effect_age_ev_se_correlation": _round(
                age["fixed_effect_correlation"]
            ),
            "fixed_effect_strata": ["home_n", "away_n", "market", "selection"],
            "fixed_effect_minimum_stratum_rows": 4,
            "fixed_effect_rows": int(age["fixed_effect_rows"]),
            "n20_n20": {
                "evaluations": int(age["n20_rows"]),
                "fixtures": int(age["n20_fixtures"]),
                "age_median_days": _round(age["n20_age_median"]),
                "age_ev_se_correlation": _round(age["n20_age_correlation"]),
                "fresh_age_mean_days": _round(age["fresh_age_mean"], 3),
                "fresh_ev_se_mean": _round(age["fresh_ev_se_mean"]),
                "old_age_mean_days": _round(age["old_age_mean"], 3),
                "old_ev_se_mean": _round(age["old_ev_se_mean"]),
            },
        },
        "coefficient_propagation": {
            "interior_lambda_jacobian_per_xg_mean": 0.5,
            "frozen_model_captures": int(captures["count"]),
            "base_total_inside_1_35_4_40": int(captures["inside"]),
            "base_total_above_4_40": int(captures["above"]),
            "base_total_below_1_35": int(captures["below"]),
            "ev_se_node_weight_effective_sigma_multiplier": round(ev_multiplier, 10),
            "simulation_node_weight_effective_sigma_multiplier": round(
                simulation_multiplier, 10
            ),
            "effective_sigma_multiplier_ratio": round(
                ev_multiplier / simulation_multiplier, 10
            ),
            "lower_node_floor": 0.01,
            "shared_sigma_semantics": "OWNER_DECISION_REQUIRED_THREE_WAY",
        },
        "coverage_denominator": {
            "runtime_canonical_team_match_history_rows": int(canonical["total"]),
            "runtime_active_competition_rows": int(canonical["active"]),
            "runtime_competition_ids": canonical["competitions"],
            "offline_corpus": {
                "snapshot_as_of": CORPUS_SNAPSHOT,
                "corpus_sha256": CORPUS_SHA256,
                "file_sha256": CORPUS_FILE_SHA256,
                "history_rows": CORPUS_ROWS,
                "team_identity_namespace": "api_football.provider_team_id.v1",
                "materializer_commit": "0c77c086",
            },
            "active_11_competitions": {
                "competition_ids": sorted(ACTIVE_COMPETITIONS),
                **_coverage_metrics(source_rows, corpus),
            },
        },
        "forbidden_uses": [
            "CURRENT_65_PICK_PROFIT_TUNING",
            "AGE_CUTOFF_BACKTEST_SELECTION",
            "EV_CAP_BACKTEST_SELECTION",
            "STALE_XG_CAUSES_HIGH_EV_CLAIM",
            "PRODUCTION_PARAMETER_CHANGE_WITHOUT_OWNER_APPROVAL",
        ],
    }


def _render_markdown(evidence: Mapping[str, Any]) -> str:
    age = evidence["age_falsification"]
    n20 = age["n20_n20"]
    coefficient = evidence["coefficient_propagation"]
    coverage = evidence["coverage_denominator"]
    active = coverage["active_11_competitions"]
    lineage = evidence["reproducibility"]["row_count_lineage"]
    minimum = evidence["reproducibility"]["minimum_lineage"]
    return f"""# EV SE offline preregistration baseline — 2026-08-23

Status: `PRE_MODEL_DIAGNOSTIC_PASS / REPRODUCIBLE / PARAMETER_GATE_REVIEW_READY`

## Execution boundary

- Exact production release observed: `{RELEASE_ID}`.
- Exact production schema: `{SCHEMA}`.
- Evidence observed at: `{OBSERVED_AT}`.
- Provider calls / production database writes / outcomes read: `0 / 0 / 0`.
- No model, threshold, Scheduler, notification, deployment, or runtime configuration changed.

This document preregisters the problem and behavioral acceptance conditions. It does not approve a formula, coefficient, implementation, or release. Reproduction is defined in `README.md`; every numeric field below is rendered by `scripts/audit_ev_se_offline_preregistration.py`.

## Binding non-claims

- Do not claim that stale xG raises EV. That causal claim failed its prior test.
- Do not use profit, loss, hit rate, or the current 65 settled picks to choose an uncertainty coefficient.
- Do not introduce or backtest-select an age cutoff or EV ceiling.
- The target is epistemic: `ev_se` claims to express uncertainty about the current match lambdas. The current formula treats old and recent source matches as exchangeable conditional on observed values and sample size; that stationarity assumption requires an explicit test and policy.

## Reproduction predicate and row-count lineage

`usable` means: both EV fields are numeric, `ev_se >= 0`, `COALESCE(recorded_at, evaluated_at) <= {OBSERVED_AT}`, the API-Football fixture identity resolves, both xG sides obey `kickoff_at < evaluated_at` and `captured_at <= evaluated_at`, visible rows are capped at 20, both sides have `n >= 3`, and age plus both reconstructed sigmas are non-null.

The four counts are different cohorts:

- `{lineage['handoff_ev_se_values']}`: handoff snapshot rows with an `ev_se` value.
- `{lineage['handoff_age_correlation_subset']}`: the handoff's age-correlation subset; it is not the handoff EV-SE count and cannot be compared as if it were.
- `{lineage['frozen_baseline_usable']}`: this preregistration's frozen usable cohort at `{OBSERVED_AT}`.
- `{lineage['owner_live_recount']}`: Owner's later unbounded live recount. Its extra `{lineage['owner_live_recount_added_after_frozen_cutoff']}` rows arrived after the frozen cutoff; row 2604 was recorded at `{lineage['first_post_cutoff_row_recorded_at']}` and row 2653 at `{lineage['owner_live_row_2653_recorded_at']}`.

The handoff minimum `{minimum['handoff_min_reported_4dp']:.4f}` was `{minimum['handoff_min_exact']:.6f}` rounded to four decimals. The new `{minimum['frozen_min_exact']:.6f}` row was evaluated at `{minimum['new_min_evaluated_at']}` and recorded at `{minimum['new_min_recorded_at']}`. The minimum changed because a new evaluation entered after the handoff snapshot, not because the filter changed.

## Code facts frozen before model design

### 1. Meaning of the existing `0.5`

The lambda point estimate uses:

```text
base_home = (home_xg_for + away_xg_against) / 2
base_away = (away_xg_for + home_xg_against) / 2
total     = clamp(base_home + base_away)
delta     = base_home - base_away + non-xG adjustments
lambda_home = (total + delta) / 2
lambda_away = (total - delta) / 2
```

When the total and final lambdas are inside their clamp boundaries, this simplifies to:

```text
lambda_home = base_home + constant / 2
lambda_away = base_away - constant / 2
```

Therefore the local Jacobian of each lambda with respect to each of its two xG means is `0.5`, and independent-error propagation gives:

```text
sigma_home = 0.5 * sqrt(SE(home attack)^2 + SE(away defence)^2)
sigma_away = 0.5 * sqrt(SE(away attack)^2 + SE(home defence)^2)
```

Conclusion: `0.5` is not an arbitrary gate discount in the unclamped interior. It is the derivative of the existing arithmetic-mean lambda estimator. The July design document recorded this formula but did not record the derivation.

The coefficient is only piecewise valid. A total clamp or final-lambda clamp changes the Jacobian. In the `{coefficient['frozen_model_captures']}` frozen model captures, `{coefficient['base_total_inside_1_35_4_40']}` base totals were inside `[1.35, 4.40]`; `{coefficient['base_total_above_4_40']}` was above `4.40` and `{coefficient['base_total_below_1_35']}` was below `1.35`. Any future uncertainty implementation must propagate through the actual piecewise calibration path rather than silently applying one global coefficient at clamp boundaries.

### 2. Owner decision 1 is a three-way semantic choice

The EV-SE nodes use `0.25 / 0.50 / 0.25`, so effective SD is `{coefficient['ev_se_node_weight_effective_sigma_multiplier']:.4f} sigma`. Simulation uses `0.158655 / 0.68269 / 0.158655`, so effective SD is `{coefficient['simulation_node_weight_effective_sigma_multiplier']:.4f} sigma`; their ratio is `{coefficient['effective_sigma_multiplier_ratio']:.4f}`. Both paths also floor the lower node at `max(mu - sigma, {coefficient['lower_node_floor']:.2f})`, which further compresses dispersion as `mu - sigma` approaches zero.

Owner must choose one:

1. **True standard deviation.** Both current weight sets are wrong and both consumers must change; neither is a reference implementation.
2. **Outer-node distance.** The two consumers may retain different probability weights only after their probability meanings and the `{coefficient['effective_sigma_multiplier_ratio']:.4f}` contraction ratio receive an explicit source and approval.
3. **Retain current behavior.** Record that EV-SE and the main simulation intentionally apply different risk measures to the same `lambda_sigma`, including the lower-node floor compression.

### 3. Existing point-in-time and hard sample boundaries remain binding

- `kickoff_at < as_of`.
- `captured_at <= as_of`.
- `limit_per_team = 20`.
- Each attack/defence sample group requires `n >= 3`.

No replacement PIT subsystem is proposed. Historical reconstruction additionally restricted xG rows to `captured_at <= evaluated_at` so later backfill could not appear in an earlier evaluation. It applies point-in-time visibility before the latest-20 cap so a later backfill cannot displace an older row that was visible at the frozen evaluation time.

### 4. Coverage is partially represented by `n`, but missingness is not identified

The current standard error contains `1 / sqrt(n)`. It therefore reacts to the number of observed xG rows.

It does not identify why `n` has that value, and it selects the latest 20 rows that have xG rather than the xG-covered subset of the latest 20 matches that should exist. Consequently:

- five occurred matches with five xG rows; and
- twenty occurred matches with only five xG rows

are identical after `_xg_uncertainty_rows` if only the five observed rows are presented. Conversely, twenty older xG rows can fill `n=20` even when several of the most recent expected matches have no xG.

## Falsification test A — does age retain an effect after fixing n?

The frozen read-only reconstruction produced `{age['usable_evaluations']:,}` usable evaluations across `{age['distinct_fixtures']}` fixtures. Fixed effects retain only exact `(home_n, away_n, market, selection)` strata with at least four rows.

| Measurement | Result |
|---|---:|
| `ev_se` min / mean / max | `{age['ev_se']['min']:.6f} / {age['ev_se']['mean']:.6f} / {age['ev_se']['max']:.6f}` |
| raw `latest age × ev_se` correlation | `{age['raw_latest_age_ev_se_correlation']:+.6f}` |
| raw `min(home_n, away_n) × ev_se` correlation | `{age['raw_min_n_ev_se_correlation']:+.6f}` |
| within exact `(home_n, away_n, market, selection)` `age × ev_se` correlation | `{age['fixed_effect_age_ev_se_correlation']:+.6f}` |
| fixed-effect rows | `{age['fixed_effect_rows']:,}` |

The dominant exact sample stratum was `home_n=20 / away_n=20`:

| Measurement | Result |
|---|---:|
| evaluations / fixtures | `{n20['evaluations']:,} / {n20['fixtures']}` |
| age median | `{n20['age_median_days']:.3f} days` |
| age correlation with `ev_se` | `{n20['age_ev_se_correlation']:+.6f}` |
| fresh half mean age / mean `ev_se` | `{n20['fresh_age_mean_days']:.3f} days / {n20['fresh_ev_se_mean']:.6f}` |
| old half mean age / mean `ev_se` | `{n20['old_age_mean_days']:.3f} days / {n20['old_ev_se_mean']:.6f}` |

Result: after fixing sample size and market/selection, age contributes effectively zero to the reported `ev_se`. The previously observed approximately 10% old-versus-fresh difference is not evidence of an age response; it is explained by sample-size and composition differences. The problem statement is therefore upgraded to: **the current uncertainty formula has no explicit recency response**.

This is an epistemic formula diagnosis, not evidence that stale xG biases EV upward or downward.

## Falsification test B — can an expected-match denominator vary independently of n?

The production `canonical_team_match_history` table cannot currently serve the active runtime: it contains `{coverage['runtime_canonical_team_match_history_rows']}` rows, all from Allsvenskan, and has `{coverage['runtime_active_competition_rows']}` coverage rows for the active 11 competitions.

Offline denominator feasibility was tested with the already frozen saved-raw Gate 1 corpus:

- snapshot: `{coverage['offline_corpus']['snapshot_as_of']}`;
- canonical corpus fingerprint: `{coverage['offline_corpus']['corpus_sha256']}`;
- file SHA-256: `{coverage['offline_corpus']['file_sha256']}`;
- team-history rows: `{coverage['offline_corpus']['history_rows']:,}`;
- identity namespace: `api_football.provider_team_id.v1`.

For each evaluation and team, the expected set was the latest 20 finished canonical fixtures from the same provider league strictly before the target kickoff. Coverage was the intersection of that set with xG rows visible by the evaluation time. Evaluations at or after kickoff were excluded.

Active 11-competition result:

| Measurement | Result |
|---|---:|
| evaluations with both expected denominators `>=3` | `{active['evaluations']:,}` |
| both teams fully covered in their expected latest 20 | `{active['both_sides_full_expected_latest20_coverage']}` |
| old algorithm reports `n=20` for both teams | `{active['legacy_n20_both_evaluations']:,}` |
| old algorithm reports `n=20` for both teams but expected latest-20 coverage is incomplete | `{active['legacy_n20_both_but_expected_latest20_missing']:,}` |
| side rows missing at least one expected xG fixture | `{active['side_rows_with_missing_expected_xg']:,}` |
| side coverage min / median / mean | `{active['side_coverage_min']:.2f} / {active['side_coverage_median']:.2f} / {active['side_coverage_mean']:.6f}` |

Among evaluations for which the old algorithm reports `n=20` on both teams, `{active['legacy_n20_both_but_expected_latest20_missing']:,} / ({active['legacy_n20_both_but_expected_latest20_missing']:,} + {active['both_sides_full_expected_latest20_coverage']}) = {active['false_full_share_at_legacy_n20_both']:.6f}` still have at least one recent expected-match coverage gap. Thus fixture-level coverage has substantial independent variation at fixed `n=20`; it is identifiable and not merely a duplicate transform of n.

The frozen corpus is sufficient to prove offline identifiability. It is not itself a production runtime authority. A runtime implementation requires an approved, point-in-time available expected-fixture denominator for the active 11 competitions.

## Preregistered behavioral invariants

Any candidate method must satisfy all five invariants without consulting current-pick profit or loss:

1. **Age monotonicity:** holding xG values, expected fixtures, observed fixtures, sample count, market, and price fixed, making evidence older must not reduce `lambda_sigma` or `ev_se`.
2. **Sample and coverage monotonicity:** holding values and ages fixed, adding a valid recent observed fixture or increasing recent expected-fixture coverage must not increase uncertainty. A missing expected fixture must not be treated as a match that never occurred.
3. **Fresh complete baseline parity:** when the latest expected fixture set is fully covered and fresh, the candidate must reproduce the approved interior baseline within a preregistered numerical tolerance; no global inflation is allowed merely to close the gate more often.
4. **No-evidence fail closed:** fewer than three valid observations, an unavailable expected denominator, identity conflict, or unknown coverage state must not produce a high-confidence active pick.
5. **Automatic seasonal recovery:** as a team accumulates new, fully covered evidence, uncertainty must decrease continuously under the same rule. Bundesliga or another restarting league must recover without an age cutoff or season-start switch.

Additional structural requirements:

- The `0.5` interior coefficient is defined by the lambda Jacobian, not tuned from outcomes.
- Clamp-boundary propagation must use the actual piecewise lambda function.
- `lambda_sigma` must follow the Owner-approved probability meaning and consequences for both consumers.
- Expected fixtures and observed xG fixtures must be compared by canonical provider fixture identity.
- The latest-20 cap and `n>=3` lower bound remain unchanged unless separately approved.

## Owner decisions required before implementation

1. Choose one of the three `lambda_sigma` semantic contracts above and approve its consequences for both consumers and the `0.01` floor.
2. Approve the runtime expected-match denominator authority and its point-in-time availability contract for the active 11 competitions.
3. Approve a formula family for recency and missing-coverage uncertainty. Coefficients remain unset at this gate.

Until those decisions are recorded, the correct state is `OFFLINE_DIAGNOSTIC_REPRODUCIBLE / MODEL_PARAMETER_CHANGE_NOT_AUTHORIZED`.
"""


def _self_check() -> None:
    required_source = {
        "src/w2/markets/analysis_evidence.py": (
            'low = max(value - sigma, Decimal("0.01"))',
            '(low, Decimal("0.25"))',
            '(value, Decimal("0.5"))',
            '(high, Decimal("0.25"))',
        ),
        "src/w2/strategy/simulate.py": (
            "(max(mu - sigma, 0.01), 0.158655)",
            "(max(mu, 0.01), 0.68269)",
            "(max(mu + sigma, 0.01), 0.158655)",
        ),
        "src/w2/strategy/calibration.py": (
            "minimum_total_goals: float = 1.35",
            "maximum_total_goals: float = 4.40",
        ),
        "src/w2/prematch/analysis_calculator.py": (
            "sigma_home = 0.5 * math.sqrt(",
            "sigma_away = 0.5 * math.sqrt(",
        ),
    }
    for relative_path, fragments in required_source.items():
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        if any(fragment not in source for fragment in fragments):
            raise AssertionError(f"EV_SE_SOURCE_CONTRACT_CHANGED:{relative_path}")
    assert round(math.sqrt(0.5), 10) == 0.7071067812
    assert round(math.sqrt(0.31731), 10) == 0.5633027605
    assert round(math.sqrt(0.5) / math.sqrt(0.31731), 4) == 1.2553


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path)
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
    if args.corpus is None:
        parser.error("--corpus is required unless --self-check is used")
    source_rows = _read_production(args)
    evidence = build_evidence(source_rows, _load_corpus(args.corpus))
    rendered_json = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    rendered_markdown = _render_markdown(evidence)
    if args.check:
        if args.output_json.read_text(encoding="utf-8") != rendered_json:
            raise SystemExit("EV_SE_EVIDENCE_JSON_DIFF")
        if args.output_markdown.read_text(encoding="utf-8") != rendered_markdown:
            raise SystemExit("EV_SE_BASELINE_MARKDOWN_DIFF")
        print(json.dumps({"reproduction": "PASS"}, sort_keys=True))
        return
    args.output_json.write_text(rendered_json, encoding="utf-8")
    args.output_markdown.write_text(rendered_markdown, encoding="utf-8")
    print(
        json.dumps(
            {
                "output_json": str(args.output_json),
                "output_markdown": str(args.output_markdown),
                "provider_calls": 0,
                "production_database_writes": 0,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
