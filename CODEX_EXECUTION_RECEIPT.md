# W2 Codex Execution Receipt

```text
AUTHORITY = W2_CODEX_EXECUTION_RECEIPT_LATEST
STATUS = COMPLETE_TERMINAL
EXECUTION_TASK = W2_DASHBOARD_OWNER_MARKET_EVIDENCE_CONSISTENCY_REMEDIATION_V1
TERMINAL_GATE = DASHBOARD_OWNER_MARKET_TRUTH_ACCEPTANCE_PASS
EXACT_CONTEXT_BASE_SHA = 30618eda7578a407df97a890c46c2a348e686e5b
EXACT_IMPLEMENTATION_BASE_SHA = 14a25727c77b5ede3a1731ec2487e08fa2be4eab
EXACT_IMPLEMENTATION_HEAD_SHA = 4370393be9b2593ec008d150daa9bf39ddbf265f
EXACT_SOURCE_TREE_SHA = e9c4a71154f14b361eb0057a022ba80fc0e48258
EXACT_ORIGIN_MAIN_SHA = d2740a573c748cfaef38c66e951618e8782e09d0
PR_NUMBER_OR_NONE = 505
PR_STATE = MERGED
PR_MERGE_SHA = d2740a573c748cfaef38c66e951618e8782e09d0
PR_FAST_RUN_ID = 31324283979
FULL_CI_RUN_ID = 31324325261
RELEASE_RUN_ID = 31324620283
PROMOTION_RUN_ID = 31325104555
CI_TERMINAL_STATUS = PASS
RELEASE_REQUIRED = PASS_EXACT_HEAD
CHANGED_FILES = 11_LISTED_BELOW
TEST_EVIDENCE = PASS_LISTED_BELOW
RUNTIME_OR_READ_EVIDENCE = PASS_LISTED_BELOW
FINAL_DEPLOYED_SOURCE_SHA = 4370393be9b2593ec008d150daa9bf39ddbf265f
PROVIDER_CALLS = 0
DB_BUSINESS_WRITES = 0
SCHEDULER_OR_CADENCE_CHANGED = false
WHITELIST_CHANGED = false
MODEL_OR_THRESHOLD_CHANGED = false
MIGRATION_CHANGED = false
PHASE_0_5_REEXECUTED = false
ROUND_4_STATUS = NOT_STARTED
CANDIDATE_STATUS = OFF
FORMAL_STATUS = OFF
LOCK_STATUS = OFF
PRODUCTION_STATUS = OFF
P6_STATUS = NOT_AUTHORIZED
REPOSITORY_HYGIENE = PASS
UNRESOLVED_ITEMS = NONE_WITHIN_AUTHORIZED_SCOPE
NEXT_GATE = NONE_TERMINAL_STOP
```

## Result

PR #505 closed D15-01 through D15-06 without changing the existing movement
engine. Read-only persisted evidence proved legitimate price-only movement:
the canonical line stayed constant while side-price medians changed. The public
workspace now exposes the exact movement class and supporting from/to evidence,
and uses one freshness-gated market-evidence status across Market Radar, Market
Fact, selected-match market view and Model Lab market summary.

Stale snapshots remain visible as historical Market Memory but cannot be
publicly ready. Quote counts distinguish snapshots, bookmaker pairs and
single-side rows. Scoreline status has labelled context, and repeated Attention
groups collapse while preserving expansion to each real fixture.

## Changed files

```text
DASHBOARD_DATA_CONTRACT.md
apps/web/e2e/decision-contract.spec.ts
apps/web/src/components/IntelligenceConsole.tsx
apps/web/src/intelligence.css
apps/web/src/types/intelligenceWorkspace.ts
docs/operations/architecture_convergence/W2_D15_MARKET_EVIDENCE_REPORT.md
src/w2/api/schemas.py
src/w2/dashboard/workspace.py
tests/contract/test_dashboard_intelligence_workspace_contract.py
tests/unit/test_dashboard_intelligence_workspace.py
tests/unit/test_round3_market_intelligence.py
```

## Contract and test evidence

```text
focused Python/unit/contract regression = 147 passed
final D15/ORC06/layout Web focus = 6 passed
full Web E2E = 56 passed
TypeScript typecheck = PASS
Web build = PASS
Ruff = PASS
MyPy = PASS_281_SOURCE_FILES
tracked generated outputs = PASS
W2 all-stage checks = PASS
secret scan = PASS
git diff check = PASS
PR_FAST_REQUIRED @ exact head = PASS
FULL_CI_RELEASE_REQUIRED @ exact head = PASS
```

The exact-head Full CI and release matrices passed static contracts, four
unit/contract shards, two integration shards, migration schema checks, staging
parity, predeploy E2E, compose packaging, full Web Playwright, immutable image
builds, image smoke and release-manifest verification.

## Exact persisted evidence classification

The sanitized repository report records the existing real two-snapshot cases.
For the reported Asian Handicap market, line `-0.5` remained unchanged while
the HOME median moved `1.815 -> 1.85` and AWAY moved `1.91 -> 1.90`, so the
authoritative class is `PRICE_MOVEMENT`. For Totals, line `2.5` remained
unchanged while the OVER median moved `1.83 -> 1.85`. Bookmaker-count changes
were retained as coverage evidence only, not movement inputs.

```text
movement_engine_change = NONE_REQUIRED
movement_contract = STABLE|PRICE_MOVEMENT|LINE_MOVEMENT|LINE_AND_PRICE_MOVEMENT
public_PRICE_MOVEMENT_label = 赔率变化
from_to_capture_time_visible = true
line_delta_visible = true
side_price_median_delta_visible = true
provider_calls = 0
db_business_writes = 0
would_write_checkpoint = false
no_call_on_read = true
```

## Deployment

```text
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
PYTHON_IMAGE_DIGEST = sha256:480e5bd443e25079836cbeaa35a27feafaeab7ce3b73a8591802b6d9752746d8
WEB_IMAGE_DIGEST = sha256:831f2aa1c5d0af240ec73f3052800f21419d1a898aa8f421b3fad581cc4ab062
FULL_CI_WALL_SECONDS = 414
PREHEAT_SECONDS = 246
DEPLOY_SWITCH_SECONDS = 48
HEALTH = PASS
READY = PASS
RELEASE_SYNC = PASS
ROLLBACK_EXECUTED = false
FINAL_RESULT = PASS
```

## Postdeploy real-data acceptance

The deployed unified endpoint returned six real matches and twelve AH/OU
market rows. Six rows were stale historical memory and six were insufficient;
there were zero `READY + STALE` conflicts. Market Fact, Market Radar and Model
Lab market summary agreed. Non-insufficient movements carried from/to time,
line delta, side-price delta and probability delta. Quote-row counts equalled
both canonical observation counts and twice bookmaker-pair counts.

```text
schema = w2.dashboard-intelligence-workspace.v1
public_authority = NEW_INTELLIGENCE_WORKSPACE_ONLY
Web/API source identity = 4370393be9b2593ec008d150daa9bf39ddbf265f
market_rows = 12
stale_rows = 6
insufficient_rows = 6
stale_ready_conflicts = 0
provider_calls = 0
db_writes = 0
would_write_checkpoint = false
no_call_on_read = true
active_whitelist_count = 13
free_bridge_mode = SHADOW_ONLY
candidate/formal/lock/production = OFF
```

## Real-page viewport acceptance

Playwright validated the deployed real page after selecting the persisted
price-movement fixture. Every required viewport showed the stale-memory notice,
exact price-movement label, from/to timestamps and deltas, unambiguous quote
counts, Model Lab comparison status, labelled Scoreline context, and the
zero-call/zero-write read contract. No primary `市场证据：就绪` or legacy `次观测`
copy appeared.

```text
1280x720   client_width=1280 scroll_width=1280 horizontal_overflow=false
1366x768   client_width=1366 scroll_width=1366 horizontal_overflow=false
1512x982   client_width=1512 scroll_width=1512 horizontal_overflow=false
1536x1024  client_width=1536 scroll_width=1536 horizontal_overflow=false
```

## Finding closure and frozen controls

```text
D15_01 = CLOSED_PASS
D15_02 = CLOSED_PASS
D15_03 = CLOSED_PASS
D15_04 = CLOSED_PASS
D15_05 = CLOSED_PASS
D15_06 = CLOSED_PASS
```

No Provider call, manual Provider probe, DB business write, migration,
Scheduler/cadence change, whitelist change, model/factor/threshold change,
Phase 0.5 re-execution, external-intelligence activation, Round4 start, P6
execution, Candidate/Formal/Lock/Production enablement or real-money authority
occurred. The task stops at `DASHBOARD_OWNER_MARKET_TRUTH_ACCEPTANCE_PASS`.
