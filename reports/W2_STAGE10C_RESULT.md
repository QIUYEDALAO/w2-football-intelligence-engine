# W2 Stage10C Result

STAGE_10C=COMPLETED_LOCAL
SERVER_DEPLOYMENT=IN_PROGRESS_APPROVED
FORMAL_RECOMMENDATION=false
CANDIDATE=false
DEEPSEEK=false

## Deployment

- Approved initial release: `d506f019e64471863292f143bb08557f30c1be2f`
- Previous staging revision: `b5d354303c3093dcc8c4aea8c15a69d1ce674f26`
- Compose project: `w2-staging`
- Migration status: `NO_OP_ALREADY_AT_HEAD`
- Production deployment: `DISABLED`
- Public business ports: `NONE`

## Live Daily Cycle

- actual_fixture_count=1
- Fixture: `1489399` Argentina vs Austria
- kickoff_utc=`2026-06-22T17:00:00+00:00`
- source_snapshot_id=`20260622T163004_391908Z`
- source_captured_at=`2026-06-22T16:30:04.391908+00:00`
- matchday_status=`SETTLEMENT_PENDING`
- temporal_status=`POSTMATCH_RECOMPUTED_FROM_LOCKED_PREMATCH`
- integrity_status=`PASS`
- markets_present=`ONE_X_TWO,ASIAN_HANDICAP,TOTALS,BTTS`
- missed_prematch_window_count=0

## Card State

- action=`WATCH`
- published_grade=`C`
- gate4_status=`PROVISIONAL_FORWARD_HOLDOUT_PENDING`
- primary_market=`ONE_X_TWO`
- primary_selection=`AUSTRIA_WIN`
- primary_executable_odds=`8.2500`
- primary_market_quality=`WATCH_ONLY`
- primary_outlier_status=`OUTLIER`
- secondary_market=`ASIAN_HANDICAP`
- secondary_selection=`AUSTRIA`
- secondary_line=`+0.75`
- secondary_executable_odds=`2.5200`
- secondary_market_quality=`READY`

`WARN_ONLY`: the displayed primary direction is a watch-only outlier price from the all-market ranking. It remains research-only and is not a formal recommendation. The cleaner executable direction remains the secondary Austria +0.75 line.

## Read Model Wiring

- Added Stage10C report projector: `scripts/project_stage10c_matchday_read_model.py`
- Read model sink: `read_model_checkpoint`
- checkpoint_count=3
- fixture_count=1
- API priority: PostgreSQL Stage10C checkpoint, then report file fallback, then legacy dashboard fixture fallback.
- Web/Dashboard remains same-origin through `/api/v1/...` and `/api/ops/...`.

## Validation

- `scripts/check_w2_stage10b.py`: PASS
- `scripts/check_w2_stage10c.py`: PASS
- `scripts/project_stage10c_matchday_read_model.py --dry-run`: PASS
- `tests/unit/test_stage10c_matchday.py`: PASS
- `ruff`/`mypy`: PASS for touched code before full verification

## Final State

- STAGE_10C=COMPLETED_LOCAL
- DASHBOARD_LIVE_READ_MODEL=READY_FOR_FINAL_STAGING_DEPLOY
- MATCHDAY_ALL_MARKET_CARDS=READY_LOCAL_STAGING
- FORMAL_RECOMMENDATION=false
- CANDIDATE=false
- GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING
- STAGE_9=BLOCKED
- PUSH_BLOCKED_NO_ORIGIN
