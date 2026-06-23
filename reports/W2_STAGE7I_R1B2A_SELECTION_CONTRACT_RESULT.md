# W2 Stage7I-R1B2A Selection Contract Result

## Summary

- Stage package: W2-STAGE7I-R1B2A live successor selection contract closure
- Baseline commit: `54a498c701af0e754645cf51658e45683fa6352a`
- R1B1 CI run: `28009675284`
- R1B1 CI result: `success`
- Staging revision observed: `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- Gate5: `OPEN`
- Candidate output: `false`
- Formal recommendation output: `false`
- Deployment freeze: `ACTIVE`

R1B2A closes the contract between staging read data, a candidate manifest, and
the selector. It does not select a formal successor fixture and does not start
or stop any observer.

## Read-Only Staging Baseline

- `w2-staging.service`: enabled and active
- Long-running containers: 6 running and healthy
- API `/health`: 200
- API `/ready`: 200
- Web: 200
- Public listeners: SSH only; API/Web are localhost-bound
- `.env`: mode `600`; contents not read
- Server revision: `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`

The first Alembic readonly attempt from the compose working directory failed
with missing script configuration; this was treated as a probe limitation and
did not modify runtime state.

## Legacy Observer Audit

- Known observer PIDs `723787` and `723789` were still active.
- Runtime directory observed:
  `/opt/w2/shared/runtime/stage7i/runs/stage7i_20260622T183939Z_397fdfa`
- The legacy observer uses a per-run lock path, not the R1B1 global singleton
  lock.
- `/opt/w2/shared/runtime/stage7i/observer-global.lock` was absent before and
  after the check; the check did not create it.
- Status recorded: `LEGACY_STAGE7I_OBSERVER_ACTIVE_WITHOUT_GLOBAL_LOCK`

This does not block R1B2A tooling changes, but it must block R1B2B observer
start until resolved by the approved runtime bootstrap procedure.

## Live API Contract Probe

Read-only fixture list probe:

`/v1/fixtures?status=NS&page_size=100&timezone=UTC`

Observed schema:

- Top-level keys: `items`, `meta`, `request_id`
- Item count: 1
- Item keys:
  - `away_team_id`
  - `competition_id`
  - `competition_name`
  - `data_state`
  - `fixture_id`
  - `home_team_id`
  - `kickoff_beijing`
  - `kickoff_display`
  - `kickoff_utc`
  - `last_captured`
  - `lifecycle_state`
  - `operational_date_beijing`
  - `primary_line`
  - `primary_market`
  - `primary_odds`
  - `published_grade`
  - `status`

The fixture summary did not contain provider mapping evidence or market
observation evidence.

Detail probe for fixture `1489399`:

- Detail had `provenance`, `bookmaker_count`, market ladders, and source
  snapshot fields.
- Detail did not contain a `provider_mapping` object.
- Odds timeline endpoint returned HTTP 500 during the probe.
- `/ops/mapping-conflicts` returned a read API list, but absence of a conflict
  item is not treated as reliable mapping evidence.

Running the R1B1 selector directly against the live fixture list produced exit
code `2` and rejection reasons:

- `PRE_MATCH_LEAD_INSUFFICIENT`
- `PROVIDER_MAPPING_MISSING`
- `MARKET_OBSERVATION_MISSING`

This confirms `FixtureSummary` is not a candidate manifest.

## Evidence Sources

Provider mapping authority for R1B2A:

- Explicit mapping evidence input to the candidate builder, backed by W2
  staging/provider artifacts such as
  `/opt/w2/shared/runtime/stage5b/processed/national_provider_mappings.json`
  or an equivalent future read API.
- Mapping must provide provider, provider fixture ID, home/away provider team
  IDs, source, confidence, conflict state, reliable flag, and evidence SHA.
- The builder rejects missing, conflicting, or low-confidence mapping evidence.

Market evidence authority for R1B2A:

- Explicit market evidence input to the candidate builder, backed by W2
  staging market snapshots/timelines or an equivalent future read API.
- Market evidence must provide market, captured time, bookmaker count,
  live/suspended state, source, provenance, freshness limit seconds, and
  evidence SHA.
- Freshness is not invented by the selector. The builder and selector require
  explicit `freshness_limit_seconds` from market evidence and recompute age at
  selection time.

## Contract Changes

- Added `scripts/build_stage7i_successor_candidates.py`.
- Updated `scripts/select_stage7i_successor.py` to require a candidate manifest
  instead of treating `/v1/fixtures` as complete evidence.
- Selector now revalidates freshness, evidence hashes, mapping source, market
  source/provenance, live/suspended flags, and 6h/6h observation window.
- Selector dry-run no longer creates absent global lock files.
- Selector checks both global lock and legacy observer PID files.
- Updated Stage7I checker static file requirements.
- Added live contract unit tests.
- Updated runbook and handoff to R1B2A.

## Safe Observation Window

R1B2A fixes the Stage7I successor observation window:

- Observation duration: 24h
- Minimum pre-kickoff coverage: 6h
- Minimum post-kickoff coverage: 6h

Eligible kickoff range:

`now + 6h <= kickoff <= run_end - 6h`

The window covers multiple pre-match market observations, closing, actual
kickoff, match completion, result sync, settlement/evaluation, and final audit.
It is an evidence policy, not a betting, model, or odds threshold.

## Validation

Required validation for this package:

- `python3 -m py_compile` for Stage7I scripts
- all Stage7I script `--help` commands
- R1B1 and R1B2A unit tests
- Stage1 contract checker
- Ruff
- Mypy
- Pytest
- `scripts/check_w2_all.py`
- Secret scan
- `git diff --check`

## Remaining Blockers

- `SUCCESSOR_FIXTURE_NOT_SELECTED`
- `SUCCESSOR_OBSERVATION_NOT_STARTED`
- `LEGACY_STAGE7I_OBSERVER_ACTIVE_WITHOUT_GLOBAL_LOCK`
- `ACTUAL_KICKOFF_NOT_CAPTURED_BY_CONTINUOUS_FORWARD_RUN`
- `CLOSING_NOT_CAPTURED_BY_CONTINUOUS_FORWARD_RUN`
- `SETTLEMENT_EVALUATION_NOT_CAPTURED`
- `FINAL_SHADOW_DB_AUDIT_PENDING`
- `GATE5_OPEN`

## Next Step

Stage7I-R1B2B dynamic selection and observer bootstrap may proceed only after
the containing commit passes CI. R1B2B must use the candidate manifest builder,
must not consume raw FixtureSummary as selector input, and must not start while
a legacy observer remains active.

## Rollback

No rollback is required if validation and CI pass. This is a tooling-only
change and does not alter staging runtime state, database schema, W1, sensitive
values, deployment configuration, or GitHub settings.
