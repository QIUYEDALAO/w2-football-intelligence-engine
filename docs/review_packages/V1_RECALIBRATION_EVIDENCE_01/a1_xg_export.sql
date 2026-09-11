COPY (
  SELECT fixture_id, team_id, opponent_team_id, kickoff_at, captured_at,
         xg_for, xg_against
  FROM team_xg_match
  WHERE kickoff_at >= TIMESTAMPTZ '2026-07-22T00:00:00Z'
    AND kickoff_at < TIMESTAMPTZ '2026-08-31T00:00:00Z'
    AND captured_at <= TIMESTAMPTZ '2026-08-30T15:58:43Z'
) TO STDOUT WITH CSV HEADER;
