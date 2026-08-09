# Dashboard Owner Visual Parity + zh-CN Remediation

```text
AUTHORITY = W2_DASHBOARD_OWNER_VISUAL_PARITY_ZH_CN_REMEDIATION_V1
OWNER_DATE = 2026-08-09
OWNER_DECISION = CHANGES_REQUIRED
BASE_MAIN = d61768ecf8457a72df80a5cb0220072de76dfdd4
DEPLOYED_SOURCE = d61768ecf8457a72df80a5cb0220072de76dfdd4
CURRENT_PRE_ROUND4_SCOPE = FUNCTIONALLY_COMPLETE_BUT_OWNER_VISUAL_UX_NOT_ACCEPTED
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
```

## Owner finding

The deployed unified Intelligence Workspace is functionally correct but does not satisfy Owner visual fidelity or primary-language usability.

Two Owner-provided screenshots establish the comparison:

- current deployed Workspace: long vertically stacked English-heavy page;
- approved target direction: compact dark 1536x1024 decision console with left navigation, compact top status bar, top three information cards, match board + selected-match center + model lab middle row, and validation/league performance bottom row, predominantly Chinese.

The target is NOT authority to restore obsolete Boss/recommendation semantics. It is visual/composition/language authority only.

## Existing repo visual authority to reuse

Use these existing repo assets as implementation references for layout/fidelity mechanics only:

```text
docs/ui/boss-console/w2_boss_decision_console_prototype.html
docs/ui/boss-console/golden/v2.1/reference/
docs/ui/boss-console/golden/v2.1/actual/
docs/ui/boss-console/golden/v2.1/diff/
docs/ui/boss-console/design-qa.md
```

The prior QA proved source-to-React pixel fidelity at desktop/mobile. Reuse its grid density, typography scale, spacing, borders, panel system, internal scrolling, responsive behavior, and visual regression method.

DO NOT restore obsolete Boss L1/L2 product authority, recommendation-first semantics, public EV/CLV/ROI, market opportunity language, old lock authority, or deleted legacy public routes.

## Product semantics that remain frozen

The final product remains the unified `w2.dashboard-intelligence-workspace.v1` public authority and consumes only the existing unified endpoint.

Preserve:

- exact seven intelligence states;
- exact four risk axes;
- Market Fact / W2 Analysis / Validation / Formal Recommendation boundary;
- Formal/Candidate/Lock/Production OFF;
- `MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY`;
- no public ROI/CLV/edge/value/profit/betting-worthiness claims;
- real persisted market timeline only; no interpolation or synthetic signals;
- scoreline Top 3 10,000-simulation semantics;
- External Intelligence `NOT_CONNECTED` truthfulness;
- exact 13-league whitelist;
- no-call-on-read;
- replay/validation semantics already accepted.

## P0 visual composition target — desktop

At exact `1536x1024`, the first viewport must read like the Owner target design, not a documentation page.

Required composition:

```text
LEFT SIDEBAR
  product logo/name
  Chinese navigation
  compact data-source health

TOP BAR
  W2 Intelligence
  13 leagues
  SHADOW_ONLY
  Candidate/Formal/Lock/Production OFF
  data update time
  provider quota when source-bound
  health

ROW 1
  Attention Feed      | Market Radar       | External Intelligence

ROW 2
  Match Board         | Selected Match     | Model Lab
                      | W2 Analysis         | Scoreline Top 3

ROW 3
  Validation / Forward Validation          | League Performance

BOTTOM STATUS BAR
  source / timezone / market reference / release identity
```

The primary desktop workspace should fit the key decision surfaces within one viewport. Use internal panel scrolling for lists rather than turning the whole page into a long vertical stack.

At 1536x1024, the user must immediately see at minimum:

- Attention summary;
- Market Radar;
- External status;
- 5+ match rows;
- selected match and main market line;
- W2/model/market relationship;
- Model Lab;
- Scoreline Top 3 when available or truthful unavailable state;
- Validation summary;
- League Performance summary;
- data/system health.

Do not require page scrolling to discover these primary surfaces.

## Chinese-first public UI contract

Primary public UI language is `zh-CN`.

Every visible navigation label, panel title, explanatory sentence, state badge, risk label, readiness phrase, reason summary, market label, time/date label, empty state, health state and button must be understandable in Chinese.

Reuse and extend existing helpers instead of creating duplicate translation systems:

```text
apps/web/src/lib/formatters.ts
translateTeam()
translateCompetition()
translateReason()
apps/web/src/lib/labels.ts
```

Examples of required primary presentation:

```text
Attention                  -> 关注情报
Match Board                -> 今日比赛
Market Radar               -> 市场雷达
Model Lab                  -> 模型实验室
Validation                 -> 赛后验证
Forward / Replay           -> 前向记录 / 回放
External                   -> 外部情报
Data & Ops                 -> 数据与系统

DATA_INCOMPLETE            -> 数据不完整
COLLECTION_INCIDENT        -> 采集异常
MODEL_DIAGNOSTIC_WARNING   -> 模型诊断警告
MARKET_ANOMALY             -> 市场异常
MODEL_MARKET_DISAGREEMENT  -> 模型与市场分歧
MARKET_MOVEMENT            -> 盘口变化
MARKET_STABLE              -> 市场稳定

DATA_IDENTITY_NOT_READY        -> 身份映射未就绪
DATA_MARKET_TIMELINE_INSUFFICIENT -> 盘口时间线证据不足
DATA_REQUIRED_INPUT_MISSING    -> 缺少必要输入
DATA_STATUS_BLOCKED            -> 数据状态阻塞
MODEL_SIMULATION_NOT_READY     -> 模型模拟未就绪
```

Canonical enum/reason codes may remain available in a secondary `技术详情`/tooltip/debug layer for auditability, but raw underscore codes must not dominate the primary screen.

`Intl.DateTimeFormat` for public presentation must use `zh-CN` and the approved product timezone semantics.

Team and competition names should use existing translation maps where available. Unknown names may fall back truthfully to source names; do not fabricate translations. Expand mappings only for verified source identities needed by the active 13 leagues/current real fixtures.

## Information-density rules

The Owner target is an executive intelligence console, not a raw contract dump.

Required:

- Attention: show ~5 highest-priority items in the primary card; `查看全部` exposes the rest.
- Match Board: compact rows, internal scroll; support current 16 and future 15/30 volumes without page growth.
- Reason codes: synthesize a short Chinese factual summary; put exhaustive codes under details.
- Selected match must be visually central and larger than generic diagnostic panels.
- Market Radar should use compact factual micro-trends/point path only from real persisted snapshots.
- External Intelligence is a compact four-card status area.
- Validation/league tables use compact numeric hierarchy.
- Avoid giant cards with excessive blank space.
- Avoid uppercase/monospace canonical code as primary typography.

## Visual fidelity rules

Preserve the Owner target visual language:

- dark navy/near-black cockpit;
- compact left rail;
- thin low-contrast borders;
- dense card grid;
- small status chips;
- restrained blue/green/amber/red semantic accents;
- selected match row with clear accent;
- no oversized rounded SaaS cards;
- no large documentation-style headings;
- Chinese information hierarchy optimized for scanning.

Implement from the existing repo source visual/golden methodology rather than approximating from memory.

## Responsive targets

Mandatory deterministic visual tests:

```text
1536x1024  PRIMARY OWNER VIEW
2048x1084  CURRENT OWNER SCREEN CLASS
1920x1080
1440x900
1366x768
390x844
```

Desktop primary surfaces should remain dashboard-like; mobile may stack naturally.

## Acceptance tests

### Language

- no primary navigation English;
- no raw canonical state code as primary badge text;
- no raw reason-code wall in primary Attention rows;
- no `TIME_NOT_AVAILABLE`, `NO_REASON_CODE`, `NOT_AVAILABLE` as the only user-facing explanation when a Chinese mapped phrase exists;
- team/competition translations reused where available;
- technical canonical codes remain accessible in secondary detail only.

### Layout

- 1536x1024 first viewport contains the required primary surfaces;
- no whole-page vertical stacking of all primary modules on desktop;
- Attention and Match Board use bounded internal scrolling;
- no horizontal viewport overflow at desktop targets;
- selected match remains central and visible;
- Validation and League Performance are visible in the first 1536x1024 composition.

### Semantics

- unified endpoint only;
- no legacy fallback;
- seven-state/four-risk contracts unchanged;
- no forbidden ROI/CLV/EV/opportunity semantics;
- Formal/Candidate/Lock/Production OFF unchanged;
- no Provider calls or writes caused by UI reads;
- no scheduler/cadence/whitelist/model/threshold changes;
- no Round4 changes.

### Visual regression

Produce committed deterministic screenshots for all required viewports plus visual-diff evidence against the repo-bound visual composition reference where applicable. The Owner-provided screenshot remains the final subjective visual authority; do not claim exact pixel equality to an unavailable chat binary.

## Execution model

One continuous implementation task is authorized through technical acceptance. Ordinary in-scope visual/test/localization failures are self-remediated without Owner relay.

Use one Draft PR. Do not merge/deploy until the final implementation has:

- TypeScript PASS;
- Web build PASS;
- full Web E2E PASS;
- focused localization assertions PASS;
- deterministic screenshot/regression PASS;
- existing backend/unit/contract gates affected by the change PASS;
- Exact-head Full CI + RELEASE_REQUIRED PASS;
- Repository Hygiene PASS.

After technical PASS, auto-approve/merge is allowed because this authority contains the Owner's explicit visual/language product decision and no new runtime authority is introduced. Then deploy through the frozen `LOCAL_OCI_RELAY_PRIMARY` path and perform postdeploy visual smoke at the exact approved main.

## Terminal target

```text
DASHBOARD_OWNER_VISUAL_UX_ACCEPTANCE_PASS
```

Round4 remains `NOT_STARTED` until this remediation is complete.

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
