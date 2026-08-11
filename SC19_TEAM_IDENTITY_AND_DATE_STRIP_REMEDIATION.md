# SC19 Team Identity Recovery and Persisted Date Strip

```text
AUTHORITY = W2_SC19_TEAM_IDENTITY_AND_DATE_STRIP_V1
OWNER_DATE = 2026-08-11
OWNER_DECISION = AUTHORIZED
BASE_MAIN_SHA = 99baac47aad81d6afa0af9f368434bf93f14bd58
SC18_00_FT_RETENTION = OWNER_ACCEPTED_CLOSED_PASS
SHADOW_CANDIDATE = KEEP_ACTIVE_SHADOW_ONLY
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = OFF
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
TERMINAL_GATE = OWNER_SC19_POSTDEPLOY_REREVIEW
```

## Purpose

SC18-00 is accepted: finished fixtures remain in the correct Asia/Shanghai football day and replay, with terminal status projected from current persisted fixture identity.

Owner postdeploy review exposed two next issues, with strict priority order:

1. **P0 public team identity/display regression or uncovered identity gap**: all five retained 2026-08-10 fixtures currently render generic `主队（身份待确认） vs 客队（身份待确认）`. This must be investigated and repaired before any navigation enhancement.
2. **P1 persisted date strip**: expose past and future football-day fixture inventory without issuing Provider requests on Dashboard reads, and distinguish future schedule visibility from market-evidence availability.

Do not attribute the team-name problem to PR #520 without proof. PR #520 only overlays current fixture status. PR #518 introduced the reviewed canonical-team public-label authority and fail-closed placeholder behavior. The current symptom may therefore be a newly exposed canonical identity/crosswalk/materialization gap rather than a direct #520 field regression.

## SC19-01 — Finished-fixture team identity trace (P0)

For all five retained fixtures in football day `2026-08-10`, produce a sanitized source-bound trace covering both sides:

```text
fixture_id
provider_fixture_id
competition_id
season
home/away provider_team_id
home/away w2_team_id
fixture team_identity_status
raw persisted provider team name
canonical_teams row presence
canonical display/public zh name presence
provider_team_identity_crosswalk row presence
crosswalk competition_id / season / validity interval
crosswalk identity_status
crosswalk review_status / review provenance presence
public label state
```

Compare the trace with known previously displayed fixtures such as `1575453` and `1493049` and identify the exact first authority where identity becomes unresolved.

Required classification for each side:

```text
RECOVERABLE_EXISTING_IDENTITY_NOT_PROJECTED
CROSSWALK_COMPETITION_ALIAS_MISMATCH
CROSSWALK_SEASON_MISMATCH
CROSSWALK_VALIDITY_WINDOW_MISMATCH
CROSSWALK_REVIEW_NOT_READY
CANONICAL_TEAM_MISSING
CANONICAL_CHINESE_LABEL_MISSING
PROVIDER_TEAM_ID_MISSING
GENUINELY_UNRESOLVED
```

No Provider calls and no public fallback to guessed or raw English names are allowed.

## SC19-02 — Restore canonical public team identity without weakening fail-closed policy (P0)

Repair the persisted/read-model identity path proven by SC19-01.

Binding rules:

- do not revert SC18-05's prohibition on silently treating raw Provider English names as successful localization;
- if reviewed canonical identity and an approved Chinese public name already exist, the public workspace MUST render them;
- if a recoverable existing mapping is missed because of fixture-id form, competition alias, season key, or projection/materialization mismatch, fix that authority join deterministically;
- do not auto-create canonical IDs from provider IDs;
- do not invent Chinese translations;
- genuinely unresolved identities remain explicit auditable gap states;
- preserve raw Provider name only in collapsed technical evidence.

Acceptance for the currently retained football day:

```text
NO_RECOVERABLE_TEAM_IDENTITY_MAY_RENDER_GENERIC_PLACEHOLDER
PUBLIC_NAME_SOURCE_IS_CANONICAL_REVIEWED_AUTHORITY
RAW_ENGLISH_IS_TECHNICAL_ONLY
IDENTITY_GAPS_REMAIN_MEASURABLE
```

Update the existing public-label coverage matrix/report after remediation.

## SC19-03 — Persisted football-day date-strip contract (P1, only after SC19-01/02 local PASS)

Add one read-only date-strip projection sourced only from already persisted fixture/read-model data.

Data contract target:

```text
window_default = T-7 through T+7 around the selected football day
one entry per Asia/Shanghai 12:00→12:00 football day
fields:
  football_day
  fixture_count
  competition_count
  finished_fixture_count
  upcoming_fixture_count
  persisted_inventory_status
  persisted_competition_coverage_count
  active_whitelist_count = 13
  market_collection_window_status
  market_evidence_fixture_count
  display_state
```

No Dashboard date-strip read may call Provider or write business data.

The date-strip must not claim complete 13-league future coverage unless the persisted inventory actually proves it. Current future/matchday policies may cover fewer than all 13 competitions, so use truthful wording such as `当前已知赛程` / `已持久化赛程`, and expose coverage metadata where needed.

## SC19-04 — Future-day market semantics and next-known-matchday (P1)

Do not classify every future fixture without odds as `证据不足`.

Derive the label from persisted timing/plan evidence:

```text
fixture exists + no market evidence + first relevant odds collection checkpoint is still in the future
=> 未进入市场采集窗口

fixture exists + relevant market collection checkpoint is due/past + no usable market evidence
=> 市场证据未就绪

fixture has persisted usable market evidence
=> 市场证据可用 / 已观测
```

Do not hard-code a Provider plan assumption such as a universal T+1 odds window; use the existing persisted checkpoint/schedule authority.

For an EMPTY day, replace `下一有赛日 尚未确认` only when the date-strip has a later persisted day with `fixture_count > 0`:

```text
next_available_date = first later persisted football_day with fixture_count > 0
```

If future inventory coverage is partial or no later persisted fixture is known, say `当前持久化范围内尚未确认`, not a fabricated date.

## SC19-05 — Date-strip UX (P1)

Desktop/13-inch design:

- data contract covers 15 days by default (`T-7..T+7`);
- UI may show a responsive 7-day slice with left/right controls and the selected day centered when practical;
- each cell shows date + fixture count + concise state;
- past terminal days: `已完场` when supported by persisted statuses;
- selected current day: `今天` / `当前`;
- future persisted fixtures outside collection window: `赛程 · 未进入市场采集窗口`;
- future due/past collection with missing evidence: `市场证据未就绪`;
- empty persisted day: `0 场`;
- click uses the existing single selected-day read path only.

Do not create 15 parallel API requests and do not call Provider from browser/date navigation.

## SC19-06 — Regression and truth tests (P1)

Mandatory cases:

```text
# team identity
finished fixture retained after FT + reviewed canonical team mapping exists
=> Chinese public team name remains visible

fixture status overlay
=> may change status only; cannot erase team identity/name fields

canonical identity ready + Chinese label missing
=> explicit 译名待映射, not raw English success

identity unresolved
=> explicit 身份待映射, raw name technical only

# date strip
15-day contract uses Asia/Shanghai 12→12 football-day boundaries
Dashboard read => provider_calls=0, db_writes=0
future fixture outside persisted market checkpoint window => 未进入市场采集窗口
missing evidence after due checkpoint => 市场证据未就绪
empty day next-known date derives only from persisted fixture inventory
partial competition coverage is not presented as complete 13-league inventory
no other-date fixture is inserted into selected empty day
```

Also preserve finished-fixture replay/card retention from SC18-00.

## SC19-07 — Full verification, merge and deployment

After SC19-01..06 pass:

1. focused/full Python;
2. Ruff + MyPy;
3. Web typecheck/build/full E2E;
4. real-shape visual checks at 1366x768 and 1512x982, including date strip and team labels;
5. public label coverage gate;
6. secret/tracked-output/protected-evidence/repository hygiene;
7. exact-head Full CI + `RELEASE_REQUIRED`;
8. automatic merge;
9. deploy only via Owner-local OCI relay;
10. verify Web/API exact identity, health/ready/release sync;
11. live verify retained finished fixtures show recoverable canonical team names and date strip uses persisted-only inventory;
12. verify Dashboard read `provider_calls=0`, `db_writes=0`, `no_call_on_read=true`;
13. update context and Round4 exact release identity only;
14. stop at `OWNER_SC19_POSTDEPLOY_REREVIEW`.

Ordinary implementation/test/CI/deployment-preparation failures are in scope: `fix -> revalidate -> continue`.

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
RAW_PROVIDER_ENGLISH_AS_LOCALIZED_SUCCESS = FORBIDDEN
```