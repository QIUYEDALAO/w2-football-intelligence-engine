# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_SC20_SINGLE_PUBLIC_AUTHORITY_CUTOVER
CURRENT_GATE = SC20_SINGLE_AUTHORITY_CUTOVER_ACTIVE
AUTHORITY = SC20_PUBLIC_SEMANTICS_SINGLE_AUTHORITY_CUTOVER.md
BASE_MAIN = f2b82c7d59341e8ecc98ccb34130b983c51664fc
BASE_RELEASE = PR_524_MERGED_DEPLOYED
SC19_SCOPE_CAUSE_FOUNDATION = RETAIN
SC19_DUAL_PUBLIC_AUTHORITY = OWNER_REJECTED
IMPLEMENTATION = ONE_PR_PHYSICAL_CUTOVER
SYSTEM_HEALTH_PUBLIC_SEMANTICS = OPS_ONLY_NOT_WORKSPACE_PUBLIC_SEMANTICS
TEAM_PUBLIC_LABEL_AUTHORITY = CANONICAL_IDENTITY_PLUS_CONFIG_IDENTITY_PUBLIC_TEAM_LABELS_ZH_CN_V1
SHADOW_CANDIDATE = KEEP_ACTIVE_SHADOW_ONLY
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
TERMINAL_GATE = OWNER_SC20_SINGLE_AUTHORITY_POSTDEPLOY_REREVIEW
```

## Owner decision

PR #524's `WorkspacePublicSemantics(scope, cause)` foundation is accepted, but the repository still carries the previous day-mode/focus/system-health/team-translation public chains. Those parallel authorities are not accepted.

Execute SC20 continuously in one PR. Do not stage a compatibility migration and defer cleanup.

## Binding decisions

### Public semantics

The only business/public semantics model is:

```text
WorkspacePublicSemantics
  scope = MATCH | SELECTED_DAY | CROSS_DAY_CUMULATIVE | GLOBAL
  cause = NOT_YET_DUE | AWAITING_COLLECTION | INSUFFICIENT
          | UNAVAILABLE | UNASSESSED | LABEL_MISSING
          | IDENTITY_UNRESOLVED | AMBIGUOUS
```

All primary Dashboard presentation must go through one `scope + cause -> PublicPresentation` authority.

### System health

Option B is selected. Do **not** add `SYSTEM_FAULT` to `cause`.

Raw system/scheduler/collector/API/database health lives only in the Ops/system-status surface as technical telemetry. It does not determine business headline, card tone/color, focus layout, attention classification or any second public page state.

### Team labels

The replacement Chinese-label authority already exists on current main:

```text
config/identity/public_team_labels.zh-CN.v1.json
src/w2/identity/public_team_labels.py
```

It is keyed by stable `w2_team_id` and requires APPROVED reviewed labels. Use canonical identity + this reviewed label authority only. The old frontend `TEAM_TRANSLATIONS` / `translateTeam()` chain must be physically deleted after same-PR parity migration proof; do not retain it as fallback or rename it.

## Continuous execution order

1. **SC20-01:** recompute exact current-main consumer inventory for all retired public identifiers and classify every hit.
2. **SC20-02:** establish one `PublicPresentation` converter that consumes only `WorkspacePublicSemantics` plus factual context for primary business presentation.
3. **SC20-03:** migrate all live consumers and physically delete `DashboardDayMode/day_mode`, `DashboardFocusType/default_focus_type`, `public_system_health`, date-strip `display_state`, `DAY_MODE_LABELS`, all `workspace.day_mode` branches and old mode CSS. No aliases, deprecated fields or fallback readers.
4. **SC20-04:** prove label parity/gaps against the reviewed canonical label config, then physically delete `TEAM_TRANSLATIONS`, `translateTeam()` and obsolete Dashboard V2 translation/reference dependencies. No raw-English-as-localized-success behavior.
5. **SC20-05:** convert date strip, match/day/global/cumulative focus and public copy to facts + `scope/cause` only. `NOT_YET_DUE` must never look like a collection incident.
6. **SC20-06:** add a CI architecture gate that mechanically forbids resurrection of retired identifiers in current public-authority paths and behavior-tests `NOT_YET_DUE != COLLECTION_INCIDENT`.
7. **SC20-07:** run full verification, exact-head Full CI and `RELEASE_REQUIRED`; merge automatically; deploy only by Owner-local OCI relay; verify live API contains no retired public fields and live UI uses the single semantics/label authorities; update context and Round4 exact identity only; stop at Owner rereview.

Ordinary implementation/test/CI/deployment-preparation failures are in scope:

```text
fix -> revalidate -> continue
```

## Mechanical acceptance proof

Current public-authority paths must produce zero hits for:

```text
DashboardDayMode
day_mode
default_focus_type
DashboardFocusType
public_system_health
DAY_MODE_LABELS
TEAM_TRANSLATIONS
translateTeam
v41-global--blocked
v41-global--calm
v41-global--empty
v41-pill--mode-
```

Date-strip `display_state` must have zero current Dashboard/public-contract hits. Historical text may remain only under an explicit archive path that is not imported, parsed, or treated as current authority.

Do not globally delete `COLLECTION_INCIDENT`; it remains a legitimate technical intelligence state. Instead prove that `NOT_YET_DUE` and normal waiting can never map to collection-incident public copy/tone/class.

## Mandatory live/regression acceptance

```text
selected future day + persisted fixtures + collection not due
=> SELECTED_DAY + NOT_YET_DUE, normal waiting presentation, no incident styling

system-health telemetry changes while business evidence is unchanged
=> primary business presentation unchanged

canonical reviewed Chinese label exists
=> Chinese public name from canonical reviewed authority

canonical identity exists but approved Chinese label missing
=> LABEL_MISSING semantics, no frontend dictionary fallback

identity unresolved / ambiguous
=> explicit identity semantics, no guessed translation

date strip
=> facts + public_semantics only, no display_state

workspace live JSON
=> no day_mode / default_focus_type / public_system_health

read path
=> provider_calls=0, db_writes=0, no_call_on_read=true
```

## Frozen stop lines

```text
NEW_PROVIDER_OR_PLAN = NOT_AUTHORIZED
MANUAL_PROVIDER_PROBE = FORBIDDEN
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_CHANGE = NOT_AUTHORIZED
MODEL_RETRAINING = NOT_AUTHORIZED
BOOKMAKER_DEPTH_THRESHOLD_CHANGE = NOT_AUTHORIZED
MARKET_DIRECTION_BENCHMARK_DEFINITION = NOT_AUTHORIZED
EXTERNAL_INTELLIGENCE_ACTIVATION = NOT_AUTHORIZED
PHASE_0_5_REEXECUTION = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
ROUND_4_START = NOT_AUTHORIZED
P6_EXECUTION = NOT_AUTHORIZED
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = OFF
READ_PROVIDER_CALLS = 0_REQUIRED
READ_DB_BUSINESS_WRITES = 0_REQUIRED
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
DELETE_PROTECTED_HISTORICAL_EVIDENCE = FORBIDDEN
DEPRECATED_PUBLIC_STATUS_ALIAS = FORBIDDEN
LEGACY_PUBLIC_STATUS_FALLBACK = FORBIDDEN
FRONTEND_TEAM_TRANSLATION_AUTHORITY = FORBIDDEN
SYSTEM_HEALTH_AS_BUSINESS_PUBLIC_STATUS = FORBIDDEN
```