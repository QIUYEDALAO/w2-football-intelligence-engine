# V2-FORWARD-PREREG-AMENDMENT-01 status matrix

| Requirement | Status | Evidence |
|---|---|---|
| protocol frozen before result | PASS | commit `cb958902`; protocol SHA `aa0d7e14...dd52` |
| old preregistration preserved | PASS | exact file SHA `cad4b549...36c1` |
| old status | `SUPERSEDED_BEFORE_FIRST_SAMPLE` | successor binding |
| zero rows before amendment | `CONFIRMED_RECORD_NOT_LIVE_QUERIED` | POINT-EV release/schema; V2 migration absent |
| fresh production query | NOT PERFORMED | production reads `0` |
| complete successor identity | PASS | successor JSON and `EVIDENCE.json` |
| successor semantic identity | PASS | `bf2b539d...4e98` |
| exact cohort start | UNRESOLVED | no activation authority; rows forbidden |
| start resolution rule | PASS | max(freeze, activation effective time) |
| backfill before resolved start | FORBIDDEN | successor cohort contract |
| base variant | FROZEN PRIMARY | `BASE_PRE_LINEUP` |
| lineup variant | NO ROWS ALLOWED | separate preregistration required |
| full denominator | PASS | all eligible scheduled opportunities |
| strict pair numerator | PASS | `fixtures_with_paired_v1_production_capture` |
| POINT-EV epoch | PASS | `POINT_EV_FAIL_CLOSED / ea557bb8` |
| one-look date/sample | PASS | `2028-02-01T00:05Z / 5,500` |
| interim metric look | FORBIDDEN | successor first-evaluation contract |
| old HOLDOUT role | PLANNING ONLY | contaminated prior, not confirmation |
| validator/check | PASS | successor and old-file hashes |
| validator self-test | PASS | 5/5 mutants caught |
| canonical serializer parity | PASS | production authority independently returns `bf2b539d...4e98` |
| focused/package matrix tests | PASS | 7 passed |
| Ruff | PASS | full repository |
| mypy | PASS | 299 `src apps`; strict validator |
| full pytest | BASELINE-EQUIVALENT | 2,973 passed / 5 failed / 9 skipped; same five Task 4 failures |
| Gate 1 | **FAIL** | prospective confirmation absent |
| Gate 2 | **CLOSED** | no admission authority |
| Provider / production R/W | PASS | `0 / 0 / 0` |
| deployment / migration / collector | PASS | `0 / 0 / 0` |
| candidate / notification | PASS | `0 / 0` |
| alpha / beta | PASS | `NULL / NULL` |

Terminal role: `SUCCESSOR_FROZEN_NO_ROWS_ALLOWED_UNTIL_ACTIVATION_AUTHORITY`.
