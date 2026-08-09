# Dashboard Owner 13-inch Truth & Readability Remediation

```text
AUTHORITY = W2_DASHBOARD_OWNER_13IN_TRUTH_READABILITY_REMEDIATION_V1
OWNER_DATE = 2026-08-09
OWNER_DECISION = CHANGES_REQUIRED_BOUNDED
BASE_MAIN = 62cf3efc6676d23688c3b6268ca822025b3c9148
PR_501 = MERGED_BUT_OWNER_UX_ACCEPTANCE_REVOKED
PR_501_HEAD = da280c54d93d3ac6b0041e7e543f441c61542a62
PR_501_CONTEXT = 24b6b8a5174c755ef5688c79aaa6be549ce1c5f0
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
TARGET = DASHBOARD_OWNER_13IN_TRUTH_READABILITY_ACCEPTANCE_PASS
```

## Owner decision

The technical and deployment acceptance of PR #501 remains valid, but its claimed `DASHBOARD_OWNER_VISUAL_UX_ACCEPTANCE_PASS` is revoked as a final Owner UX/truth verdict.

Owner real-device inspection on a 13-inch laptop exposed both readability failures and public-data interpretation defects. Functional correctness and screenshot no-overflow checks are not sufficient Owner acceptance.

This task is a bounded Dashboard/read-model presentation remediation. It does **not** authorize Round4, Provider changes, Scheduler/cadence changes, model/factor/threshold retraining, Candidate/Formal/Lock/Production enablement, external-intelligence activation, Phase 0.5 rerun, or real-money authority.

## Evidence-backed root causes

1. Current desktop CSS intentionally uses many 6–9 px labels/values and keeps a three-column cockpit through the `max-width: 1180px` range. On a 13-inch laptop this is technically responsive but practically unreadable.
2. `LeaguePerformance` renders `translateCompetition(league.league)`, while the read adapter currently passes the performance checkpoint `competition_id` as `league`; provider IDs such as `1` and `103` therefore remain numeric.
3. `next_eval_at` is rendered as `下次评估` without checking whether it is already earlier than the workspace `generated_at`/current read time.
4. Validation always renders directional accuracy even when Brier/LogLoss/calibration evidence is unavailable.
5. Forward-ledger exclusion-reason data already exists in the persisted performance projection, but the unified workspace adapter does not expose it.
6. Model Lab joins duplicate market statuses directly, producing copy such as `证据不足 · 证据不足`.
7. Scoreline eyebrow always says `10,000 次既有模拟` even when scoreline status is unavailable.
8. Provider budget falls back to canonical `UNKNOWN`; the public UI does not distinguish `not read by read-only design` from `read failed`.
9. `ADVISORY`, `MARKET_NOT_READY`, `IDENTITY_NOT_READY` and related canonical enums can still leak into primary copy when localization maps do not contain them.
10. Native `input[type=date]` displays locale-dependent `DD/MM/YYYY`, conflicting with ISO date elsewhere.
11. Sidebar stacks system health and provider-budget status without separate labels.
12. Fixed cockpit rows, sticky header and nested scroll regions can produce clipping/overlap or covered content at certain viewport heights/scroll positions.

## Severity and required remediation

### P0 — conclusion trust / readability

#### D13-01 — League identity must be resolved

Public league rows must show a canonical league name, never a bare numeric provider league ID.

Use existing persisted/runtime identity authority, preferably `CompetitionRegistry` / provider mapping, or another already-authoritative competition identity source. Do not invent ad-hoc ID-name guesses.

Requirements:

- provider league IDs such as `1`, `103` are resolved to canonical W2 competition identity and user-facing league name;
- Chinese translation may be applied after canonical identity resolution;
- unresolved identity must fail closed as `联赛名称待解析（ID: ...）`, never display only the number and never silently map incorrectly;
- table row count must equal the payload league row count;
- the panel heading must distinguish `有验证样本的联赛 N` from the 13-league active whitelist;
- on common laptop viewports, enough rows must be visible to make the table useful, with an obvious scroll affordance when additional rows exist.

#### D13-02 — Past `next_eval_at` cannot be labelled “next”

Compare `next_eval_at` against the workspace `generated_at` (and, when safely available in the client, current page time). If the source timestamp is not in the future:

- do not show `下次评估 <past time>`;
- display `评估时间已过期` / `暂无未来评估时间` with the source time available in technical details;
- keep the source value unchanged for audit;
- do not alter Scheduler/cadence or invent a new next-eval timestamp.

Add a deterministic stale-next-eval test.

#### D13-03 — Public statistical readiness must fail closed

Current tracking code has `MIN_DECISIVE_SAMPLES_FOR_RATE = 5`; this task must **not** silently change the model/tracking threshold or retrain anything.

However, public Dashboard `可用` status and a precise directional percentage must not be promoted solely because the upstream rate gate says `AVAILABLE` when primary probability-quality evidence is absent.

Public display-readiness rule:

- probability quality remains primary;
- league/global directional accuracy is secondary;
- `AVAILABLE` in the public Dashboard requires source statistical availability **and** sufficient primary probability-quality evidence for the same displayed cohort (at minimum the required Brier/LogLoss/calibration readiness supported by the checkpoint contract);
- otherwise downgrade public display state to `样本积累中` / `证据不足` without changing the underlying stored tracking status;
- an `effective_n=5`, `80.0%`, blank Brier/calibration row must not appear as an authoritative `可用 80.0%` result.

Do not introduce a new arbitrary numeric sample threshold. If no existing approved statistical threshold supports a stronger numeric gate, use the evidence-readiness rule above and keep the raw source status in technical details.

#### D13-04 — Probability-primary degradation rule

When W2 Brier / market Brier / LogLoss / calibration evidence needed by the probability panel is unavailable or not ready:

- directional accuracy must not be the only dominant numeric KPI;
- hide it or render it clearly muted/secondary with `概率质量证据不足，方向指标仅作样本记录`;
- do not let `78.6%` visually imply validated model quality while primary probability metrics are all `—`;
- preserve raw directional counts/effective N in technical details or secondary sample context.

Add positive and negative E2E cases.

#### D13-05 — Exclusion explainability

The persisted performance projection already carries exclusion-reason distributions (for example `validation_excluded_by_reason` / `canonical_excluded_by_reason`). The unified workspace currently discards them.

Expose the existing source-bound exclusion distribution through the unified read model without Provider calls, without business writes, and without fabrication.

When excluded count is nonzero, public validation must show:

- included/eligible count;
- excluded count and exclusion share;
- top exclusion reasons with counts (Chinese-primary labels, canonical code in technical detail);
- pending count separately.

For the observed `56 validation / 16 eligible / 40 excluded` cohort, the UI must make the 71% exclusion visibly interpretable before showing secondary directional accuracy.

#### D13-06 — 13-inch responsive readability

Readability has priority over forcing every primary panel into one screen.

Required behavior:

- large desktop may keep the dense 3-column cockpit;
- typical 13-inch logical viewports must reflow/reallocate space instead of shrinking primary text to 6–9 px;
- at smaller desktop/laptop widths, switch to 2-column or other readable layout before text becomes tiny; moving the sidebar to a compact/top navigation is allowed;
- primary body/value text must be practically readable without browser zoom; target >= 12 px minimum, preferably 13–14 px for primary values/rows;
- secondary public labels should generally be >= 10–11 px;
- only collapsed technical/audit details may use smaller text;
- do not require “all panels above the fold” on 13-inch screens if that conflicts with readability;
- match/attention tables may use internal scrolling, but scrollbars/affordances must be obvious and text must remain readable.

Add deterministic responsive acceptance for at least:

```text
1280x720
1280x800
1366x768
1440x900
1512x982
1536x1024
1920x1080
```

The acceptance must assert more than `no horizontal overflow`: verify minimum computed font sizes on representative primary text and verify intended reflow/column count.

#### D13-07 — No overlap / sticky-cover defects

At each required viewport and at top/mid/lower scroll positions:

- panel bounding boxes must not overlap;
- sticky header must not cover panel headings/content;
- nested scroll regions must not escape their containers;
- no floating orphan metric cards;
- selection/scroll state must not break grid geometry.

### P1 — rendering / consistency

#### D13-08 — Deduplicate repeated statuses

If AH and OU share the same Market/Model status, render one human-readable summary plus market-specific detail, not `证据不足 · 证据不足`.

#### D13-09 — Scoreline heading must match readiness

Only display `10,000 次既有模拟` when:

```text
scoreline.status == READY
AND simulations_completed == 10000
```

Otherwise use a neutral heading such as `比分参考`, state why unavailable, and keep canonical reason/simulation count in technical details. Never claim an existing 10,000 simulation artifact when the current fixture has no usable scoreline projection.

#### D13-10 — Provider budget UNKNOWN semantics

Dashboard read must remain `provider_calls=0`.

If no source-bound quota/budget status was read for this checkpoint, public UI must say `额度未读取（只读页面不查询 Provider）` or equivalent, not bare `UNKNOWN`.

If a persisted quota status is already available, display that persisted status. Do not make a Provider call merely to populate the Dashboard.

Canonical `UNKNOWN` may remain in technical details.

#### D13-11 — Canonical enums stay secondary

Add Chinese primary labels for `ADVISORY`, `MARKET_NOT_READY`, `IDENTITY_NOT_READY` and every canonical enum/reason that can reach current primary surfaces.

Acceptance: primary UI text outside collapsed technical details must not contain raw uppercase underscore enums or English status phrases such as `MARKET NOT READY`, `IDENTITY NOT READY`, `ADVISORY`, `INCIDENT`, except immutable product/technical identifiers explicitly approved for display (`W2 INTELLIGENCE`, schema/version codes, `SHADOW_ONLY` as secondary label).

#### D13-12 — ISO date consistency

Public displayed date must be consistently `YYYY-MM-DD`.

Do not rely on browser-localized native date-input rendering as the visible source of truth. A native picker may remain behind an ISO-formatted visible control if useful.

#### D13-13 — Health/budget labels must be unambiguous

Sidebar/topbar must label separately:

- system/data health;
- Provider budget/quota read status.

Do not render `BLOCKED DAY` followed by an unlabeled `UNKNOWN` line.

## Existing truths that must remain

The following current behavior is accepted and must not regress:

```text
NEW_INTELLIGENCE_WORKSPACE_ONLY
w2.dashboard-intelligence-workspace.v1
BLOCKED_DAY fail-closed semantics
provider_calls=0
DB business writes=0
no_call_on_read=true
0/1/2+ factual market timeline, no interpolation
external intelligence NOT_CONNECTED and non-blocking
Phase 0.5 historical NO_EDGE / V gate fail / incremental edge NOT_PROVEN
exact 13-league runtime whitelist
SHADOW_ONLY
Candidate/Formal/Lock/Production OFF
Track A CLOSED_PASS
```

## Scope boundaries

Allowed:

- frontend responsive/layout/localization/rendering changes;
- bounded unified workspace adapter/read-contract changes needed to expose **already persisted** identity/exclusion/statistical evidence;
- source-bound competition identity resolution using existing registry/mapping authority;
- additive schema-compatible fields if needed, with tests and no migration;
- test/golden/visual QA updates;
- local OCI relay deployment after merge and exact-head acceptance.

Not allowed:

- Provider calls for Dashboard rendering/audit;
- DB business writes;
- new Provider or paid plan;
- Scheduler/cadence changes;
- active whitelist changes;
- model/factor/threshold retraining;
- changing `MIN_DECISIVE_SAMPLES_FOR_RATE` merely to make this UI pass;
- synthetic probability/market/identity data;
- Phase 0.5 rerun;
- Round4 start;
- P6 execution;
- Candidate/Formal/Lock/Production or real-money enablement.

## Required tests/evidence

The task must add deterministic tests for D13-01 through D13-13, including real edge cases represented by the Owner screenshots:

```text
numeric provider league id
past next_eval_at
n=5 / 80% / no probability metrics
all probability metrics unavailable + directional accuracy present
high exclusion share with reason distribution
repeated market statuses
scoreline unavailable with no 10,000 claim
provider budget UNKNOWN without read
ADVISORY and MARKET_NOT_READY localization
ISO date display
separate health vs provider-budget labels
13-inch responsive font-size/reflow
scroll-position overlap/sticky-cover checks
```

Acceptance must include:

- focused backend/unit/contract tests;
- TypeScript/typecheck/build;
- full Web E2E;
- deterministic responsive screenshots;
- computed-font and geometry assertions;
- Ruff / MyPy / secret scan / tracked outputs;
- exact-head Full CI + `RELEASE_REQUIRED` PASS;
- Repository Hygiene PASS.

## Continuous execution and deployment

No intermediate Owner gate is required. Codex may fix all in-scope findings and ordinary regressions continuously.

After exact-head technical acceptance:

1. merge the exact reviewed head automatically;
2. deploy using the frozen primary transport only:
   `GitHub/GHCR -> Owner local computer -> LOCAL OCI relay -> SCP -> VPS -> digest verify/import -> warm switch`;
3. perform postdeploy API/Web/source-identity/no-call/no-write checks;
4. perform real-browser visual/readability smoke at a laptop-sized viewport when the available environment can access the VPS; if direct browser access is unavailable, do not fabricate a visual PASS—use immutable Web identity + committed deterministic screenshots and leave the real-device Owner observation explicit;
5. stop at `DASHBOARD_OWNER_13IN_TRUTH_READABILITY_ACCEPTANCE_PASS` only when all D13 findings are closed.

Round4 remains `NOT_STARTED` after this task. Do not automatically enter it.

## Terminal classifications

```text
DASHBOARD_OWNER_13IN_TRUTH_READABILITY_ACCEPTANCE_PASS
DASHBOARD_OWNER_13IN_REMEDIATION_BLOCKED_SOURCE_EVIDENCE
DASHBOARD_OWNER_13IN_REMEDIATION_ROLLED_BACK
```
