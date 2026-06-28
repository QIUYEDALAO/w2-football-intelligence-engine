# W2 Team Value Mapping Runbook

This runbook controls A4 squad value mapping for `F8_SQUAD_VALUE`.

## Scope

The mapping is a reviewed static artifact. It must not call providers, scrape
websites, invoke LLMs, read private credentials, or infer values from odds, xG, scores, market
movement, or fixture results.

## Export Team IDs

Export the API-Football team ids already present in local fixture artifacts:

```bash
uv run --python 3.12 python scripts/export_w2_world_cup_team_ids.py \
  --competition-id world_cup_2026 \
  --output /tmp/w2_world_cup_team_ids.csv
```

The CSV contains:

- `team_id`
- `team_name`
- `seen_fixture_count`
- `example_fixture_id`

Rows without API-Football team ids are skipped. This is intentional: values cannot
be attached safely without the provider team id used by runtime fixtures.

## Fill Mapping

Update `config/team_values/world_cup_2026.v1.json` only with human-reviewed values.
Each item must include:

- `team_id`
- `team_name`
- `squad_value_eur`
- `currency`
- `observed_at`
- `source_system`
- `source_url`
- `confidence`
- `reviewed_by`

`observed_at` must be at or before the fixture `as_of`. Future-dated values are
blocked. Unmatched teams stay unmapped and runtime must keep F8 as
`MAPPING_MISSING`.

## Validate Mapping

Run:

```bash
uv run --python 3.12 python scripts/check_team_values_mapping.py \
  --mapping config/team_values/world_cup_2026.v1.json \
  --team-ids /tmp/w2_world_cup_team_ids.csv \
  --as-of 2026-06-27T00:00:00Z
```

The validator checks required source metadata, duplicate ids, unknown ids,
positive EUR values, `observed_at <= as_of`, source URL shape, reviewer presence,
confidence bounds, and production-forbidden placeholder terms.

An empty `items` list is valid for safety and should report:

```json
{
  "ok": true,
  "mapped_teams": 0
}
```

That state is a blocker for F8 readiness. It means runtime should continue to show
`MAPPING_MISSING`, and staging rollout for A4 readiness should not proceed.

## Runtime Expectations

When both teams have reviewed values as of the fixture timestamp:

- `F8_SQUAD_VALUE.status = READY`
- `collection_status = READY`
- `source_group = squad_value`
- `is_independent_signal = true`

When either team is missing or the value is after `as_of`:

- `F8_SQUAD_VALUE.status = UNAVAILABLE`
- `collection_status = MAPPING_MISSING`
- `is_independent_signal = false`

## Release Gate

Before opening a runtime acceptance request:

- Exported team ids are committed or attached to the review packet.
- Mapping validator passes.
- Every mapped item has a reviewable `source_url` and `reviewed_by`.
- No placeholder, demo, inferred, or generated squad values are present.
- FORMAL/CANDIDATE remain disabled.
- `beats_market` remains false.
