# W2 Stage7I Final Observation Audit

## Summary

- Stage package: Stage7I 24h final observation audit
- Fixture: `1489404`
- Runtime:
  `/opt/w2/shared/runtime/stage7i/runs/stage7i_20260623T095944Z_1489404`
- Expected end: `2026-06-24T09:59:44.331436Z`
- Audit time: `2026-06-24T10:08:23.452395Z`
- Decision: `BLOCKED_NON_QUALIFYING_LIFECYCLE_GAP`
- Gate5: `OPEN`
- Candidate: `false`
- Formal recommendation: `false`

The Stage7I observer itself completed naturally and wrote both `COMPLETED` and
`summary.json`. The run is not Gate5-qualifying because the lifecycle collector
was inactive before the fixture lifecycle completed, leaving no legal internal
actual kickoff evidence, no closing observation, no final result evidence, no
settlement/evaluation, and no final Shadow DB audit.

## Read-Only Boundary

This audit did not recover the lifecycle collector, send signals, stop the
observer, deploy, restart services or containers, call the provider, read `.env`
content, modify W1, or write staging runtime data.

## Observer Evidence

- Historical PID/PGID: `1435421` / `1435396`
- Process after buffer: not alive
- `COMPLETED`: present
- `summary.json`: present
- Started at: `2026-06-23T09:59:44.331436Z`
- Completed at: `2026-06-24T10:01:11.955864Z`
- Sample count: `289`
- Coverage seconds: `86487.295089`
- Observation timestamps: strictly increasing
- Maximum sample gap: `300.338218` seconds
- Server revision: `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- Revision stability: `true`
- Latest systemd: enabled/active
- Long-running containers: healthy, restart count unchanged in summary
- Public business ports: none
- API/Web: localhost-only policy remained true

## Lifecycle Evidence

- Lifecycle collector active after window: `false`
- `fixture_status.jsonl`: `1`
- `market_observations.jsonl`: `2`
- `result_status.jsonl`: `0`
- `request_audit.jsonl`: `7`
- Last market observation: `2026-06-23T13:24:35.678215Z`
- Last market bookmaker count: `14`
- Last market live: `false`
- Last market suspended: `false`
- Last market raw payload SHA256:
  `057f07726020e622b88830def284d87cc079c25029ba5f5aea31c1214940187d`

## Boundary Evidence

- Actual kickoff: unavailable from legal internal provider fields
- Closing observation: unavailable because actual kickoff is unavailable
- Final result evidence: absent
- Settlement/evaluation: not run; no result evidence exists
- Forward/retrospective separation in builder output: `true`
- Final Shadow DB audit: `PENDING`

Scheduled kickoff and first poll time were not used as substitutes for actual
kickoff.

## Final Builder And Checker

The final evidence builder was run against a local `/tmp` snapshot copied from
selected staging evidence files, not against staging runtime directly.

- Builder output path: `/tmp/w2_stage7i_final_evidence_from_snapshot.json`
- Builder status: `BLOCKED`
- Builder blockers:
  - `ACTUAL_KICKOFF_SOURCE_UNAVAILABLE`
  - `PENDING_ACTUAL_KICKOFF`

Final checker command:

```bash
python3 scripts/check_w2_stage7i.py --mode final --expected-fixture-id 1489404 /tmp/w2_stage7i_final_evidence_from_snapshot.json
```

Checker result:

- Exit code: `1`
- Summary: `W2 Stage7I check FAIL: final status must be COMPLETED`

## Gate5 Decision

Gate5 remains `OPEN`.

The run is not eligible for Gate5 closure because required lifecycle evidence is
missing:

- legal actual kickoff source
- closing observation strictly before actual kickoff
- final result evidence
- settlement/evaluation after result
- final Shadow DB audit PASS
- final checker PASS

## Classification

Selected classification:

`BLOCKED_NON_QUALIFYING_LIFECYCLE_GAP`

Rationale: observer completion is proven, but lifecycle collector interruption
created a non-qualifying evidence gap.
