# W2 Repository Hygiene Policy

This is a permanent W2 engineering rule. Every task/round must run a repository-hygiene closure before it may be declared fully complete.

## Core rule

```text
TASK_GOAL_REACHED != TASK_FULLY_CLOSED
TASK_FULLY_CLOSED = FUNCTIONAL_ACCEPTANCE_PASS + REPOSITORY_HYGIENE_PASS
```

After the task objective is achieved, inspect all code/files/assets touched or made obsolete by the task and delete anything that is provably no longer needed.

The objective is to prevent W2 from accumulating dead compatibility layers, abandoned experiments, duplicate scripts, stale fixtures, temporary generated files and superseded assets.

## Evidence-based deletion only

Delete an asset only when repository evidence proves it has no remaining required role.

Required proof should include as applicable:

```text
NO_RUNTIME_IMPORTS_OR_REFERENCES
NO_CLI_OR_ENTRYPOINT_REFERENCE
NO_ROUTE_OR_API_REFERENCE
NO_SCHEDULER_OR_WORKFLOW_REFERENCE
NO_CONFIG_DISCOVERY_REFERENCE
NO_TEST_OR_FIXTURE_DEPENDENCY
NO_CI_OR_RELEASE_GATE_DEPENDENCY
NO_MIGRATION_OR_SCHEMA_HISTORY_REQUIREMENT
NO_BACKWARD_COMPATIBILITY_REQUIREMENT
NO_AUDIT_OR_ACCEPTANCE_EVIDENCE_RETENTION_REQUIREMENT
NO_DOCUMENTED_REUSABLE_TOOLING_ROLE
```

Do not delete based only on naming, age, comments, PR descriptions or intuition.

## Assets that should normally be removed when obsolete

Examples:

```text
superseded implementation files
dead components/modules/classes/functions
obsolete wrappers/adapters after authority migration
unused feature flags and their dead branches
one-off migration helpers after their supported lifecycle ends, when no rollback/history requirement remains
stale test fixtures for removed behavior
duplicate config files superseded by one canonical authority
temporary audit/debug scripts with no reusable role
generated scratch outputs accidentally tracked in Git
old static assets no longer referenced by any product surface
abandoned experimental code not serving preserved historical evidence
compatibility shims whose supported compatibility window has ended
```

## Assets that must not be deleted merely to make the repository smaller

Preserve when still required:

```text
DB/schema migrations required for history or upgrade paths
final task receipts and acceptance evidence
security/release/audit evidence required for traceability
current context authority
reusable validated audit/diagnostic tooling
CI/release/deployment scripts still invoked by workflows
backward-compatibility paths still consumed by supported callers
historical replay/settlement evidence required by W2 contracts
user-approved protected baselines
licenses/notices/legal provenance
```

## Mandatory task-close procedure

Before declaring any task PASS:

1. list all files added, changed, replaced or made obsolete by the task;
2. classify each as `KEEP`, `DELETE`, or `RETAIN_FOR_EVIDENCE`;
3. search repository imports/references/entrypoints/workflows/config discovery;
4. delete every `DELETE` asset in the same task closure when safe;
5. remove dead imports, exports, flags, tests and documentation references created by those deletions;
6. run focused tests plus repository-required static/contract tests;
7. record the cleanup result in the final receipt.

Required final receipt fields:

```text
REPOSITORY_HYGIENE = PASS
DEAD_ASSETS_FOUND = <count>
DEAD_ASSETS_DELETED = <count>
OBSOLETE_CODE_LINES_REMOVED = <count when measurable>
RETAINED_FOR_EVIDENCE = <list/count>
UNRESOLVED_HYGIENE_ITEMS = 0
```

If a suspected dead asset cannot be proven safe to delete, classify it as `REVIEW_REQUIRED`, do not guess, and explain the exact unresolved dependency. A task may not silently claim hygiene PASS while known dead assets remain without justification.

## No cleanup scope creep

Repository hygiene is allowed to remove dead/obsolete material created or exposed by the completed task. It is not authority for unrelated refactors or architecture redesign.

```text
CLEANUP != REWRITE
CLEANUP != NEW_FEATURE
CLEANUP != BEHAVIOR_CHANGE
```

Deletion must preserve accepted runtime/product behavior.

## Current Round 2 application

Round 2 R2-C must include a hygiene pass after the final capability matrix is assembled and before Round 2 is declared PASS.

Specifically inspect:

```text
Round 2 temporary audit scaffolding
one-off debug helpers
tracked dry-run scratch outputs
superseded audit fixtures
obsolete observation-heartbeat glue
stale 14-day-only control artifacts no longer required after terminal closure
any duplicate context/task entrypoints superseded by current authority
```

Do not delete reusable league-audit tooling merely because Round 2 ends. Keep it if it remains a supported capability-audit tool.

Do not delete Round 1/2 final receipts, audit evidence indexes, sanitized evidence hashes or permanent product/context authority required for traceability.
