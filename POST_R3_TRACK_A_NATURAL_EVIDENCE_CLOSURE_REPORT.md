# W2 Post-R3 Track A Natural Evidence Closure Audit

```text
TASK = W2_POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE
RESULT = WAIT_MORE_NATURAL_EVIDENCE
TRACK_A = NOT_CLOSED
RECURRING_INTERNAL_DEFECT = NOT_PROVEN
ROUND_4 = NOT_STARTED
```

## Technical conclusion

Natural post-restore evidence is now meaningful but not source-bound enough to
close Track A safely. At the audit `as_of` of
`2026-08-09T06:10:16.671712Z`, 38 T12/T6/T3/T60 windows had ended after the
controlled Round-3 interval. Eight windows have a DB-backed latest endpoint
capture timestamp inside the legal window, covering every checkpoint class and
all four represented active competitions. The public collection reader marks
all eight `READY`, which proves that each visible endpoint capture is linked to
persisted market observations.

The same read surface exposes 30 ended windows without a complete terminal
trace: 26 still point to a capture before the window and four point to a later
capture while the within-window history is not exposed. The clearest recurrence
condition is Chinese Super League fixture `1523233`, T6 window
`05:35:00–06:05:00Z`: its latest endpoint capture remains the successful T12
capture at `00:01:23Z`, while `next_refresh_at` advanced to T3 at `08:35:00Z`.
Thus `DUE_WINDOW_BUT_NO_FRESH_CAPTURE` did recur after restore.

That observation is not yet proof of an internal defect. The public read
surface does not expose the checkpoint terminal status/reason, scheduler task
identity, request-ledger row, quota state, or raw/endpoint capture identity for
the missing window. A quota/policy terminal reason and a scheduler/task defect
cannot be distinguished honestly. Successful captures in all four represented
competitions also disprove a global path outage. The only evidence-correct
classification is therefore `WAIT_MORE_NATURAL_EVIDENCE`.

## Exact authority and isolation

| Item | Value |
|---|---|
| Exact `origin/main` | `d61768ecf8457a72df80a5cb0220072de76dfdd4` |
| Exact context base | `713b8aea3cc1cef81d729b5f21b3ee54a61a4962` |
| Audit `as_of` | `2026-08-09T06:10:16.671712Z` |
| Runtime deployed source | `51ebbeabc5497ce48708b3587705e2922c4805da` |
| Read source | public DB-backed Dashboard read API |
| Frozen attribution baseline | `2026-08-08T10:19:12Z` / 128 fixture-markets |
| Frozen baseline SHA-256 | `01999b11e5eea10cf4d68460bb5ba6d1f71c83820709adaaa104a1e5992c58fa` |
| Provider calls for this audit | `0` |
| Database business writes | `0` |
| Production-code changes | `0` |

The exact 13-league authority remains unchanged. The current evidence cohort
contains only the four naturally represented active competitions:
Allsvenskan, Brasileirão Série A, Chinese Super League and Eliteserien. No
whitelist, Scheduler, cadence, Provider policy, model, factor, threshold or
runtime flag was changed.

## Naturally crossed checkpoint evidence

| Checkpoint | Ended windows | Latest capture inside window |
|---|---:|---:|
| `T12_ODDS` | 13 | 2 |
| `T6_ODDS` | 6 | 2 |
| `T3_ODDS` | 7 | 2 |
| `T60_ODDS_LINEUPS` | 12 | 2 |
| **Total** | **38** | **8** |

The eight positive window examples are:

| Competition | Fixture | Checkpoint | Window | Capture |
|---|---:|---|---|---|
| Chinese Super League | 1523229 | T60 | Aug 8 10:35–10:55Z | Aug 8 10:36:14Z |
| Chinese Super League | 1523230 | T60 | Aug 8 10:35–10:55Z | Aug 8 10:36:16Z |
| Brasileirão Série A | 1492323 | T12 | Aug 8 11:30–12:00Z | Aug 8 11:31:21Z |
| Allsvenskan | 1494237 | T3 | Aug 8 12:30–13:00Z | Aug 8 12:31:13Z |
| Eliteserien | 1494729 | T3 | Aug 8 13:00–13:30Z | Aug 8 13:01:14Z |
| Eliteserien | 1494731 | T60 | Aug 8 13:00–13:20Z | Aug 8 13:01:11Z |
| Brasileirão Série A | 1492326 | T6 | Aug 8 13:00–13:30Z | Aug 8 13:01:17Z |
| Chinese Super League | 1523233 | T12 | Aug 8 23:35–Aug 9 00:05Z | Aug 9 00:01:23Z |

These timestamps are persisted endpoint-capture hints, not synthetic points.
For the eight `READY` rows, exact-main public collection semantics additionally
prove that the endpoint capture ID is present in persisted normalized market
observations. The public response does not reveal the new capture IDs, raw
payload hashes, request IDs or quota snapshots, so the matrix labels those
fields partial rather than fabricating lineage.

## Recurrence and cause boundary

```text
DUE_WINDOW_BUT_NO_FRESH_CAPTURE = RECURRENCE_CONDITION_OBSERVED
INTERNAL_SCHEDULER_CACHE_LEDGER_CAPTURE_NORMALIZATION_DEFECT = NOT_PROVEN
```

Fixture `1523233` is the minimum conclusive recurrence example. The T6 window
ended at `06:05:00Z`; at `06:10:16Z` the latest endpoint capture was still
`00:01:23Z`, and the public next checkpoint had advanced to T3. This proves no
fresh endpoint capture was visible for T6. It does not prove why.

The missing source-bound terminal fields are exact and finite:

- checkpoint terminal status and reason for every ended window;
- scheduler task ID or explicit non-execution reason;
- request-ledger identity and quota state;
- raw-payload and endpoint-capture identity for post-baseline captures;
- a post-baseline Round-3 reprojection carrying current timeline and Model Lab
  status.

Until those fields are readable from persisted evidence, classifying the gap as
quota/policy terminal behavior or as an internal defect would exceed the data.

## Frozen projection reconciliation

The accepted baseline remains exactly:

```text
TIMELINE_DEPTH = 0:92 / 1:9 / 2+:27
MODEL_LAB = MARKET_NOT_READY:125 / MODEL_NOT_READY:2 /
            INSUFFICIENT_BOOKMAKER_DEPTH:1
PROJECTION_SOURCE_EVENT_AT = 2026-08-08T10:19:12Z FOR ALL 128 ROWS
```

The public collection overlay sees later endpoint captures, but the persisted
Round-3 projection still points to the frozen source event. Therefore a truthful
current 0/1/2+ or Model Lab matrix cannot be produced from the exposed fields.
This audit does not copy, interpolate or synthesize those later captures into
Market Radar. The frozen baseline is preserved and the current reprojection is
reported as unavailable, not as unchanged product truth.

## Next natural evidence windows

The first future legal windows after the audit `as_of` are:

| Start–end (UTC) | Competition | Fixture | Checkpoint |
|---|---|---:|---|
| 06:30–07:00 | Eliteserien | 1494727 | T6 |
| 07:00–07:30 | Brasileirão Série A | 1492320 | T12 |
| 07:00–07:30 | Brasileirão Série A | 1492327 | T12 |
| 08:00–08:30 | Brasileirão Série A | 1492324 | T6 |
| 08:00–08:30 | Chinese Super League | 1523232 | T3 |
| 08:30–09:00 | Allsvenskan | 1494233 | T6 |
| 08:30–09:00 | Allsvenskan | 1494234 | T6 |
| 08:35–09:05 | Chinese Super League | 1523233 | T3 |

Waiting is event-based. The next audit must require source-bound terminal rows,
not merely more elapsed time or another timestamp-only `READY` overlay. No
artificial collection or cadence change is authorized.

## Repository Hygiene and stop line

Only context authority/evidence files are changed. No runtime, API, scheduler,
schema, migration, configuration, test, dependency or production-code file is
modified. `ROUND4_READINESS_DECISION_PACKET.md` is intentionally absent because
the evidence is not sufficient to make that decision meaningful.

```text
REPOSITORY_HYGIENE = PASS
ROUND4_READINESS_DECISION_PACKET = NOT_CREATED_EVIDENCE_INSUFFICIENT
PROVIDER_CALLS_FOR_AUDIT = 0
DB_BUSINESS_WRITES = 0
PRODUCTION_CODE_CHANGES = 0
SCHEDULER_OR_CADENCE_CHANGES = 0
WHITELIST_CHANGES = 0
MODEL_OR_THRESHOLD_CHANGES = 0
PHASE_0_5_REEXECUTION = 0
ROUND_4 = NOT_STARTED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

Machine-readable evidence:

```text
POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_MATRIX.json
SHA256 = adf0dc4844851e2f96f6d15d11b9688212748f817fbc543be85a6f4ae72a227c
ENDED_WINDOWS = 38
```
