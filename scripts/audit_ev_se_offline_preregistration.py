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
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.strategy.simulate import _exact_score_matrix

OBSERVED_AT = "2026-08-23T12:00:50Z"
RELEASE_ID = "d05ab74217e37af2e85732ac3a63ee4d9e214aa1"
SCHEMA = "0070_notification_delivery_routing"
CORPUS_SHA256 = "d19b217afe159c87dbf8d0dea87c260374ac9d18ffd8bb97581cfffe858cedc5"
CORPUS_FILE_SHA256 = "80e49d1a32b5dd9653d41826e87415acff0d32a6804dea408f3b99737a6ab5e2"
CORPUS_SNAPSHOT = "2026-08-22T05:50:41.929427Z"
CORPUS_ROWS = 38_706
FLOAT_TOLERANCE = 0.000001
GH3_DISTANCE = math.sqrt(3.0)
GH3_WEIGHTS = (1.0 / 6.0, 2.0 / 3.0, 1.0 / 6.0)
PAYLOAD_PRICE_SOURCE = "PAYLOAD_DECIMAL_ODDS"
DERIVED_PRICE_SOURCE = "DERIVED_FROM_CURRENT_EV_AND_FIVE_STATE_DISTRIBUTION"
STANDARDIZED_EFFECT_MATERIALITY_THRESHOLD = 0.20
REVIEWER_SQRT2_POOLED_DELTA_REFERENCE = 0.022213
PRICE_SOURCE_COMPARISON_FIELDS = {
    "reported_point_ev_delta": "reported_point_ev_delta",
    "internal_quadrature_mean_ev_delta_gh3_minus_old": "analysis_mean_delta",
    "ev_se_delta_gh3_minus_old": "analysis_se_delta",
    "mixed_score_matrix_ev_delta_gh3_minus_old": "simulation_ev_delta",
}

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
WITH frozen_evaluations AS (
  SELECT e.evaluation_id, e.fixture_id, e.model_input_hash, e.market,
         e.selection, e.evaluated_at,
         (e.payload->>'current_ev')::float8 AS current_ev,
         (e.payload->>'current_ev_minus_se')::float8 AS current_ev_minus_se,
         (e.payload->>'decimal_odds')::float8 AS decimal_odds,
         (e.payload->>'exact_line')::float8 AS exact_line,
         e.payload->'model_settlement_distribution' AS model_distribution
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
         avg(x.xg_for) AS mean_for,
         avg(x.xg_against) AS mean_against,
         stddev_samp(x.xg_for) / sqrt(count(x.id)) AS se_for,
         stddev_samp(x.xg_against) / sqrt(count(x.id)) AS se_against
  FROM sides s
  LEFT JOIN visible_xg x
    ON x.evaluation_id = s.evaluation_id AND x.side = s.side
  GROUP BY s.evaluation_id, s.side
), usable AS (
  SELECT e.*, i.competition_id,
         home.n AS home_n, away.n AS away_n,
         home.mean_for AS home_xg_for,
         home.mean_against AS home_xg_against,
         away.mean_for AS away_xg_for,
         away.mean_against AS away_xg_against,
         0.5 * sqrt(home.se_for ^ 2 + away.se_against ^ 2) AS sigma_home,
         0.5 * sqrt(away.se_for ^ 2 + home.se_against ^ 2) AS sigma_away
  FROM frozen_evaluations e
  JOIN identities i ON i.provider_fixture_id = e.fixture_id
  JOIN side_stats home
    ON home.evaluation_id = e.evaluation_id AND home.side = 'HOME'
  JOIN side_stats away
    ON away.evaluation_id = e.evaluation_id AND away.side = 'AWAY'
  WHERE home.n >= 3 AND away.n >= 3
    AND home.se_for IS NOT NULL AND home.se_against IS NOT NULL
    AND away.se_for IS NOT NULL AND away.se_against IS NOT NULL
)
SELECT json_build_object(
  'kind', 'contract_evaluation',
  'evaluation_id', evaluation_id,
  'fixture_id', fixture_id,
  'competition_id', competition_id,
  'model_input_hash', model_input_hash,
  'market', market,
  'selection', selection,
  'evaluated_at', evaluated_at,
  'current_ev', current_ev,
  'current_ev_minus_se', current_ev_minus_se,
  'decimal_odds', decimal_odds,
  'exact_line', exact_line,
  'model_distribution', model_distribution,
  'home_xg_for', home_xg_for,
  'home_xg_against', home_xg_against,
  'away_xg_for', away_xg_for,
  'away_xg_against', away_xg_against,
  'sigma_home', sigma_home,
  'sigma_away', sigma_away
)::text
FROM usable
ORDER BY model_input_hash, evaluation_id
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
  'kind', 'enabled_competition',
  'competition_id', competition_id,
  'season', season,
  'provider_league_id', coalesce(
    payload->>'provider_league_id',
    payload#>>'{provider_mapping,league_id}'
  )
)::text
FROM league_season
WHERE (payload->>'enabled')::boolean IS TRUE
ORDER BY competition_id, season
) TO STDOUT;

COPY (
SELECT json_build_object(
  'kind', 'canonical_history',
  'total', count(*),
  'competitions', array_agg(DISTINCT competition_id ORDER BY competition_id),
  'active', count(*) FILTER (
    WHERE competition_id IN (
      SELECT competition_id
      FROM league_season
      WHERE (payload->>'enabled')::boolean IS TRUE
    )
  )
)::text
FROM canonical_team_match_history
WHERE captured_at <= timestamptz '2026-08-23T12:00:50Z'
) TO STDOUT;

COPY (
WITH enabled AS (
  SELECT competition_id, season,
         coalesce(
           payload->>'provider_league_id',
           payload#>>'{provider_mapping,league_id}'
         ) AS provider_league_id
  FROM league_season
  WHERE (payload->>'enabled')::boolean IS TRUE
), canonical AS (
  SELECT competition_id, count(*) AS team_rows,
         count(DISTINCT fixture_id) AS fixtures
  FROM canonical_team_match_history
  WHERE captured_at <= timestamptz '2026-08-23T12:00:50Z'
  GROUP BY competition_id
), identities AS (
  SELECT competition_id, count(DISTINCT provider_fixture_id) AS fixtures
  FROM matchday_fixture_identities
  WHERE provider = 'api_football'
    AND captured_at <= timestamptz '2026-08-23T12:00:50Z'
  GROUP BY competition_id
)
SELECT json_build_object(
  'kind', 'denominator_runtime_competition',
  'competition_id', e.competition_id,
  'season', e.season,
  'provider_league_id', e.provider_league_id,
  'canonical_history_team_rows', coalesce(c.team_rows, 0),
  'canonical_history_fixtures', coalesce(c.fixtures, 0),
  'matchday_identity_fixtures', coalesce(i.fixtures, 0)
)::text
FROM enabled e
LEFT JOIN canonical c ON c.competition_id = e.competition_id
LEFT JOIN identities i ON i.competition_id = e.competition_id
ORDER BY e.competition_id, e.season
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
  ),
  'contract_evaluations', (
    SELECT count(*)
    FROM dynamic_prematch_evaluations e
    JOIN identities i ON i.provider_fixture_id = e.fixture_id
    WHERE e.payload->>'current_ev' IS NOT NULL
      AND e.payload->>'current_ev_minus_se' IS NOT NULL
      AND (e.payload->>'current_ev')::float8
            - (e.payload->>'current_ev_minus_se')::float8 >= 0
      AND coalesce(e.recorded_at, e.evaluated_at)
            <= timestamptz '2026-08-23T12:00:50Z'
  ),
  'enabled_competitions', (
    SELECT count(*) FROM league_season
    WHERE (payload->>'enabled')::boolean IS TRUE
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
    source_rows: list[dict[str, Any]],
    corpus: Mapping[str, Any],
    enabled_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    enabled = {
        str(row["competition_id"]): str(row["provider_league_id"])
        for row in enabled_rows
    }
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

    states: dict[str, dict[str, Any]] = {
        competition_id: {
            "evaluations": 0,
            "point_in_time_denominator_available_evaluations": 0,
            "expected_fixture_side_slots": 0,
            "observed_xg_fixture_side_slots": 0,
            "pit_expected_fixture_side_slots": 0,
            "pit_observed_xg_fixture_side_slots": 0,
            "both_sides_full": 0,
            "legacy_n20_both": 0,
            "false_full": 0,
            "missing_sides": 0,
            "side_coverages": [],
        }
        for competition_id in enabled
    }
    for row in source_rows:
        competition_id = str(row.get("competition_id") or "")
        if row["kind"] != "coverage_evaluation" or competition_id not in enabled:
            continue
        evaluated_at = _utc(str(row["evaluated_at"]))
        kickoff = _utc(str(row["kickoff_utc"]))
        if evaluated_at >= kickoff:
            continue
        side_coverages: list[float] = []
        legacy_counts: list[int] = []
        point_in_time_visible: list[bool] = []
        expected_counts: list[int] = []
        observed_counts: list[int] = []
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
            expected_counts.append(len(expected))
            observed_counts.append(observed)
            point_in_time_visible.append(
                all(history["result_first_captured_at"] <= evaluated_at for history in expected)
            )
            legacy_counts.append(
                _visible_xg_count(xg_by_team[team_id], before=evaluated_at)
            )
        if len(side_coverages) != 2:
            continue
        state = states[competition_id]
        state["evaluations"] += 1
        state["expected_fixture_side_slots"] += sum(expected_counts)
        state["observed_xg_fixture_side_slots"] += sum(observed_counts)
        state["side_coverages"].extend(side_coverages)
        side_full = [math.isclose(value, 1.0) for value in side_coverages]
        state["both_sides_full"] += int(all(side_full))
        state["missing_sides"] += sum(not value for value in side_full)
        legacy_n20 = all(value == 20 for value in legacy_counts)
        state["legacy_n20_both"] += int(legacy_n20)
        state["false_full"] += int(legacy_n20 and not all(side_full))
        if all(point_in_time_visible):
            state["point_in_time_denominator_available_evaluations"] += 1
            state["pit_expected_fixture_side_slots"] += sum(expected_counts)
            state["pit_observed_xg_fixture_side_slots"] += sum(observed_counts)

    corpus_by_league: dict[str, set[str]] = defaultdict(set)
    corpus_team_rows_by_league: dict[str, int] = defaultdict(int)
    for row in corpus["history_rows"]:
        provider_league_id = str(row["provider_league_id"])
        corpus_by_league[provider_league_id].add(str(row["provider_fixture_id"]))
        corpus_team_rows_by_league[provider_league_id] += 1

    by_competition = []
    for competition_id, provider_league_id in sorted(enabled.items()):
        state = states[competition_id]
        evaluations = int(state["evaluations"])
        expected_slots = int(state["expected_fixture_side_slots"])
        pit_evaluations = int(state["point_in_time_denominator_available_evaluations"])
        pit_expected = int(state["pit_expected_fixture_side_slots"])
        side_coverages = list(state.pop("side_coverages"))
        by_competition.append(
            {
                "competition_id": competition_id,
                "provider_league_id": provider_league_id,
                "offline_corpus_finished_fixtures": len(
                    corpus_by_league[provider_league_id]
                ),
                "offline_corpus_team_history_rows": corpus_team_rows_by_league[
                    provider_league_id
                ],
                "evaluations_with_both_expected_denominators_ge3": evaluations,
                "point_in_time_denominator_available_evaluations": pit_evaluations,
                "point_in_time_denominator_unavailable_evaluations": (
                    evaluations - pit_evaluations
                ),
                "expected_fixture_side_slots": expected_slots,
                "observed_xg_fixture_side_slots": int(
                    state["observed_xg_fixture_side_slots"]
                ),
                "offline_structural_xg_coverage": (
                    _round(state["observed_xg_fixture_side_slots"] / expected_slots)
                    if expected_slots
                    else None
                ),
                "pit_expected_fixture_side_slots": pit_expected,
                "pit_observed_xg_fixture_side_slots": int(
                    state["pit_observed_xg_fixture_side_slots"]
                ),
                "point_in_time_xg_coverage": (
                    _round(state["pit_observed_xg_fixture_side_slots"] / pit_expected)
                    if pit_expected
                    else None
                ),
                "side_coverage_median": (
                    _round(statistics.median(side_coverages))
                    if side_coverages
                    else None
                ),
                "both_sides_full_expected_latest20_coverage": int(
                    state["both_sides_full"]
                ),
                "legacy_n20_both_evaluations": int(state["legacy_n20_both"]),
                "legacy_n20_both_but_expected_latest20_missing": int(
                    state["false_full"]
                ),
                "side_rows_with_missing_expected_xg": int(state["missing_sides"]),
            }
        )

    return {
        "scope_source": "league_season.payload.enabled",
        "enabled_competition_count_observed": len(enabled),
        "competition_ids": sorted(enabled),
        "aggregate_counts_without_coverage_average": {
            "evaluations": sum(row["evaluations_with_both_expected_denominators_ge3"] for row in by_competition),
            "both_sides_full_expected_latest20_coverage": sum(row["both_sides_full_expected_latest20_coverage"] for row in by_competition),
            "legacy_n20_both_evaluations": sum(row["legacy_n20_both_evaluations"] for row in by_competition),
            "legacy_n20_both_but_expected_latest20_missing": sum(row["legacy_n20_both_but_expected_latest20_missing"] for row in by_competition),
            "side_rows_with_missing_expected_xg": sum(row["side_rows_with_missing_expected_xg"] for row in by_competition),
        },
        "by_competition": by_competition,
    }


_DISTRIBUTION_FIELDS = {
    "WIN": "full_win_probability",
    "HALF_WIN": "half_win_probability",
    "PUSH": "push_probability",
    "HALF_LOSS": "half_loss_probability",
    "LOSS": "full_loss_probability",
}
_SETTLEMENT_BUCKETS: dict[
    tuple[str, str, str], dict[str, tuple[tuple[int, int], ...]]
] = {}


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("EV_SE_EMPTY_DISTRIBUTION")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _distribution_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "n": 0,
            "min": None,
            "p05": None,
            "p25": None,
            "median": None,
            "mean": None,
            "p75": None,
            "p95": None,
            "max": None,
            "max_absolute": None,
        }
    return {
        "n": len(values),
        "min": _round(min(values)),
        "p05": _round(_percentile(values, 0.05)),
        "p25": _round(_percentile(values, 0.25)),
        "median": _round(_percentile(values, 0.50)),
        "mean": _round(statistics.fmean(values)),
        "p75": _round(_percentile(values, 0.75)),
        "p95": _round(_percentile(values, 0.95)),
        "max": _round(max(values)),
        "max_absolute": _round(max(abs(value) for value in values)),
    }


def _distribution_difference_assessment(
    first: list[float], second: list[float]
) -> dict[str, Any]:
    if not first or not second:
        raise ValueError("EV_SE_PRICE_SOURCE_STRATUM_EMPTY")
    degrees_of_freedom = len(first) + len(second) - 2
    pooled_sd = (
        math.sqrt(
            (
                (len(first) - 1) * statistics.variance(first)
                + (len(second) - 1) * statistics.variance(second)
            )
            / degrees_of_freedom
        )
        if len(first) > 1 and len(second) > 1 and degrees_of_freedom > 0
        else 0.0
    )
    mean_gap = abs(statistics.fmean(first) - statistics.fmean(second))
    central_quantiles = {
        "p05": 0.05,
        "p25": 0.25,
        "median": 0.50,
        "p75": 0.75,
        "p95": 0.95,
    }
    quantile_gaps = {
        name: abs(_percentile(first, probability) - _percentile(second, probability))
        for name, probability in central_quantiles.items()
    }
    largest_quantile = max(quantile_gaps, key=quantile_gaps.get)
    if pooled_sd == 0.0:
        standardized_mean_gap = 0.0 if mean_gap == 0.0 else math.inf
        standardized_quantile_gap = (
            0.0 if quantile_gaps[largest_quantile] == 0.0 else math.inf
        )
    else:
        standardized_mean_gap = mean_gap / pooled_sd
        standardized_quantile_gap = quantile_gaps[largest_quantile] / pooled_sd
    material = (
        max(standardized_mean_gap, standardized_quantile_gap)
        >= STANDARDIZED_EFFECT_MATERIALITY_THRESHOLD
    )
    return {
        "criterion": "MATERIAL_IF_ABSOLUTE_STANDARDIZED_MEAN_GAP_OR_MAX_P05_P25_MEDIAN_P75_P95_GAP_IS_AT_LEAST_0_20_POOLED_WITHIN_SOURCE_SD",
        "criterion_purpose": "DESCRIPTIVE_REPORTING_ONLY_NOT_A_MODEL_GATE_OR_PARAMETER",
        "threshold": STANDARDIZED_EFFECT_MATERIALITY_THRESHOLD,
        "pooled_within_source_sd": _round(pooled_sd),
        "absolute_mean_gap": _round(mean_gap),
        "absolute_standardized_mean_gap": (
            _round(standardized_mean_gap)
            if math.isfinite(standardized_mean_gap)
            else "INFINITE"
        ),
        "largest_central_quantile_gap": largest_quantile,
        "absolute_largest_central_quantile_gap": _round(
            quantile_gaps[largest_quantile]
        ),
        "absolute_standardized_largest_central_quantile_gap": (
            _round(standardized_quantile_gap)
            if math.isfinite(standardized_quantile_gap)
            else "INFINITE"
        ),
        "material_difference": material,
        "classification": (
            "MATERIAL_PRICE_SOURCE_DIFFERENCE"
            if material
            else "NO_MATERIAL_PRICE_SOURCE_DIFFERENCE"
        ),
        "pooled_statistic_may_be_sole_reporting_granularity": not material,
    }


def _computed_distribution(
    matrix: Mapping[tuple[int, int], float], row: Mapping[str, Any]
) -> dict[str, float]:
    market = str(row["market"])
    selection = str(row["selection"])
    line_text = str(row["exact_line"])
    cache_key = (market, selection, line_text)
    buckets = _SETTLEMENT_BUCKETS.get(cache_key)
    if buckets is None:
        line = Decimal(line_text)
        mutable: dict[str, list[tuple[int, int]]] = {
            key: [] for key in _DISTRIBUTION_FIELDS
        }
        for home in range(13):
            for away in range(13):
                outcome = (
                    settle_asian_handicap(home, away, selection, line)
                    if market == "ASIAN_HANDICAP"
                    else settle_total_goals(home + away, selection, line)
                )
                mutable[outcome.value].append((home, away))
        buckets = {key: tuple(scores) for key, scores in mutable.items()}
        _SETTLEMENT_BUCKETS[cache_key] = buckets
    values = {
        key: sum(matrix[score] for score in scores)
        for key, scores in buckets.items()
    }
    total = sum(values.values())
    return {key: value / total for key, value in values.items()}


def _score_matrix(lambda_home: float, lambda_away: float) -> dict[tuple[int, int], float]:
    return _exact_score_matrix(
        lambda_home,
        lambda_away,
        rho=0.0,
        max_goals=12,
    )


def _stored_distribution(row: Mapping[str, Any]) -> dict[str, float]:
    raw = row.get("model_distribution")
    if not isinstance(raw, Mapping) or set(raw) != set(_DISTRIBUTION_FIELDS):
        raise ValueError(f"EV_SE_MODEL_DISTRIBUTION_INVALID:{row['evaluation_id']}")
    return {key: float(raw[key]) for key in _DISTRIBUTION_FIELDS}


def _fit_objective(
    rows: list[dict[str, Any]], lambda_home: float, lambda_away: float
) -> float:
    matrix = _score_matrix(lambda_home, lambda_away)
    return sum(
        (actual - _stored_distribution(row)[key]) ** 2
        for row in rows
        for key, actual in _computed_distribution(matrix, row).items()
    )


def _initial_lambdas(row: Mapping[str, Any]) -> tuple[float, float]:
    base_home = (float(row["home_xg_for"]) + float(row["away_xg_against"])) / 2.0
    base_away = (float(row["away_xg_for"]) + float(row["home_xg_against"])) / 2.0
    total = min(max(base_home + base_away, 1.35), 4.40)
    delta = base_home - base_away + 0.12
    return (
        min(max((total + delta) / 2.0, 0.15), 4.25),
        min(max((total - delta) / 2.0, 0.15), 4.25),
    )


def _fit_lambdas(rows: list[dict[str, Any]]) -> tuple[float, float, float]:
    current = _initial_lambdas(rows[0])
    current_score = _fit_objective(rows, *current)
    step = 0.25
    while step > 0.00000025:
        candidates = {
            (
                min(max(current[0] + home_step * step, 0.15), 4.25),
                min(max(current[1] + away_step * step, 0.15), 4.25),
            )
            for home_step in (-1, 0, 1)
            for away_step in (-1, 0, 1)
            if home_step or away_step
        }
        scored = sorted(
            (_fit_objective(rows, *candidate), candidate) for candidate in candidates
        )
        best_score, best = scored[0]
        if best_score + 1e-18 < current_score:
            current, current_score = best, best_score
        else:
            step /= 2.0
    return current[0], current[1], current_score


def _lambda_nodes(
    mu: float,
    sigma: float,
    *,
    distance: float,
    weights: tuple[float, float, float],
) -> tuple[tuple[float, float], ...]:
    if sigma <= 0:
        return ((max(mu, 0.01), 1.0),)
    return (
        (max(mu - distance * sigma, 0.01), weights[0]),
        (max(mu, 0.01), weights[1]),
        (max(mu + distance * sigma, 0.01), weights[2]),
    )


def _scenario_rows(
    lambda_home: float,
    lambda_away: float,
    sigma_home: float,
    sigma_away: float,
    *,
    distance: float,
    weights: tuple[float, float, float],
) -> list[tuple[float, dict[tuple[int, int], float]]]:
    return [
        (home_weight * away_weight, _score_matrix(home_lambda, away_lambda))
        for home_lambda, home_weight in _lambda_nodes(
            lambda_home, sigma_home, distance=distance, weights=weights
        )
        for away_lambda, away_weight in _lambda_nodes(
            lambda_away, sigma_away, distance=distance, weights=weights
        )
    ]


def _ev_from_distribution(distribution: Mapping[str, float], price: float) -> float:
    return (
        float(distribution["WIN"]) * (price - 1.0)
        + float(distribution["HALF_WIN"]) * 0.5 * (price - 1.0)
        - float(distribution["HALF_LOSS"]) * 0.5
        - float(distribution["LOSS"])
    )


def _price(row: Mapping[str, Any]) -> tuple[float, str]:
    raw = row.get("decimal_odds")
    if raw is not None and float(raw) > 1.0:
        return float(raw), PAYLOAD_PRICE_SOURCE
    distribution = _stored_distribution(row)
    gain = distribution["WIN"] + 0.5 * distribution["HALF_WIN"]
    loss = distribution["LOSS"] + 0.5 * distribution["HALF_LOSS"]
    if gain <= 0:
        raise ValueError(f"EV_SE_PRICE_NOT_IDENTIFIABLE:{row['evaluation_id']}")
    price = 1.0 + (float(row["current_ev"]) + loss) / gain
    if price <= 1.0:
        raise ValueError(f"EV_SE_PRICE_INVALID:{row['evaluation_id']}")
    return price, DERIVED_PRICE_SOURCE


def _scenario_ev_stats(
    scenarios: list[tuple[float, dict[tuple[int, int], float]]],
    row: Mapping[str, Any],
    price: float,
) -> tuple[float, float]:
    values = [
        (weight, _ev_from_distribution(_computed_distribution(matrix, row), price))
        for weight, matrix in scenarios
    ]
    total_weight = sum(weight for weight, _ in values)
    mean = sum(weight * value for weight, value in values) / total_weight
    variance = sum(
        weight / total_weight * (value - mean) ** 2 for weight, value in values
    )
    return mean, math.sqrt(max(variance, 0.0))


def _mixed_ev(
    scenarios: list[tuple[float, dict[tuple[int, int], float]]],
    row: Mapping[str, Any],
    price: float,
) -> float:
    total_weight = sum(weight for weight, _ in scenarios)
    mixed = {key: 0.0 for key in _DISTRIBUTION_FIELDS}
    for weight, matrix in scenarios:
        distribution = _computed_distribution(matrix, row)
        for key, value in distribution.items():
            mixed[key] += weight / total_weight * value
    rounded = {key: round(value, 6) for key, value in mixed.items()}
    return _ev_from_distribution(rounded, price)


def _effective_lambda_sd(
    mu: float,
    sigma: float,
    *,
    distance: float,
    weights: tuple[float, float, float],
) -> float:
    nodes = _lambda_nodes(mu, sigma, distance=distance, weights=weights)
    total_weight = sum(weight for _, weight in nodes)
    mean = sum(value * weight for value, weight in nodes) / total_weight
    variance = sum(
        weight / total_weight * (value - mean) ** 2 for value, weight in nodes
    )
    return math.sqrt(max(variance, 0.0))


def _contract1_metrics(source_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in source_rows if row["kind"] == "contract_evaluation"]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["model_input_hash"])].append(row)
    eligible_groups = {
        key: values
        for key, values in grouped.items()
        if {str(row["market"]) for row in values} == {"ASIAN_HANDICAP", "TOTALS"}
    }
    excluded = sorted(
        row["evaluation_id"]
        for key, values in grouped.items()
        if key not in eligible_groups
        for row in values
    )

    lambda_by_group: dict[str, tuple[float, float]] = {}
    fit_distribution_errors: list[float] = []
    fit_objectives: list[float] = []
    sigma_ranges: list[float] = []
    for key, values in sorted(eligible_groups.items()):
        lambda_home, lambda_away, objective = _fit_lambdas(values)
        lambda_by_group[key] = (lambda_home, lambda_away)
        fit_objectives.append(objective)
        matrix = _score_matrix(lambda_home, lambda_away)
        fit_distribution_errors.extend(
            abs(actual - _stored_distribution(row)[field])
            for row in values
            for field, actual in _computed_distribution(matrix, row).items()
        )
        sigma_ranges.extend(
            (
                max(float(row[side]) for row in values)
                - min(float(row[side]) for row in values)
            )
            for side in ("sigma_home", "sigma_away")
        )

    replay_records: list[dict[str, Any]] = []
    analysis_old_se_residual_details: list[dict[str, Any]] = []
    point_ev_fit_residuals: list[float] = []
    for key, values in sorted(eligible_groups.items()):
        lambda_home, lambda_away = lambda_by_group[key]
        for row in values:
            sigma_home = float(row["sigma_home"])
            sigma_away = float(row["sigma_away"])
            price, price_source = _price(row)
            old_analysis = _scenario_rows(
                lambda_home,
                lambda_away,
                sigma_home,
                sigma_away,
                distance=1.0,
                weights=(0.25, 0.50, 0.25),
            )
            old_simulation = _scenario_rows(
                lambda_home,
                lambda_away,
                sigma_home,
                sigma_away,
                distance=1.0,
                weights=(0.158655, 0.68269, 0.158655),
            )
            gh3 = _scenario_rows(
                lambda_home,
                lambda_away,
                sigma_home,
                sigma_away,
                distance=GH3_DISTANCE,
                weights=GH3_WEIGHTS,
            )
            old_mean, old_se = _scenario_ev_stats(old_analysis, row, price)
            gh3_mean, gh3_se = _scenario_ev_stats(gh3, row, price)
            reported_se = float(row["current_ev"]) - float(row["current_ev_minus_se"])
            old_se_residual = old_se - reported_se
            point_distribution = _computed_distribution(
                _score_matrix(lambda_home, lambda_away), row
            )
            point_ev_residual = (
                _ev_from_distribution(point_distribution, price)
                - float(row["current_ev"])
            )
            replay_records.append(
                {
                    "model_input_hash": key,
                    "evaluation_id": str(row["evaluation_id"]),
                    "price_source": price_source,
                    "reported_point_ev_delta": 0.0,
                    "analysis_mean_delta": gh3_mean - old_mean,
                    "analysis_se_delta": gh3_se - old_se,
                    "reconstructed_old_ev_se": old_se,
                    "old_se_residual": old_se_residual,
                    "point_ev_residual": point_ev_residual,
                    "simulation_ev_delta": _mixed_ev(gh3, row, price)
                    - _mixed_ev(old_simulation, row, price),
                }
            )
            if abs(old_se_residual) > FLOAT_TOLERANCE + 1e-12:
                analysis_old_se_residual_details.append(
                    {
                        "evaluation_id": str(row["evaluation_id"]),
                        "fixture_id": str(row["fixture_id"]),
                        "model_input_hash": key,
                        "market": str(row["market"]),
                        "evaluated_at": str(row["evaluated_at"]),
                        "line": _round(float(row["exact_line"])),
                        "price": _round(price),
                        "price_source": price_source,
                        "reported_ev_se": _round(reported_se),
                        "reconstructed_old_ev_se": _round(old_se),
                        "residual": _round(old_se_residual),
                        "lambda_home": _round(lambda_home),
                        "lambda_away": _round(lambda_away),
                        "sigma_home": _round(sigma_home),
                        "sigma_away": _round(sigma_away),
                    }
                )
            point_ev_fit_residuals.append(point_ev_residual)

    nonreproducible_groups = {
        str(row["model_input_hash"])
        for row in replay_records
        if abs(float(row["old_se_residual"])) > FLOAT_TOLERANCE + 1e-12
    }
    reproducible_groups = {
        key: values
        for key, values in eligible_groups.items()
        if key not in nonreproducible_groups
    }
    reproducible_records = [
        row
        for row in replay_records
        if str(row["model_input_hash"]) not in nonreproducible_groups
    ]
    excluded_nonreproducible_records = [
        row
        for row in replay_records
        if str(row["model_input_hash"]) in nonreproducible_groups
    ]
    analysis_mean_deltas = [
        float(row["analysis_mean_delta"]) for row in reproducible_records
    ]
    analysis_se_deltas = [
        float(row["analysis_se_delta"]) for row in reproducible_records
    ]
    simulation_ev_deltas = [
        float(row["simulation_ev_delta"]) for row in reproducible_records
    ]
    analysis_old_se_residuals = [
        float(row["old_se_residual"]) for row in replay_records
    ]
    reproducible_old_se_residuals = [
        float(row["old_se_residual"]) for row in reproducible_records
    ]
    price_sources: dict[str, int] = defaultdict(int)
    for row in reproducible_records:
        price_sources[str(row["price_source"])] += 1
    evaluation_count = len(reproducible_records)
    expected_price_sources = {PAYLOAD_PRICE_SOURCE, DERIVED_PRICE_SOURCE}
    if set(price_sources) != expected_price_sources:
        raise ValueError(f"EV_SE_PRICE_SOURCE_SET_INVALID:{sorted(price_sources)}")

    attempted_price_sources: dict[str, int] = defaultdict(int)
    excluded_price_sources: dict[str, int] = defaultdict(int)
    for row in replay_records:
        attempted_price_sources[str(row["price_source"])] += 1
    for row in excluded_nonreproducible_records:
        excluded_price_sources[str(row["price_source"])] += 1

    price_source_strata: dict[str, Any] = {}
    for price_source in sorted(expected_price_sources):
        stratum = [
            row
            for row in reproducible_records
            if str(row["price_source"]) == price_source
        ]
        predicted_linear_deltas = [
            float(row["reconstructed_old_ev_se"]) * (math.sqrt(2.0) - 1.0)
            for row in stratum
        ]
        actual_ev_se_deltas = [float(row["analysis_se_delta"]) for row in stratum]
        predicted_mean = statistics.fmean(predicted_linear_deltas)
        actual_mean = statistics.fmean(actual_ev_se_deltas)
        price_source_strata[price_source] = {
            "n": len(stratum),
            **{
                output_field: _distribution_summary(
                    [float(row[record_field]) for row in stratum]
                )
                for output_field, record_field in PRICE_SOURCE_COMPARISON_FIELDS.items()
            },
            "pure_sqrt_2_linear_rescaling_reference": {
                "basis": "FORWARD_RECONSTRUCTED_OLD_EV_SE_TIMES_SQRT_2_MINUS_1;_NO_HISTORICAL_SIGMA_BACKSOLVE",
                "predicted_ev_se_delta": _distribution_summary(
                    predicted_linear_deltas
                ),
                "actual_minus_predicted_ev_se_delta": _distribution_summary(
                    [
                        actual - predicted
                        for actual, predicted in zip(
                            actual_ev_se_deltas,
                            predicted_linear_deltas,
                            strict=True,
                        )
                    ]
                ),
                "actual_mean": _round(actual_mean),
                "predicted_mean": _round(predicted_mean),
                "absolute_relative_mean_gap": _round(
                    abs(actual_mean - predicted_mean) / abs(predicted_mean)
                ),
            },
        }

    distribution_difference_assessments = {
        output_field: _distribution_difference_assessment(
            [
                float(row[record_field])
                for row in reproducible_records
                if str(row["price_source"]) == DERIVED_PRICE_SOURCE
            ],
            [
                float(row[record_field])
                for row in reproducible_records
                if str(row["price_source"]) == PAYLOAD_PRICE_SOURCE
            ],
        )
        for output_field, record_field in PRICE_SOURCE_COMPARISON_FIELDS.items()
    }
    ev_se_difference = distribution_difference_assessments[
        "ev_se_delta_gh3_minus_old"
    ]
    pooled_linear_predictions = [
        float(row["reconstructed_old_ev_se"]) * (math.sqrt(2.0) - 1.0)
        for row in reproducible_records
    ]
    pooled_linear_prediction_mean = statistics.fmean(pooled_linear_predictions)
    pooled_actual_ev_se_delta_mean = statistics.fmean(analysis_se_deltas)
    pooled_reference = {
        "basis": "FORWARD_RECONSTRUCTED_OLD_EV_SE_TIMES_SQRT_2_MINUS_1;_NO_HISTORICAL_SIGMA_BACKSOLVE",
        "predicted_ev_se_delta": _distribution_summary(
            pooled_linear_predictions
        ),
        "actual_mean": _round(pooled_actual_ev_se_delta_mean),
        "recomputed_predicted_mean": _round(pooled_linear_prediction_mean),
        "absolute_relative_mean_gap_to_recomputed_prediction": _round(
            abs(pooled_actual_ev_se_delta_mean - pooled_linear_prediction_mean)
            / abs(pooled_linear_prediction_mean)
        ),
        "reviewer_supplied_predicted_mean": REVIEWER_SQRT2_POOLED_DELTA_REFERENCE,
        "absolute_relative_mean_gap_to_reviewer_reference": _round(
            abs(
                pooled_actual_ev_se_delta_mean
                - REVIEWER_SQRT2_POOLED_DELTA_REFERENCE
            )
            / REVIEWER_SQRT2_POOLED_DELTA_REFERENCE
        ),
    }

    floor_samples = []
    old_floor_sides = 0
    gh3_floor_sides = 0
    old_floor_groups: set[str] = set()
    gh3_floor_groups: set[str] = set()
    lower_node_margins: list[dict[str, Any]] = []
    for key, values in sorted(reproducible_groups.items()):
        fixture_id = str(values[0]["fixture_id"])
        lambda_home, lambda_away = lambda_by_group[key]
        for side, mu, sigma in (
            ("HOME", lambda_home, float(values[0]["sigma_home"])),
            ("AWAY", lambda_away, float(values[0]["sigma_away"])),
        ):
            old_floor = mu - sigma < 0.01
            gh3_floor = mu - GH3_DISTANCE * sigma < 0.01
            lower_node_margins.append(
                {
                    "model_input_hash": key,
                    "fixture_id": fixture_id,
                    "side": side,
                    "evaluation_ids": sorted(str(row["evaluation_id"]) for row in values),
                    "mu": _round(mu),
                    "sigma": _round(sigma),
                    "old_unfloored_lower_node": _round(mu - sigma),
                    "gh3_unfloored_lower_node": _round(
                        mu - GH3_DISTANCE * sigma
                    ),
                }
            )
            old_floor_sides += int(old_floor)
            gh3_floor_sides += int(gh3_floor)
            if old_floor:
                old_floor_groups.add(key)
            if gh3_floor:
                gh3_floor_groups.add(key)
                gh3_sd = _effective_lambda_sd(
                    mu, sigma, distance=GH3_DISTANCE, weights=GH3_WEIGHTS
                )
                floor_samples.append(
                    {
                        "model_input_hash": key,
                        "fixture_id": fixture_id,
                        "side": side,
                        "evaluation_ids": sorted(str(row["evaluation_id"]) for row in values),
                        "mu": _round(mu),
                        "sigma": _round(sigma),
                        "old_floor_triggered": old_floor,
                        "gh3_effective_sd": _round(gh3_sd),
                        "gh3_effective_sd_over_sigma": _round(gh3_sd / sigma),
                    }
                )
    side_inputs = len(reproducible_groups) * 2
    gh3_ratios = [float(row["gh3_effective_sd_over_sigma"]) for row in floor_samples]
    gh3_sds = [float(row["gh3_effective_sd"]) for row in floor_samples]
    return {
        "same_evaluation_cohort": {
            "frozen_usable_evaluations": len(rows),
            "paired_market_eligible_evaluations": evaluation_count,
            "paired_market_model_input_groups": len(reproducible_groups),
            "paired_market_identifiable_evaluations_before_baseline_gate": len(
                replay_records
            ),
            "paired_market_identifiable_model_input_groups_before_baseline_gate": len(
                eligible_groups
            ),
            "baseline_reproducible_evaluations": evaluation_count,
            "baseline_reproducible_model_input_groups": len(reproducible_groups),
            "excluded_nonreproducible_evaluations": len(replay_records)
            - evaluation_count,
            "excluded_nonreproducible_model_input_groups": len(
                nonreproducible_groups
            ),
            "excluded_nonreproducible_fixtures": len(
                {str(row["fixture_id"]) for row in analysis_old_se_residual_details}
            ),
            "excluded_nonreproducible_evaluation_ids": sorted(
                str(row["evaluation_id"])
                for row in replay_records
                if str(row["model_input_hash"]) in nonreproducible_groups
            ),
            "excluded_nonreproducible_reason": "FROZEN_DYNAMIC_EVALUATION_OMITS_ORIGINAL_SIGMA;_CURRENT_PIT_INPUT_RECONSTRUCTION_DOES_NOT_REPLAY_REPORTED_OLD_EV_SE_WITHIN_TOLERANCE;_NO_SIGMA_BACKSOLVE_ALLOWED",
            "excluded_unidentifiable_single_market_evaluations": len(excluded),
            "excluded_evaluation_ids": excluded,
            "price_source_counts": dict(sorted(price_sources.items())),
            "price_source_baseline_gate_lineage": {
                price_source: {
                    "attempted_identifiable_evaluations": attempted_price_sources[
                        price_source
                    ],
                    "accepted_evaluations": price_sources[price_source],
                    "excluded_evaluations": excluded_price_sources[price_source],
                    "failure_rate_among_attempted": _round(
                        excluded_price_sources[price_source]
                        / attempted_price_sources[price_source]
                    ),
                    "excluded_to_accepted_ratio": _round(
                        excluded_price_sources[price_source]
                        / price_sources[price_source]
                    ),
                }
                for price_source in sorted(expected_price_sources)
            },
        },
        "lambda_reconstruction": {
            "method": "DETERMINISTIC_TWO_DIMENSION_PATTERN_SEARCH_AGAINST_FROZEN_FIVE_STATE_DISTRIBUTIONS",
            "rho": 0.0,
            "max_goals": 12,
            "max_absolute_distribution_probability_error": _round(max(fit_distribution_errors)),
            "max_fit_objective": _round(max(fit_objectives)),
            "max_sigma_range_within_model_input_group": _round(max(sigma_ranges)),
            "point_ev_fit_residual": _distribution_summary(point_ev_fit_residuals),
            "old_analysis_ev_se_residual": _distribution_summary(
                analysis_old_se_residuals
            ),
            "baseline_gate_tolerance": FLOAT_TOLERANCE,
            "baseline_reproducible_old_analysis_ev_se_residual": _distribution_summary(
                reproducible_old_se_residuals
            ),
            "old_analysis_ev_se_residual_outliers_over_tolerance": sorted(
                analysis_old_se_residual_details,
                key=lambda row: (-abs(float(row["residual"])), row["evaluation_id"]),
            ),
        },
        "analysis_evidence_consumer": {
            "reported_point_ev_delta": _distribution_summary([0.0] * evaluation_count),
            "reason_reported_ev_unchanged": "REPORTED_EV_USES_POINT_LAMBDAS;_lambda_scenarios_ONLY_COMPUTES_EV_SE",
            "internal_quadrature_mean_ev_delta_gh3_minus_old": _distribution_summary(
                analysis_mean_deltas
            ),
            "ev_se_delta_gh3_minus_old": _distribution_summary(analysis_se_deltas),
        },
        "simulation_consumer": {
            "mixed_score_matrix_ev_delta_gh3_minus_old": _distribution_summary(
                simulation_ev_deltas
            ),
            "settlement_probability_rounding_decimals": 6,
        },
        "price_source_stratified_comparison": {
            "strata": price_source_strata,
            "distribution_difference_assessments": distribution_difference_assessments,
            "ev_se_pooled_mean_question": {
                "pooled_mean": _round(pooled_actual_ev_se_delta_mean),
                "answer": (
                    "YES_MIXTURE_OF_MATERIALLY_DIFFERENT_PRICE_SOURCE_DISTRIBUTIONS"
                    if ev_se_difference["material_difference"]
                    else "MATHEMATICAL_MIXTURE_BUT_NO_MATERIAL_PRICE_SOURCE_DISTRIBUTION_DIFFERENCE"
                ),
                "pooled_mean_must_not_be_the_only_reporting_granularity": bool(
                    ev_se_difference["material_difference"]
                ),
                "criterion_reference": ev_se_difference["criterion"],
            },
            "pure_sqrt_2_linear_rescaling_reference": pooled_reference,
        },
        "lower_node_floor": {
            "floor": 0.01,
            "lambda_side_inputs": side_inputs,
            "old_distance_sigma": 1.0,
            "old_triggered_lambda_sides": old_floor_sides,
            "old_trigger_rate": _round(old_floor_sides / side_inputs),
            "old_affected_model_input_groups": len(old_floor_groups),
            "old_affected_evaluations": sum(
                len(eligible_groups[key]) for key in old_floor_groups
            ),
            "gh3_distance_sigma": _round(GH3_DISTANCE, 10),
            "gh3_triggered_lambda_sides": gh3_floor_sides,
            "gh3_trigger_rate": _round(gh3_floor_sides / side_inputs),
            "gh3_affected_model_input_groups": len(gh3_floor_groups),
            "gh3_affected_evaluations": sum(
                len(eligible_groups[key]) for key in gh3_floor_groups
            ),
            "newly_affected_model_input_groups": len(
                gh3_floor_groups - old_floor_groups
            ),
            "newly_affected_evaluations": sum(
                len(eligible_groups[key])
                for key in gh3_floor_groups - old_floor_groups
            ),
            "gh3_effective_sd_on_triggered_sides": _distribution_summary(gh3_sds),
            "gh3_effective_sd_over_sigma_on_triggered_sides": _distribution_summary(
                gh3_ratios
            ),
            "affected_samples": floor_samples,
            "closest_unfloored_lower_nodes": {
                "old": min(
                    lower_node_margins,
                    key=lambda row: float(row["old_unfloored_lower_node"]),
                ),
                "gh3": min(
                    lower_node_margins,
                    key=lambda row: float(row["gh3_unfloored_lower_node"]),
                ),
            },
            "contract_exception": "WHEN_THE_0_01_FLOOR_TRIGGERS_THE_DISCRETE_NODE_SD_IS_LESS_THAN_SIGMA",
        },
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
    enabled_rows = [row for row in source_rows if row["kind"] == "enabled_competition"]
    runtime_denominator_rows = [
        row for row in source_rows if row["kind"] == "denominator_runtime_competition"
    ]
    observed_counts = {
        kind: sum(row["kind"] == kind for row in source_rows)
        for kind in ("coverage_evaluation", "contract_evaluation", "enabled_competition", "xg")
    }
    expected_counts = {
        "coverage_evaluation": int(source_counts["coverage_evaluations"]),
        "contract_evaluation": int(source_counts["contract_evaluations"]),
        "enabled_competition": int(source_counts["enabled_competitions"]),
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
    coverage_metrics = _coverage_metrics(source_rows, corpus, enabled_rows)
    coverage_by_competition = {
        row["competition_id"]: row for row in coverage_metrics["by_competition"]
    }
    enabled_competition_ids = set(coverage_by_competition)
    runtime_competition_ids = {
        str(row["competition_id"]) for row in runtime_denominator_rows
    }
    if runtime_competition_ids != enabled_competition_ids:
        raise ValueError(
            "EV_SE_RUNTIME_DENOMINATOR_SCOPE_MISMATCH:"
            f"{sorted(runtime_competition_ids)}:{sorted(enabled_competition_ids)}"
        )
    for row in runtime_denominator_rows:
        coverage_by_competition[str(row["competition_id"])]["runtime_sources"] = {
            "canonical_team_match_history_team_rows": int(
                row["canonical_history_team_rows"]
            ),
            "canonical_team_match_history_fixtures": int(
                row["canonical_history_fixtures"]
            ),
            "matchday_fixture_identity_fixtures": int(
                row["matchday_identity_fixtures"]
            ),
        }
    contract1 = _contract1_metrics(source_rows)
    cohort = contract1["same_evaluation_cohort"]
    reconstruction = contract1["lambda_reconstruction"]
    if (
        int(cohort["excluded_unidentifiable_single_market_evaluations"])
        + int(cohort["paired_market_identifiable_evaluations_before_baseline_gate"])
        != int(cohort["frozen_usable_evaluations"])
    ):
        raise ValueError("EV_SE_CONTRACT1_IDENTIFIABLE_COHORT_MISMATCH")
    if (
        int(cohort["excluded_nonreproducible_evaluations"])
        + int(cohort["baseline_reproducible_evaluations"])
        != int(cohort["paired_market_identifiable_evaluations_before_baseline_gate"])
    ):
        raise ValueError("EV_SE_CONTRACT1_BASELINE_GATE_COHORT_MISMATCH")
    if (
        float(reconstruction["max_absolute_distribution_probability_error"])
        > FLOAT_TOLERANCE
        or float(reconstruction["point_ev_fit_residual"]["max_absolute"])
        > FLOAT_TOLERANCE
        or float(
            reconstruction["baseline_reproducible_old_analysis_ev_se_residual"][
                "max_absolute"
            ]
        )
        > FLOAT_TOLERANCE
    ):
        raise ValueError("EV_SE_CONTRACT1_BASELINE_REPRODUCTION_FAILED")
    stratified = contract1["price_source_stratified_comparison"]
    strata = stratified["strata"]
    expected_price_sources = {PAYLOAD_PRICE_SOURCE, DERIVED_PRICE_SOURCE}
    if set(strata) != expected_price_sources:
        raise ValueError("EV_SE_CONTRACT1_PRICE_SOURCE_STRATA_MISSING")
    if sum(int(stratum["n"]) for stratum in strata.values()) != int(
        cohort["baseline_reproducible_evaluations"]
    ):
        raise ValueError("EV_SE_CONTRACT1_PRICE_SOURCE_STRATA_COUNT_MISMATCH")
    pooled_summaries = {
        "reported_point_ev_delta": contract1["analysis_evidence_consumer"][
            "reported_point_ev_delta"
        ],
        "internal_quadrature_mean_ev_delta_gh3_minus_old": contract1[
            "analysis_evidence_consumer"
        ]["internal_quadrature_mean_ev_delta_gh3_minus_old"],
        "ev_se_delta_gh3_minus_old": contract1["analysis_evidence_consumer"][
            "ev_se_delta_gh3_minus_old"
        ],
        "mixed_score_matrix_ev_delta_gh3_minus_old": contract1[
            "simulation_consumer"
        ]["mixed_score_matrix_ev_delta_gh3_minus_old"],
    }
    required_summary_fields = {
        "n",
        "min",
        "p05",
        "p25",
        "median",
        "mean",
        "p75",
        "p95",
        "max",
        "max_absolute",
    }
    for metric, pooled_summary in pooled_summaries.items():
        weighted_mean = 0.0
        for stratum in strata.values():
            summary = stratum[metric]
            if set(summary) != required_summary_fields or int(summary["n"]) != int(
                stratum["n"]
            ):
                raise ValueError(
                    f"EV_SE_CONTRACT1_PRICE_SOURCE_SUMMARY_INVALID:{metric}"
                )
            weighted_mean += float(summary["mean"]) * int(stratum["n"])
        weighted_mean /= int(cohort["baseline_reproducible_evaluations"])
        if abs(weighted_mean - float(pooled_summary["mean"])) > 2 * FLOAT_TOLERANCE:
            raise ValueError(
                f"EV_SE_CONTRACT1_PRICE_SOURCE_WEIGHTED_MEAN_MISMATCH:{metric}"
            )
    gate_lineage = cohort["price_source_baseline_gate_lineage"]
    if any(
        int(gate_lineage[source]["accepted_evaluations"])
        + int(gate_lineage[source]["excluded_evaluations"])
        != int(gate_lineage[source]["attempted_identifiable_evaluations"])
        for source in expected_price_sources
    ):
        raise ValueError("EV_SE_CONTRACT1_PRICE_SOURCE_GATE_LINEAGE_MISMATCH")
    return {
        "schema_version": "w2.ev_se.offline_preregistration_evidence.v4",
        "status": "OWNER_CONTRACT1_SEMANTICS_APPROVED_OFFLINE_GH3_IMPACT_PRICE_SOURCE_STRATIFIED_PRODUCTION_CHANGE_GATED",
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
            "shared_sigma_semantics": "CONTRACT_1_TRUE_STANDARD_DEVIATION",
        },
        "owner_decisions": {
            "item_1_lambda_sigma_semantics": {
                "status": "APPROVED_SEMANTIC_CONTRACT_ONLY",
                "contract": "CONTRACT_1_TRUE_STANDARD_DEVIATION",
                "meaning": "lambda_sigma_is_the_standard_deviation_of_the_lambda_distribution",
                "reference_quadrature": {
                    "name": "GH-3",
                    "standardized_nodes": [
                        -_round(GH3_DISTANCE, 10),
                        0.0,
                        _round(GH3_DISTANCE, 10),
                    ],
                    "weights": [
                        _round(GH3_WEIGHTS[0], 10),
                        _round(GH3_WEIGHTS[1], 10),
                        _round(GH3_WEIGHTS[2], 10),
                    ],
                    "matched_standard_normal_moments": {
                        "m0": 1.0,
                        "m1": 0.0,
                        "m2": 1.0,
                        "m3": 0.0,
                        "m4": 3.0,
                    },
                },
                "coefficient_or_formula_approved": False,
                "production_implementation_approved": False,
                "production_gate": "INDEPENDENT_CHANGE_REQUIRED_BEFORE_EV_SE_FORMULA_CHANGE",
            },
            "item_2_expected_match_denominator_authority": {
                "status": "OWNER_DECISION_REQUIRED_EVIDENCE_ONLY",
            },
            "item_3_formula_family": {
                "status": "FROZEN_PENDING_ITEM_2_DECISION",
            },
        },
        "contract_1_gh3_offline_impact": contract1,
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
            "enabled_scope_feasibility": coverage_metrics,
            "authority_candidate_facts": {
                "canonical_team_match_history": {
                    "status": "CURRENT_SCOPE_INSUFFICIENT",
                    "reason": "NO_ROWS_FOR_THE_ENABLED_SCOPE_AT_THE_FROZEN_OBSERVATION",
                },
                "matchday_fixture_identities": {
                    "status": "IDENTITY_ONLY_NOT_A_FINISHED_MATCH_DENOMINATOR",
                    "reason": "THE_TABLE_HAS_NO_FINISHED_STATUS_RESULT_OR_RESULT_VISIBILITY_TIME",
                },
                "persisted_saved_raw_fixtures": {
                    "status": "SOURCE_FEASIBLE_RUNTIME_MATERIALIZATION_REQUIRED",
                    "reason": "THE_FROZEN_CORPUS_PROVES_FIXTURE_IDENTITY_KICKOFF_RESULT_AND_FIRST_RESULT_VISIBILITY_BUT_IS_NOT_A_RUNTIME_TABLE",
                },
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
    contract = evidence["contract_1_gh3_offline_impact"]
    cohort = contract["same_evaluation_cohort"]
    reconstruction = contract["lambda_reconstruction"]
    analysis_consumer = contract["analysis_evidence_consumer"]
    simulation_consumer = contract["simulation_consumer"]
    stratified = contract["price_source_stratified_comparison"]
    price_strata = stratified["strata"]
    ev_se_source_assessment = stratified["distribution_difference_assessments"][
        "ev_se_delta_gh3_minus_old"
    ]
    pooled_sqrt2 = stratified["pure_sqrt_2_linear_rescaling_reference"]
    floor = contract["lower_node_floor"]
    coverage = evidence["coverage_denominator"]
    scope = coverage["enabled_scope_feasibility"]
    aggregate = scope["aggregate_counts_without_coverage_average"]
    lineage = evidence["reproducibility"]["row_count_lineage"]
    minimum = evidence["reproducibility"]["minimum_lineage"]
    per_league_rows = "\n".join(
        "| `{competition_id}` | `{evaluations_with_both_expected_denominators_ge3}` | "
        "`{offline_corpus_finished_fixtures}` | `{offline_structural_xg_coverage}` | "
        "`{point_in_time_denominator_available_evaluations}` | "
        "`{point_in_time_xg_coverage}` | `{canonical}` / `{identities}` |".format(
            **row,
            canonical=row["runtime_sources"][
                "canonical_team_match_history_fixtures"
            ],
            identities=row["runtime_sources"]["matchday_fixture_identity_fixtures"],
        )
        for row in scope["by_competition"]
    )
    floor_sd_text = (
        f"{floor['gh3_effective_sd_on_triggered_sides']['min']:.6f} / "
        f"{floor['gh3_effective_sd_on_triggered_sides']['median']:.6f} / "
        f"{floor['gh3_effective_sd_on_triggered_sides']['max']:.6f}"
        if floor["gh3_triggered_lambda_sides"]
        else "not observed (0 triggered sides)"
    )
    floor_ratio_text = (
        f"{floor['gh3_effective_sd_over_sigma_on_triggered_sides']['min']:.6f} / "
        f"{floor['gh3_effective_sd_over_sigma_on_triggered_sides']['median']:.6f} / "
        f"{floor['gh3_effective_sd_over_sigma_on_triggered_sides']['max']:.6f}"
        if floor["gh3_triggered_lambda_sides"]
        else "not observed (0 triggered sides)"
    )
    metric_labels = {
        "reported_point_ev_delta": "reported point EV delta",
        "internal_quadrature_mean_ev_delta_gh3_minus_old": "internal quadrature mean EV delta",
        "ev_se_delta_gh3_minus_old": "ev_se delta",
        "mixed_score_matrix_ev_delta_gh3_minus_old": "mixed-score-matrix EV delta",
    }
    price_source_rows = "\n".join(
        "| `{source}` | {metric} | `{n}` | `{min:+.6f}` | `{p05:+.6f}` | "
        "`{p25:+.6f}` | `{median:+.6f}` | `{mean:+.6f}` | `{p75:+.6f}` | "
        "`{p95:+.6f}` | `{max:+.6f}` | `{max_absolute:.6f}` |".format(
            source=source,
            metric=metric_labels[metric],
            **price_strata[source][metric],
        )
        for source in (DERIVED_PRICE_SOURCE, PAYLOAD_PRICE_SOURCE)
        for metric in PRICE_SOURCE_COMPARISON_FIELDS
    )
    sqrt2_source_rows = "\n".join(
        "| `{source}` | `{n}` | `{actual:+.6f}` | `{predicted:+.6f}` | "
        "`{gap:.4%}` |".format(
            source=source,
            n=price_strata[source]["n"],
            actual=price_strata[source]["pure_sqrt_2_linear_rescaling_reference"][
                "actual_mean"
            ],
            predicted=price_strata[source][
                "pure_sqrt_2_linear_rescaling_reference"
            ]["predicted_mean"],
            gap=price_strata[source]["pure_sqrt_2_linear_rescaling_reference"][
                "absolute_relative_mean_gap"
            ],
        )
        for source in (DERIVED_PRICE_SOURCE, PAYLOAD_PRICE_SOURCE)
    )
    ev_se_mixture_text = (
        "The price-source layers meet the preregistered descriptive materiality criterion. The pooled mean must therefore not be the only reporting granularity."
        if ev_se_source_assessment["material_difference"]
        else "The pooled cohort is mathematically a mixture of two price-source layers, but their `ev_se` delta distributions do not meet the preregistered descriptive materiality criterion; the pooled mean remains a valid compact summary when the two layer summaries accompany it."
    )
    return f"""# EV SE offline preregistration baseline — 2026-08-23

Status: `CONTRACT_1_SEMANTICS_APPROVED / OFFLINE_GH3_IMPACT_REPRODUCIBLE / PRODUCTION_IMPLEMENTATION_GATED / SE_FORMULA_FROZEN`

## Execution boundary

- Exact production release observed: `{RELEASE_ID}`.
- Exact production schema: `{SCHEMA}`.
- Evidence observed at: `{OBSERVED_AT}`.
- Provider calls / production database writes / outcomes read: `0 / 0 / 0`.
- No model, threshold, Scheduler, notification, deployment, or runtime configuration changed.

This document preregisters the problem and behavioral acceptance conditions and records the Owner's Contract 1 semantic decision. The approval defines what `lambda_sigma` means; it does not approve any coefficient, SE formula, production implementation, or release. Reproduction is defined in `README.md`; every numeric field below is rendered by `scripts/audit_ev_se_offline_preregistration.py`.

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

### 2. Owner decision 1 — Contract 1 is approved as a semantic contract

The EV-SE nodes use `0.25 / 0.50 / 0.25`, so effective SD is `{coefficient['ev_se_node_weight_effective_sigma_multiplier']:.4f} sigma`. Simulation uses `0.158655 / 0.68269 / 0.158655`, so effective SD is `{coefficient['simulation_node_weight_effective_sigma_multiplier']:.4f} sigma`; their ratio is `{coefficient['effective_sigma_multiplier_ratio']:.4f}`. Both paths also floor the lower node at `max(mu - sigma, {coefficient['lower_node_floor']:.2f})`, which further compresses dispersion as `mu - sigma` approaches zero.

Owner selected **Contract 1: `lambda_sigma` is the true standard deviation of the lambda distribution**. This approval is semantic only. It does not approve the current SE formula, any coefficient, production code, or release.

The reference discretization is GH-3: standardized nodes `-sqrt(3), 0, +sqrt(3)` and weights `1/6, 2/3, 1/6`. Its discrete moments are `m0=1, m1=0, m2=1, m3=0, m4=3`, matching a standard normal through degree four. At an interior point where the `0.01` floor does not fire, its effective SD is therefore exactly `sigma`. The old paths match neither the required second moment nor each other.

## EV-SE-EXEC-05 — frozen GH-3 impact

Of the `{cohort['frozen_usable_evaluations']:,}` usable evaluations, `{cohort['excluded_unidentifiable_single_market_evaluations']}` were excluded because their model-input group contains only one market, so both point lambdas cannot be identified from the frozen five-state distributions. That leaves `{cohort['paired_market_identifiable_evaluations_before_baseline_gate']:,}` identifiable evaluations in `{cohort['paired_market_identifiable_model_input_groups_before_baseline_gate']:,}` groups before the baseline-reproduction gate.

The frozen dynamic read model does not retain the original lambda sigmas. Current PIT input reconstruction failed to reproduce old reported `ev_se` within `{reconstruction['baseline_gate_tolerance']:.6f}` for `{cohort['excluded_nonreproducible_evaluations']}` evaluations / `{cohort['excluded_nonreproducible_model_input_groups']}` whole model-input groups across `{cohort['excluded_nonreproducible_fixtures']}` fixtures. The script excludes those groups instead of back-solving sigma from the answer. Their exact evaluation IDs, timestamps, inputs, reported values, reconstructed values, and residuals remain in the JSON. The actual old-versus-GH-3 comparison therefore uses the same `{cohort['baseline_reproducible_evaluations']:,}` evaluations in `{cohort['baseline_reproducible_model_input_groups']:,}` groups on both sides. Prices came from the payload for `{cohort['price_source_counts'].get('PAYLOAD_DECIMAL_ODDS', 0):,}` comparison rows and were algebraically recovered from current EV plus the five-state distribution for `{cohort['price_source_counts'].get('DERIVED_FROM_CURRENT_EV_AND_FIVE_STATE_DISTRIBUTION', 0):,}` rows.

Lambda reconstruction is outcome-free. It fits the two point lambdas to the frozen AH/TOTALS five-state distributions with `rho=0` and the existing 13x13 matrix. Maximum absolute distribution-probability error is `{reconstruction['max_absolute_distribution_probability_error']:.6f}`; maximum point-EV reconstruction residual is `{reconstruction['point_ev_fit_residual']['max_absolute']:.6f}`. Before the baseline gate, maximum old reported `ev_se` reconstruction residual is `{reconstruction['old_analysis_ev_se_residual']['max_absolute']:.6f}`; inside the accepted comparison cohort it is `{reconstruction['baseline_reproducible_old_analysis_ev_se_residual']['max_absolute']:.6f}`.

| Consumer / measurement | mean delta GH-3 minus old | p05 / median / p95 | min / max | max absolute |
|---|---:|---:|---:|---:|
| analysis-evidence reported point EV | `{analysis_consumer['reported_point_ev_delta']['mean']:+.6f}` | `{analysis_consumer['reported_point_ev_delta']['p05']:+.6f} / {analysis_consumer['reported_point_ev_delta']['median']:+.6f} / {analysis_consumer['reported_point_ev_delta']['p95']:+.6f}` | `{analysis_consumer['reported_point_ev_delta']['min']:+.6f} / {analysis_consumer['reported_point_ev_delta']['max']:+.6f}` | `{analysis_consumer['reported_point_ev_delta']['max_absolute']:.6f}` |
| analysis-evidence internal quadrature mean EV | `{analysis_consumer['internal_quadrature_mean_ev_delta_gh3_minus_old']['mean']:+.6f}` | `{analysis_consumer['internal_quadrature_mean_ev_delta_gh3_minus_old']['p05']:+.6f} / {analysis_consumer['internal_quadrature_mean_ev_delta_gh3_minus_old']['median']:+.6f} / {analysis_consumer['internal_quadrature_mean_ev_delta_gh3_minus_old']['p95']:+.6f}` | `{analysis_consumer['internal_quadrature_mean_ev_delta_gh3_minus_old']['min']:+.6f} / {analysis_consumer['internal_quadrature_mean_ev_delta_gh3_minus_old']['max']:+.6f}` | `{analysis_consumer['internal_quadrature_mean_ev_delta_gh3_minus_old']['max_absolute']:.6f}` |
| analysis-evidence `ev_se` | `{analysis_consumer['ev_se_delta_gh3_minus_old']['mean']:+.6f}` | `{analysis_consumer['ev_se_delta_gh3_minus_old']['p05']:+.6f} / {analysis_consumer['ev_se_delta_gh3_minus_old']['median']:+.6f} / {analysis_consumer['ev_se_delta_gh3_minus_old']['p95']:+.6f}` | `{analysis_consumer['ev_se_delta_gh3_minus_old']['min']:+.6f} / {analysis_consumer['ev_se_delta_gh3_minus_old']['max']:+.6f}` | `{analysis_consumer['ev_se_delta_gh3_minus_old']['max_absolute']:.6f}` |
| simulation mixed-score EV | `{simulation_consumer['mixed_score_matrix_ev_delta_gh3_minus_old']['mean']:+.6f}` | `{simulation_consumer['mixed_score_matrix_ev_delta_gh3_minus_old']['p05']:+.6f} / {simulation_consumer['mixed_score_matrix_ev_delta_gh3_minus_old']['median']:+.6f} / {simulation_consumer['mixed_score_matrix_ev_delta_gh3_minus_old']['p95']:+.6f}` | `{simulation_consumer['mixed_score_matrix_ev_delta_gh3_minus_old']['min']:+.6f} / {simulation_consumer['mixed_score_matrix_ev_delta_gh3_minus_old']['max']:+.6f}` | `{simulation_consumer['mixed_score_matrix_ev_delta_gh3_minus_old']['max_absolute']:.6f}` |

The reported analysis-evidence point EV stays unchanged because `_lambda_scenarios` only computes `ev_se`; the internal quadrature mean is reported separately so the weighting effect is still visible.

## EV-SE-EXEC-06 — price-source stratification

The baseline gate lineage is source-specific. `{DERIVED_PRICE_SOURCE}` has `{cohort['price_source_baseline_gate_lineage'][DERIVED_PRICE_SOURCE]['attempted_identifiable_evaluations']}` attempted identifiable evaluations, `{cohort['price_source_baseline_gate_lineage'][DERIVED_PRICE_SOURCE]['accepted_evaluations']}` accepted, and `{cohort['price_source_baseline_gate_lineage'][DERIVED_PRICE_SOURCE]['excluded_evaluations']}` excluded. Its true failure rate among attempted rows is `{cohort['price_source_baseline_gate_lineage'][DERIVED_PRICE_SOURCE]['failure_rate_among_attempted']:.4%}`; `14 / 478 = {cohort['price_source_baseline_gate_lineage'][DERIVED_PRICE_SOURCE]['excluded_to_accepted_ratio']:.4%}` is the excluded-to-accepted ratio, not the attempted-row failure rate. `{PAYLOAD_PRICE_SOURCE}` has `{cohort['price_source_baseline_gate_lineage'][PAYLOAD_PRICE_SOURCE]['attempted_identifiable_evaluations']}` attempted, `{cohort['price_source_baseline_gate_lineage'][PAYLOAD_PRICE_SOURCE]['accepted_evaluations']}` accepted, and `{cohort['price_source_baseline_gate_lineage'][PAYLOAD_PRICE_SOURCE]['excluded_evaluations']}` excluded. This records the observed concentration without changing any of the 14 exclusions.

| price source | comparison measurement | n | min | p05 | p25 | median | mean | p75 | p95 | max | max absolute |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{price_source_rows}

The reporting-only materiality rule is fixed before interpreting the layers: a difference is material when either the absolute mean gap or the largest absolute `p05/p25/median/p75/p95` gap is at least `{ev_se_source_assessment['threshold']:.2f}` pooled within-source SD. This is a descriptive reporting criterion, not a model gate, coefficient, or outcome-derived threshold. For `ev_se_delta_gh3_minus_old`, the absolute standardized mean gap is `{ev_se_source_assessment['absolute_standardized_mean_gap']:.6f}` and the largest standardized central-quantile gap is `{ev_se_source_assessment['absolute_standardized_largest_central_quantile_gap']:.6f}` at `{ev_se_source_assessment['largest_central_quantile_gap']}`. Classification: `{ev_se_source_assessment['classification']}`. {ev_se_mixture_text}

The pure linear-rescaling reference uses each accepted row's forward-reconstructed old `ev_se * (sqrt(2) - 1)`; it does not infer or back-solve historical sigma.

| price source | n | actual mean `ev_se` delta | pure `sqrt(2)` predicted mean | absolute relative gap |
|---|---:|---:|---:|---:|
{sqrt2_source_rows}
| pooled | `{cohort['baseline_reproducible_evaluations']}` | `{pooled_sqrt2['actual_mean']:+.6f}` | `{pooled_sqrt2['recomputed_predicted_mean']:+.6f}` | `{pooled_sqrt2['absolute_relative_mean_gap_to_recomputed_prediction']:.4%}` |

The independently supplied pooled prediction was `{pooled_sqrt2['reviewer_supplied_predicted_mean']:+.6f}`; the observed pooled `{pooled_sqrt2['actual_mean']:+.6f}` differs by `{pooled_sqrt2['absolute_relative_mean_gap_to_reviewer_reference']:.4%}`. The layer rows show whether that near-`sqrt(2)` behavior is shared across both price sources rather than being only a pooled artifact.

### `0.01` lower-node floor

| Measurement | old `mu-sigma` | GH-3 `mu-sqrt(3)sigma` |
|---|---:|---:|
| triggered lambda sides / side inputs | `{floor['old_triggered_lambda_sides']} / {floor['lambda_side_inputs']}` | `{floor['gh3_triggered_lambda_sides']} / {floor['lambda_side_inputs']}` |
| trigger rate | `{floor['old_trigger_rate']:.6f}` | `{floor['gh3_trigger_rate']:.6f}` |
| affected model-input groups | `{floor['old_affected_model_input_groups']}` | `{floor['gh3_affected_model_input_groups']}` |
| affected evaluations | `{floor['old_affected_evaluations']}` | `{floor['gh3_affected_evaluations']}` |

GH-3 newly affects `{floor['newly_affected_model_input_groups']}` model-input groups / `{floor['newly_affected_evaluations']}` evaluations. The closest unfloored lower nodes are `{floor['closest_unfloored_lower_nodes']['old']['old_unfloored_lower_node']:.6f}` under the old path and `{floor['closest_unfloored_lower_nodes']['gh3']['gh3_unfloored_lower_node']:.6f}` under GH-3, both still well above `0.01`; this is why the observed trigger counts are zero rather than the anticipated increase. For the `{floor['gh3_triggered_lambda_sides']}` triggered lambda sides, actual effective SD is `{floor_sd_text}` (min / median / max), or `{floor_ratio_text}` times input `sigma`. The JSON contains every affected model-input hash, fixture, side, evaluation ID, `mu`, `sigma`, actual SD, and collapse ratio; when the trigger count is zero the affected-sample list is correctly empty and effective-SD collapse is `N/A` for this frozen cohort.

Therefore Contract 1 has one explicit exception under the current positivity treatment: once the floor fires, the actual discrete-node SD is less than `sigma`. Production implementation requires a separate gate that either accepts and documents this exception or separately approves a positivity-preserving distribution; this offline package does neither.

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

The production `canonical_team_match_history` table cannot currently serve the enabled runtime scope: it contains `{coverage['runtime_canonical_team_match_history_rows']}` rows, all from Allsvenskan, and has `{coverage['runtime_active_competition_rows']}` rows for the enabled competitions.

Offline denominator feasibility was tested with the already frozen saved-raw Gate 1 corpus:

- snapshot: `{coverage['offline_corpus']['snapshot_as_of']}`;
- canonical corpus fingerprint: `{coverage['offline_corpus']['corpus_sha256']}`;
- file SHA-256: `{coverage['offline_corpus']['file_sha256']}`;
- team-history rows: `{coverage['offline_corpus']['history_rows']:,}`;
- identity namespace: `api_football.provider_team_id.v1`.

For each evaluation and team, the expected set was the latest 20 finished canonical fixtures from the same provider league strictly before the target kickoff. Coverage was the intersection of that set with xG rows visible by the evaluation time. Evaluations at or after kickoff were excluded.

The enabled scope is read from `league_season.payload.enabled`; the script neither assumes a fixed league count nor divides by one. The frozen observation contains `{scope['enabled_competition_count_observed']}` enabled competitions. Coverage is reported per league only; no overall coverage average is computed.

| competition | evaluable rows | frozen finished fixtures | offline structural xG coverage | PIT denominator available rows | PIT xG coverage | runtime canonical fixtures / identity fixtures |
|---|---:|---:|---:|---:|---:|---:|
{per_league_rows}

Across the enabled rows, count-only lineage remains `{aggregate['evaluations']:,}` evaluable, `{aggregate['both_sides_full_expected_latest20_coverage']}` fully covered, and `{aggregate['legacy_n20_both_but_expected_latest20_missing']:,}` false-full evaluations inside `{aggregate['legacy_n20_both_evaluations']:,}` legacy `n=20/n=20` evaluations. These are counts, not an overall coverage estimate. They retain the prior proof that fixture-level missingness varies independently at fixed `n`.

The frozen corpus is sufficient to prove offline identifiability. It is not itself a production runtime authority. `result_first_captured_at <= evaluated_at` is used to show where the full structural latest-20 denominator was actually visible at evaluation time; the gap between the two columns is evidence that kickoff-only hindsight cannot be silently called runtime PIT availability.

Authority feasibility facts, not an Owner decision:

- `canonical_team_match_history`: current enabled-scope coverage is insufficient.
- `matchday_fixture_identities`: useful identity routing, but it has no finished status, result, or first-result visibility time and cannot alone define the denominator.
- persisted saved-raw fixtures: the frozen corpus proves that fixture identity, league, kickoff, finished result, and first-result visibility can be derived. A production use would require an approved, PIT-preserving runtime materialization rather than direct unbounded raw scans.

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

## Gate state and remaining Owner decisions

1. **Decided:** Contract 1 defines `lambda_sigma` as a true standard deviation. GH-3 is the reference offline specification. This is not production implementation approval.
2. **Open:** approve the runtime expected-match denominator authority and its point-in-time availability contract. The evidence above does not self-approve one.
3. **Frozen:** formula-family selection remains closed until item 2 is decided. Coefficients remain unset.

Contract 1 production implementation must be an independent change with its own Gate and must precede any SE-formula change. Bundling the two would make attribution impossible: a changed result could come from repairing the quadrature scale, changing the SE formula, or both. The current state is `CONTRACT_1_SEMANTICS_APPROVED / CONTRACT_1_PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED / ITEM_2_OWNER_DECISION_REQUIRED / ITEM_3_FROZEN`.
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
            "dixon_coles_rho: float = 0.0",
            "minimum_lambda: float = 0.15",
            "maximum_lambda: float = 4.25",
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
    nodes = (-GH3_DISTANCE, 0.0, GH3_DISTANCE)
    assert math.isclose(sum(GH3_WEIGHTS), 1.0)
    assert math.isclose(
        sum(weight * node for weight, node in zip(GH3_WEIGHTS, nodes, strict=True)),
        0.0,
    )
    assert math.isclose(
        sum(
            weight * node**2
            for weight, node in zip(GH3_WEIGHTS, nodes, strict=True)
        ),
        1.0,
    )
    assert math.isclose(
        sum(
            weight * node**4
            for weight, node in zip(GH3_WEIGHTS, nodes, strict=True)
        ),
        3.0,
    )
    identical = _distribution_difference_assessment(
        [0.0, 1.0, 2.0], [0.0, 1.0, 2.0]
    )
    shifted = _distribution_difference_assessment(
        [0.0, 1.0, 2.0], [1.0, 2.0, 3.0]
    )
    assert identical["classification"] == "NO_MATERIAL_PRICE_SOURCE_DIFFERENCE"
    assert shifted["classification"] == "MATERIAL_PRICE_SOURCE_DIFFERENCE"
    assert set(_distribution_summary([1.0])) == {
        "n",
        "min",
        "p05",
        "p25",
        "median",
        "mean",
        "p75",
        "p95",
        "max",
        "max_absolute",
    }


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
