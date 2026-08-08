# W2 Current Task Checklist

```text
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME = PASS
ACTIVE_TASK = AWAIT_OWNER_ROUND_3_OR_BIG_FIVE_COLLECTION_DECISION
FREE_BRIDGE_MODE = SHADOW_ONLY
ACTIVE_WHITELIST = 13_UNCHANGED
ROUND_3 = NOT_STARTED
```

## Completed controlled runtime closure

- [x] Re-fetched latest `origin/main`, `origin/context/current` and PR #495.
- [x] Independently audited PR #495 and corrected the quota double-reserve
  defect to Provider 100 / W2 maximum 80 / minimum remaining 20.
- [x] Passed PR #495 Fast CI and exact-source Release Candidate gates.
- [x] Merged PR #495 at
  `eccab2542fa68bb0ae557e6f073dfdd927297f07`.
- [x] Added exactly one bounded existing-scheduler runtime integration in PR
  #496; no second scheduler daemon or duplicate evidence model was introduced.
- [x] Reused the shared Provider ledger, raw payload, endpoint capture, fixture
  identity, checkpoint, lineup and AH/OU market contracts.
- [x] Kept `fixtures?ids` disabled; normal Free runtime uses no-season date
  discovery and single-fixture follow-ups only.
- [x] Passed the full local suite: 2,464 passed, 13 skipped; Ruff, strict mypy,
  secret scan, diff check and developer check all passed.
- [x] Passed PR #496 Fast CI and final Release Candidate gates.
- [x] Merged PR #496 as final `main` SHA
  `c241b877a4168659f465163108f7a53fb8fd82a5`.
- [x] Passed main promotion and main immutable Release Candidate/image-smoke
  gates.
- [x] Deployed the immutable `c241b877…` Python and web digests through the
  normal W2 staging release path; cold deployment completed in 185 seconds.
- [x] Proved default/rollback `OFF` returns `DISABLED` with zero Provider
  calls.
- [x] Activated only worker as `SHADOW_ONLY` for controlled acceptance while
  scheduler remained `OFF`, preventing concurrent calls.
- [x] Used exactly two new real Provider calls with no retry: one
  `fixtures?date=2026-08-08` and one `odds?fixture=1575448`.
- [x] Proved fixture `1575448` belongs to existing-whitelist
  `primeira_liga`, canonicalized its identity, and persisted 182 AH plus 240
  OU observations from 14 bookmakers.
- [x] Proved all 464 target market observations retain raw payload, endpoint
  capture and quote timestamp lineage.
- [x] Re-ran the bridge against fresh cache with zero Provider calls and zero
  duplicate identity/market writes.
- [x] Proved one-step feature-flag rollback: zero calls, no evidence deletion,
  exact 13 whitelist unchanged.
- [x] Restored worker and scheduler to `SHADOW_ONLY`; the first post-restart
  scheduler audit also used zero Provider calls.
- [x] Verified all six deployed services running and release SHA/digests exact.
- [x] Verified the four audit-only league IDs have empty intersection with
  runtime whitelist.
- [x] Verified recommendations and recommendation locks remain zero;
  Candidate/Formal/Lock/Production are OFF and Round 3 is not started.
- [x] Executed repository hygiene and retained every implementation/test/runbook
  asset because each has a live runtime, verification, rollback or audit role.
- [x] Created `FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_RECEIPT.md`.

## Provider acceptance accounting

```text
PROVIDER_DAILY_LIMIT = 100
W2_DAILY_CALL_CEILING = 80
MIN_PROVIDER_DAILY_REMAINING = 20
SHARED_LEDGER_BEFORE = 26
SHARED_LEDGER_AFTER = 28
TASK_REAL_VALIDATION_CALLS = 2
FINAL_PROVIDER_REMAINING_AT_ACCEPTANCE = 93
AUTOMATIC_RETRIES = 0
CACHE_RERUN_CALLS = 0
POST_RESTART_CACHE_CALLS = 0
```

## Repository hygiene result

```text
REPOSITORY_HYGIENE = PASS
DEAD_ASSETS_FOUND = 0
DEAD_ASSETS_DELETED = 0
OBSOLETE_CODE_LINES_REMOVED = 0
RETAINED_FOR_EVIDENCE = BRIDGE_IMPLEMENTATION_TESTS_RUNBOOK_AND_FINAL_RECEIPT
UNRESOLVED_HYGIENE_ITEMS = 0
```

Ignored local virtual environments and tool caches are not tracked repository
assets and were not included in the release.

## Waiting state

```text
NEXT = AWAIT_OWNER_ROUND_3_OR_BIG_FIVE_COLLECTION_DECISION
```

This state does not authorize another Provider validation, deployment, paid
plan, Provider cutover, whitelist change, recommendation enablement or Round 3
implementation.
