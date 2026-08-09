# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_DASHBOARD_IA_DESIGN_FREEZE
CURRENT_GATE = DASHBOARD_IA_DESIGN_FREEZE_ACTIVE
AUTHORITY = DASHBOARD_OWNER_INFORMATION_ARCHITECTURE_RESET.md
BASE_MAIN = d2740a573c748cfaef38c66e951618e8782e09d0
PR_505 = MERGED_DEPLOYED_TECHNICAL_TRUTH_PASS_PRODUCT_UX_REVOKED
TRACK_A = TRACK_A_CLOSED_PASS
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
CURRENT_PHASE = DESIGN_ONLY
TERMINAL_GATE = OWNER_DASHBOARD_IA_DESIGN_REVIEW
```

## Binding correction

Do not open another incremental Dxx production-UI patch round on the current layout.

The current Dashboard truth contract is substantially improved, but the deployed page remains a long technical report with the wrong default focus and no frozen product-level visual target. The next task is to freeze the information architecture and target screen before touching production React/CSS again.

## Binding read order

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. DASHBOARD_OWNER_INFORMATION_ARCHITECTURE_RESET.md
5. current deployed/main Dashboard screenshots and real payload shape
6. Owner-provided compact cockpit reference / repo-bound composition reference
7. D13/D14/D15 truth contracts and accepted tests
```

## Stage A — execute continuously

1. Inspect current real production screenshots/data shape and current UI/component/CSS structure.
2. Produce the new information architecture around:
   `今日摘要 -> 优先短名单 -> 所选比赛情报 -> 诊断上下文`.
3. Create an editable design source. Figma is preferred if available; a repo-bound static HTML prototype is acceptable.
4. Create `REAL_SHAPE_DASHBOARD_DESIGN_FIXTURE.json` representing a realistic mixed day: several blocked matches plus at least one evidence-rich fixture with real 2+ snapshot/market-memory shapes. Also create a degraded/blocked-day design state.
5. Create repo-bound target screenshots at exactly 1280x720, 1512x982 and 1536x1024.
6. Create `DASHBOARD_IA_DESIGN_SPEC.md` defining layout, hierarchy, default-focus policy, typography, contrast, component behavior and secondary-view boundaries.
7. Create `DESIGN_REVIEW_PACKET.md` mapping every current Owner/Claude finding to the frozen target.
8. Include the remaining semantic cleanup in the design contract: dimension-specific risk reasons, league status matching the actual only-record blocker, and one model-unavailability explanation authority.
9. Do not change production React/CSS/read-model behavior during Stage A.
10. Do not deploy Stage A.

## Non-negotiable product rules

```text
DEFAULT_SELECTION = NOT_MATCHES_ZERO
DEFAULT_SELECTION = MOST_USEFUL_SOURCE_BOUND_EVIDENCE_NOT_BETTING_VALUE
FIRST_SCREEN = BOUNDED_DASHBOARD_NOT_LONG_REPORT
EMPTY_NOT_CONNECTED_TECHNICAL_SECTIONS = SECONDARY_BY_DEFAULT
GOVERNANCE_STATUS = ONE_COMPACT_SYSTEM_ENTRY_NOT_REPEATED_EVERYWHERE
PUBLIC_BODY_TEXT >= 13PX
SECONDARY_TEXT >= 12PX
VISIBLE_TECHNICAL_TEXT >= 11PX
NORMAL_TEXT_CONTRAST >= 4.5_TO_1
DATES_AND_MATCH_NAMES = NO_AVOIDABLE_TRUNCATION
1280x720 = USABLE_FIRST_SCREEN
200_PERCENT_ZOOM = USABLE
KEYBOARD_FOCUS_ORDER = MATCHES_VISUAL_HIERARCHY
```

## Visual quality gate

The existing same-render screenshot equality test is only a determinism check and cannot be treated as visual acceptance.

Stage B will require a stored approved target and real image-diff/`toHaveScreenshot`-style regression. The deterministic test data must use the same default-focus rule as production.

## Stop

Stop after all Stage-A artifacts are committed and coherent at:

```text
OWNER_DASHBOARD_IA_DESIGN_REVIEW
```

Do not implement the production redesign, merge production UI changes, deploy, start Round4 or enter P6 before that design gate is cleared.

## Frozen stop lines

```text
PRODUCTION_UI_IMPLEMENTATION_BEFORE_DESIGN_FREEZE = FORBIDDEN
VPS_DEPLOYMENT_STAGE_A = FORBIDDEN
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
```
