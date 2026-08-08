# W2 Codex Execution + Handoff Protocol

```text
AUTHORITY = W2_CODEX_EXECUTION_HANDOFF_PROTOCOL_V2
PURPOSE = GITHUB_AS_SINGLE_HANDOFF_LAYER
USER_COPY_PASTE_LONG_TASKS = NOT_REQUIRED
USER_COPY_PASTE_CODEX_REPORTS = NOT_REQUIRED
OWNER_MANUAL_MONITORING = NOT_REQUIRED
```

## 1. Permanent operating model

GitHub `context/current` is the single handoff layer between Owner, ChatGPT review, and Codex execution.

The Owner must not be required to manually carry detailed task instructions, completion reports, or completion notifications between ChatGPT and Codex.

At the start of every Codex run:

1. fetch latest `origin/main`;
2. fetch latest `origin/context/current`;
3. read this protocol;
4. read `CODEX_SELF_ACCEPTANCE_PROTOCOL.md`;
5. read `CURRENT_STATE.yaml`;
6. read `NEXT_ACTION.md`;
7. follow the binding read order in `NEXT_ACTION.md`;
8. execute only the currently authorized task and stop line;
9. run the complete self-acceptance/remediation loop before declaring review-ready.

If GitHub authority is inconsistent, stale, missing, or conflicts with actual repository evidence, stop and record the conflict in the execution receipt instead of guessing.

## 2. Permanent Codex bootstrap command

The Owner may use this same short instruction for every future Codex execution session:

```text
同步最新 origin/main 和 origin/context/current，严格执行 context/current/CODEX_EXECUTION_PROTOCOL.md；按 CURRENT_STATE.yaml 和 NEXT_ACTION.md 执行当前唯一授权任务，并按 CODEX_SELF_ACCEPTANCE_PROTOCOL.md 自验收、自修复到全部强制门槛 PASS 或明确 BLOCKED；完成后把标准回执写回 GitHub 并停在指定 Gate。
```

No stage-specific long prompt from the Owner is required when GitHub authority is complete.

## 3. Execution evidence rule

Do not treat PR descriptions, status files, code comments, or prior self-declared receipts as proof by themselves.

Use as applicable:

- current code / actual entrypoints
- schemas / models / migrations
- tests / contract tests / E2E
- actual runtime/read evidence
- Provider/call evidence when the task requires it
- CI status tied to exact head SHA
- repository reachability / hygiene evidence

## 4. Self-acceptance before handoff

Codex must execute `CODEX_SELF_ACCEPTANCE_PROTOCOL.md` before marking completion.

If a mandatory criterion fails and the fix remains within current authority, Codex must remediate and rerun the relevant gates automatically. It must not require the Owner to shuttle a failure report to ChatGPT merely to receive an obvious in-scope correction instruction.

Codex may stop only in one of two states:

```text
READY_FOR_CHATGPT_REVIEW
BLOCKED
```

## 5. Mandatory completion handoff

Every Codex run must create or update:

```text
CODEX_EXECUTION_RECEIPT.md
```

This file is the standard machine-readable/human-readable handoff for independent ChatGPT review.

Minimum receipt fields:

```text
EXECUTION_TASK
TERMINAL_GATE
STATUS
READY_FOR_CHATGPT_REVIEW
EXACT_ORIGIN_MAIN_SHA
EXACT_CONTEXT_BASE_SHA
EXACT_IMPLEMENTATION_BASE_SHA
EXACT_IMPLEMENTATION_HEAD_SHA
PR_NUMBER_OR_NONE
PR_STATE
CI_RUN_IDS
CI_TERMINAL_STATUS
CHANGED_FILES
ACCEPTANCE_MATRIX
TEST_EVIDENCE
RUNTIME_OR_READ_EVIDENCE
PROVIDER_CALLS
DB_BUSINESS_WRITES
SCHEDULER_OR_CADENCE_CHANGED
WHITELIST_CHANGED
MODEL_OR_THRESHOLD_CHANGED
ROUND_4_STATUS
CANDIDATE_STATUS
FORMAL_STATUS
LOCK_STATUS
PRODUCTION_STATUS
REPOSITORY_HYGIENE
WORKTREE_CLEAN
UNRESOLVED_ITEMS
NEXT_GATE
```

If a field is not applicable, write `NOT_APPLICABLE`; do not omit important control fields.

## 6. Mandatory context update at completion

Before Codex declares completion, it must update `context/current` so that:

- `CURRENT_STATE.yaml` reflects the actual terminal state;
- `NEXT_ACTION.md` reflects the actual next review gate or blocked state;
- `CODEX_EXECUTION_RECEIPT.md` contains the latest exact evidence;
- any task-specific packet required by `NEXT_ACTION.md` is updated;
- no next development phase is silently authorized.

Codex must stop exactly at the gate defined by current authority.

## 7. Visible Codex reply should be short

The full report belongs in GitHub, not in chat.

Preferred review-ready reply:

```text
DONE | context=<exact context/current SHA> | PR=<number-or-none> | head=<exact head SHA-or-none> | gate=<terminal gate>
```

If blocked:

```text
BLOCKED | context=<exact context/current SHA> | reason=<short reason> | gate=<terminal gate>
```

Do not duplicate the full receipt in the visible chat unless the Owner explicitly asks for it.

## 8. Automatic ChatGPT review handoff

The Owner does not need to paste the Codex report into ChatGPT or manually announce completion.

When `CODEX_EXECUTION_RECEIPT.md` reaches:

```text
STATUS = READY_FOR_CHATGPT_REVIEW
READY_FOR_CHATGPT_REVIEW = true
```

an external ChatGPT review watcher may detect the GitHub state and independently inspect the exact PR/head/diff/tests/CI and active acceptance authority.

The watcher must deduplicate reviews using `CHATGPT_REVIEW_RECEIPT.md` so the same exact implementation head is not repeatedly reviewed/notified.

## 9. ChatGPT → Codex task handoff

When ChatGPT/Owner review authorizes work or requires remediation, the detailed instruction must be written into GitHub authority files first, normally:

- `CURRENT_STATE.yaml`
- `NEXT_ACTION.md`
- the applicable Owner approval/review/remediation document

Once those files are complete, the Owner should only need the permanent bootstrap command in Section 2.

## 10. Permanent stop-line behavior

This protocol itself never authorizes a task, phase, merge, deployment, Provider call, Scheduler change, or production authority.

Actual authorization always comes from the latest `CURRENT_STATE.yaml`, `NEXT_ACTION.md`, and their referenced Owner authority.

For W2, unless explicitly changed by later Owner authority, preserve:

```text
PHASE_0_5_REEXECUTION = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
ROUND_4 = NOT_STARTED
```
