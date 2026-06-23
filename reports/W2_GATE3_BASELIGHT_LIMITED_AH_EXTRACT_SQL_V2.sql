-- W2 Gate3 Baselight limited AH extract V2.
-- Execute through Baselight MCP only with explicit --live approval.
-- Tables:
--   "@blt.ultimate_soccer_dataset.match_betting_odds"
--   "@blt.ultimate_soccer_dataset.matches"
--
-- Boundary:
-- - Asian Handicap only.
-- - pre_match odds only.
-- - DATE_ONLY collected_at semantics.
-- - No T-1h/T-30m/T-10m or exact closing claim.
-- - Limited sample: <= 1000 fixtures and <= 250000 rows.

WITH preferred_matches AS (
    SELECT
        m.match_id,
        m.competition_name AS competition,
        CAST(m.season_year AS VARCHAR) AS season,
        m.kickoff_timestamp AS kickoff_utc,
        m.home_team_id,
        m.home_team_name,
        m.away_team_id,
        m.away_team_name,
        m.status,
        m.home_score,
        m.away_score,
        ROW_NUMBER() OVER (
            PARTITION BY m.competition_name, CAST(m.season_year AS VARCHAR)
            ORDER BY m.kickoff_timestamp, m.match_id
        ) AS fixture_rank
    FROM "@blt.ultimate_soccer_dataset.matches" m
    WHERE
        lower(CAST(m.status AS VARCHAR)) IN (
            'match finished',
            'finished',
            'ft',
            'aet',
            'pen'
        )
        AND m.home_score IS NOT NULL
        AND m.away_score IS NOT NULL
        AND m.competition_name IN (
            'Premier League',
            'Serie A',
            'Bundesliga',
            'La Liga',
            'UEFA Champions League',
            'UEFA Europa League'
        )
),
limited_fixtures AS (
    SELECT *
    FROM preferred_matches
    WHERE fixture_rank <= 250
    ORDER BY competition, season, kickoff_utc, match_id
    LIMIT 1000
)
SELECT
    lf.match_id,
    lf.competition,
    lf.season,
    lf.kickoff_utc,
    lf.home_team_id,
    lf.home_team_name,
    lf.away_team_id,
    lf.away_team_name,
    lf.status,
    lf.home_score,
    lf.away_score,
    o.bookmaker,
    o.market,
    o.outcome,
    o.odds,
    o.odds_type,
    o.collected_at
FROM limited_fixtures lf
JOIN "@blt.ultimate_soccer_dataset.match_betting_odds" o
    ON o.match_id = lf.match_id
WHERE
    o.market = 'Asian Handicap'
    AND o.odds_type = 'pre_match'
    AND o.odds > 1
    AND regexp_matches(CAST(o.outcome AS VARCHAR), '[+-]?[0-9]+(\\.[0-9]+)?')
ORDER BY
    lf.kickoff_utc,
    lf.match_id,
    o.bookmaker,
    o.outcome,
    o.collected_at
LIMIT 250000
