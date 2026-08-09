# Dashboard V4.1 Postdeploy Remediation Acceptance Receipt

```text
AUTHORITY = W2_DASHBOARD_V41_POSTDEPLOY_BOUNDED_REMEDIATION_V1
RESULT = OWNER_DASHBOARD_V41_POSTDEPLOY_REREVIEW
PR = 507
IMPLEMENTATION_BASE_SHA = c6d8c6c7304d302f31bea5a88967e3bc9e945b37
SOURCE_HEAD_SHA = 99e4acc275edc94ae012c12dd541609b2be3fffe
SOURCE_TREE_SHA = ec11f9a15d0cac1e7f49bf722f1fd1b760d856e6
FINAL_MAIN_SHA = 6787b7f12a74f69f76e0f4f88c9a875cece66673
FULL_CI_RUN = 31336303846
PROMOTION_RUN = 31336887357
RELEASE_REQUIRED = PASS
ROUND_4 = NOT_STARTED
ROUND_4_EXECUTION_AUTHORITY = NOT_GRANTED
```

## D16 closure

| Finding | Result | Evidence |
|---|---|---|
| D16-01 public mode/system authority | CLOSED | one Chinese day-mode badge; raw `BLOCKED_DAY` becomes scoped `PARTIAL_DEGRADATION` |
| D16-02 priority/focus eligibility | CLOSED | exact primary eligibility; useful 1/2+ evidence focus; zero-evidence rows are other-attention |
| D16-03 primary reason auditability | CLOSED | dedicated main reason plus subordinate secondary reasons; primary-only counts |
| D16-04 Chinese four-risk copy | CLOSED | Chinese source-bound explanations; codes retained in technical detail |
| D16-05 causal summary | CLOSED | one canonical evidence/conclusion/recovery summary authority |
| D16-06 nested desktop scrolling | CLOSED | desktop focus/shortlist nested vertical scroll removed; responsive natural flow retained |
| D16-07 validation checkpoint truth | CLOSED | exact `AVAILABLE/STALE/INCOMPLETE/NOT_AVAILABLE` state model |

## Verification

```text
FOCUSED_PYTHON = 41 passed
FULL_LOCAL_PYTHON = 2538 passed, 8 skipped, 1 existing sudo-prompt test deselected
FULL_WEB_E2E = 51 passed
TYPECHECK = PASS
WEB_BUILD = PASS
RUFF = PASS
MYPY = PASS
SECRET_SCAN = PASS
TRACKED_OUTPUTS = PASS
PROTECTED_EVIDENCE = PASS
REPOSITORY_HYGIENE = PASS
EXACT_HEAD_FULL_CI = PASS
RELEASE_REQUIRED = PASS
```

Exact-head CI supplied the authoritative migration, staging parity, integration,
unit/contract, static-contract, Web E2E, Python/Web image build, image smoke,
release manifest and `RELEASE_REQUIRED` result.

The deterministic D16 browser matrix covered 1180, 1280x720, 1366x768,
1512x982, 1536x1024, 200% zoom, keyboard focus, 0/1/2+ snapshots and the frozen
four day/focus modes. Revised acceptance targets are:

```text
1366x768 = sha256:1689ee5ac87ce2fd5712bb078205cc5b0a80bdf3f78f47218d98b3cdf4cae410
1512x982 = sha256:bd97246f2a62c35683c963d2db80d3d26124c1fb44a90ec6cb34dc6d003b9d24
```

## Release and deployment

| Evidence | Result |
|---|---|
| Python image | `sha256:b628d0a749b04ec87915c73406268242b1c3f2544af4aa072ca607fd756939ec` |
| Web image | `sha256:1c259ba82fd9961a28c033b6a01dcf2ae35ee42f4889abc284683e9ea7f48b8a` |
| Transport | local OCI relay primary; both exact digests verified |
| Main promotion | PASS, run `31336887357` |
| Warm switch | PASS in 34 seconds; target 300 seconds |
| Health / ready / release sync | PASS / PASS / PASS |
| Rollback | not required |

No SSH or Fail2ban configuration was changed during this release. No Provider
probe/call, Scheduler/cadence change, whitelist change, model/factor/threshold
change, Phase 0.5 rerun, external-intelligence connection, Candidate/Formal/Lock/
Production enablement, P6 execution or Round4 start occurred.

## Live real-payload acceptance

```text
schema = w2.dashboard-intelligence-workspace.v1
Web/API source identity = 99e4acc275edc94ae012c12dd541609b2be3fffe
data_profile = real-db
data_source = read_model_checkpoint
day_mode = NORMAL
default_focus_type = MATCH
default_focus_fixture_id = 1492329
match_count = 3
attention_count = 3
raw_system_health = BLOCKED_DAY
public_system_health = PARTIAL_DEGRADATION
priority_primary = STALE_MARKET_MEMORY
priority_secondary_includes = MARKET_MOVEMENT
zero_evidence_default_focus = false
global_model_quality = STALE
provider_calls = 0
db_writes = 0
would_write_checkpoint = false
no_call_on_read = true
```

The live payload used only the exact seven intelligence states and exact four
risk axes. All public risk explanations were Chinese-first, attention and match
used the same factual summary, and current stale evidence correctly dominated
historical movement. Immediately adjacent to a live unified-endpoint GET, the
persisted vector was unchanged:

```text
provider_request_logs = 685 | max 2026-08-09 00:01:19.347942+00
matchday_endpoint_captures = 532 | max 2026-08-09 00:01:19+00
read_model_checkpoint = 674 | max 2026-08-08 10:31:34.788657+00
```

## Repository hygiene

```text
CHANGED_FILES = 17
DEAD_ASSETS_FOUND = 0
DEAD_ASSETS_DELETED = 0
OBSOLETE_CODE_LINES_REMOVED = 127
RETAINED_FOR_EVIDENCE = 2 revised D16 screenshot targets plus existing protected history
UNRESOLVED_HYGIENE_ITEMS = 0
REPOSITORY_HYGIENE = PASS
```

## Terminal boundary

```text
NEXT_GATE = OWNER_DASHBOARD_V41_POSTDEPLOY_REREVIEW
NEXT_AUTOMATIC_ACTION = NONE
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
```
