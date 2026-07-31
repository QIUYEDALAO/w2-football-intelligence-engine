# W2 GitHub Copilot Instructions

Read `/AI_PROJECT_CONTEXT.md` and `/AGENTS.md` before proposing or changing code.

The current task is EVAL-02B runtime-safety and concurrency remediation. Provider calls,
real canary execution, persistent scheduler, Candidate, Formal, Lock, and Production are
not authorized.

Apply these invariants everywhere:

1. Missing or unknown safety inputs deny execution.
2. Failures after a possible external Provider side effect are persisted, surfaced, and
   stop further calls.
3. Idempotency is accepted only after the expected constraint and stored business fields
   are verified.
4. Required zero evidence is failure, not normal completion.
5. A canary passes only when every required delta is positive and one full lineage is
   reconciled.

Do not modify the tested split-line mapping `2/2.5 -> 2.25` without real contrary Provider
evidence. `readiness.py` is a status calculator, not a Provider live-call entrypoint.
