# Dashboard Owner Canonical Identity & Collection Semantics Remediation

```text
AUTHORITY = W2_DASHBOARD_OWNER_CANONICAL_IDENTITY_COLLECTION_SEMANTICS_REMEDIATION_V1
OWNER_DATE = 2026-08-09
OWNER_DECISION = CHANGES_REQUIRED_BOUNDED
BASE_MAIN = 5f8066187acc323d23ac4d73da7115100a58aa48
PR_502_503_TECHNICAL_RESULT = PASS_MERGED_DEPLOYED
PR_502_503_OWNER_ACCEPTANCE = REVOKED_BY_REAL_DATA_REVIEW
TRACK_A = TRACK_A_CLOSED_PASS
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
TERMINAL_TARGET = DASHBOARD_OWNER_CANONICAL_TRUTH_ACCEPTANCE_PASS
```

## Independent review conclusion

The D13 remediation correctly fixed the prior 13-inch readability, stale-time,
small-sample, probability-primary, exclusion visibility, localization, date and
live aggregate-price defects. Those fixes must remain.

Real persisted data now exposes a second bounded class of truth defects. The
current Dashboard resolves source aliases to canonical identities but does not
canonicalize/aggregate the performance cohort before public projection. It also
marks collection risk `OK` when no collection incident code exists, even when no
source-bound assessment evidence is available.

This authority reopens only the unified Dashboard/read-model truth and display
boundary. It does not reopen the architecture, Provider policy, Scheduler,
model, whitelist, Round4 or production authority.

## Findings and severity

### P0 — D14-01 Canonical competition aggregation

Current source evidence:

- `performance:cohort:league:<source>` rows can use either provider league ID or
  canonical competition ID;
- the D13 resolver maps both aliases to one canonical competition but leaves one
  public row per source checkpoint;
- therefore the same competition can appear twice and its sample is split.

Required result:

1. Public league performance must have **at most one row per canonical national
   league identity**.
2. Resolve aliases using the existing DB-backed `CompetitionRegistry`, including
   provider mapping and canonical competition ID.
3. Canonicalize before the public workspace response, not by display-name string
   dedupe in React.
4. Do not add aggregate percentages or counts from ambiguous overlapping source
   cohorts. If source cohort overlap cannot be proven absent, reconstruct the
   canonical aggregate from existing fixture-level performance checkpoints or
   fail closed with an explicit aggregation-conflict state. Never double-count.
5. Recompute direction counts/rate from canonical fixture rows or proven
   disjoint counts; do not average percentages.
6. Probability metrics may be weighted/recomputed only from source-bound
   sufficient statistics. Otherwise remain null and `SAMPLE_BUILDING`.
7. Preserve and expose source aliases/checkpoint identities in technical details.
8. Add invariants proving canonical totals, no duplicate canonical ID, no
   duplicate public Chinese display name, and no fixture double-count.

Deterministic acceptance must include at least:

```text
allsvenskan + provider alias -> one 瑞典超 row
chinese_super_league + provider alias -> one 中超 row
same fixture visible through two aliases -> counted once
ambiguous aggregate-only overlap -> fail closed, not summed
```

### P0 — D14-02 Collection risk requires assessment evidence

`read_contract.provider_calls=0` means the Dashboard read made no Provider call;
it does not by itself prove that collection failed or succeeded. The current
risk builder nevertheless returns `COLLECTION_RISK=OK` whenever no incident code
is present. Absence of an incident code is not evidence of a healthy collection.

Required result:

1. `COLLECTION_RISK=OK` may be presented as green/normal only when persisted,
   source-bound collection evidence proves an assessed terminal/capture state
   for the relevant fixture/window and the evidence is within its declared
   freshness semantics.
2. If no assessment evidence exists, show `未评估` / `采集状态无法评估`, not
   `正常`. This must not be promoted to `COLLECTION_INCIDENT` unless an actual
   incident is proven.
3. Preserve the exact four risk axes. A safe implementation may retain the
   canonical `OK/ATTENTION/INCIDENT` risk contract while adding an explicit
   assessment/evidence field, or use `ATTENTION` with a dedicated
   `COLLECTION_ASSESSMENT_NOT_AVAILABLE` reason. Do not silently redefine `OK`.
4. Expose the evidence basis and `source_as_of` in technical details. If the
   evidence is stale, say stale; if absent, say unassessed.
5. No Provider probe and no business write is allowed.

Deterministic cases:

```text
no incident + no terminal/capture evidence -> 未评估, not green OK
fresh persisted successful capture/terminal evidence -> 正常 with evidence time
persisted quota/scheduler/collection incident -> 异常 with source reason
provider_calls=0 on read -> remains a read invariant, not a risk conclusion
```

### P1 — D14-03 One canonical Chinese competition naming authority

Public competition names must be consistent and canonical:

- no `Chinese 中超`;
- no `Campeonato Brasileiro 巴甲`;
- no untranslated `Liga Profesional de Futbol`;
- no raw `world_cup_2026` slug.

Use canonical competition ID plus one Chinese display-name authority. The
registry/source name remains audit evidence, not the primary label. Unresolved
identity must display `赛事名称待解析`, with the raw value only in technical
details.

### P1 — D14-04 Separate leagues from tournaments

The registry already exposes `scope_group`; the World Cup profile is a
`tournament/world_cup` authority, not a national league.

Required result:

- `联赛表现` contains only canonical national-league rows;
- tournament/cup rows are either shown in a separate `杯赛 / 其他赛事` section or
  explicitly summarized outside the league table;
- no data is silently discarded;
- `world_cup_2026` is displayed as `世界杯` if shown;
- public counts distinguish league row count from tournament row count.

Do not change the active whitelist or delete historical evidence in this task.

### P1 — D14-05 Baseline prior is not model-ready

The current adapter passes `simulation.status` and `calibration_status`
independently, allowing `READY + BASELINE_PRIOR` to render as `模型视图：就绪`.

Required result:

- when the model/calibration evidence is baseline-prior-only, public status is
  `仅先验` / `PRIOR_ONLY`, never `就绪`;
- source simulation status remains available in technical details;
- Inspector, Model Lab and Scoreline context must use the same public model
  readiness semantics;
- do not change the model, calibration artifact, factors or thresholds.

### P1 — D14-06 Homogeneous Attention collapse

If every visible match is included in Attention and all rows share the same
intelligence state plus the same dominant blocker class, the primary Attention
surface must not duplicate the Match Board.

Render one aggregate item such as:

```text
当日阻塞 · 9 场比赛全部数据不完整
```

Include state/reason counts and an explicit expand control. Individual rows must
remain reachable and selection behavior must remain correct. Heterogeneous
Attention must continue to show individual priority rows.

### P1 — D14-07 Explain the football-day boundary

The DayView already exposes:

```text
football_day_timezone
football_day_cutoff_hour
football_day_start_utc
football_day_end_utc
```

Project these existing fields into the unified workspace schema and show the
window near the date, for example:

```text
比赛日 2026-08-09 · 北京时间 08-09 12:00 至 08-10 11:59
```

Do not duplicate the cutoff rule in ad-hoc frontend logic. The display must be
derived from the shared backend football-day authority.

### P1 — D14-08 Explain `仅记录`

A public `仅记录` label must state why. Separate at least:

```text
PROBABILITY_QUALITY_NOT_READY -> 仅记录（概率质量未就绪）
SAMPLE_INSUFFICIENT -> 仅记录（样本不足）
MARKET_DIRECTION_BENCHMARK_NOT_DEFINED -> 市场方向基准未定义
```

These reasons have different release conditions and must not be collapsed into
one unexplained label. Preserve canonical codes in technical details.

## Source-of-truth constraints

- Use only existing persisted read-model/performance/registry/checkpoint data.
- Existing fixture-level performance checkpoints may be read to prove canonical
  aggregation and dedupe; no Provider call is permitted.
- No migration is expected. If Codex proves a migration is unavoidable, stop as
  `BLOCKED_OWNER_DECISION_REQUIRED` rather than inventing a shortcut.
- No direct frontend grouping by translated text.
- No percentage averaging.
- No deletion of evidence or historical checkpoints.
- No changing `MIN_DECISIVE_SAMPLES_FOR_RATE` merely to satisfy the UI.

## Required tests

### Backend / contract

- canonical alias aggregation and fixture-level dedupe;
- unresolved/ambiguous overlap fail-closed behavior;
- league/tournament classification from registry `scope_group`;
- one canonical Chinese display identity per public competition;
- collection `OK` requires source-bound assessment evidence;
- no-assessment collection state is not green `OK`;
- baseline-prior public readiness is `PRIOR_ONLY`;
- football-day boundary fields are exact pass-throughs;
- explicit `only_record_reason`/benchmark semantics;
- schema extra-field and invalid-enum fail-closed coverage;
- repeated endpoint reads preserve `provider_calls=0`, `db_writes=0`,
  `would_write_checkpoint=false`, `no_call_on_read=true`.

### Web / real-data rendering

- no duplicate canonical league rows;
- no mixed-language or raw-slug primary competition names;
- World Cup absent from `联赛表现` and present only in the separate tournament
  treatment when source data exists;
- no green collection-normal state without assessment evidence;
- homogeneous blocked-day Attention collapses to one aggregate row and expands;
- heterogeneous Attention remains itemized;
- `READY + BASELINE_PRIOR` displays `仅先验`;
- football-day boundary explains next-calendar-day kickoff rows;
- every `仅记录` label exposes a distinct reason;
- 1280x720, 1366x768, 1512x982 and 1920x1080 remain readable and free of
  overlap/horizontal overflow.

## Continuous execution, merge and deployment

Codex is authorized to execute this bounded remediation continuously:

```text
trace root causes
-> implement source-bound fixes
-> focused tests
-> full CI / RELEASE_REQUIRED
-> Repository Hygiene
-> merge accepted PR(s)
-> promote exact immutable images
-> LOCAL_OCI_RELAY_PRIMARY
-> VPS warm switch
-> postdeploy real-data acceptance
```

Ordinary in-scope failures must be fixed and revalidated without an intermediate
Owner relay. Multiple PRs are allowed only when a postdeploy live-data defect is
discovered; they remain one continuous task.

Postdeploy acceptance must use real persisted data and prove:

```text
NO_DUPLICATE_CANONICAL_LEAGUE_ROWS
NO_MIXED_OR_RAW_SLUG_COMPETITION_NAMES
TOURNAMENT_NOT_IN_LEAGUE_TABLE
COLLECTION_OK_REQUIRES_ASSESSMENT_EVIDENCE
BASELINE_PRIOR_NOT_READY
HOMOGENEOUS_ATTENTION_AGGREGATES
FOOTBALL_DAY_BOUNDARY_VISIBLE
ONLY_RECORD_REASON_EXPLICIT
PROVIDER_CALLS_FROM_READ = 0
DB_BUSINESS_WRITES_FROM_READ = 0
NO_CALL_ON_READ = true
SIX_SERVICES_HEALTHY
WEB_API_EXACT_SOURCE_MATCH
```

## Terminal classifications

```text
DASHBOARD_OWNER_CANONICAL_TRUTH_ACCEPTANCE_PASS
DASHBOARD_OWNER_CANONICAL_TRUTH_ROLLED_BACK
BLOCKED_OWNER_DECISION_REQUIRED
```

Do not start Round4 after PASS. Stop at Owner Round4 decision gate.

## Frozen stop lines

```text
ROUND_4_START = NOT_AUTHORIZED
P6_EXECUTION = NOT_AUTHORIZED
NEW_PROVIDER_OR_PLAN = NOT_AUTHORIZED
MANUAL_PROVIDER_PROBE = FORBIDDEN
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_RETRAINING = NOT_AUTHORIZED
EXTERNAL_INTELLIGENCE_ACTIVATION = NOT_AUTHORIZED
PHASE_0_5_REEXECUTION = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
VPS_DIRECT_GHCR_BULK_IMAGE_PULL = FORBIDDEN_AS_PRIMARY_TRANSPORT
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
```
