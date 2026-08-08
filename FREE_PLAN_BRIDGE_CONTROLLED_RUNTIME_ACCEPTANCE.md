# W2 Free Plan Bridge — Controlled Runtime Acceptance

Task:

```text
W2_MI_FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_CLOSURE
```

PASS requires **all** hard gates below.

## A. Source / PR identity

Required:

```text
PR_495 = FOUND
PR_495_BASE = exact trusted main
PR_495_HEAD = exact audited head
PR_495_MERGEABLE = true before merge
ROUND_3 = NOT_STARTED
```

Codex must re-fetch before every merge/deploy boundary and record exact SHAs.

## B. PR #495 independent code audit

Do not trust PR description. Verify the actual code and tests prove:

- disabled by default before controlled activation;
- no runtime whitelist change;
- no audit-only league reachability;
- no independent duplicate scheduler;
- single-fixture Free default; `ids` batching disabled unless separately verified;
- raw payload, capture, fixture identity and AH/OU normalization reuse existing canonical contracts;
- no duplicate market/fixture schema;
- cache-key dedupe and no-idle-polling work;
- secret handling remains safe.

## C. Quota semantics — hard gate

Required final semantics:

```text
PROVIDER_DAILY_LIMIT = 100
W2_DAILY_CALL_CEILING = 80
MIN_PROVIDER_DAILY_REMAINING = 20
EFFECTIVE_W2_CEILING = 80_NOT_60
AUTOMATIC_RETRY = false
```

Tests must cover at least:

```text
actual=79 + planned=1 => allowed when Provider capacity permits
actual=80 + planned=1 => blocked
provider_remaining=20 => no subsequent bridge call
provider_remaining<20 => blocked
provider_remaining unknown => fail closed for nonessential call
```

No double subtraction of the 20-call reserve is allowed.

## D. Shared quota truth — hard gate

Bridge quota accounting must include **all API-Football calls sharing the same key/account**, not only bridge calls.

Required evidence:

```text
UNACCOUNTED_PROVIDER_CALLS = 0 within validation scope
BRIDGE_LOCAL_COUNTER_AS_SOLE_AUTHORITY = false
PROVIDER_HEADER_OR_STATUS_RECONCILIATION = PASS
STRICTER_OF_PROVIDER_AND_LOCAL_LEDGER_WINS = true
```

Process restart must not reset daily actual-use accounting.

## E. Runtime ownership

There must be exactly one clear runtime owner inside the existing W2 scheduler/operations framework.

Required:

```text
NEW_INDEPENDENT_SCHEDULER_DAEMON = 0
DUPLICATE_COLLECTION_OWNER = 0
```

A task run with no due target fixture must perform zero fixture-followup Provider calls.

## F. Target universe isolation

Required:

```text
ACTIVE_WHITELIST = exact existing 13
AUDIT_ONLY_4_RUNTIME_REACHABILITY = 0
NEW_ENABLED_LEAGUES = 0
NEW_DAYVIEW_LEAGUES = 0
```

Discovery may see Provider rows outside the whitelist, but they must be locally rejected before follow-up calls/persistence as W2 target fixtures.

## G. Call efficiency / dedupe

For equivalent request keys and already-fresh evidence:

```text
DUPLICATE_CALLS = 0
CACHE_HIT_PROVIDER_CALLS = 0
IDLE_FOLLOWUP_CALLS = 0
```

If date discovery already contains canonical fixture identity fields, a second fixture-detail call must not be mandatory merely by architecture convention. Any retained detail call must have a documented evidence need.

Free-plan `fixtures?ids=...` may not be attempted in normal runtime unless a later real capability proof explicitly enables it.

## H. Refresh/cadence contract

The implementation must define and test collection states for:

```text
DISCOVERY
PREMATCH_MARKET
LINEUP_WINDOW
POSTMATCH_STATISTICS
```

Reuse existing authoritative checkpoint/freshness policy when present. Any new cadence is operational-only and may not be described as a betting/alert threshold.

Heavy-day prioritization must be deterministic and quota-safe. Required ordering must make current core market evidence higher priority than optional enrichment.

## I. Persistence / normalization

Real or fixture-grounded acceptance must prove:

```text
raw payload stored
endpoint capture recorded
fixture identity canonicalized
AH normalized
OU normalized
bookmaker data preserved
quote timestamp/capture lineage preserved
```

No recommendation or opportunity semantics may be created by ingestion.

## J. Failure behavior

Tests must prove fail-closed behavior for at least:

```text
HTTP_429
PLAN_RESTRICTED
UNKNOWN_QUOTA
RESERVE_REACHED
SCHEMA_UNSAFE
EMPTY_OR_INVALID_FIXTURE_ID
OUT_OF_WHITELIST_FIXTURE
```

Required:

```text
AUTOMATIC_RETRY = 0
LATER_LOWER_PRIORITY_CALLS_AFTER_HARD_STOP = 0 when fail-fast applies
STOP_EVIDENCE_PRESERVED = true
```

## K. Pre-merge quality

Before PR #495 merge:

- focused bridge tests PASS;
- quota tests PASS;
- package/architecture contract tests PASS;
- full repository-required pytest PASS (environment-gated skips may remain documented);
- Ruff PASS;
- Mypy PASS;
- secret scan PASS;
- PR Fast PASS;
- any required Full Release Candidate / protected-baseline gate PASS.

If any required gate fails, Codex must fix within scope and continue; do not ask owner again.

## L. PR #495 merge

Only after A–K PASS:

```text
PR_495 = MERGED
MERGE_SHA = recorded
```

Re-fetch main after merge.

## M. Controlled runtime integration

If PR #495 itself does not provide safe runtime ownership, create exactly one bounded follow-up runtime-integration PR.

Allowed changes only:

```text
existing scheduler/operations integration
shared quota ledger/reconciliation
cache/freshness wiring
feature flag / SHADOW_ONLY mode
focused tests/operational docs
rollback control
```

Forbidden:

```text
Round 3 logic
league additions
recommendation gates
new Provider purchase/cutover
parallel data model
```

Follow normal PR/CI/release governance and continue remediation until accepted.

## N. Deployment / shadow activation

Deployment is allowed only from accepted immutable artifacts through normal W2 release procedure.

Required post-deploy state:

```text
FREE_BRIDGE_MODE = SHADOW_ONLY
ACTIVE_WHITELIST = 13_UNCHANGED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_3 = NOT_STARTED
```

Rollback control must be one-step/feature-flag based and proven before real shadow acceptance.

## O. Real Free-plan shadow acceptance

Use current real fixtures only after code/deploy gates pass.

Task-wide new validation calls:

```text
<= 20
```

Provider/day invariants:

```text
W2 calls <= 80
Provider remaining >= 20 after accepted run
no retry
```

When current match availability permits, prove an end-to-end path for at least one existing-whitelist fixture:

```text
discovery
-> target whitelist filter
-> canonical fixture identity
-> odds
-> AH/OU normalized observations
-> raw payload + endpoint capture lineage
```

If lineup/statistics are not meaningful for the selected fixture state, do not waste calls; record `NOT_DUE` instead of manufacturing coverage.

## P. Shadow no-op success

A day/run with no due target fixtures is a valid PASS condition for the scheduler behavior if it proves:

```text
PROVIDER_FOLLOWUP_CALLS = 0
NO_ERROR = true
NO_FAKE_DATA = true
```

## Q. Rollback proof

Required:

```text
ROLLBACK_MECHANISM = VERIFIED
DISABLE_BRIDGE_STOPS_NEW_BRIDGE_CALLS = true
ROLLBACK_DOES_NOT_CHANGE_13_WHITELIST = true
ROLLBACK_DOES_NOT_DELETE_VALID_EXISTING_EVIDENCE = true
```

Do not require a destructive rollback.

## R. Repository hygiene

Before PASS, execute `REPOSITORY_HYGIENE_POLICY.md`.

Delete provably dead:

- one-off validation scripts;
- obsolete duplicated quota helpers introduced by this work;
- superseded fixtures/tests/configs;
- scratch tracked outputs;
- stale bridge wiring after final authority is selected.

Preserve reusable bridge/audit tooling and required receipts/evidence.

Required:

```text
REPOSITORY_HYGIENE = PASS
UNRESOLVED_HYGIENE_ITEMS = 0
```

## S. Final receipt

Create:

```text
FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_RECEIPT.md
```

It must record at least:

```text
PR_495_FINAL_HEAD_SHA
PR_495_MERGE_SHA
RUNTIME_INTEGRATION_PR if any
FINAL_MAIN_SHA
DEPLOYED_SOURCE_SHA / immutable artifact identity if deployed
PROVIDER_DAILY_LIMIT
W2_DAILY_CALL_CEILING
MIN_PROVIDER_DAILY_REMAINING
REAL_VALIDATION_CALLS
FINAL_PROVIDER_REMAINING
SHARED_LEDGER_STATUS
CACHE_DEDUPE_STATUS
IDLE_POLLING_STATUS
ACTIVE_WHITELIST_BEFORE_AFTER
AUDIT_ONLY_RUNTIME_REACHABILITY
SHADOW_MODE
ROLLBACK_STATUS
REPOSITORY_HYGIENE
CANDIDATE
FORMAL
LOCK
PRODUCTION
ROUND_3
```

## Expected final state

```text
FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME = PASS
FREE_BRIDGE_MODE = SHADOW_ONLY
API_FOOTBALL_PRO_RENEWAL = NOT_REQUIRED_NOW
ACTIVE_WHITELIST = 13_UNCHANGED
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_ROUND_3_OR_BIG_FIVE_COLLECTION_DECISION
```

A successful bridge is data infrastructure only. It does not authorize Round 3 automatically.
