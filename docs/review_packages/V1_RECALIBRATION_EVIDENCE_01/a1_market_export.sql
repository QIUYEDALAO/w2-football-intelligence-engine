COPY (
  SELECT DISTINCT ON (o.provider_fixture_id, o.bookmaker_id, o.canonical_market,
                      o.canonical_selection, o.line)
         o.observation_id, o.provider_fixture_id, o.fixture_id, o.provider,
         o.bookmaker_id, o.bookmaker_name, o.capture_id, o.provider_bet_id,
         o.raw_market_label, o.canonical_market, o.canonical_selection,
         o.provider_selection, o.line, o.decimal_odds, o.suspended, o.live,
         o.provider_updated_at, o.captured_at, o.ingested_at, o.raw_payload_sha256,
         o.source_revision
  FROM matchday_market_observations o
  JOIN (SELECT DISTINCT fixture_id, kickoff_at FROM team_xg_match
        WHERE kickoff_at >= TIMESTAMPTZ '2026-07-22T00:00:00Z'
          AND kickoff_at < TIMESTAMPTZ '2026-08-31T00:00:00Z') x
    ON o.provider_fixture_id = x.fixture_id
  WHERE o.captured_at <= TIMESTAMPTZ '2026-08-30T15:58:43Z'
    AND o.captured_at < x.kickoff_at
    AND o.live = false
    AND o.suspended = false
  ORDER BY o.provider_fixture_id, o.bookmaker_id, o.canonical_market,
           o.canonical_selection, o.line, o.captured_at DESC, o.observation_id DESC
) TO STDOUT WITH CSV HEADER;
