# W2 Free-Tier Historical Proof

Date: 2026-07-07

This document records the free-tier historical season proof attempt. The goal
was to avoid paid API usage, avoid league enablement, and use historical data
where possible to prove the W2 chain.

## Provider Budget

- Single-day hard budget for this phase: <=80 provider requests
- Phase 0 capability probe: 3 provider requests
- Fixture-window probe: 2 provider requests
- Phase 2 initial historical evidence-only audit attempts: 6 provider requests
- Phase 2 post-fix Premier League 2024 evidence-only verification: 3 provider requests
- Provider requests in this phase so far: 14
- User-observed official dashboard usage before this phase: 37 calls
- Raw provider payloads: not committed
- Headers and keys: not recorded

## Phase 0 Capability

The free-tier metadata probe used:

- `status`
- `leagues?id=39`
- `leagues?id=71`

Both league metadata calls returned one league record and no `errors.plan`.
The selected historical season is:

```text
SEASON_FREE=2024
```

For `SEASON_FREE=2024`, both Premier League (`id=39`) and Brasileirao Serie A
(`id=71`) advertised fixtures, fixture statistics, player statistics, and
lineups coverage. Odds coverage was advertised as false.

See [FREE_TIER_CAPABILITY.md](FREE_TIER_CAPABILITY.md).

## Phase 1 Local Historical Raw

Local historical raw exists for the two control leagues:

| league | local raw | provider params | response_count |
| --- | --- | --- | ---: |
| premier_league | `runtime/stage5b/raw/039_P2_fixtures.json` | `league=39, season=2024` | 380 |
| brasileirao_serie_a | `runtime/stage5b/raw/051_P2_fixtures.json` | `league=71, season=2024` | 380 |

These files are existing local runtime artifacts and are not committed as part
of this PR.

## Phase 2 Evidence-Only Provider Audit

The audit harness now supports an explicit per-run season override:

```bash
--audit-season-override 2024
```

or:

```bash
W2_AUDIT_SEASON_OVERRIDE=2024
```

This override does not mutate `provider_mapping.api_football_season` in any
competition profile.

### Results

The first implementation attempted historical proof through the future-fixture
query shape:

```text
fixtures?league=<id>&season=2024&next=5
```

That query returned `PLAN_DOES_NOT_COVER_SEASON` for the control leagues. A
direct fixture-window probe then showed that historical Premier League fixtures
are available with:

```text
fixtures?league=39&season=2024
fixtures?league=39&season=2023
```

Both returned 380 fixtures and no `errors.plan`.

The audit harness was therefore corrected so that an explicit historical
season override uses the completed-result query path:

```text
fixtures?league=<id>&season=<override>&status=FT
```

Post-fix verification:

| control | provider calls | provider_mapping | fixtures | bookmaker_depth | classification |
| --- | ---: | --- | --- | --- | --- |
| premier_league 2024 | 3 | PASS | PASS, 380 fixtures | FAIL, no AH/OU bookmaker depth | 2024 fixtures window works; odds depth unavailable |

This proves the problem was the future-fixture query shape, not a general 2024
free-tier fixture blackout.

## Phase 3 Offline Historical E2E

Because provider fixture access is plan-gated, downstream proof used existing
local historical raw rather than new provider calls.

Historical fixture used:

| field | value |
| --- | --- |
| fixture_id | `1208021` |
| league | Premier League |
| season | 2024 |
| kickoff_utc | `2024-08-16T19:00:00Z` |
| home | Manchester United |
| away | Fulham |
| local raw source | `runtime/stage5b/raw/039_P2_fixtures.json` |

Initial single-match offline proof output:

```text
/tmp/w2_free_tier_historical_e2e_20260706T165824Z
```

| artifact | sha256 |
| --- | --- |
| `historical_matchday_dry_run.json` | `d56410aa026776d7821b18002dd64f931a6966e92d54be91f7be6422ba2288b3` |
| `historical_day_view.json` | `91c772705c2d6bd1fa1be9ca5cd67df62dfd190bdc8c08bad80c7575b205cc08` |
| `historical_l1.html` | `d3f3a0366f611720b3cd1ea42ca367bc2768e424fc2914822aac330652b429c8` |
| `historical_replay_frontdoor.json` | `d1f8eaeada87ffde0402a9c33297786a3e99ddf6c7336cd34d74775d785c4e3e` |

Observed downstream result:

- matchday status: `DRY_RUN_READY`
- decision_tier: `ANALYSIS_PICK`
- reason_code: `LINEUPS_PENDING`
- DayView total cards: 1
- DayView `analysis_pick`: 1
- DayView `partial`: 1
- L1 HTML contains analysis recommendation, not-ready section, next refresh, and
  staging-only policy text
- replay front-door preserves the DecisionCard hash as
  `PRESENT_UNVERIFIED`
- provider_calls=0
- db_reads=0
- db_writes=0

Expanded multi-day local-raw proof output:

```text
/tmp/w2_free_tier_multi_day_e2e_20260706T172116Z
```

The local raw directory contains 56 files. The expanded proof sampled multiple
fixture raw files and multiple football days:

| football_day | competition | fixture_id | local raw | card_hash_consistent |
| --- | --- | --- | --- | --- |
| 2024-08-16 | premier_league | `1208021` | `runtime/stage5b/raw/039_P2_fixtures.json` | true |
| 2024-04-13 | brasileirao_serie_a | `1180355` | `runtime/stage5b/raw/051_P2_fixtures.json` | true |
| 2023-08-11 | premier_league | `1035037` | `runtime/stage5b/raw/038_P2_fixtures.json` | true |

For all three samples:

- matchday status: `DRY_RUN_READY`
- decision_tier: `ANALYSIS_PICK`
- reason_code: `LINEUPS_PENDING`
- DayView total cards: 1
- L1 HTML contains analysis recommendation, next-refresh, and staging-only text
- matchday / DayView / replay card hashes match
- provider_calls=0
- db_reads=0
- db_writes=0

## Phase 4 Guardrail

The provider audit harness now includes a plan fail-fast guard. In real provider
audit mode, a provider payload with `errors.plan` stops the current audit with:

```text
PLAN_DOES_NOT_COVER_SEASON
```

This prevents repeated calls after the first observed plan restriction.

## Decision

Free-tier metadata and Premier League 2024/2023 historical fixtures are
available. The plan-gated failure was caused by the future-fixture `next=5`
query shape under a historical season override. Therefore:

- Do not enable any national league.
- Do not treat category-level blockers as profile mapping fixes.
- Do not use `next=5` as evidence for historical season coverage.
- Use existing local historical raw for offline chain proof.
- A paid-plan decision is still required for bookmaker-depth / AH-OU evidence if
  odds coverage remains unavailable on the free tier.

## Safety

- provider_calls_this_phase=14
- db_reads=0
- db_writes=0
- enabled_true=false
- staging_deploy=false
- production_deploy=false
- scheduler_restart=false
- checkpoint_write=false
- lock_capture_write=false
- settlement_write=false
- raw_payload_committed=false
- key_or_header_committed=false
