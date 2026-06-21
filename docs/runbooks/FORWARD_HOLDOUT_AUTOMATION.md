# Forward Holdout Automation

Stage 7D provides the automation foundation for the forward holdout cycle. It does not enable
autorun or live networking.

## Defaults

- `W2_FORWARD_HOLDOUT_AUTORUN=false`
- `W2_FORWARD_HOLDOUT_NETWORK=false`
- minimum provider quota reserve: `2500`
- per-cycle cap: `100`
- hard stop when remaining quota is unknown

The schedule policy lives in `config/policies/forward_holdout_schedule.v1.json`. All Celery Beat
entries are disabled until explicitly approved in a later stage.

## Offline Rehearsal

Run the dry cycle:

```bash
uv run python scripts/run_stage7d_dry_cycle.py
uv run python scripts/check_w2_stage7d.py
```

The rehearsal uses fictional fixtures only. It validates T-24h and T-1h locks, duplicate lock
prevention, kickoff lock rejection, result append-only behavior, settlement idempotency, checkpoint
resume, and Gate 4 staying pending.

## Live Operation Boundary

Do not enable live scheduling from this stage. A later approval must specify:

- allowed network window
- request budget
- API key injection path
- cycle cadence
- operator rollback procedure

If quota is unknown, below reserve, or the provider returns 401, 403, or 429, the cycle must stop
and emit an operational alert. Request audits must never record provider keys or authentication
headers.

## Status Outputs

Expected Stage 7D status:

- `STAGE_7D=COMPLETED`
- `FORWARD_HOLDOUT_AUTORUN=DISABLED_PENDING_APPROVAL`
- `GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING`
- `STAGE_9=BLOCKED`
