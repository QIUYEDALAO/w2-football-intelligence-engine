# W2 Admission Concept Inventory

Task: `W2-RETIREMENT-CLOSEOUT`  
Inventory baseline: `6cb44576b1edf91b1f1e41f1a4007a5bdd8e51bd`  
Scope: locations that calculate, classify, select, rank, display, notify, or preserve historical
economic-admission / claimed-advantage semantics.

## Disposition vocabulary

- `已改`: changed by `W2-RETIREMENT-CLOSEOUT`.
- `保留-产品内容`: retained because the calculation or neutral model/market comparison is product
  content.
- `保留-历史`: retained because old rows must continue to describe their historical state.
- `保留-不可见`: retained internal computation that does not itself make a public advantage claim.
- `死代码-仅记录`: no current production caller; recorded without modification.
- `待确认`: evidence is insufficient to decide safely.

## A. Current admission and product decision chain

| ID | Location | Exact predicate / selection | Actual consumer and semantic effect | Economic flag | 本轮处置 |
|---|---|---|---|---|---|
| A1 | `src/w2/domain/admission_contract.py:19` `economic_admission_pass` | `EV > 0 AND EV-SE > 0 AND cashflow_price_edge >= 0.05`; probability delta is diagnostic only | Shared predicate for evidence, market candidate, lifecycle, and V4 | Function does not read it | 保留-不可见 |
| A2 | `src/w2/markets/analysis_evidence.py:193` `_side_evidence` | A1 pass produces `analysis_direction_allowed=true`, `READY`, `MODEL_MARKET_EDGE_READY`; otherwise `NO_EDGE` | Projected into `ev_eligible`; consumed by market candidate, formal recommendation, adapter, card, and API | No | 保留-不可见 |
| A3 | `src/w2/markets/market_candidate.py:485/539` `_best_evaluated_side` / `_admission_eligible` | Complete mainline evidence + admissible calibration + A1; order by eligible, `EV-SE` desc, cashflow edge desc, EV desc, side | Chooses the single AH/OU side and binds its executable quote | No | 保留-产品内容 |
| A4 | `src/w2/markets/market_candidate.py:79` `select_authoritative_market_candidate` | Across AH/OU: eligible, `EV-SE` desc, cashflow edge desc, EV desc, market/selection | `analysis_calculator.py:6719` selects the one market/side analysed by formal, V4, and Decision Contract | No | 保留-产品内容 |
| A5 | `src/w2/markets/market_candidate.py:315` candidate projection | executable + model `READY` + evidence `COMPLETE` + `analysis_direction_allowed` | Writes internal `ev_eligible`; consumed by market selector and evidence projections | No | 保留-不可见 |
| A6 | `src/w2/markets/market_candidate.py:379-440` ladder evaluation | Recomputes A2 for every line/side, counts allowed rows, labels mainline/alternate and selected state | Internal market-ladder audit projection | No | 保留-不可见 |
| A7 | `src/w2/strategy/market_selector.py:21` `select_analysis_markets` | Pick decision + ready line + `candidate.ev_eligible` + score >= 0.55; then score, calibration error, quote age, bookmaker count; secondary also score >= 0.65, correlation <= 0.35, scoreline intersection | Writes primary/secondary analysis market roles | No; indirectly consumes A2/A5 | 保留-产品内容 |
| A8 | `src/w2/matchday/intake_v2.py:1269` `_selected_analysis_candidate` | Uses A7; previously returned input-order `selectable[0]` when A7 had no primary | `v4_decision_from_matchday:859` binds the result to an exact quote and V4 input | No | **已改**: no primary now returns `None` |
| A9 | `src/w2/prematch/lifecycle.py:452` `classify_evaluation` | After data/quote/calibration gates, A1 pass -> `ANALYSIS_COMPLETE`; fail -> `NO_EDGE_CURRENT` with economic blocker codes | Persisted evaluation and workspace execution diagnosis | No | 保留-不可见 |
| A10 | `src/w2/prematch/lifecycle.py:279` `bind_evaluation_opportunity` | `ANALYSIS_COMPLETE` and `NO_EDGE_CURRENT` both map to `EVALUATED_NO_EDGE`; other states map to `BLOCKED_BY_GATE` | New path cannot form `EVALUATED_CANDIDATE` | No | 保留-产品内容 |
| A11 | `src/w2/strategy/analysis_recommendation.py:96/124/152/176/202` multi-market analysis | AH/OU intent strength >= 0.55; first-half probability distance >= 0.08; top score scenario >= 0.18 | Intermediate analysis card; AH/OU public result is later neutralised to model-market divergence; first-half/score are not selectable by A7 | No | 保留-产品内容 |
| A12 | `src/w2/prematch/analysis_calculator.py:3738` `_apply_mainline_market_selection` | Mainline price < 1.40 or signal strength < 0.50 downgrades to `WATCH` and clears direction | Market-quality analysis card decision | No | 保留-产品内容 |
| A13 | `src/w2/prematch/analysis_calculator.py:5895` `_attach_market_candidate_evidence_projection` | If selected side is absent, display comparison chooses the model-ready side with maximum EV and labels it `BEST_AVAILABLE_NO_EDGE` | Comparison-only card projection | No | 保留-产品内容 |
| A14 | `src/w2/domain/decision_adapter.py:549` `_canonical_pick_evidence_ready` | Canonical quote/evidence parity, numeric EV/EV-SE, and `analysis_direction_allowed=true` | Internal guard before a Decision Contract can contain a pick | No | 保留-不可见 |
| A15 | `src/w2/domain/decision_adapter.py:416` `_market_anchor_display_tier` | When its separate feature is on: market devig, ready divergence, allowed direction, abs(delta) >= 0.05; otherwise pick becomes watch | Optional public Decision Contract guard | No; separate `W2_MARKET_ANCHOR_DISPLAY_ENABLED` | 保留-产品内容 |
| A16 | `src/w2/domain/decision_adapter.py:183` advisory threshold | `watch_only` or candidate EV below policy `effective_threshold` downgrades to watch | Advisory-blind-spot product risk policy | No | 保留-产品内容 |
| A17 | `src/w2/strategy/formal_recommendation.py:106/313` formal recommendation | Executable canonical candidate with allowed direction and EV parity; EV <= 0.15, EV >= 0.035, EV >= 0.035 + EV-SE; reverse value requires line > 0 and EV >= 0.08 + EV-SE | Formal payload is computed, then suppressed by formal capability/env when disabled | No | 保留-不可见 |
| A18 | `src/w2/formal/readiness.py:13` `evaluate_formal_ah_readiness` | Global evidence + fixture evidence + human approval; capability additionally required for `formal_eligible` | Formal readiness gate; despite the name, not an economic predicate | No | 保留-不可见 |
| A19 | `src/w2/domain/recommendation_decision_v4.py:473` `_outcome` | With flag on: A1 fail -> `NO_EDGE`, formal admission pass -> `FORMAL_RECOMMEND`; with flag off -> `MODEL_MARKET_DIVERGENCE` | Public recommendation authority | **Yes** | 保留-产品内容 |
| A20 | `src/w2/prematch/analysis_calculator.py:6028` and `:5840-5850` card decoration | Complete AH/OU evidence keeps the analysed direction but changes decision to `MODEL_MARKET_DIVERGENCE` with fixed disclaimer | Intended public product shape: direction plus neutral divergence explanation | No; market capability applies | 保留-产品内容 |
| A21 | `src/w2/dashboard/workspace.py:1344` `_market_eligibility` | Market observation available + quote ready + model ready; does not apply A1 | Internal workspace readiness aggregation | No | 保留-不可见 |
| A22 | `src/w2/dashboard/workspace.py:1148` `_shadow_candidate` | Economic flag + candidate capability + enabled market + V4 `ANALYSIS_PICK` + selected payload + eligibility ready | Controls whether workspace can expose an active shadow candidate | **Yes** | 保留-产品内容 |
| A23 | `src/w2/dashboard/workspace.py:1061` formal projection | Always exposes retired status, reason, and reactivation prerequisites | Public explanation that formal recommendation is off | Displays flag state | 保留-产品内容 |

## B. Independent legacy value / edge paths

| ID | Location | Exact predicate / selection | Actual consumer and semantic effect | Economic flag | 本轮处置 |
|---|---|---|---|---|---|
| B1 | `src/w2/pricing/value_vs_market.py:19` `pricing_status` | coverage >= 0.5 and max absolute AH/OU line edge >= 0.25 -> `RULE_BASED_UNCALIBRATED`; otherwise watch | Pricing shadow diagnostic, formal/report/card input | No | 保留-产品内容 |
| B2 | `src/w2/reporting/match_decision.py:56` `decide_match` | Formal intent requires a complete payload and EV > 0; otherwise abs(AH edge) < 0.25 produces threshold reason; direction must match edge sign | Report and audit-export classification | No | 保留-产品内容 |
| B3 | `src/w2/operations/production_readiness.py:201` `_invalid_formal` | Formal payload with missing or non-positive EV is invalid | Operations readiness only | No | 保留-不可见 |
| B4 | `src/w2/analysis/market_movement.py:20` `classify_divergence_origin` | Positive current EV; movement share > 0.5 -> movement-created, age ratio >= 0.6 -> stable | Diagnostic movement/risk class | No | 保留-产品内容 |
| B5 | `src/w2/markets/value_engine.py:229/257` `grade_candidate` / `MarketValueEngine` | Risk EV thresholds 0.05/0.025/0 assign A/B/C/D and order by risk EV | No production constructor found under `src/w2`; tests/legacy library only | No | **死代码-仅记录** |
| B6 | `src/w2/matchday/cards.py:113/204` `ResearchCardBuilder` / `_diagnostics` | Previously assigned A/B/C/D, sorted by risk EV, and selected first watch row as primary. Now retains raw/risk EV only, uses fixed market enumeration, and marks every row diagnostic/unselected | Manual Stage10C cycle and read-model projector | No | **已改**: neutral diagnostics, no grade or primary/secondary direction |
| B7 | `src/w2/readiness/data_gate.py:199/501` legacy readiness adapter | `AH_EV_BELOW_FORMAL_THRESHOLD` plus blocked readiness -> partial `EDGE_INSUFFICIENT` | Internal Decision Adapter readiness mapping | No | 保留-不可见 |

### Stage10C activity decision

Stage10C is not registered in repository scheduler code, local cron, or local launchd. It is
nevertheless a current manual operations entry, not dormant:

- `docs/runbooks/STAGE10C_DAILY_OPERATIONS.md:6` instructs the operator to run
  `scripts/run_stage10c_daily_cycle.py --dry-run`;
- `docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md:2399`
  classifies the script as `MANUAL_OPS`, `operator -> script`, `KEEP`;
- `scripts/run_stage10c_daily_cycle.py:26` constructs `DailyMatchdayCycle` directly.

Disposition: active manual path, so B6 was neutralised rather than labelled `DORMANT_LEGACY`.

## C. Historical candidate semantics

| ID | Location | Historical predicate / consumer | Economic flag | 本轮处置 |
|---|---|---|---|---|
| C1 | `src/w2/api/repository.py:480` `_official_funnel_recommendations` | Requires historical payload `ANALYSIS_PICK_ACTIVE`, final opportunity `EVALUATED_CANDIDATE`, and matching latest identities; projects old official rows and settlement record | No | 保留-历史 |
| C2 | `src/w2/dashboard/workspace.py:687` `_evaluation_execution` | Old evaluation/opportunity states determine ever-formed/latest candidate history and its historical copy | No | 保留-历史 |
| C3 | `src/w2/prematch/candidate_notifications.py:86` `enqueue_attempt_notification_in_session` | Historical/current explicit `EVALUATED_CANDIDATE` transitions create formed/changed/confirmed/withdrawn events | No | 保留-历史 |
| C4 | `src/w2/prematch/candidate_notifications.py:1026` `_closeout_recommendations` | Requires historical `ANALYSIS_PICK_ACTIVE` plus final `EVALUATED_CANDIDATE` | No | 保留-历史 |
| C5 | `src/w2/prematch/candidate_notifications.py:1663` `_change_details` | Side/line/bookmaker changes, price ratio threshold, or EV absolute-change threshold drives historical material-change notifications | No | 保留-历史 |
| C6 | `src/w2/prematch/candidate_notifications.py:1731` `_opportunity_state` | Historical `original_state=ANALYSIS_PICK_ACTIVE` maps to `EVALUATED_CANDIDATE` | No | 保留-历史 |

## D. Dead definitions and explicit exclusions

| ID | Location | Finding | 本轮处置 |
|---|---|---|---|
| D1 | `src/w2/prematch/analysis_calculator.py:267` `_public_market_is_primary_pick` | Checks pick/recommend, executable quote, `ev_eligible`, and primary role; no caller found | **死代码-仅记录** |
| D2 | `src/w2/strategy/candidate.py:133` `generate_candidate` | Chooses the highest decimal odds after hard gates and always emits watch; no EV predicate and no production caller beyond tests | 死代码-仅记录 |
| D3 | `scripts/audit_*`, backtest, debug, settled-candidate rescore | Read-only evidence and diagnostic scripts may read EV/candidate fields but do not choose public product output | 保留-不可见 |

## Reactivation warning

Any future proposal to restore a `+EV`, value, candidate, or betting-advantage claim must review
every A/B/C/D row above. In particular it must not treat the current economic feature flag as a
repository-wide kill switch: it directly controls V4 outcome and workspace shadow exposure, while
several upstream computations intentionally remain available as neutral model diagnostics.
