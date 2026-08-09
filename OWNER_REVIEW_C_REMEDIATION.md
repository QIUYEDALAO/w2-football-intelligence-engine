# W2 Owner Review C — Bounded UI Contract Remediation

```text
AUTHORITY = W2_OWNER_REVIEW_C_REMEDIATION_V1
OWNER_REVIEW_C = CHANGES_REQUIRED_BOUNDED
IMPLEMENTATION_PR = 499
REVIEWED_BASE = f14136f07d69ece09e61fec6b1dd546e67c0267c
REVIEWED_HEAD = e9fda39783b7e0ce80cff635e9e2d61dd51bf73f
REVIEWED_CONTEXT = 70fe2e52fdd731ce2aa37c79f7acacfaa3abb4bb
P3_P4_P5_ARCHITECTURE = ACCEPTED
REMEDIATION_SCOPE = FINAL_UI_PRESENTATION_CONTRACT_ONLY
P5_5 = NOT_AUTHORIZED
ROUND_4 = NOT_STARTED
```

## 1. Review conclusion

The P3→P5 architecture, unified endpoint cutover, truth-state behavior, no-call/no-write contract, seven-state/four-risk semantics, scoreline source semantics, validation source reuse, responsive foundation, exact-head CI and Repository Hygiene are accepted.

Owner Review C is not yet final PASS because the exact approved P0 presentation contract still has a small set of omissions in the final Web UI. These are bounded presentation fixes on the existing PR #499. No new backend architecture, Provider work, Scheduler work, model work or new product semantics are authorized.

The purpose of this remediation is to close all presently identified P0→P5 UI contract gaps in one pass so the next stop is the final Owner Review C rereview, not another intermediate handoff.

## 2. Required fixes

### ORC-01 — Match Board must identify the market with the main line

P0 freezes the Match Board market field as a fact such as:

```text
AH -0.25
OU 2.5
```

The reviewed UI renders `market_fact.main_line` as a bare value, which can be ambiguous because the market identity is absent.

Fix using only the existing unified P2 payload. Do not call a legacy endpoint and do not infer a pick/side.

Acceptance:

- every displayed Match Board main line includes the factual market identity (`AH` or `OU`);
- the value remains a market fact, never a selection/pick;
- unavailable market remains explicit;
- E2E covers AH and OU rendering and confirms no Home/Under/Over pick semantics are introduced.

### ORC-02 — Market Radar must visibly render the two-sided prices

P0 requires Market Radar, when evidence exists, to show:

- AH/OU market identity;
- bookmaker count;
- selected/canonical main line;
- **two-sided prices**;
- snapshot count;
- observation count;
- freshness;
- persisted timeline.

The reviewed P3 UI shows the other fields but does not visibly render `market.prices`.

Acceptance:

- AH and OU cards visibly show both available sides from the P2 `prices` object;
- no side is described as a market recommendation;
- no missing side is fabricated;
- E2E asserts both-side price visibility for a populated market and explicit unavailable behavior when no price evidence exists.

### ORC-03 — Validation must visibly expose cohort/checkpoint identity

P0 Probability Validation requires cohort identity in addition to Brier/LogLoss/ECE/reliability/status/effective N.

The P2 payload already exposes `validation.probability.checkpoint_metadata`; the reviewed UI does not surface it.

Acceptance:

- Validation visibly shows the existing checkpoint/cohort identity from `checkpoint_metadata`;
- no new cohort name or timestamp is invented;
- missing metadata is explicit;
- E2E asserts the source checkpoint identity is present.

### ORC-04 — League Performance must include `Decisive N`

P0 freezes the League Performance required columns as:

```text
League
Validation N
Decisive N
Correct
Wrong
PUSH
W2 Direction Accuracy
Brier
Calibration
Statistical Status
```

The P2 payload already contains `decisive_n`; the reviewed final table omits that column.

Acceptance:

- add `Decisive N` and render `league.decisive_n`;
- preserve current Validation N / Correct / Wrong / PUSH / Accuracy / Brier / Calibration / Statistical Status;
- `VOID` may remain as an additional factual settlement column, but it must not replace `Decisive N`;
- responsive table remains usable at all required viewports;
- E2E asserts the exact required column and value.

### ORC-05 — Compact header must include data-update/system-health context

P0 global-header requirements include supported data-update/system-health context in addition to W2 INTELLIGENCE, 13 LEAGUES, SHADOW_ONLY and all OFF states.

The reviewed topbar includes the mode/authority states but does not surface the current read update/system-health context there.

Acceptance:

- add compact, non-KPI-wall header facts bound to existing unified fields, e.g. generated/update time and `data_operations.system_health`;
- do not invent real-time freshness or Provider status;
- keep the header compact at 1536×1024 and all required responsive widths;
- E2E asserts the displayed values are sourced from the unified payload.

### ORC-06 — Scoreline reference must visibly include model/readiness context

P0 Scoreline Top 3 requires model/readiness context together with 10,000 simulations, top three outcomes and unconditional probability.

The reviewed scoreline panel shows the scoreline artifact semantics but not the selected match readiness/model state in the scoreline surface.

Acceptance:

- add compact source-bound model/readiness context from the selected match (`w2_analysis.model_view.status` and `readiness.status`, with reason when useful);
- keep `MODEL_SCORELINE_REFERENCE` / `NOT_PROVEN` / 10,000 / `unconditional_probability` / `sample_count` unchanged;
- do not turn readiness into confidence or recommendation language;
- E2E asserts context is visible for READY and UNAVAILABLE scoreline states.

## 3. Accepted behavior that must not regress

Preserve all accepted PR #499 behavior:

```text
PUBLIC_DASHBOARD_AUTHORITY = NEW_INTELLIGENCE_WORKSPACE_ONLY
PUBLIC_API = GET /v1/dashboard/intelligence-workspace
LEGACY_FALLBACK = NONE
P3_P4_P5_ARCHITECTURE = ACCEPTED
EXACT_SEVEN_STATES = PRESERVE
EXACT_FOUR_RISKS = PRESERVE
0_SNAPSHOT_NOT_TREND = PRESERVE
1_SNAPSHOT_NOT_TREND = PRESERVE
2_PLUS_DISCRETE_REAL_EVIDENCE = PRESERVE
NO_INTERPOLATION = PRESERVE
NO_SYNTHETIC_SIGNAL = PRESERVE
SCORELINE_READY_10000 = PRESERVE
SCORELINE_UNCONDITIONAL_PROBABILITY = PRESERVE
API_FOOTBALL_PREDICTION = NOT_AVAILABLE
EXTERNAL_INTELLIGENCE = NOT_CONNECTED_NON_BLOCKING
MARKET_DIRECTION_BENCHMARK = NOT_DEFINED
NO_PUBLIC_CLV = PRESERVE
NO_PUBLIC_ROI = PRESERVE
NO_MARKET_AS_PICK = PRESERVE
FORMAL = OFF
CANDIDATE = OFF
LOCK = OFF
PRODUCTION = OFF
```

Do not restore `/performance` as a second Dashboard. Do not restore Boss L1/L2 or historical Step4/Post4.

## 4. Continuous remediation / acceptance loop

Do not stop after implementing individual items.

```text
FIX ORC-01..ORC-06 ON EXISTING PR #499
↓
RUN FOCUSED TYPECHECK / CONTRACT / PLAYWRIGHT
↓
IF IN-SCOPE FAILURE -> FIX AND RE-RUN
↓
REGENERATE ALL FOUR DETERMINISTIC WORKSPACE SCREENSHOTS
↓
VERIFY 1536x1024 COMPOSITION + REQUIRED RESPONSIVE GEOMETRY
↓
RUN EXACT-HEAD FULL CI
↓
RELEASE_REQUIRED = PASS
↓
REPOSITORY_HYGIENE = PASS
↓
STOP OWNER_REVIEW_C_REREVIEW
```

No Owner handoff is required between these six fixes or their tests.

## 5. Visual evidence requirement

Regenerate:

- `intelligence-workspace-1536x1024.png`
- `intelligence-workspace-1920x1080.png`
- `intelligence-workspace-1440x900.png`
- `intelligence-workspace-1366x768.png`

Preserve deterministic browser/clock/DPR/locale/timezone settings.

The original Owner-approved 1536×1024 binary remains `OWNER_REFERENCE_BINARY_NOT_REPO_BOUND`; do not falsely claim pixel equality to an unavailable source. The final candidate screenshot must therefore remain explicitly presented for Owner visual sign-off at Owner Review C rereview.

## 6. Forbidden scope

- P5.5 cleanup or legacy deletion
- merge PR #499
- Provider calls / probes / plan changes
- Scheduler / cadence changes
- whitelist changes
- model / factor / threshold / retraining changes
- migrations / DB business writes for this remediation
- external-source connection
- Phase 0.5 rerun
- Round 4
- Candidate / Formal / Lock / Production enablement
- product-semantic expansion beyond the frozen P0/P1/P2 contract

## 7. Required terminal evidence

Before stopping:

```text
ORC_01_TYPED_MAIN_LINE = PASS
ORC_02_TWO_SIDED_PRICES = PASS
ORC_03_VALIDATION_CHECKPOINT_IDENTITY = PASS
ORC_04_LEAGUE_DECISIVE_N = PASS
ORC_05_HEADER_UPDATE_AND_HEALTH = PASS
ORC_06_SCORELINE_MODEL_READINESS_CONTEXT = PASS
EXISTING_P3_P4_P5_TRUTH_MATRIX = PASS
PUBLIC_UNIFIED_ENDPOINT_ONLY = PASS
NO_CALL_NO_WRITE = PASS
FOUR_SCREENSHOTS_REGENERATED = PASS
RESPONSIVE_NO_PAGE_OVERFLOW = PASS
EXACT_HEAD_FULL_CI = PASS
RELEASE_REQUIRED = PASS
REPOSITORY_HYGIENE = PASS
WORKTREE = CLEAN
P5_5 = NOT_STARTED_NOT_AUTHORIZED
ROUND_4 = NOT_STARTED
NEXT = OWNER_REVIEW_C_REREVIEW
```
