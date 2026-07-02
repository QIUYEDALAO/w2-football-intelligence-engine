W2 team value mappings live here as reviewed static artifacts.

These files must be curated from a real, reviewable source. Missing teams must remain
unmapped and must not be inferred from odds, xG, scores, market movement, LLM output, or
runtime search. Runtime code treats absent mappings as `MAPPING_MISSING`.

Required item fields:

- `team_id`: API-Football team id used by the fixture payload.
- `team_name`: human-readable team name for review only.
- `squad_value_eur`: positive reviewed squad value in EUR.
- `currency`: must be `EUR`.
- `observed_at`: ISO timestamp that must be at or before the fixture `as_of`.
- `source_system`: reviewed source label.
- `source_url`: reviewable HTTP(S) source URL.
- `source_tier`: confidence tier for the value source.
- `primary_source_review_status`: whether the primary source was directly reviewed.
- `confidence`: optional number from 0 to 1.
- `reviewed_by`: human reviewer identifier.

Confidence policy:

- `primary_reviewed`: direct human review against the primary source page, capped at `0.95`.
- `secondary_with_primary_reference`: reviewed secondary publication with a retained
  primary-source URL, capped at `0.85`.

The current `world_cup_2026.v1.json` artifact is graded as
`secondary_with_primary_reference` with `primary_source_review_status=pending_primary_review`.
It must not be described as directly verified against Transfermarkt until a human reviewer
records a primary-source sample review.

Update cadence:

- Refresh once after the group stage.
- Refresh once before the knockout stage.
- Keep older artifacts immutable; create a new version when values change.

Validation flow:

```bash
uv run --python 3.12 python scripts/export_w2_world_cup_team_ids.py \
  --competition-id world_cup_2026 \
  --output /tmp/w2_world_cup_team_ids.csv

uv run --python 3.12 python scripts/check_team_values_mapping.py \
  --mapping config/team_values/world_cup_2026.v1.json \
  --team-ids /tmp/w2_world_cup_team_ids.csv \
  --as-of 2026-06-27T00:00:00Z
```

An empty `items` array is allowed and safe, but it means F8 stays
`MAPPING_MISSING`. Do not deploy an A4 runtime rollout for F8 readiness until real
reviewed values are present and the validator passes.
