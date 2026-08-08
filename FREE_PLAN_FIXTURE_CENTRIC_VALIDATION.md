# W2 Free-Plan Fixture-Centric Validation

```text
TASK = W2_MI_FREE_PLAN_FIXTURE_CENTRIC_BRIDGE
EVIDENCE_DATE_UTC = 2026-08-08
ORIGIN_MAIN = b04dcc7e521dce413740bcf754b1a45755a3e83e
ORIGIN_CONTEXT_CURRENT_BASE = 8cbbba09199b7178808b4b9f3a85a9a5b240b771
OUTCOME = FREE_FIXTURE_CENTRIC_CURRENT_DATA_WORKS
CAVEAT = FREE_PLAN_IDS_PARAMETER_RESTRICTED
PROVIDER_CALLS_ATTEMPTED = 5
AUTOMATIC_RETRIES = 0
BUSINESS_WRITES = 0
ROUND_3 = NOT_STARTED
```

## Decision

The active API-Football Free account can return current-season fixtures and
market data through no-season, fixture-centric request shapes. The controlled
proof returned a real 2026 Argentina Primera fixture, its fixture detail,
pre-match odds with both Asian Handicap and Goals Over/Under markets, and
fixture statistics.

The exact classified outcome is:

```text
FREE_FIXTURE_CENTRIC_CURRENT_DATA_WORKS
```

Free nevertheless rejected the multi-fixture `ids` parameter. This is a
capability restriction, not a blocker for the single-fixture bridge:

```text
FREE_PLAN_IDS_PARAMETER_RESTRICTED
FREE_DEFAULT_FOLLOW_UP_SHAPE = ONE_FIXTURE_ID_PER_REQUEST
```

This result does not overturn the already-proven
`FREE_PLAN_SEASON_ENTITLEMENT_RESTRICTION`. It narrows that root cause: current
league-plus-season enumeration is restricted, while current no-season fixture
discovery and fixture-id follow-ups work.

## Sanitized five-call ledger

All five calls were read-only, one-shot requests. No call included `season`, no
automatic retry ran, and no credential, auth header, raw response or business
record was retained.

| # | Request | HTTP | Result | Quota header after call |
|---:|---|---:|---|---:|
| 1 | `GET /fixtures?date=2026-08-08` | 200 | `results=1153`, no Provider errors; 25 fixtures mapped to existing W2 target league IDs | 98 |
| 2 | `GET /fixtures?id=1493055` | 200 | one current-season fixture; no Provider errors | 98 |
| 3 | `GET /odds?fixture=1493055` | 200 | one odds row, 14 bookmakers, AH and OU present | 97 |
| 4 | `GET /fixtures/statistics?fixture=1493055` | 200 | two team rows including ordinary match statistics and xG fields | 96 |
| 5 | `GET /fixtures?ids=1493055-1523228` | 200 | `results=0`; `errors.plan`: Free has no access to the `Ids` parameter | not returned |

The final confirmed daily-remaining header was 96, safely above the required
20-call reserve. The unsupported `ids` diagnostic returned no remaining header;
it is counted conservatively among the five attempted calls.

No adjacent-date or live discovery call was needed. Live odds were not tested
because the selected fixture was already full-time; testing them would have
violated the rule that live odds may be queried only for an actually live match.

## Real fixture evidence

```text
FIXTURE_ID = 1493055
LEAGUE_ID = 128
LEAGUE = Argentina Primera Division
SEASON_OBSERVED_IN_RESPONSE = 2026
KICKOFF = 2026-08-08T00:45:00+00:00
STATUS_AT_VALIDATION = FT
HOME = Independ. Rivadavia
AWAY = Estudiantes de Rio Cuarto
```

The odds response contained 14 bookmakers:

```text
10Bet, 1xBet, 888Sport, Bet365, BetVictor, Betano, Betfair, Dafabet,
Marathonbet, Pinnacle, SBO, Superbet, Unibet, William Hill
```

It exposed 157 distinct Provider market names. `Asian Handicap` and
`Goals Over/Under` were both present, and the response carried Provider update
time `2026-08-08T00:04:20+00:00`.

The statistics response contained two team rows and included possession,
shots, passes and the Provider fields `expected_goals` and `goals_prevented`.
This validates fixture-scoped extended data for this control; it does not claim
uniform xG availability for all leagues or fixtures.

## Bounded bridge implementation

```text
PR = https://github.com/QIUYEDALAO/w2-football-intelligence-engine/pull/495
BASE_SHA = b04dcc7e521dce413740bcf754b1a45755a3e83e
HEAD_SHA = d73882dcee3c37819f248f6048bc2308c146feb1
PR_STATE = OPEN
MERGEABLE = true
RUNTIME_DEFAULT = DISABLED
PRODUCTION_ACTIVATION = NOT_EXECUTED
```

The PR adds only a planner and replay/materialization adapter. It does not wire
the Scheduler or execute Provider calls. It:

- filters discovery to supplied existing target league IDs and caller-supplied
  due fixture IDs;
- de-duplicates fixture IDs and uses existing endpoint-capture request keys as
  cache keys;
- emits no follow-up calls when no target fixture is due;
- uses single `id` requests under the Free default and keeps bounded `ids`
  batching behind an explicit verified-capability flag;
- applies a conservative W2 hard cap and reserve guard;
- reuses `RawPayloadStore`, the existing endpoint-capture contract,
  `MatchdayFixtureIdentityV1`, and formal AH/OU normalization rather than
  creating a parallel data model.

## Verification

```text
FOCUSED_AND_CONTRACT_TESTS = 43_PASSED
RUFF = PASS
MYPY_STRICT = PASS_278_SOURCE_FILES
PR_FAST_REQUIRED = PASS
PR_FAST_PYTHON = PASS
CONTEXT_ONLY_NOT_APPLICABLE = PASS
```

An initial full-suite run reached 209 passed and 2 skipped before exposing two
architecture-matrix counts changed by the new module/test. The two exact matrix
counts were updated, and the affected contract suite then passed. GitHub's
required Python/Fast gates passed on the final head.

## Safety and stop line

```text
API_FOOTBALL_PRO_RENEWAL = NOT_EXECUTED
ACTIVE_WHITELIST = 13_UNCHANGED
NET_NEW_LEAGUE_ENABLEMENT = 0
PROVIDER_CUTOVER = NOT_EXECUTED
PRODUCTION_SCHEDULER_CHANGE = false
PERSISTENT_COLLECTION_EXPANSION = false
PRODUCTION_DB_WRITES = 0
PR_MERGE = NOT_EXECUTED
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_PR_REVIEW_AND_CONTROLLED_ACTIVATION_DECISION
```

## Repository hygiene

```text
REPOSITORY_HYGIENE = PASS
DEAD_ASSETS_FOUND = 2_TRANSIENT_DIAGNOSTIC_SCRIPTS
DEAD_ASSETS_DELETED = 2_TRANSIENT_DIAGNOSTIC_SCRIPTS
OBSOLETE_CODE_LINES_REMOVED = 0
RETAINED_FOR_EVIDENCE = 2_FINAL_REPORTS_PLUS_SANITIZED_LEDGER_SUMMARY
UNRESOLVED_HYGIENE_ITEMS = 0
```

The open PR's three changed files are retained as implementation, tests and the
contract-protected architecture count update. The two one-shot local diagnostic
scripts were removed after their sanitized facts were transferred here.
