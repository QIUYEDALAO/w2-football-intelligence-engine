# W2 Stage10D Result

STAGE_10D=COMPLETED_LOCAL
BEIJING_OPERATIONAL_DAY=PASS
UTC_STORAGE=PASS
KICKOFF_BEIJING_DISPLAY=PASS
NO_JAPAN_TIME_WINDOW=true
PROVIDER_FIXTURE_COUNT_RECONCILED=true
READ_MODEL_DASHBOARD_COUNT_MATCH=true
FORMAL_RECOMMENDATION=false
CANDIDATE=false

## Beijing Operational Day

- Date: 2026-06-23
- Beijing window: 2026-06-23T00:00:00+08:00 to 2026-06-24T00:00:00+08:00
- UTC query window: 2026-06-22T16:00:00Z to 2026-06-23T16:00:00Z
- Provider requests: 3
- API key: PRESENT
- Remaining quota present: True

## Coverage

- Provider authoritative fixtures: 79
- World Cup fixtures in Beijing day: 4
- Normalized/database/read-model/displayed: 1/1/1/1
- Card count: 1
- Missing count: 78
- Coverage status: PARTIAL
- Reason distribution: `{'COMPETITION_FILTERED': 75, 'INCLUDED': 1, 'READ_MODEL_PROJECTION_MISSING': 3}`

## Dashboard One-Fixture Root Cause

The deployed Stage10C read model projected only one validated append-only snapshot: Argentina vs Austria. The old matchday API also interpreted date filtering by UTC date prefix, so Beijing 2026-06-23 did not align with the user-facing operational day. Stage10D fixes the API/Dashboard semantics to use Asia/Shanghai operational dates and exposes coverage warnings instead of silently showing a partial list.

## Stage7I

- Status: PASS
- Run ID: stage7i_20260622T183939Z_397fdfa
- Observer PID: 723789
- Sample count: 9
- First revision: 397fdfad607efbc1d2fcbdbe0ca305d7a8fcce64
- Current revision: 397fdfad607efbc1d2fcbdbe0ca305d7a8fcce64

## Final State

STAGE_10D=COMPLETED_LOCAL
BEIJING_OPERATIONAL_DAY=PASS
NO_JAPAN_TIME_WINDOW=true
SERVER_DEPLOYMENT=PAUSED_PENDING_APPROVAL
PUSH_BLOCKED_NO_ORIGIN
