\pset footer off
\pset tuples_only off
COPY (
  WITH evaluated_attempts AS (
    SELECT DISTINCT opportunity_identity_hash, attempt_identity_hash
    FROM dynamic_prematch_evaluations
    WHERE official_funnel_eligible IS TRUE AND opportunity_identity_hash IS NOT NULL
      AND attempt_identity_hash IS NOT NULL
  ), eligible_opps AS (
    SELECT o.* FROM dynamic_prematch_opportunities o
    JOIN evaluated_attempts a ON a.opportunity_identity_hash=o.opportunity_identity_hash
      AND a.attempt_identity_hash=o.latest_attempt_identity_hash
    WHERE o.state IN ('EVALUATED_CANDIDATE','EVALUATED_NO_EDGE','BLOCKED_BY_GATE')
  ), final_opps AS (
    SELECT DISTINCT ON (REPLACE(fixture_id,'api_football:',''), market) * FROM eligible_opps
    ORDER BY REPLACE(fixture_id,'api_football:',''), market, scheduled_checkpoint_at DESC,
      recorded_at DESC, opportunity_identity_hash DESC
  ), final_evals AS (
    SELECT DISTINCT ON (REPLACE(e.fixture_id,'api_football:',''),e.market) e.*,o.state AS opportunity_state,o.payload::text AS opportunity_payload
    FROM dynamic_prematch_evaluations e JOIN final_opps o
      ON REPLACE(e.fixture_id,'api_football:','')=REPLACE(o.fixture_id,'api_football:','')
      AND e.market=o.market AND e.opportunity_identity_hash=o.opportunity_identity_hash
      AND e.attempt_identity_hash=o.latest_attempt_identity_hash
    WHERE o.state='EVALUATED_CANDIDATE' AND e.official_funnel_eligible IS TRUE
      AND e.payload->>'state'='ANALYSIS_PICK_ACTIVE'
    ORDER BY REPLACE(e.fixture_id,'api_football:',''),e.market,e.evaluated_at DESC,e.evaluation_id DESC
  ), active_comp AS (
    SELECT competition_id FROM league_season WHERE payload->>'enabled'='true'
  ), canonical_results AS (
    SELECT DISTINCT ON (fixture_id) * FROM results
    ORDER BY fixture_id, confirmed_at DESC NULLS LAST, id DESC
  )
  SELECT e.evaluation_id, REPLACE(e.fixture_id,'api_football:','') AS fixture_id, e.market,
    e.selection,e.capture_id,e.capture_at,e.evaluated_at,e.bookmaker_count,
    e.opportunity_identity_hash,e.attempt_identity_hash,e.model_forecast_capture_identity_hash,
    e.payload::text AS evaluation_payload,f.competition_id,f.season,f.kickoff_utc,
    f.home_provider_team_id,f.away_provider_team_id,c.payload::text AS model_capture_payload,
    r.fixture_id AS result_fixture_id,r.home_goals,r.away_goals,r.result_status,r.confirmed_at,
    e.opportunity_state,e.opportunity_payload
  FROM final_evals e
  LEFT JOIN matchday_fixture_identities f ON f.provider_fixture_id=REPLACE(e.fixture_id,'api_football:','')
  LEFT JOIN model_forecast_capture c ON c.capture_identity_hash=e.model_forecast_capture_identity_hash
  LEFT JOIN canonical_results r ON r.fixture_id=CASE WHEN e.fixture_id LIKE 'api_football:%' THEN e.fixture_id
    ELSE 'api_football:'||e.fixture_id END
  WHERE f.competition_id IN (SELECT competition_id FROM active_comp) AND e.opportunity_state='EVALUATED_CANDIDATE' AND r.id IS NOT NULL
) TO STDOUT WITH CSV HEADER;
