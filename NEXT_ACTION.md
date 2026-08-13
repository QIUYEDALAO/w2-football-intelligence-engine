# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_SC21_STAGE14_FACTOR_COVERAGE_AND_MODEL_INPUT_CONVERGENCE
CURRENT_GATE = SC21_FACTOR_INPUT_CONVERGENCE_ACTIVE
AUTHORITY = SC21_STAGE14_FACTOR_COVERAGE_AND_MODEL_INPUT_CONVERGENCE.md
BASE_MAIN = 3b7f87db2f0cb49d75582313ca593d30262c0d3d
DEPLOYED_SOURCE = VERIFY_AND_RECONCILE_FIRST
PR_531 = MERGED_RETAIN_DAILY_MATCH_BROWSER
PR_532 = MERGED_RETAIN_EXACT_13_T168_T72_T48_COLLECTION
PR_533 = MERGED_RETAIN_CHECKPOINT_DIRECT_FIXTURE_TRUTH
SC20_SINGLE_PUBLIC_AUTHORITY = CLOSED_PASS_RETAIN
SHADOW_CANDIDATE = KEEP_ACTIVE_SHADOW_ONLY
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
TERMINAL_GATE = OWNER_SC21_FACTOR_INPUT_CHAIN_POSTDEPLOY_REREVIEW
```

## Binding conclusion

The next bottleneck is model/factor input coverage, not merely AH/OU presence. The provisional live snapshot reports persisted market evidence for 19/19 reviewed future fixtures, but only 3/19 have usable four-field xG and no fixture currently forms an影子候选.

Do not start by enabling every Provider endpoint. First establish the exact current factor truth, then repair persisted-evidence and no-Provider materialization paths in hard-gate order.

## Continuous execution order

1. **SC21-00 — exact identity/context reconciliation**
   - sync exact main/context;
   - measure API/Web/worker/scheduler deployed identities;
   - prove PR #532 and PR #533 are the running collection authorities;
   - if accepted merged main is not deployed, deploy it through Owner-local OCI relay before the live audit.

2. **SC21-01 — Stage14 Factor Coverage Truth Matrix V2, read-only**
   - exact active 13 competitions;
   - exact persisted T+7 fixture inventory, including the reported 19 fixtures;
   - per fixture/team/factor source, row count, as-of, freshness, identity, materialization, model role, candidate role and request cost;
   - distinguish `NOT_YET_DUE`, `DUE_NOT_COLLECTED`, `RAW_ABSENT`, `RAW_PRESENT_NOT_MATERIALIZED`, `IDENTITY_NOT_MAPPED`, `UNDER_SAMPLED`, `STALE`, `POLICY_DISABLED`, `PROVIDER_NOT_AVAILABLE`, `READY`;
   - Provider calls 0, business writes 0.

3. **SC21-02 — persisted-evidence xG convergence**
   - xG is the current simulation hard gate;
   - inventory persisted statistics/raw xG evidence, team xG match rows and rolling snapshots;
   - run saved-raw materialization first;
   - fix parser/identity/as-of/sample/projection defects without Provider calls;
   - no proxy xG, no post-kickoff leakage;
   - if live statistics collection is truly required, create an Owner decision packet and continue all independent work. Do not enable statistics automatically.

4. **SC21-03 — rating/Elo materialization from existing evidence**
   - canonical as-of authority only;
   - exclude `rolling_xg_proxy` / `PROXY_ONLY` from eligible model rating;
   - no Provider calls, no weight changes;
   - missing rating remains an enhancement gap, not the xG blocker.

5. **SC21-04 — team-value as-of materialization**
   - reuse `scripts/materialize_team_value_asof.py` and the existing canonical writer;
   - dry-run, exact eligible count/artifact hash, then controlled write;
   - require valid player/team identity and as-of evidence;
   - no invented mappings and no Provider calls.

6. **SC21-05 — lineup timing and deferred-domain truth**
   - preserve T-60/T-45/T-30; do not collect early;
   - separate not-yet-due, due-no-attempt, Provider-empty and captured;
   - injuries remain policy-disabled/not audited;
   - H2H remains diagnostic;
   - matchday statistics remains disabled unless separately approved.

7. **SC21-06 — public factor semantics**
   - keep the single accepted `scope + cause -> PublicPresentation` authority;
   - xG: 模型核心输入未就绪;
   - lineup before window: 尚未到首发采集时间;
   - rating/value: 增强输入未就绪;
   - policy-disabled domains: 当前策略未启用/仅作审计;
   - market evidence without exact quote: 市场证据可见，精确候选报价未就绪;
   - never collapse every condition into `必需输入缺失`.

8. **SC21-07 — shadow candidate chain acceptance**
   - preserve RecommendationDecisionV4 unchanged;
   - independently verify market freshness/depth, exact executable quote, four-field xG/model output, candidate model identity and settlement evidence;
   - one eligible market must not be erased by another weak market;
   - zero candidates remains a valid result if no fixture passes.

9. **SC21-08 — full verification and deployment**
   - separate reviewable PRs by authority boundary;
   - exact-head CI and `RELEASE_REQUIRED` on each implementation PR;
   - automatic merge after pass;
   - final deploy through Owner-local OCI relay;
   - VPS materialization writes only as `dry-run -> exact count/hash guard -> controlled apply`;
   - reproduce the postdeploy matrix and verify `provider_calls=0`, `db_writes=0`, `no_call_on_read=true` on reads;
   - refresh Round4 exact identity only and stop.

Ordinary audit/parser/identity/materialization/projection/UI/test/CI/deployment-preparation failures are in scope:

```text
fix -> revalidate -> continue
```

No Owner relay is required between in-scope steps. If one branch requires a new Provider/plan, new live endpoint, cadence/whitelist change, external dataset, model/threshold change or manual identity invention, create a decision packet for that branch and continue all independent branches.

## Mandatory role distinction

```text
four-field xG missing
=> simulation hard gate, model unavailable

rating / team value missing
=> model enhancement not ready under current simulation policy

lineup before T-60/T-45/T-30
=> NOT_YET_DUE, not a collection incident

persisted market snapshot exists but stale
=> historical evidence visible, current comparison/candidate paused

market aggregate exists but exact executable quote missing
=> no candidate; never promote Radar median
```

## Frozen stop lines

```text
NEW_PROVIDER_OR_PLAN = NOT_AUTHORIZED
MANUAL_PROVIDER_PROBE = FORBIDDEN
NEW_LIVE_STATISTICS_COLLECTION = NOT_AUTHORIZED_WITHOUT_DECISION_PACKET
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_WEIGHT_THRESHOLD_CHANGE = NOT_AUTHORIZED
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
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
DELETE_PROTECTED_HISTORICAL_EVIDENCE = FORBIDDEN
RADAR_MEDIAN_AS_EXECUTABLE_QUOTE = FORBIDDEN
PROXY_XG_AS_TRUE_XG = FORBIDDEN
POST_KICKOFF_FACTOR_LEAKAGE = FORBIDDEN
```