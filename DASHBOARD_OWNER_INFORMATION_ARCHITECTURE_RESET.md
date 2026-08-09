# Dashboard Owner Information Architecture Reset

```text
AUTHORITY = W2_DASHBOARD_OWNER_INFORMATION_ARCHITECTURE_RESET_V1
OWNER_DATE = 2026-08-10
OWNER_DECISION = DESIGN_RESET_REQUIRED
BASE_MAIN = d2740a573c748cfaef38c66e951618e8782e09d0
PR_505_TECHNICAL_TRUTH_RESULT = PASS_RETAINED
PR_505_PRODUCT_UX_ACCEPTANCE = REVOKED
TRACK_A = TRACK_A_CLOSED_PASS
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
CURRENT_PHASE = IA_DESIGN_FREEZE_ONLY
TERMINAL_GATE = OWNER_DASHBOARD_IA_DESIGN_REVIEW
```

## Why this reset is required

The current Dashboard now has substantially improved source truth, read-only discipline, market-memory semantics, canonical league identity, stale-evidence behavior and 13-inch responsiveness. Those technical truth improvements are retained.

However, real Owner inspection proves that the page is still organized as a long technical report rather than a decision-oriented football intelligence dashboard. Continuing to add Dxx point fixes to the current composition would preserve the wrong information architecture and increase CSS/UI patch layering.

This authority therefore stops incremental layout patching and freezes a new product hierarchy before any further production implementation.

## Confirmed evidence from current main

1. The backend still sets `selected_fixture_id = matches[0].fixture_id`.
2. The frontend still falls back to the first match.
3. The E2E layout fixture selects the last match, which is typically the richer-data fixture. Therefore test-default and real-default states are materially different.
4. The deterministic visual test compares two screenshots of the same render; it proves stability, not usability or fidelity to an approved target.
5. `intelligence.css` contains later Owner-remediation overrides over earlier layout/overflow rules, including natural-flow overrides and breakpoint rewrites. Further append-only patching is forbidden.
6. Primary Dashboard hierarchy currently gives comparable prominence to Attention, Market Radar, Match Board, selected-match details, External Intelligence, Model Lab, Scoreline, Validation, League Performance, History/Replay and Data/Ops.
7. System-governance states are repeated in header/sidebar/footer/detail surfaces and visually compete with football intelligence.

## Product hierarchy to freeze

The new Dashboard must answer, in order:

```text
1. 今天发生了什么？
2. 哪几场最需要我看？
3. 当前选中比赛的市场证据是什么？
4. W2 对这场比赛能说什么、不能说什么？
5. 当前最大的阻塞是什么？
6. 验证/系统/外部情报的详情在哪里查看？
```

This is an intelligence-review hierarchy, not a betting recommendation hierarchy.

Forbidden public semantics remain unchanged: no opportunity/value/edge/profit/betting-worthiness/bookmaker-intent/real-volume claims.

## Required first-screen architecture

At 1280x720 and 1512x982, the first screen must be a bounded dashboard, not a long report.

### Zone A — Today Summary

Compact top strip, maximum one row plus optional second compact line:

- football day/date and boundary;
- number of matches;
- number of Attention groups;
- market-evidence summary such as fresh/stale/insufficient counts;
- system degradation only when it materially blocks interpretation;
- one compact `系统状态` entry for governance/read-contract details.

Do not permanently repeat Candidate/Formal/Lock/Production/Provider/read-contract badges across multiple first-screen locations. Those controls remain true but move behind the system-status drawer/details surface, with one concise immutable-mode indicator on the first screen.

### Zone B — Priority Shortlist

Primary left rail/list containing 3–6 prioritized fixtures/groups, not a duplicate of the full match list.

Ordering is for review priority only, never betting attractiveness.

Priority must be deterministic and source-bound. Recommended hierarchy:

1. explicit Collection/Data/Model incidents requiring review;
2. fresh market movement supported by visible line/price evidence;
3. fresh 2+ snapshot market evidence with available model comparison;
4. stale Market Memory requiring awareness;
5. remaining fixtures.

Each row must state why it is in the shortlist.

Full match list is accessible but secondary.

### Zone C — Selected Match Intelligence

The center/primary workspace. It must include in one coherent hierarchy:

- fixture identity, league, kickoff;
- one public readiness/state summary;
- AH/OU current market evidence with freshness;
- real movement evidence when present;
- compact W2 model/readiness statement;
- the three most important blockers/reasons;
- Scoreline Top 3 only when truly ready;
- a clear action affordance for deeper diagnostics.

Do not spread one match across several equal-weight panels that repeat the same state.

### Zone D — Context / Diagnostics

Right-side or secondary compact area:

- Market comparison/model relation;
- risk dimensions with dimension-specific reason text;
- compact validation signal if meaningful.

External Intelligence, full League Performance, History/Replay and Data/Ops are secondary views/drawers/tabs, not permanent first-screen blocks when they are empty/not-connected/technical.

## Default selected fixture policy

`matches[0]` is forbidden as the product selection policy.

Create a deterministic `default_focus_fixture_id` / equivalent source-bound selection using **evidence usefulness**, not betting value.

Minimum ranking inputs may include only existing fields:

```text
market evidence status: READY > STALE > INSUFFICIENT
timeline depth: 2+ > 1 > 0
real movement with visible evidence
model comparison availability
scoreline readiness
intelligence-state review severity
kickoff time
fixture id deterministic tie-break
```

The rule must never use EV, value, opportunity or recommendation semantics.

If any fixture has fresh 2+ snapshot market evidence, a zero-evidence fixture must not be the default focus unless a higher-precedence collection/system incident explicitly makes it the primary day-level incident; in that case the page must visibly explain why the incident is the default focus.

The same default-selection policy must be used by deterministic E2E data and real production data.

## Remaining semantic cleanup to incorporate in the new design

These are not separate patch rounds. They must be solved inside the redesigned component contract.

### Risk explanation authority

Do not render generic repeated `需要复核相关证据` for several dimensions.

Each risk dimension must display a dimension-specific source-bound explanation/reason, using the existing risk reason codes/explanation. Example intent:

```text
数据风险 -> 数据字段已过期 / 身份映射未就绪
模型风险 -> 模型校准未就绪 / 模型输入不足
采集风险 -> Provider 返回空 / 采集证据过期 / 未评估
事件风险 -> 阵容/伤停/事件证据
```

Do not fabricate a reason when source evidence is absent.

### League public status

The public status must match `only_record_reason`.

Do not show `样本积累中` when the actual blocker is `PROBABILITY_QUALITY_NOT_READY`.

Use distinct public meanings such as:

```text
样本不足
概率质量待就绪
聚合冲突
可用
```

Stored/source statistical status remains available in technical detail.

### Unified model unavailability reason

W2 Analysis and Model Lab must use one display authority for model status + explanation.

Do not show the same `不可用` object with `暂无` in one panel and `版本待确认` in another. Derive one source-bound public model status detail and reuse it everywhere.

## 13-inch readability/accessibility contract

At 1280x720 and 1512x982:

- primary body text >= 13 CSS px;
- secondary explanatory text >= 12 CSS px;
- technical/audit text >= 11 CSS px when visible;
- normal text contrast >= 4.5:1 against its background;
- dates/times and match names must not be truncated when space exists elsewhere;
- no horizontal page overflow;
- keyboard focus order must follow visual hierarchy;
- 200% browser zoom must remain usable without losing primary actions/data;
- technical codes/schema/checkpoints must never visually outrank football conclusions.

## Design-source requirement

Before production React/CSS implementation, create a frozen design authority.

Preferred workflow:

```text
Owner/reference screenshots
+ current truthful production data shape
-> Figma or repo-bound static HTML prototype
-> repo-bound PNG screenshots
-> DASHBOARD_IA_DESIGN_SPEC.md
-> deterministic real-shape fixture JSON
```

Figma is optional as an editing tool; repository-bound PNG + spec + fixture are mandatory authority so implementation and tests cannot drift from an external file.

Required design screenshots:

```text
1280x720
1512x982
1536x1024
```

At least two data states must be designed:

1. mixed real day with one evidence-rich fixture and several blocked fixtures;
2. degraded/blocked day with little or no fresh market evidence.

The target must reuse the Owner-approved compact dark cockpit visual language without restoring obsolete Boss/EV/recommendation semantics.

## Visual acceptance must change

The current same-render screenshot equality test may remain as a determinism check but is insufficient as a visual quality gate.

The implementation phase must eventually use an approved stored target with a real visual regression mechanism such as Playwright `toHaveScreenshot` / image-diff baseline or equivalent.

The deterministic fixture used for visual acceptance must reproduce realistic production data shape, including blocked fixtures and at least one evidence-rich fixture. Do not select a prettier fixture only in the test unless the same product default-selection policy would select it in production.

## CSS/component architecture requirement

Do not append another remediation block to the end of `intelligence.css`.

The implementation phase must refactor the layout rather than layer overrides. Recommended target:

```text
workspace-shell
workspace-summary
priority-shortlist
selected-match-intelligence
context-diagnostics
secondary-views
```

CSS may be split into layout/components/tokens or comprehensively rewritten. Remove superseded selectors and contradictory overflow/height rules instead of overriding them later.

## Stage A — authorized now: Design Freeze only

Authorized work:

- inspect current real screenshots/data and existing Owner composition reference;
- define the new information architecture;
- create Figma or static HTML prototype;
- create repo-bound design PNGs at required viewports;
- create realistic deterministic fixture JSON;
- create `DASHBOARD_IA_DESIGN_SPEC.md`;
- create a design review packet that maps each Owner complaint to the new target;
- no production React/CSS/read-model behavior changes;
- no deployment.

Terminal result for Stage A:

```text
OWNER_DASHBOARD_IA_DESIGN_REVIEW
```

This is a product/visual gate, not a routine technical approval. Do not auto-merge implementation code before this design authority is frozen.

## Stage B — not yet authorized

After design freeze, implementation will be authorized separately to:

- implement the frozen target;
- introduce deterministic default-focus selection;
- consolidate repeated states;
- refactor CSS/component structure;
- add true target-image regression;
- preserve all D13/D14/D15 truth semantics;
- full CI then local OCI relay deployment and real-device verification.

## Permanent stop lines

```text
PRODUCTION_UI_IMPLEMENTATION_BEFORE_DESIGN_FREEZE = FORBIDDEN
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
VPS_DEPLOYMENT_FOR_STAGE_A = FORBIDDEN
```
