# Owner SC18-00 FT Retention Remediation

```text
AUTHORITY = W2_SC18_00_FT_RETENTION_REMEDIATION_V1
PRIORITY = P0
TERMINAL_GATE = OWNER_SC18_00_FT_RETENTION_REREVIEW
```

## Observed failure

The following finished fixtures remained inside football day `2026-08-10`
(`2026-08-10T04:00:00Z` inclusive to `2026-08-11T04:00:00Z` exclusive) but
disappeared from the unified DayView and replay surface:

| fixture | kickoff UTC | terminal score |
|---|---|---|
| `1493049` | `2026-08-10T22:00:00Z` | `0-2` |
| `1575453` | `2026-08-10T19:15:00Z` | `2-2` |
| `1494239` | `2026-08-10T17:00:00Z` | `2-2` |

Persisted diagnosis also showed two independent defects: DayView discarded all
started/terminal cards, and UTC calendar-day discovery stopped refreshing the
still-active Asia/Shanghai football day between 08:00 and 12:00.

## Required invariant

- Service/repository football-day filtering remains the membership authority.
- DayView must retain every card already selected inside that window, including
  started, terminal, and result-pending fixtures.
- Natural SHADOW_ONLY discovery must use the active football-day date, allowing
  the existing write-side result materializer and settlement loop to consume
  terminal fixture payloads without any Provider call on API read.
- The three acceptance fixtures must be visible after FT and represented in
  replay. A real additional in-window fixture must not be hidden merely to force
  an exact synthetic count.

## Frozen controls

No manual Provider probe, new Provider, new endpoint, cadence change, whitelist
change, model/threshold change, Phase 0.5 rerun, Round 4/P6 start, or
Formal/Lock/Production/real-money activation is authorized.

## Closure evidence

- PR `#519` fixed active-football-day discovery and retained every persisted
  in-window card through terminal status.
- Live acceptance exposed one additional stale-status projection boundary;
  PR `#520` overlays current persisted fixture identity status without
  modifying the frozen analysis-card checkpoint.
- Exact implementation head:
  `37d4b5c5ac1ecf73473019ec6a088cfa6d0f76b4`.
- Exact main merge:
  `99baac47aad81d6afa0af9f368434bf93f14bd58`.
- Exact source tree:
  `46b88b10884bf84bb008cbb6773366f54d7ab52c`.
- Exact-head Full CI `31455118727`: `RELEASE_REQUIRED=PASS`.
- Main promotion `31455505907`: `PROMOTION_REQUIRED=PASS`, exact-head manifest
  reused.
- Local OCI relay verified both immutable digests; warm switch passed in 41
  seconds.
- Public football-day workspace `2026-08-10` contains five real cards. The
  three acceptance fixtures remain visible as `FINISHED` and remain present in
  replay. Persisted terminal scores are `0-2`, `2-2`, and `2-2`.
- Public read contract remains `provider_calls=0`, `db_writes=0`,
  `no_call_on_read=true`.
- The existing natural SHADOW_ONLY Scheduler supplied discovery and result
  materialization. No manual Provider probe or control-plane change occurred.
- These fixtures had no tracked candidate, so no settlement is claimed. The
  P0 retention and result-materialization path is closed without fabricating a
  validation sample.
- Repository Hygiene passed: both SC18-00 isolated worktrees were clean and
  removed; the primary worktree's pre-existing Owner edits were untouched.
  Locally generated temporary OCI archives were moved to the recoverable system
  Trash after direct deletion was safety-rejected; they are not tracked files.

Terminal state: `OWNER_SC18_00_FT_RETENTION_REREVIEW`.
