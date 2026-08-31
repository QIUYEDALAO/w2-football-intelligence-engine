\set ON_ERROR_STOP on
\pset footer off
COPY (
  SELECT
    evaluation_id,
    fixture_id,
    market,
    selection,
    evaluated_at,
    official_funnel_eligible,
    payload::text AS evaluation_payload
  FROM dynamic_prematch_evaluations
  WHERE evaluated_at > TIMESTAMPTZ '2026-08-30T14:27:00Z'
    AND evaluated_at <= TIMESTAMPTZ '2026-08-31T03:22:53Z'
  ORDER BY evaluated_at, evaluation_id
) TO STDOUT WITH CSV HEADER;
