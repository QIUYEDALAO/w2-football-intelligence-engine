-- W2 Gate3 Baselight limited AH extract SQL
--
-- Boundary:
-- - Intended for user execution in Baselight, not Codex execution.
-- - Do not download full Baselight data.
-- - Export the result to a local non-Git path:
--   /Users/liudehua/.openclaw/workspace/w2_external_data/baselight_gate3_limited_ah/
-- - Treat collected_at as DATE_ONLY; do not infer intraday phase timing.
--
-- Source tables:
-- - odds:    @blt.ultimate_soccer_dataset.match_betting_odds
-- - matches: @blt.ultimate_soccer_dataset.matches

WITH ah_joined AS (
    SELECT
        o.match_id,
        o.bookmaker,
        o.market,
        o.outcome,
        o.odds,
        o.odds_type,
        o.collected_at,
        m.competition_name AS competition,
        COALESCE(CAST(m.season_year AS VARCHAR), CAST(m.season_id AS VARCHAR)) AS season,
        COALESCE(m.kickoff_timestamp, m.date) AS kickoff_utc,
        m.home_team_id,
        m.home_team_name,
        m.away_team_id,
        m.away_team_name,
        m.status,
        CAST(m.home_score AS INTEGER) AS home_score,
        CAST(m.away_score AS INTEGER) AS away_score,
        CASE
            WHEN REGEXP_LIKE(o.outcome, '[-+]?[0-9]+(\\.[0-9]+)?') THEN 1
            ELSE 0
        END AS outcome_has_line
    FROM "@blt.ultimate_soccer_dataset"."match_betting_odds" o
    INNER JOIN "@blt.ultimate_soccer_dataset"."matches" m
        ON o.match_id = m.match_id
    WHERE o.market = 'Asian Handicap'
      AND o.odds_type = 'pre_match'
      AND o.odds > 1
      AND m.home_score IS NOT NULL
      AND m.away_score IS NOT NULL
      AND LOWER(COALESCE(m.status, '')) IN (
          'finished',
          'full time',
          'full-time',
          'ft',
          'match finished',
          'completed',
          'closed'
      )
),
eligible AS (
    SELECT *
    FROM ah_joined
    WHERE outcome_has_line = 1
),
preferred_competitions AS (
    SELECT *
    FROM eligible
    WHERE competition IN (
        'Premier League',
        'Serie A',
        'Bundesliga',
        'La Liga',
        'UEFA Champions League',
        'UEFA Europa League'
    )
),
fixture_strata AS (
    SELECT
        match_id,
        competition,
        season,
        MIN(kickoff_utc) AS kickoff_utc,
        COUNT(DISTINCT bookmaker) AS fixture_bookmaker_count,
        COUNT(*) AS fixture_quote_count,
        ROW_NUMBER() OVER (
            PARTITION BY competition, season
            ORDER BY MIN(kickoff_utc), match_id
        ) AS stratum_fixture_rank
    FROM preferred_competitions
    GROUP BY match_id, competition, season
),
selected_fixtures AS (
    SELECT match_id
    FROM fixture_strata
    WHERE stratum_fixture_rank <= 400
    QUALIFY COUNT(*) OVER (PARTITION BY competition, season) >= 150
    LIMIT 2000
)
SELECT
    e.match_id,
    e.competition,
    e.season,
    e.kickoff_utc,
    e.home_team_id,
    e.home_team_name,
    e.away_team_id,
    e.away_team_name,
    e.status,
    e.home_score,
    e.away_score,
    e.bookmaker,
    e.market,
    e.outcome,
    e.odds,
    e.odds_type,
    e.collected_at
FROM eligible e
INNER JOIN selected_fixtures sf
    ON e.match_id = sf.match_id
ORDER BY
    e.kickoff_utc,
    e.match_id,
    e.bookmaker,
    e.outcome,
    e.collected_at;
