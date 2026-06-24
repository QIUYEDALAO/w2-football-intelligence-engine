# W2 Stage7I-R1B2 Final Result

## Summary

- Stage package: `W2-STAGE7I-R1B2`
- Baseline contract commit: `7126f7540e8171dab83c1e2f81ab9a2b6c04fbbc`
- Staging revision: `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- Successor fixture: `1489404`
- Observer historical PID/PGID: `1435421 / 1435396`
- Observer sample count: `289`
- Observer coverage: `86487.295089s`
- Revision stable: `true`
- Final status: `BLOCKED_NON_QUALIFYING_LIFECYCLE_GAP`
- Gate5: `OPEN`
- Candidate output: `false`
- Formal recommendation output: `false`

R1B2 successfully selected and observed a dynamic successor fixture for more than
24 hours on one stable staging revision. The run is not Gate5-qualifying because
the independent lifecycle collector became inactive before the fixture lifecycle
completed. Required actual-kickoff, closing, result, settlement/evaluation, and
final Shadow DB evidence is therefore missing.

## 1. Legacy Run Disposition

The prior fixture `1489401` run was archived as `BLOCKED_NON_QUALIFYING`.

- Old observer PIDs: `723787`, `723789`
- Old observer PGID: `723782`
- Sample count: `177`
- `COMPLETED`: absent
- `summary.json`: absent
- `forward_complete=false`
- `gate5_eligible=false`
- Same-fixture restart: forbidden
- Candidate: `false`
- Formal recommendation: `false`

The legacy observer was terminated only under the separately approved recovery
work recorded by the earlier R1B2 evidence. No such signal or recovery action was
performed during the final read-only audit.

## 2. Successor Selection And Bootstrap

The successor was selected dynamically from W2 staging/provider evidence rather
than hardcoded fixture data.

- Selected fixture: `1489404`
- Scheduled kickoff: `2026-06-23T17:00:00Z`
- Selection source: `W2_STAGING_PROVIDER_DATA`
- Provider recovery requests used during the earlier bootstrap package: `3`
- Future fixtures recovered: `4`
- Selected-fixture bookmaker coverage: `14`
- Candidate manifest count: `1`
- Selector blocker: none
- Bootstrap checker: `PASS`

Observer runtime:

`/opt/w2/shared/runtime/stage7i/runs/stage7i_20260623T095944Z_1489404`

- Started: `2026-06-23T09:59:44.331436Z`
- Expected end: `2026-06-24T09:59:44.331436Z`
- Completed: `2026-06-24T10:01:11.955864Z`
- `COMPLETED`: present
- `summary.json`: present
- Process after audit buffer: not alive
- Sample count: `289`
- Coverage: `86487.295089s`
- Maximum sample gap: `300.338218s`
- Observation timestamps: strictly increasing
- Revision stable: `true`

## 3. Runtime Continuity Result

The observer-side stability evidence passed the 24h duration and revision
requirements:

- `w2-staging.service`: enabled/active in the final summary
- Long-running containers: healthy with unchanged restart counts
- API/Web: localhost-only
- Public business ports: none
- Server revision remained
  `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- Alembic head remained `0017_create_stage9a_shadow_strategy`
- Candidate: `false`
- Formal recommendation: `false`

The 24h observer completion is valid runtime-continuity evidence. It is not, by
itself, complete fixture-lifecycle or Gate5 evidence.

## 4. Lifecycle Evidence Gap

Historical lifecycle continuity evidence recorded the blocker
`STAGE7I_LIFECYCLE_COLLECTOR_INACTIVE`. At final audit time:

- Collector active: `false`
- `fixture_status.jsonl`: `1`
- `market_observations.jsonl`: `2`
- `request_audit.jsonl`: `7`
- `result_status.jsonl`: `0`
- Last market observation: `2026-06-23T13:24:35.678215Z`
- Last market bookmaker count: `14`
- Actual kickoff: `ACTUAL_KICKOFF_SOURCE_UNAVAILABLE`
- Closing: `PENDING_ACTUAL_KICKOFF`
- Final result evidence: missing
- Settlement/evaluation: `NOT_RUN_NO_RESULT`
- Final Shadow DB audit: `PENDING`

Scheduled kickoff, status-transition poll time, and external sources were not
used as substitutes for legal internal actual-kickoff evidence.

## 5. Final Builder And Checker

The final evidence builder was run against a local `/tmp` snapshot of selected
read-only staging evidence.

- Builder status: `BLOCKED`
- Builder blockers:
  - `ACTUAL_KICKOFF_SOURCE_UNAVAILABLE`
  - `PENDING_ACTUAL_KICKOFF`

Final checker:

```text
W2 Stage7I check FAIL: final status must be COMPLETED
```

The checker failure is expected and fail-closed: the observer completed, but the
fixture lifecycle evidence did not satisfy the final contract.

## 6. Gate5 Decision

Gate5 remains `OPEN`; this run is not eligible for Gate5 closure.

Missing requirements:

- legal internal actual kickoff;
- closing observation strictly before actual kickoff;
- final result evidence;
- post-result settlement/evaluation;
- final Shadow DB audit `PASS`;
- final checker `PASS`.

The run must not be relabeled, replayed, or supplemented retrospectively to
become qualifying forward evidence.

## 7. Safety Boundary

The final observation audit did not:

- recover the lifecycle collector;
- call the provider;
- send a signal;
- deploy or restart services or containers;
- write staging runtime data;
- read `.env`;
- modify W1;
- enable candidate output;
- enable formal recommendation output.

## 8. Validation And CI

Final audit package commit:

`f6cb856eeaafdfafe0fd314c390d14faafe8e486`

GitHub Actions:

- Run: `28091440346`
- Workflow: `W2 Stage 2 CI`
- Result: `success`

The package passed its targeted Stage7I contracts, full `make verify`
(`249 passed`), Mypy, secret scan, JSON validation, and `git diff --check`.

## 9. Recovery Point

Final classification:

`BLOCKED_NON_QUALIFYING_LIFECYCLE_GAP`

Any lifecycle recovery or successor observation must be a separately approved
stage package. The current run and its evidence gap cannot be reused to close
Gate5.
