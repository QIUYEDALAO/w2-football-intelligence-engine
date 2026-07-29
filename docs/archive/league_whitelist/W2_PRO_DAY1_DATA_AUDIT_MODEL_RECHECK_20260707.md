# W2 Pro Day-1 Data Sprint, Audit Inventory, And Model Recheck

Date: 2026-07-07

Status: `COMPLETED_DATA_INVENTORY_AND_OFFLINE_RECHECK`

This report records the first Pro-plan data sprint. It is a data collection,
audit-inventory, and offline model recheck phase only. It does not enable any
league, deploy staging or production, restart scheduler loops, write DB rows,
write checkpoints, or write lock/settlement records.

## Phase 0: Pro Confirmation

| check | result |
| --- | ---: |
| API-Football status probe | PASS |
| detected plan text | Pro |
| detected daily limit number | 7500 |
| control league | brasileirao_serie_a |
| control league id | 71 |
| control season | 2026 |
| fixture probe response count | 380 |
| provider errors | none |
| provider calls | 3 |

Phase 0 greenlit bulk collection: current-season Pro access is active and the
Brazil 2026 fixture probe returned real data.

## Provider Usage

| run | actual provider calls | last observed quota remaining | note |
| --- | ---: | ---: | --- |
| phase0 | 3 | 7404 | Pro confirmation |
| collect slow | 2996 | 4480 | conservative throttle, stopped manually for speed |
| collect fast | 3304 | 1189 | resumed with no sleep |
| collect full | 1118 | -14 | user approved using remaining quota; provider reserve reached |
| collect resume interrupted | ~68 | 7450 | transient SSL EOF; cache writes persisted |
| collect resume completed | 915 | 6597 | completed Allsvenskan 2025 and Eliteserien 2026/2024/2025 |
| audit inventory | 30 | 6487 | 14-league provider mapping / fixtures / odds inventory |

Approximate provider calls consumed by this PR evidence phase across the two
quota windows: `8434`. The first quota window intentionally stopped after the
provider returned a negative remaining value. After quota reset, collection was
resumed, completed, and followed by a small 14-league audit inventory.

Raw provider payloads and request cache are stored only under:

```text
runtime/w2_pro_day1_provider_data/
```

These files are not committed.

## Persistent Cache Coverage

| endpoint | cached objects |
| --- | ---: |
| status | 1 |
| leagues | 26 |
| fixtures | 26 |
| statistics | 5121 |
| odds | 1155 |
| lineups | 2105 |
| total | 8434 |

## Collection Scope

The intended in-season scope was:

- brasileirao_serie_a
- argentina_primera
- mls
- chinese_super_league
- allsvenskan
- eliteserien

The first quota window was exhausted before `eliteserien` collection started.
The second quota window completed the remaining collection.

## Per-League Collection Result

| league | 2026 fixtures | 2026 finished | 2026 future/non-finished | 2026 odds | 2026 lineups | 2024 statistics | 2025 statistics | status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| brasileirao_serie_a | 380 | 177 | 203 | 203 | 380 | 380/380 | 380/380 | COMPLETE |
| argentina_primera | 495 | 255 | 240 | 240 | 495 | 378/378 | 510/510 | COMPLETE |
| mls | 510 | 218 | 292 | 292 | 510 | 522/522 | 540/540 | COMPLETE |
| chinese_super_league | 240 | 136 | 104 | 104 | 240 | 240/240 | 240/240 | COMPLETE |
| allsvenskan | 240 | 89 | 151 | 151 | 240 | 242/242 | 242/242 | COMPLETE |
| eliteserien | 240 | 89 | 151 | 151 | 240 | 242/242 | 241/241 | COMPLETE |

`eliteserien` 2025 has 242 fixtures and 241 finished fixtures; one fixture is
not settled and is therefore not part of the finished-statistics sample.

## Audit Inventory Status

The 14-league audit inventory was executed after quota reset.

| check | result |
| --- | ---: |
| competitions checked | 14 |
| provider_mapping PASS | 14 |
| fixtures PASS | 14 |
| odds PASS | 1 |
| bookmaker_depth PASS | 1 |
| can_enable true | 0 |
| provider calls | 30 |

`world_cup_2026` was the only inventory item with odds and bookmaker-depth
evidence in this first-fixture audit probe. This is an inventory signal only;
all profiles remain `enabled=false`, and no staging enablement decision is made
by this PR.

## Offline Model Recheck

The model recheck used only cached local raw data and made zero provider calls.
The current recheck uses the existing free-tier backtest harness with
API-Football statistics as true xG input where available.

| season | covered competitions | missing competitions | sample | log_loss | Brier | RPS | ECE | status |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2024 | brasileirao_serie_a, argentina_primera, mls, chinese_super_league, allsvenskan, eliteserien | none | 1994 | 1.054071 | 0.635640 | 0.222493 | 0.030061 | READY_FOR_REVIEW |
| 2025 | brasileirao_serie_a, argentina_primera, mls, chinese_super_league, allsvenskan, eliteserien | none | 2139 | 1.055283 | 0.636593 | 0.223735 | 0.030295 | READY_FOR_REVIEW |

Uniform baseline:

- 2024 log_loss: `1.098612`
- 2025 log_loss: `1.098612`

Interpretation: the model beats uniform on the collected in-season league data,
but it is materially weaker than the five-major-league Understat robustness
result around `0.99`. These leagues should not inherit the five-league model
conclusion without league-specific fitting and validation. `SQUAD_VALUE_MISSING`
remains a model-input warning.

## Decision

```text
NO_ENABLEMENT_DECISION
```

Pro access is confirmed, the six in-season leagues have 2026/2024/2025 provider
data cached for this phase, and the 14-league audit inventory has been produced.
Staging enablement remains blocked until:

- odds/bookmaker-depth failures are remediated or explicitly waived by policy,
- model validation is split by in-season league and reviewed,
- `SQUAD_VALUE_MISSING` is addressed or accepted as a documented limitation,
- a separate approval flips any profile to `enabled=true`.

## Safety

- provider_calls_this_phase_approx=8434
- provider_calls_this_resume_step=1013
- db_reads=0
- db_writes=0
- enabled_true=false
- staging_deploy=false
- production_deploy=false
- scheduler_restart=false
- checkpoint_write=false
- lock_capture_write=false
- settlement_write=false
- canonical_season_changed=false
- raw_payload_committed=false
- key_or_header_committed=false
