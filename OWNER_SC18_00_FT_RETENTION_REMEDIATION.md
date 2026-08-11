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
