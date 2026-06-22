# ADR-0024 Shadow Operations and Gate 5 Preflight

Status: Accepted for local/staging preflight.

Release Train 2 keeps `DEPLOYMENT_FREEZE=ACTIVE` and does not deploy new code.
It adds local Stage9B shadow operations, Stage12B W1/W2 comparison, and Gate5
preflight evidence. Gate5 cannot close while Gate4 is still pending.

Shadow API reads PostgreSQL shadow tables first and reports `NO_RUN`, `RUNNING`,
`COMPLETED_EMPTY`, `COMPLETED_WITH_RESULTS`, or `ERROR`. It no longer depends on
mounted report files for runtime status.

Forward and retrospective evidence remain physically and semantically separated.
Retrospective replay can support technical validation, but it cannot substitute
for forward samples.
