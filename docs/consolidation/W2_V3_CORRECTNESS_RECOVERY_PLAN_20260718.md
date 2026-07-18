# W2 V3 Correctness Recovery Plan

Status: `ACTIVE`  
Baseline: `main@7c7f16fd2c44468ba4932ef83473bd35f285cbd4`

This plan supersedes recovery-era implementation sequencing. PRs #333–#346 are
specification and failure-case inputs only; they are not a backlog to restore.

## Ordered gates

| Phase | Single objective | Exit condition |
|---|---|---|
| R0.0 | Freeze current baseline evidence | Current-tree CI, identity, schema, runtime and restore proof |
| R0.1a | Quote identity observation projection | Identity explainable without product changes |
| R0.1b | Stale and missing-time quote isolation | No stale or timeless current quote |
| R0.1c | Non-READY no-pick invariant | No pick, ANALYSIS_PICK, RECOMMEND or lock outside READY |
| R0.2 | Real readiness | Critical dependency failures return 503 |
| R0.3 | Fixture-scoped bounded reads | No public global observation/raw/history scans |
| R0.4 | Three-fixture sidecar materialization | Same input produces the same immutable hash |
| R0.5 | Frozen analysis-card canary | Public analysis-card performs no model/provider/wall-clock build |
| R0.6 | Frozen DayView canary | DayView and detail endpoints share one frozen authority |
| R1 | Reliability and product quality | Metrics, batch writes, degradation, ops and Web contracts pass |
| R2 | Offline deterministic model corrections | Offline/shadow validation; no champion change |
| R3 | Forward shadow evidence | At least 200 canonical settled samples with clean identity |
| R4 | Separate human reviews | RECOMMEND, champion and production reviewed independently |

## Frozen invariants

- One behavior-changing PR per phase, created from the latest merged main.
- Full local checks and `verify`, `staging-parity`, `predeploy-e2e` before merge.
- No recommendation threshold, denominator, track or league-enable changes.
- No provider calls during acceptance and no historical ledger/capture rewrites.
- RECOMMEND, lock, OFFICIAL and production remain closed through R3.
- R0.4 uses a separate `read_model_checkpoint` canary namespace; no business table.
- Root `/ready` becomes canonical in R0.2; `/v1/ready` is a temporary exact alias.

## Hard measures

- Visible current quote identity: 100%.
- Current quote older than 30 minutes or missing captured_at: 0.
- STALE/BLOCKED/INCOMPLETE with pick: 0.
- Invalid RECOMMEND downgraded to ANALYSIS_PICK: 0.
- Public provider/model/wall-clock rebuild: 0.
- Public global observation/raw history scans: 0.
- Readiness critical failures returning 503: 100%.
- R0 performance p95: no more than 1.10x the R0.0 baseline.
- R0 RSS: no more than 1.20x the R0.0 baseline; restart/OOM: 0.
- R3 canonical forward settled shadow: at least 200 before any R4 review.

