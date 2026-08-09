# W2 Post-R3 Track A Natural Evidence Closure Audit

```text
TASK = W2_POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE
RESULT = TRACK_A_CLOSED_PASS
TRACK_A = CLOSED_PASS
RECURRING_INTERNAL_DEFECT = NOT_PROVEN
ROUND_4 = NOT_STARTED
```

## Technical conclusion

Track A is closed on persisted, source-bound evidence. The initial public-read
audit found 38 naturally ended T12/T6/T3/T60 windows after the controlled
Round-3 interval. Eight windows contained an in-window endpoint capture,
covering every checkpoint class and all four naturally represented active
competitions. The VPS source-bound refresh then resolved the only material
ambiguity: the clearest missing-window recurrence is frozen-policy behavior,
not a scheduler, request-ledger, capture, normalization or readiness defect.

For canonical fixture `api_football:1523233`, T12 is persisted as `CAPTURED`
with request, endpoint-capture, plan-link, raw-payload and normalization
lineage. Its T6 window is persisted as `MISSED` with blocker
`CHECKPOINT_MISSING`, no claim, attempt count zero, no request row and no
capture. At the same time, persisted odds quota usage was 80, exactly the
unchanged W2 worker/scheduler daily hard cap, although the Provider plan limit
was 100. Exact-main runtime keeps per-fixture future refresh disabled and the
free bridge in `SHADOW_ONLY`; naturally scheduled bridge tasks completed with
zero Provider calls and zero business writes. The T6 gap is therefore an
explicit terminal non-execution under frozen policy, not a recurring internal
defect.

The existing Round-3 repository lineage reader was then reused to reproject the
64-fixture / 128 fixture-market frozen cohort using persisted observations only.
It found 23 post-baseline market rows and reconciled current timeline depth as
`0:89 / 1:8 / 2+:31`. Model Lab remains honestly `MARKET_NOT_READY:128`; Track A
does not reinterpret that product readiness state as model proof.

## Exact authority and isolation

| Item | Value |
|---|---|
| Exact `origin/main` | `d61768ecf8457a72df80a5cb0220072de76dfdd4` |
| Exact context base | `1ae340d99f14e841d9f6a61b1a0d8b97a2b2c374` |
| Final audit `as_of` | `2026-08-09T07:33:14Z` |
| Source-bound reprojection `as_of` | `2026-08-09T07:27:28.076436Z` |
| Runtime deployed source | `d61768ecf8457a72df80a5cb0220072de76dfdd4` |
| Frozen attribution baseline | `2026-08-08T10:19:12Z` / 128 fixture-markets |
| Provider calls for audit | `0` |
| Database business writes | `0` |
| Production-code changes | `0` |

The exact 13-league whitelist and every runtime stop line remain unchanged. No
Provider probe, Scheduler/cadence, quota-policy, whitelist, model, factor,
threshold or runtime change was made.

## Naturally crossed checkpoint evidence

| Checkpoint | Ended windows | In-window captures |
|---|---:|---:|
| `T12_ODDS` | 13 | 2 |
| `T6_ODDS` | 6 | 2 |
| `T3_ODDS` | 7 | 2 |
| `T60_ODDS_LINEUPS` | 12 | 2 |
| **Total** | **38** | **8** |

The eight captured windows span Allsvenskan, Brasileirão Série A, Chinese Super
League and Eliteserien. The complete historical window matrix remains in the
machine-readable artifact; the final source-bound refresh supplements rather
than rewrites that frozen public-read cohort.

## Source-bound recurrence resolution

```text
DUE_WINDOW_BUT_NO_FRESH_CAPTURE = EXPECTED_POLICY_TERMINAL
CHECKPOINT_STATUS = MISSED
CHECKPOINT_BLOCKER = CHECKPOINT_MISSING
CLAIMED = false
ATTEMPT_COUNT = 0
REQUEST_ROW_IN_WINDOW = ABSENT
CAPTURE_IN_WINDOW = ABSENT
ODDS_QUOTA_USED = 80
FROZEN_W2_DAILY_HARD_CAP = 80
PROVIDER_PLAN_LIMIT = 100
INTERNAL_DEFECT = NOT_PROVEN
```

This trace distinguishes policy terminal behavior from a broken collection
path. The same fixture's earlier T12 path has complete persisted source
lineage, and other naturally successful windows disprove a global outage.

## Frozen baseline and current reprojection

The accepted baseline remains unchanged:

```text
TIMELINE_DEPTH = 0:92 / 1:9 / 2+:27
MODEL_LAB = MARKET_NOT_READY:125 / MODEL_NOT_READY:2 /
            INSUFFICIENT_BOOKMAKER_DEPTH:1
PROJECTION_SOURCE_EVENT_AT = 2026-08-08T10:19:12Z FOR ALL 128 ROWS
```

The bounded source-bound reprojection reports:

```text
PERSISTED_OBSERVATIONS_ONLY = true
FIXTURES = 64
FIXTURE_MARKETS = 128
ENRICHED_EVIDENCE_ROWS = 23577
POST_BASELINE_MARKET_ROWS = 23
TIMELINE_DEPTH = 0:89 / 1:8 / 2+:31
ROWS_WITH_ANY_SNAPSHOT = 39
ROWS_WITH_2_PLUS = 31
MODEL_LAB = MARKET_NOT_READY:128
PROVIDER_CALLS = 0
DB_BUSINESS_WRITES = 0
```

The result is a reconciliation of existing natural evidence, not synthetic
collection and not a model/readiness promotion.

## Terminal decision and stop line

The evidence satisfies terminal classification A:

```text
TRACK_A_CLOSED_PASS
```

`ROUND4_READINESS_DECISION_PACKET.md` is produced as evidence only. Round4 is
still `NOT_STARTED` and requires separate Owner authority.

```text
REPOSITORY_HYGIENE = PASS
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
SHA256 = 317b2b71cb211d8e4e8175eb8224f2acafc4e6bd3aba08672ab92e005f05876f
ENDED_WINDOWS = 38
```
