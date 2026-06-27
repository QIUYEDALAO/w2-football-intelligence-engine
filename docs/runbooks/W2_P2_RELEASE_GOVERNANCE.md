# W2 P2 Release Governance

Status: governance baseline for P2 T17-T20.

## Purpose

This runbook makes P2 review repeatable. It covers August validation planning,
FORMAL decision review, API-Football quota upgrade planning, and PR/release
guardrails. It does not enable runtime collection or production release.

## Mandatory PR Answers

Every W2 PR touching validation, provider quota, competition scope, release
gates, or public recommendation copy must answer:

- Which task IDs are covered.
- Whether runtime competition whitelist changes.
- Whether production deploy is required.
- Whether any DB migration is destructive.
- Whether demo or staging seed is enabled.
- Whether FORMAL/CANDIDATE remain disabled.
- Whether runtime `beats_market` remains false.
- Whether odds, scores, EV, xG, or hit rates are derived from real data.
- Whether as-of locked market snapshots are preserved.
- Whether push/void settlement semantics are preserved.
- Whether API-Football quota reserve remains active.
- Which tests and release-sync checks were run.

## Risk Matrix

| Risk | Required mitigation |
| --- | --- |
| FORMAL/CANDIDATE leakage | Contract tests and runtime checks must show false. |
| `beats_market=true` drift | Gate tests must show false until a separate approved unlock PR. |
| Fake hit rate | Zero-sample summaries must return `hit_rate=null` and sample-insufficient copy. |
| Post-match line leakage | Settlement must use locked as-of market snapshots only. |
| Quota exhaustion | Reserve guard must protect odds/lineups before enrichment/backfill. |
| Runtime whitelist expansion | Must be in a separate approved PR with rollback and quota evidence. |
| Provider credential exposure | Never print `.env`; never commit sensitive values. |
| Production accident | Production deploy must remain out of scope unless explicitly authorized. |

## Release Checklist

For runtime PRs:

```bash
uv run --python 3.12 ruff check .
uv run --with mypy --python 3.12 python -m mypy src apps
uv run --with pytest --python 3.12 python -m pytest -q
uv run --python 3.12 python tests/secret_scan.py
uv run --with alembic --python 3.12 python -m alembic heads
cd apps/web && npm run typecheck && npm run build
```

For staging acceptance:

```bash
python scripts/verify_release_sync.py --base-url http://43.155.208.138 --expected-sha <SHA>
curl -s http://43.155.208.138/v1/validation/summary
curl -s http://43.155.208.138/v1/providers/status
python scripts/run_w2_handicap_walkforward.py --dry-run
```

Docs/template-only PRs do not require staging deployment unless they alter
runtime code, config, or public UI assets.

## Stop Conditions

Stop and report if any action needs `.env` access, provider credential changes,
payment, production deploy, destructive migration, runtime competition whitelist
changes, real S2 backtest, FORMAL/CANDIDATE unlock, or `beats_market=true`.
