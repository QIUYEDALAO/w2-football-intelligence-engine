COPY (
  SELECT snapshot_id, team_id, as_of_fixture_id, as_of_time, match_count,
         rolling_xg_for, rolling_xg_against, regression_index, source_system
  FROM team_xg_rolling_snapshot
  WHERE as_of_time <= TIMESTAMPTZ '2026-08-30T15:58:43Z'
) TO STDOUT WITH CSV HEADER;
