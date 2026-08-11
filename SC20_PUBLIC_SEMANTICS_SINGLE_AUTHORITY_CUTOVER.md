# SC20 Public Semantics Single Authority Cutover

```text
AUTHORITY = W2_SC20_PUBLIC_SEMANTICS_SINGLE_AUTHORITY_V1
OWNER_DATE = 2026-08-11
OWNER_DECISION = AUTHORIZED
BASE_MAIN_SHA = f2b82c7d59341e8ecc98ccb34130b983c51664fc
BASE_RELEASE = PR_524_MERGED_DEPLOYED
SC19_STATUS_SEMANTICS = TECHNICAL_FOUNDATION_ACCEPTED_BUT_DUAL_AUTHORITY_NOT_ACCEPTED
IMPLEMENTATION = SINGLE_PR_PHYSICAL_CUTOVER
DEPRECATED_ALIAS_OR_FALLBACK = FORBIDDEN
SYSTEM_HEALTH_PUBLIC_SEMANTICS_OPTION = B_OPS_ONLY
SHADOW_CANDIDATE = KEEP_ACTIVE_SHADOW_ONLY
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = OFF
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
TERMINAL_GATE = OWNER_SC20_SINGLE_AUTHORITY_POSTDEPLOY_REREVIEW
```

## Owner decision

PR #524 correctly introduced `WorkspacePublicSemantics(scope, cause)`, but the repository still contains the older public status and presentation chain. This is not accepted as a stable architecture.

The cutover must happen in one PR:

```text
inventory consumers
-> migrate every live consumer to WorkspacePublicSemantics
-> establish one PublicPresentation converter
-> delete old production/public fields, types, labels, CSS branches and fixtures
-> delete obsolete translation authority
-> update the one public contract and reference fixtures
-> add anti-resurrection architecture tests
-> full CI / merge / local OCI relay / live rereview
```

Do not retain `deprecated`, compatibility aliases, legacy fallback readers, dual-write fields, shadow public models, or temporary bridges.

## The only public semantics model

```text
WorkspacePublicSemantics
  scope = MATCH | SELECTED_DAY | CROSS_DAY_CUMULATIVE | GLOBAL
  cause = NOT_YET_DUE | AWAITING_COLLECTION | INSUFFICIENT
          | UNAVAILABLE | UNASSESSED | LABEL_MISSING
          | IDENTITY_UNRESOLVED | AMBIGUOUS
```

`cause` describes why public evidence/presentation is limited. It is not a system-health taxonomy.

The existing technical/domain facts may remain where they are authoritative, including:

```text
intelligence_state
market READY | STALE | INSUFFICIENT
raw system/degradation health
risk axes
candidate/readiness/model technical statuses
```

But those technical facts MUST NOT independently determine primary public copy, business-card color, day-level page mode, focus layout, or a second public status. They must first be projected into `WorkspacePublicSemantics`, and the public UI must consume the single presentation authority described below.

## System health decision: Option B, Ops-only

Do NOT add `SYSTEM_FAULT` to `WorkspacePublicSemantics`.

Raw scheduler/collector/API/database/system health is operational telemetry, not evidence scope/cause. It remains available only under the system/Ops surface as a technical fact.

Binding rules:

- delete `public_system_health` from the public workspace schema and payload;
- no business headline, match card, selected-day summary, attention stripe, public badge, focus selection, or business color may read raw system health directly;
- the primary dashboard header must not create a second business state from raw health;
- the system-status/Ops view may show raw health and its own technical severity, but it must not feed `WorkspacePublicSemantics` back into business content;
- when missing evidence is caused by an operational failure, business semantics are still derived from the persisted evidence/timing facts (`AWAITING_COLLECTION`, `UNAVAILABLE`, etc.), not by copying a system-health enum.

This separation is architectural and must be covered by tests.

## Canonical Chinese team-label authority decision

The repository now has a reviewed public label authority introduced during SC19:

```text
config/identity/public_team_labels.zh-CN.v1.json
src/w2/identity/public_team_labels.py
```

It is keyed by stable `w2_team_id`, requires `review_status=APPROVED`, and is already used with canonical/reviewed identity checks. This is the replacement authority for public Chinese team names.

Therefore:

- do not add a second Chinese-name field merely to preserve the frontend dictionary;
- `canonical team identity + reviewed public_team_labels.zh-CN authority` is the only successful public Chinese-name path;
- raw Provider names remain technical evidence only, except where the public product deliberately shows a non-localized raw label together with explicit `LABEL_MISSING` semantics during the migration acceptance defined below;
- no automatically invented translation is allowed.

Before deleting the old dictionary, the same PR must create a parity inventory proving which legacy labels are already represented by canonical reviewed labels and which old dictionary entries are unreachable/obsolete or lack canonical identity. This is a migration check, not a reason to retain the old runtime dictionary.

## SC20-01 — Exact consumer inventory and cutover map (P0)

On fresh `origin/main`, mechanically inventory all live/public consumers of at least:

```text
day_mode
DashboardDayMode
default_focus_type
DashboardFocusType
public_system_health
display_state  # date-strip/public contract usage
DAY_MODE_LABELS
workspace.day_mode
v41-global--blocked
v41-global--calm
v41-global--empty
v41-pill--mode-
TEAM_TRANSLATIONS
translateTeam
```

The Owner/Claude inventory (`115` occurrences across src/apps/tests/contracts at an earlier point) is a starting reference only. Recompute the exact current-main inventory before editing.

Classify every hit:

```text
LIVE_PRODUCTION_CONSUMER
PUBLIC_SCHEMA_CONTRACT
PUBLIC_TEST_OR_FIXTURE
PUBLIC_REFERENCE_OR_VISUAL_TARGET
OBSOLETE_V2_REFERENCE
ARCHIVED_HISTORICAL_EVIDENCE
UNRELATED_SYMBOL
```

Archived historical evidence may retain historical text if it is physically isolated under an archive path and cannot be imported or parsed as current authority. Everything else must be migrated or deleted in the same PR.

Produce `docs/review_packages/SC20_SINGLE_PUBLIC_AUTHORITY/CONSUMER_INVENTORY.json` and a short report.

## SC20-02 — Single PublicPresentation authority (P0)

Create one and only one public presentation converter for the main workspace, for example:

```text
derivePublicPresentation(public_semantics, factual_context) -> PublicPresentation
```

The exact module location is implementation-defined, but there must be one importable authority used by all primary Dashboard consumers.

`PublicPresentation` owns only presentation concerns, such as:

```text
headline
summary
badge label
semantic tone
primary action/callout wording
layout/focus presentation intent derived from scope
```

It MUST consume `WorkspacePublicSemantics`; it must not consume `day_mode`, `public_system_health`, raw `intelligence_state`, or raw risk/system enum as an alternate public-status authority.

Technical details may still display raw codes inside collapsed technical/Ops surfaces.

Required semantic invariants include:

```text
MATCH + NOT_YET_DUE
=> normal waiting / not an incident

SELECTED_DAY + NOT_YET_DUE
=> selected future day / known persisted schedule / no collection incident styling

SELECTED_DAY + AWAITING_COLLECTION
=> collection is due/awaited, but not fabricated as Provider failure without source evidence

MATCH + INSUFFICIENT
=> evidence insufficient, not system broken

CROSS_DAY_CUMULATIVE + INSUFFICIENT
=> cumulative evidence insufficient; never described as selected-day failure

LABEL_MISSING / IDENTITY_UNRESOLVED / AMBIGUOUS
=> identity/label gap copy, not raw-English-localized success
```

## SC20-03 — Physically delete the old public status chain (P0)

After all consumers are migrated, physically remove from current production/public authority:

```text
DashboardDayMode
day_mode
default_focus_type
DashboardFocusType
public_system_health
date-strip display_state
DAY_MODE_LABELS
all workspace.day_mode branches
v41-global--blocked / calm / empty
v41-pill--mode-* CSS and selectors
any normal-wait -> collection_incident coercion
```

No compatibility alias, deprecated property, parser fallback, dual-write output, or hidden legacy branch may remain.

Focus/layout selection must be determined from actual focus data plus the single public semantics scope. Do not introduce a renamed day-mode enum or a renamed default-focus enum.

Update or remove all affected:

```text
backend projection
Pydantic API schema
TypeScript workspace types
frontend components
CSS
contract tests
E2E fixtures
example JSON
DASHBOARD_DATA_CONTRACT.md
DASHBOARD_V41_STATE_MATRIX.md or its replacement
REAL_SHAPE fixtures
visual/reference targets
```

If a document describes the current public contract, it must be rewritten to the single model. Historical records belong under archive only.

## SC20-04 — Physically delete the old frontend team-name authority (P0)

Remove:

```text
TEAM_TRANSLATIONS
translateTeam()
all imports/usages of them
Dashboard V2 reference-adapter dependence on them
```

Do not move the dictionary under another filename and call it canonical.

Before deletion, create a parity/gap proof between the legacy dictionary and the existing reviewed canonical label authority:

```text
LEGACY_LABEL_HAS_CANONICAL_APPROVED_EQUIVALENT
LEGACY_LABEL_UNREACHABLE_CURRENT_PUBLIC_SCOPE
LEGACY_LABEL_CANONICAL_IDENTITY_MISSING
LEGACY_LABEL_REVIEWED_PUBLIC_LABEL_MISSING
```

For currently reachable public fixtures in the exact runtime scope:

```text
reviewed canonical identity + approved public label
=> Chinese public name

canonical identity ready, approved Chinese label missing
=> explicit LABEL_MISSING presentation

identity unresolved
=> explicit IDENTITY_UNRESOLVED presentation

ambiguous
=> explicit AMBIGUOUS presentation
```

The main workspace may not call a provider-name translation dictionary. The raw Provider name, if retained, belongs to technical evidence and must not masquerade as successful Chinese localization.

Delete obsolete Dashboard V2 reference code rather than migrating its legacy translation dependency into V4.1, unless a file is still mechanically proven to be needed by the current approved visual authority; in that case rewrite the reference to use the canonical read-model label, never the old dictionary.

## SC20-05 — Date strip and focus consumers use scope+cause only (P1)

Remove `display_state` from the date-strip public contract. Each cell must expose factual persisted counts/timestamps/coverage plus `public_semantics` only.

Examples:

```text
persisted future fixture + odds checkpoint not yet due
=> SELECTED_DAY / NOT_YET_DUE

checkpoint due/past + no usable evidence
=> SELECTED_DAY / AWAITING_COLLECTION or INSUFFICIENT based on factual contract

usable persisted market evidence
=> cause null when no limitation exists, or the minimal applicable cause

empty persisted selected day
=> SELECTED_DAY with factual fixture_count=0; no separate EMPTY day mode
```

`next_available_date` remains a factual navigation result derived from persisted inventory, not a public status.

Match/day/global/cumulative layout must be selected from the data shape and semantics scope, not from `default_focus_type`.

## SC20-06 — Anti-resurrection architecture gate (P0)

Add a repository checker, for example:

```text
scripts/check_dashboard_single_public_authority.py
```

It must scan current public-authority locations including at minimum:

```text
src/w2/dashboard/**
src/w2/api/schemas.py
apps/web/src/**
apps/web/e2e/**
tests/contract/**
tests/unit/**
examples/dashboard*
docs/ui/dashboard-v4.1/**
DASHBOARD_DATA_CONTRACT.md
```

It must fail CI if the retired public identifiers reappear outside an explicit historical archive allowlist.

Required mechanical proof at acceptance:

```text
DashboardDayMode = 0 live/public hits
day_mode = 0 live/public hits
default_focus_type = 0 live/public hits
DashboardFocusType = 0 live/public hits
public_system_health = 0 live/public hits
DAY_MODE_LABELS = 0
TEAM_TRANSLATIONS = 0
translateTeam = 0
v41-global--blocked = 0
v41-global--calm = 0
v41-global--empty = 0
v41-pill--mode- = 0
```

For date-strip `display_state`, require zero current dashboard/public-contract hits; unrelated domain symbols must be explicitly identified rather than globally deleted blindly.

Do not globally ban `COLLECTION_INCIDENT`; it remains a legitimate technical intelligence state for real collection incidents. Instead add behavior/architecture tests proving:

```text
NOT_YET_DUE -> never collection-incident public copy/tone/class
normal waiting -> never collection-incident public copy/tone/class
real persisted collection incident -> may use collection technical evidence, projected through the single public semantics path
```

Add this checker to CI so reintroducing a retired authority fails automatically.

## SC20-07 — Full verification, merge, deployment and live rereview (P1)

Mandatory regression coverage:

- current future selected day: `SELECTED_DAY + NOT_YET_DUE` with no incident copy/color;
- actual due-but-missing evidence: correct `AWAITING_COLLECTION/INSUFFICIENT` semantics;
- match evidence limitation: `MATCH + INSUFFICIENT` without system-health contamination;
- cross-day validation: `CROSS_DAY_CUMULATIVE` never described as selected-day failure;
- system health may change in Ops facts without changing business presentation when business evidence is unchanged;
- team label uses reviewed canonical authority only;
- no approved label => explicit label/identity semantics, never frontend translation fallback;
- date strip has no `display_state` public field;
- no old day/focus mode field exists in API JSON;
- read path remains `provider_calls=0`, `db_writes=0`, `no_call_on_read=true`;
- shadow candidate remains SHADOW_ONLY; Formal/Lock/Production remain off.

Run:

```text
focused + full Python tests
Ruff
MyPy
TypeScript typecheck/build
full Web E2E
real-shape visual tests
public contract/schema tests
SC20 architecture checker
secret scan
tracked-output/protected-evidence gates
Repository Hygiene
Exact-head Full CI
RELEASE_REQUIRED
```

After exact-head PASS:

1. merge automatically;
2. deploy by Owner-local immutable OCI relay only;
3. verify exact Web/API source identity, health/ready/release sync;
4. inspect live selected future day, current day, one limited-evidence match, date strip and team labels;
5. verify no old public field appears in live API payload;
6. verify read Provider-call and business-write deltas remain zero;
7. update `CURRENT_STATE.yaml`, `NEXT_ACTION.md` and Round4 exact release identity only;
8. stop at `OWNER_SC20_SINGLE_AUTHORITY_POSTDEPLOY_REREVIEW`.

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
VPS_DIRECT_GHCR_BULK_IMAGE_PULL = FORBIDDEN_AS_PRIMARY_TRANSPORT
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
DELETE_PROTECTED_HISTORICAL_EVIDENCE = FORBIDDEN
DEPRECATED_PUBLIC_STATUS_ALIAS = FORBIDDEN
LEGACY_PUBLIC_STATUS_FALLBACK = FORBIDDEN
FRONTEND_TEAM_TRANSLATION_AUTHORITY = FORBIDDEN
SYSTEM_HEALTH_AS_BUSINESS_PUBLIC_STATUS = FORBIDDEN
```