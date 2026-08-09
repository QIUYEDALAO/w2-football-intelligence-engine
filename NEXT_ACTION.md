# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_DASHBOARD_OWNER_VISUAL_PARITY_ZH_CN_REMEDIATION
CURRENT_GATE = DASHBOARD_OWNER_VISUAL_UX_ACCEPTANCE
AUTHORITY = DASHBOARD_OWNER_VISUAL_PARITY_ZH_CN_REMEDIATION.md
BASE_MAIN = d61768ecf8457a72df80a5cb0220072de76dfdd4
DEPLOYED_SOURCE = d61768ecf8457a72df80a5cb0220072de76dfdd4
FUNCTIONAL_PRE_ROUND4_SCOPE = COMPLETE
OWNER_VISUAL_UX_ACCEPTANCE = CHANGES_REQUIRED
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
```

## Why this task exists

The deployed unified Intelligence Workspace passed functional/runtime acceptance but failed the Owner's actual visual and usability expectation.

The current desktop UI is a long English-heavy vertical stack. The Owner target is a compact Chinese-first intelligence console similar in composition and density to the provided 1536x1024 design reference.

The current implementation also renders many canonical English enum/reason codes directly, even though the repository already contains `translateTeam`, `translateCompetition`, and `translateReason` helpers.

This is a presentation/localization remediation. It must NOT restore deleted Boss/recommendation semantics or change backend/runtime/model authority.

## Binding read order

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. DASHBOARD_OWNER_VISUAL_PARITY_ZH_CN_REMEDIATION.md
5. apps/web/src/components/IntelligenceConsole.tsx
6. apps/web/src/intelligence.css
7. apps/web/src/lib/formatters.ts
8. apps/web/src/lib/labels.ts
9. docs/ui/boss-console/design-qa.md
10. docs/ui/boss-console/w2_boss_decision_console_prototype.html
11. existing boss-console golden reference assets
12. DASHBOARD_INTELLIGENCE_WORKSPACE_PRODUCT_SPEC.md
13. CODEX_EXECUTION_RECEIPT.md
```

## Execute continuously

Create one Draft PR from fresh `origin/main` and complete the entire Owner visual/language remediation without intermediate Owner relay.

Primary requirements:

```text
PUBLIC_LANGUAGE = zh-CN
PRIMARY_DESKTOP_VIEW = 1536x1024
DESKTOP_COMPOSITION = COMPACT_MULTI_COLUMN_CONSOLE
WHOLE_PAGE_LONG_VERTICAL_STACK = NO
ATTENTION_PRIMARY_ROWS ~= 5_WITH_INTERNAL_SCROLL_OR_VIEW_ALL
MATCH_BOARD = COMPACT_INTERNAL_SCROLL
SELECTED_MATCH = CENTRAL_VISUAL_PRIORITY
MARKET_RADAR = FIRST_VIEWPORT_VISIBLE
EXTERNAL_INTELLIGENCE = FIRST_VIEWPORT_VISIBLE
MODEL_LAB = FIRST_VIEWPORT_VISIBLE
SCORELINE_TOP3 = FIRST_VIEWPORT_VISIBLE_WHEN_AVAILABLE_OR_TRUTHFUL_UNAVAILABLE
VALIDATION = FIRST_VIEWPORT_VISIBLE
LEAGUE_PERFORMANCE = FIRST_VIEWPORT_VISIBLE
DATA_SYSTEM_HEALTH = FIRST_VIEWPORT_VISIBLE
RAW_CANONICAL_CODES = SECONDARY_TECHNICAL_DETAILS_ONLY
TEAM_COMPETITION_REASON_TRANSLATIONS = REUSE_EXISTING_HELPERS
```

Do not translate by fabricating facts. Unknown team names may fall back to source names. Canonical codes remain available for audit in technical details/tooltips but must not dominate the public primary surface.

Reuse the repo-bound old Boss console only as visual-composition/fidelity reference. Do not restore its obsolete product authority, EV/CLV/ROI, recommendation-first logic, lock semantics or legacy route.

Preserve the unified endpoint and current truthful product semantics exactly.

## Required deterministic viewport acceptance

```text
1536x1024
2048x1084
1920x1080
1440x900
1366x768
390x844
```

At 1536x1024, the key decision surfaces must be visible in the first viewport without whole-page scrolling.

## Required technical gates

```text
TYPESCRIPT = PASS
WEB_BUILD = PASS
WEB_E2E = PASS
ZH_CN_LOCALIZATION_ASSERTIONS = PASS
RAW_CODE_PRIMARY_UI_NEGATIVE_ASSERTIONS = PASS
DETERMINISTIC_SCREENSHOTS = PASS
VISUAL_REGRESSION = PASS
UNIFIED_ENDPOINT_ONLY = PASS
NO_LEGACY_FALLBACK = PASS
NO_CALL_ON_READ = PASS
FORBIDDEN_PUBLIC_SEMANTICS = ABSENT
EXACT_HEAD_FULL_CI = PASS
RELEASE_REQUIRED = PASS
REPOSITORY_HYGIENE = PASS
```

Ordinary in-scope failures are self-remediated. Do not stop at a partial visual pass.

## Merge and deploy

When the exact-head implementation passes all technical gates, this Owner authority permits automatic technical approval and merge because the product/language/visual decision is already explicit here and no new runtime authority is introduced.

Then deploy the exact approved main using the frozen transport path:

```text
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
```

Perform postdeploy API/Web/release identity/real-data/visual smoke. Do not use VPS-direct GHCR bulk image pull as primary transport.

## Terminal target

```text
DASHBOARD_OWNER_VISUAL_UX_ACCEPTANCE_PASS
```

Only after this terminal target may the system return to the Round4 decision gate.

## Frozen stop lines

```text
ROUND_4_START = NOT_AUTHORIZED
P6_EXECUTION = NOT_AUTHORIZED
NEW_PROVIDER_OR_PLAN = NOT_AUTHORIZED
MANUAL_PROVIDER_PROBE = FORBIDDEN
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_CHANGE = NOT_AUTHORIZED
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
