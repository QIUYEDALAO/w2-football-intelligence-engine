# W2 Repository Agent Instructions

Before changing W2, read [`AI_PROJECT_CONTEXT.md`](AI_PROJECT_CONTEXT.md) and
[`PROJECT_STATE.yaml`](PROJECT_STATE.yaml). The detailed independent audit is
[`docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md`](docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md).

## Non-negotiable rules

- Treat code, database constraints, effective deployment configuration, and reproducible GitHub facts as evidence. Do not treat a PR description or status-file claim as proof.
- Missing or unknown safety inputs must deny execution.
- After a Provider request may have reached the external service, every downstream failure must be explicit and must stop further Provider calls.
- Never treat an `IntegrityError` as an idempotent no-op without verifying the expected constraint and the existing row's business fields.
- Do not swallow persistence failures or convert required empty evidence into success.
- Do not call the Provider, start persistent scheduler collection, or enable Candidate, Formal, Lock, or Production without explicit scoped authorization.
- A real canary fails if any required delta is zero or if the lineage cannot be reconciled.
- The valid split-line behavior `2/2.5 -> 2.25` is intentional and tested; do not “fix” it without real contrary Provider evidence.
- `src/w2/monitoring/readiness.py` is not a live Provider entrypoint. Its known issue is readiness aggregation, not hidden network execution.

## Current task

EVAL-02B remains blocked. The next work is runtime-safety and concurrency remediation for C1–C11 in the independent audit. EVAL-03 has not started.
