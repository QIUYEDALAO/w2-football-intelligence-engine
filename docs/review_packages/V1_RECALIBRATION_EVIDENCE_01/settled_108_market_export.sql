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
    SELECT DISTINCT ON (REPLACE(e.fixture_id,'api_football:',''),e.market) e.*
    FROM dynamic_prematch_evaluations e JOIN final_opps o
      ON REPLACE(e.fixture_id,'api_football:','')=REPLACE(o.fixture_id,'api_football:','')
      AND e.market=o.market AND e.opportunity_identity_hash=o.opportunity_identity_hash
      AND e.attempt_identity_hash=o.latest_attempt_identity_hash
    WHERE o.state='EVALUATED_CANDIDATE' AND e.official_funnel_eligible IS TRUE
      AND e.payload->>'state'='ANALYSIS_PICK_ACTIVE'
    ORDER BY REPLACE(e.fixture_id,'api_football:',''),e.market,e.evaluated_at DESC,e.evaluation_id DESC
  )
  SELECT DISTINCT REPLACE(e.fixture_id,'api_football:','') AS fixture_id,e.market,e.capture_id,
    o.observation_id,o.provider_fixture_id,o.bookmaker_id,o.bookmaker_name,o.canonical_market,
    o.canonical_selection,o.line,o.decimal_odds,o.live,o.suspended,o.captured_at,
    o.raw_payload_sha256
  FROM final_evals e JOIN matchday_market_observations o
    ON o.provider_fixture_id=REPLACE(e.fixture_id,'api_football:','')
    AND o.capture_id=e.capture_id AND o.canonical_market=e.market
  WHERE o.live IS FALSE AND o.suspended IS FALSE
) TO STDOUT WITH CSV HEADER;
