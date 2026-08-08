# W2 Codex Self-Acceptance Protocol

```text
AUTHORITY = W2_CODEX_SELF_ACCEPTANCE_PROTOCOL_V1
PURPOSE = EXECUTE_VALIDATE_REMEDIATE_UNTIL_REVIEW_READY
OWNER_MANUAL_MONITORING = NOT_REQUIRED
```

## 1. Operating rule

For every authorized Codex task, Codex must not stop merely because implementation work is finished.

Codex owns the complete pre-review loop:

```text
EXECUTE CURRENT AUTHORIZED TASK
↓
RUN ALL TASK-SPECIFIC ACCEPTANCE CRITERIA
↓
RUN REQUIRED FOCUSED TESTS / CONTRACT TESTS / STATIC CHECKS
↓
RUN REQUIRED EXACT-HEAD CI
↓
RUN REPOSITORY HYGIENE
↓
IF ANY ACCEPTANCE ITEM FAILS:
    FIX ONLY WITHIN CURRENT AUTHORIZED SCOPE
    RE-RUN THE FAILED AND DEPENDENT ACCEPTANCE GATES
    REPEAT UNTIL PASS OR GENUINELY BLOCKED
↓
WRITE CODEX_EXECUTION_RECEIPT.md
↓
SET READY_FOR_CHATGPT_REVIEW = true
↓
STOP AT THE DEFINED REVIEW GATE
```

A self-declared `DONE` is forbidden while any mandatory acceptance criterion is failed, pending, unknown, or not executed.

## 2. Acceptance authority

Codex must build its exact acceptance checklist from the latest GitHub authority, in this order:

1. `CURRENT_STATE.yaml`
2. `NEXT_ACTION.md`
3. the Owner approval/review/remediation file referenced by `NEXT_ACTION.md`
4. `DASHBOARD_INTELLIGENCE_WORKSPACE_PRODUCT_SPEC.md` when applicable
5. task-specific contracts / schemas / acceptance files referenced by the active authority
6. `REPOSITORY_HYGIENE_POLICY.md`
7. this self-acceptance protocol

The active task authority may add stricter criteria. This protocol never weakens them.

## 3. Mandatory acceptance matrix

Before review-ready status, `CODEX_EXECUTION_RECEIPT.md` must contain a concrete PASS/FAIL/NOT_APPLICABLE result for every required item, including at minimum:

```text
SCOPE_CONFORMANCE
PRODUCT_CONTRACT_CONFORMANCE
SCHEMA_OR_API_CONTRACT_IF_APPLICABLE
NEGATIVE_FAIL_CLOSED_TESTS_IF_APPLICABLE
FOCUSED_TESTS
FULL_REQUIRED_TESTS
STATIC_CHECKS
EXACT_HEAD_CI
NO_UNAUTHORIZED_PROVIDER_CALLS
NO_UNAUTHORIZED_DB_BUSINESS_WRITES
NO_UNAUTHORIZED_SCHEDULER_OR_CADENCE_CHANGE
NO_UNAUTHORIZED_WHITELIST_CHANGE
NO_UNAUTHORIZED_MODEL_OR_THRESHOLD_CHANGE
STOP_LINES_PRESERVED
REPOSITORY_HYGIENE
WORKTREE_CLEAN
UNRESOLVED_ITEMS
```

For current Owner Review B remediation on PR #498, all acceptance items in `OWNER_REVIEW_B_REMEDIATION.md` are mandatory and must be individually recorded.

## 4. Self-remediation authority

Codex may automatically remediate failures only when the fix is clearly inside the currently authorized task scope.

It must stop `BLOCKED` instead of guessing when a fix would require any of the following without explicit authority:

- new phase authorization
- new Provider call / provider purchase / provider cutover
- Scheduler or cadence change
- whitelist change
- model, factor or threshold change
- migration or DB business write not already authorized
- Phase 0.5 rerun
- Round 4
- Candidate / Formal / Lock / Production enablement
- destructive legacy cleanup outside the authorized cleanup phase
- product-semantic change

## 5. Review-ready completion signal

Codex may set the following only after all mandatory acceptance gates pass:

```text
STATUS = READY_FOR_CHATGPT_REVIEW
READY_FOR_CHATGPT_REVIEW = true
TERMINAL_GATE = <exact gate from NEXT_ACTION.md>
```

If blocked:

```text
STATUS = BLOCKED
READY_FOR_CHATGPT_REVIEW = false
BLOCK_REASON = <evidence-backed reason>
```

## 6. ChatGPT independent review boundary

Codex self-acceptance is a prerequisite, not final approval.

ChatGPT review must independently inspect the exact implementation head, PR diff, schemas/contracts, tests, CI tied to the exact head, runtime/read evidence as applicable, and repository hygiene. ChatGPT must not accept the Codex receipt as proof by itself.

## 7. No owner relay requirement

Once Codex has been started with the permanent bootstrap instruction, the Owner is not required to:

- monitor Codex progress;
- copy the task again;
- copy Codex's completion report into ChatGPT;
- manually tell ChatGPT that Codex finished.

Completion is signaled through GitHub `CODEX_EXECUTION_RECEIPT.md`, and ChatGPT's configured review watcher may detect that signal and perform the independent review.
