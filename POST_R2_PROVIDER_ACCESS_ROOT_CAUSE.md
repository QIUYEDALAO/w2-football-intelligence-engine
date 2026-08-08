# W2 Post-R2 — Provider Access Root Cause

```text
TASK = W2_MI_POST_R2_PROVIDER_ACCESS_AND_DATA_SOURCE_DECISION
EVIDENCE_DATE = 2026-08-08
ORIGIN_MAIN = b04dcc7e521dce413740bcf754b1a45755a3e83e
ORIGIN_CONTEXT_CURRENT_BASE = e9534b2864849c66f5864a24515cb3ef82c51614
ROOT_CAUSE = FREE_PLAN_SEASON_ENTITLEMENT_RESTRICTION
ROOT_CAUSE_CONFIDENCE = HIGH
INTERNAL_W2_FIX_REQUIRED = false
ROUND_3 = NOT_STARTED
```

## Conclusion

Round 2 did not fail because API-Football was disabled, the daily quota was
exhausted, the key was invalid, the league ID was wrong, or the W2 HTTP client
malformed the request. The paid subscription expired and the same active key is
now on the Free plan. That plan accepted `Premier League` (`id=39`) for
`season=2024`, but explicitly rejected `season=2025` and `season=2026` because
Free currently permits seasons 2022 through 2024 for this league.

The supported classification is therefore:

```text
FREE_PLAN_SEASON_ENTITLEMENT_RESTRICTION
```

The Round-2 `PLAN_RESTRICTED` classifier correctly represented the Provider's
`errors.plan` response. No internal code fix or PR is warranted.

## Why Round 2 used season 2026

The retained Round-2 evidence and `origin/main` implementation show:

- runtime whitelist rows used their copied runtime authority
  `provider_season=2026`;
- four audit-only candidates used the current UTC year, also 2026;
- `get_league(id, season)` issued
  `GET /leagues?id=<provider_id>&season=<season>`;
- authentication used the documented `x-apisports-key` header;
- `_provider_payload_error` mapped a Provider `errors.plan` field to
  `PROVIDER_PLAN_RESTRICTED` and the audit stopped fail-closed.

API-Football documents a season as its four-digit starting year. Therefore
`2026` is the correct representation for calendar-year 2026 competitions and
for European 2026/27 competitions. The controlled `2025` request was also
rejected while `2024` succeeded, proving the observed boundary is entitlement,
not an off-by-one W2 season mapping defect.

## Controlled diagnostic ledger

Exactly four new read-only Provider calls were attempted. There was no retry,
17-league rebatch, business database write, checkpoint write, Scheduler change,
credential output, or secret retention.

| # | Request | HTTP | Sanitized result | Evidence class |
|---:|---|---:|---|---|
| 1 | `GET /status` | 200 | `plan=Free`, `active=true`, `requests.current=0`, `limit_day=100`, daily remaining header `100` | `VERIFIED_BY_CALL` |
| 2 | `GET /leagues?id=39&season=2026` | 200 | `results=0`; `errors.plan`: Free has no access to this season; use 2022–2024 | `VERIFIED_BY_CALL` |
| 3 | `GET /leagues?id=39&season=2025` | 200 | same explicit Free-plan season restriction | `VERIFIED_BY_CALL` |
| 4 | `GET /leagues?id=39&season=2024` | 200 | `results=1`; `Premier League`, England, season 2024; no errors | `VERIFIED_BY_CALL` |

```text
NEW_DIAGNOSTIC_PROVIDER_CALLS = 4
TARGET_RANGE = 3_TO_5
MAX_AUTHORIZED = 8
AUTOMATIC_RETRIES = 0
BUSINESS_DB_WRITES = 0
CHECKPOINT_WRITES = 0
```

No calendar-year control was necessary: the same known league and league ID
isolated the season boundary with fewer calls.

## Root-cause discrimination

| Candidate cause | Result | Evidence |
|---|---|---|
| `FREE_PLAN_SEASON_ENTITLEMENT_RESTRICTION` | **CONFIRMED** | active Free account; 2025/2026 rejected by `errors.plan`; 2024 succeeds |
| `SEASON_PARAMETER_OR_SEASON_MAPPING_DEFECT` | Rejected | documented four-digit starting-year semantics; adjacent requests use the same valid request path; 2024 succeeds |
| `PROVIDER_COVERAGE_GAP` | Rejected for the observed stop | Provider returns Premier League 2024 and identifies `plan`, not missing coverage |
| `ACCOUNT_OR_KEY_ENTITLEMENT_MISMATCH` | Rejected as primary cause | `/status` matches owner fact: Free, active, 100/day |
| `REQUEST_SHAPE_OR_CLIENT_DEFECT` | Rejected | direct request shape matches W2; structured 200 responses and the 2024 success validate endpoint/header/ID |
| quota exhaustion / rate limit | Rejected | `/status` reported `current=0`, `limit_day=100`; no `requests` or rate-limit error |

## Official current source checks

- [API-Football pricing](https://www.api-football.com/pricing) documents Free
  at 100 requests/day, paid tiers, all endpoints/competitions, and the Free-plan
  season limitation.
- [API-Football documentation](https://www.api-football.com/documentation-v3)
  documents `/status`, the API-key header, GET-only access, and four-digit season
  parameters.
- [API-Football 2026 getting-started guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide)
  distinguishes quota from historical-season range and documents the seven-day
  pre-match odds retention limit.
- [API-Football terms](https://www.api-football.com/terms) state that an expired
  direct-dashboard subscription returns to Free.

## Required outcome

```text
CURRENT_PLAN_VERIFIED = FREE
CURRENT_ACCOUNT_ACTIVE_VERIFIED = true
CURRENT_DAILY_QUOTA_VERIFIED = 100
FREE_PLAN_CURRENT_SEASON_ACCESS = false
ROOT_CAUSE_CLASSIFICATION = FREE_PLAN_SEASON_ENTITLEMENT_RESTRICTION
ROOT_CAUSE_CONFIDENCE = HIGH
INTERNAL_FIX_REQUIRED = false
INTERNAL_FIX_PR = NONE
CURRENT_API_FOOTBALL_FREE_PATH_VIABLE = false
```

Free remains a functioning API tier, but it cannot supply W2's required current
2025/26 and 2026 data. A spend/data-source owner decision is required before the
current-season capability audit can resume. Round 3 remains not started.
