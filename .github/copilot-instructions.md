# W2 GitHub Copilot Instructions

Read `/AI_PROJECT_CONTEXT.md`, `/PROJECT_STATE.yaml`, `/NEXT_ACTION.md`, `/AGENTS.md`, `/docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md`, `/docs/operations/W2_ASSET_UNIQUENESS_AUDIT_20260731.md`, and `/docs/operations/W2_AUDIT_PERSPECTIVE_REGISTRY.md` before proposing or changing code.

GitHub Issue **#454 v4** is the execution authority; #455 is the workflow-governance authority; #456 is the computation-authority authority.

## Source and branch rules

- First synchronize GitHub to a local clean worktree and record exact `origin/main`.
- Do not work from PR #453 or any `agent/eval-02b-c9-*` branch.
- Do not merge/rebase/cherry-pick `e875050f6bc0286aed389aadfce1e17b2063635a` or another automation-authored remediation commit.
- PR #453 is quarantined evidence and must never be merged.

## Current order

```text
T00-GOV
T00-SAFE R1-R5 + asset inventory
versioned canonical serialization authority/migration
trusted-main C9 rebuild
remaining Gate A one-shot-canary remediation
offline fake-Provider rehearsal
independent second review
```

## Invariants

1. Missing, malformed, stale, unknown or unverifiable safety inputs deny execution.
2. Failures after a possible Provider side effect are persisted, surfaced, stop later calls and forbid automatic retry.
3. Idempotency requires expected-constraint and full stored-business-field verification.
4. Required zero evidence is failure.
5. Canary PASS requires positive deltas, one reconciled lineage and independent pair-hash/seed recomputation.
6. Context follows verified code/GitHub evidence.
7. Completion statements name covered and uncovered audit perspectives.
8. Same-origin tests do not replace an independent oracle.
9. One business fact has one computation authority or explicitly versioned different definitions.
10. Historical hashes are not overwritten without a versioned migration.

## R5 computation authority

- Scan duplicate serializers, hashes, formulas, taxonomies, numeric types/rounding and same-name cross-layer classes.
- The known six runtime canonical serializers are a minimum, not the final denominator.
- Do **not** choose `ensure_ascii=True` or `False` until persisted hash domains and compatibility costs are inventoried.
- The canonical serializer contract must explicitly freeze version, UTF-8, key order, compact separators, Unicode, `allow_nan=False`, numeric/Decimal/date/datetime and unsupported-type behavior.
- Use one versioned authority under `src/w2/domain/`; retain explicit compatibility readers where required.
- Do not rewrite historical identity/hash fields in place.
- Add independent Chinese/NaN/numeric/datetime/pair-hash/bootstrap-seed golden vectors.
- CI must reject a second unapproved canonical hash serializer.
- Fair odds, market taxonomy and Brier/ECE convergence is Gate C unless T00 proves direct Gate A impact.

## Audit-perspective growth

Every incident/anomaly/new finding must map to an existing perspective or add a new perspective in the same remediation. Do not close with `UNMAPPED_PERSPECTIVE > 0`. Major closure requires an independent reviewer; otherwise status is `SELF_REVIEWED_ONLY` or `PARTIAL`.

## Emergency fixes

Containment is not final closure. Post-incident review covers R1–R4, plus R5 when hash/formula/taxonomy/precision is touched, and any other affected perspective.

```text
CONTAINED_PENDING_POST_INCIDENT_REVIEW
```

## Workflow prohibition

Do not add a workflow that uses `contents: write` to rewrite business implementation, pushes to a business PR branch, or configures a bot author and executes `git push`. All source changes are normal local edits/commits/pushes/Draft PRs.

## Operational stop line

Provider calls, real canary authorization, persistent scheduler, Candidate, Formal, Lock, Production and auto merge are not authorized. Stop after the offline evidence package and report:

```text
REAL_PROVIDER_CALL_EXECUTED = false
REAL_CANARY_AUTHORIZATION_CREATED = false
AUTO_MERGE_EXECUTED = false
READY_FOR_INDEPENDENT_SECOND_REVIEW = true|false
```

Do not modify tested split-line mapping `2/2.5 -> 2.25` without contrary Provider evidence. `readiness.py` is a status calculator, not a Provider live-call entrypoint.
