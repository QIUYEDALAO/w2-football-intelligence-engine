# W2 Release Sync Runbook

This runbook verifies that GitHub, the local repository, the deployed release, the Web build, the API process, and the dashboard data source are aligned.

## Local checks

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git remote -v
git ls-remote github-w2 fix/w2-dashboard-release-data-sync
```

The local `HEAD` must match the expected GitHub branch SHA before deployment.

## Runtime endpoints

```bash
curl -s http://43.155.208.138/meta.json | jq .
curl -s http://43.155.208.138/v1/version | jq .
curl -s 'http://43.155.208.138/v1/dashboard?window=today&include_debug=true' | jq .
curl -s 'http://43.155.208.138/v1/dashboard?window=next36&include_debug=true' | jq .
```

Expected fields:

- `/meta.json`: `web_git_sha`, `web_build_time`, `release_id`, `data_mode`.
- `/v1/version`: `api_git_sha`, `api_build_time`, `release_id`, `data_profile`, `data_source`, data counts.
- `/v1/dashboard`: `data_profile`, `data_source`, `debug.empty_reason`, `debug.*_count`, `recommendations`, `upcoming`, `finished`, `all`.

If Web SHA and API SHA differ, the page must show a red mismatch warning.

## Automated verification

```bash
python scripts/verify_release_sync.py \
  --base-url http://43.155.208.138 \
  --expected-sha "$(git rev-parse HEAD)" \
  --allow-empty-data
```

Use `--min-fixtures N` and omit `--allow-empty-data` when staging is expected to have dashboard rows.

## Explicit staging seed

Staging seed is only for previewing the dashboard when the read-model is empty. It must never be confused with real data.

```bash
python scripts/seed_staging_dashboard.py --force
```

When seed data is active, `/v1/dashboard` returns `data_profile=staging-seed` and `data_source=staging-json-fallback`, and the Web UI displays a `STAGING SEED` badge.

## Empty data diagnosis

If the dashboard is empty, inspect:

- `debug.empty_reason`
- `debug.read_model_fixture_count`
- `debug.matchday_card_count`
- `debug.future_fixture_count`
- `debug.result_event_count`
- `debug.selected_date`
- `debug.next_available_date`

Suggested actions are returned directly in `debug.suggested_actions`.
