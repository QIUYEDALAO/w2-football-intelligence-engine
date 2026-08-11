# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_SC19_TEAM_IDENTITY_THEN_PERSISTED_DATE_STRIP
CURRENT_GATE = SC19_TEAM_IDENTITY_P0_ACTIVE
AUTHORITY = SC19_TEAM_IDENTITY_AND_DATE_STRIP_REMEDIATION.md
BASE_MAIN = 99baac47aad81d6afa0af9f368434bf93f14bd58
SC18_00_FT_RETENTION = OWNER_ACCEPTED_CLOSED_PASS
SC19_01_THROUGH_SC19_07 = AUTHORIZED_CONTINUOUS
SHADOW_CANDIDATE = KEEP_ACTIVE_SHADOW_ONLY
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
TERMINAL_GATE = OWNER_SC19_POSTDEPLOY_REREVIEW
```

## Binding priority

Do **not** start with the date strip.

First close the P0 public team-identity gap exposed on the five retained `2026-08-10` fixtures. Only after SC19-01/02 local acceptance passes may the date-strip work begin.

PR #520 is not pre-classified as the team-name root cause. Its code scope overlays current fixture status only. PR #518 introduced the reviewed canonical-team public-label authority and fail-closed placeholder behavior. The execution must trace the actual fixture -> provider team -> canonical team -> reviewed crosswalk -> public Chinese label chain before changing semantics.

## Binding read order

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. SC19_TEAM_IDENTITY_AND_DATE_STRIP_REMEDIATION.md
5. current main at 99baac47aad81d6afa0af9f368434bf93f14bd58
6. PR #518 team public-label authority
7. PR #519/#520 SC18-00 retention/status overlay
8. canonical team / provider crosswalk repository contracts
9. future_fixture_refresh and matchday intake persisted schedule policies
10. existing date navigation / market collection status helpers
```

## Execute continuously

1. **SC19-01 P0:** trace both teams for all five retained football-day fixtures through current persisted fixture identity, canonical team rows, reviewed crosswalks and public-label state. Classify the first missing authority precisely.
2. **SC19-02 P0:** recover every existing canonical/reviewed identity that is currently missed by projection/join. Preserve fail-closed behavior for genuinely unresolved identities; do not restore silent raw-English fallback and do not invent translations.
3. Require a local acceptance gate proving that a retained/finished fixture with reviewed canonical identity continues to display the canonical Chinese public name after status overlay and replay retention.
4. **Only after P0 PASS**, implement SC19-03 persisted `T-7..T+7` football-day date-strip contract using already stored fixtures/checkpoint data only.
5. Implement SC19-04 future-market semantics: `未进入市场采集窗口` is derived from persisted checkpoint timing; `市场证据未就绪` is used only when collection is due/past and usable evidence is absent. Never hard-code a universal Provider odds window.
6. Implement SC19-05 responsive date-strip UX. The data contract may contain 15 days; desktop/13-inch UI may render a seven-day slice with navigation. Each cell must show the fixture count and truthful state.
7. Future schedule counts must be described as current persisted inventory. Do not claim complete 13-league coverage unless the persisted coverage metadata proves it.
8. Derive empty-day `next_available_date` from the first later persisted football day with fixtures; otherwise say the current persisted range has not confirmed one.
9. Add SC19-06 regression/truth tests for identity preservation, status overlay, football-day 12->12 boundaries, partial future coverage, collection-window attribution and no-call/no-write reads.
10. Run focused/full Python, Ruff, MyPy, Web typecheck/build/full E2E, visual checks, label coverage, secret/tracked/protected/repository gates.
11. Require exact-head Full CI and `RELEASE_REQUIRED` PASS.
12. Merge automatically.
13. Redeploy only through Owner-local OCI relay.
14. Postdeploy verify exact Web/API identity, health/ready/release sync, real finished-team names/gaps, date strip, and `provider_calls=0`, `db_writes=0`, `no_call_on_read=true`.
15. Refresh context and Round4 exact release identity only, then stop at `OWNER_SC19_POSTDEPLOY_REREVIEW`.

Ordinary implementation/test/CI/deployment-preparation failures are in scope:

```text
fix -> revalidate -> continue
```

No Owner relay is required between SC19 steps.

## Mandatory acceptance cases

```text
finished retained fixture + reviewed canonical team identity
=> canonical Chinese public name visible after FT status overlay

recoverable mapping mismatch
=> repaired at authority join; generic placeholder forbidden

genuinely unresolved identity
=> explicit 身份待映射; raw provider English technical-only

T+future fixture + persisted first odds checkpoint still in future + no market evidence
=> 未进入市场采集窗口

T+future fixture + odds checkpoint due/past + no usable evidence
=> 市场证据未就绪

future date-strip coverage < 13 competitions
=> UI/read model cannot imply full 13-league schedule completeness

empty day + later persisted fixture day exists
=> next_available_date derives from persisted inventory

Dashboard reads
=> provider_calls=0, db_writes=0, no_call_on_read=true
```

## Frozen stop lines

```text
NEW_PROVIDER_OR_PLAN = NOT_AUTHORIZED
MANUAL_PROVIDER_PROBE = FORBIDDEN
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_CHANGE = NOT_AUTHORIZED
MODEL_RETRAINING = NOT_AUTHORIZED
BOOKMAKER_DEPTH_THRESHOLD_CHANGE = NOT_AUTHORIZED
MARKET_DIRECTION_BENCHMARK_DEFINITION = NOT_AUTHORIZED
EXTERNAL_INTELLIGENCE_ACTIVATION = NOT_AUTHORIZED
PHASE_0_5_REEXECUTION = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
ROUND_4_START = NOT_AUTHORIZED
P6_EXECUTION = NOT_AUTHORIZED
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = OFF
READ_PROVIDER_CALLS = 0_REQUIRED
READ_DB_BUSINESS_WRITES = 0_REQUIRED
VPS_DIRECT_GHCR_BULK_IMAGE_PULL = FORBIDDEN_AS_PRIMARY_TRANSPORT
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
DELETE_PROTECTED_HISTORICAL_EVIDENCE = FORBIDDEN
RAW_PROVIDER_ENGLISH_AS_LOCALIZED_SUCCESS = FORBIDDEN
```