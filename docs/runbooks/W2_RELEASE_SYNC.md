# W2 Release Sync Runbook

This runbook verifies that GitHub, the local repository, the deployed release, the Web build, the API process, and the dashboard data source are aligned.

Set `W2_PUBLIC_BASE_URL` and `W2_DEPLOY_ROOT` from the approved operator
configuration. Do not commit their resolved values.

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
curl -s "${W2_PUBLIC_BASE_URL}/health" | jq .
curl -s "${W2_PUBLIC_BASE_URL}/ready" | jq .
curl -s "${W2_PUBLIC_BASE_URL}/meta.json" | jq .
curl -s "${W2_PUBLIC_BASE_URL}/v1/version" | jq .
curl -s "${W2_PUBLIC_BASE_URL}/v1/dashboard?window=today&include_debug=true" | jq .
curl -s "${W2_PUBLIC_BASE_URL}/v1/dashboard?window=next36&include_debug=true" | jq .
```

Expected fields:

- `/health` and `/ready`: API JSON, not the Web SPA `index.html`.
- `/meta.json`: `web_git_sha`, `web_build_time`, `release_id`, `data_mode`.
- `/v1/version`: `api_git_sha`, `api_build_time`, `release_id`, `data_profile`, `data_source`, data counts.
- `/v1/dashboard`: `data_profile`, `data_source`, `debug.empty_reason`, `debug.*_count`, `recommendations`, `upcoming`, `finished`, `all`.

If Web SHA and API SHA differ, the page must show a red mismatch warning.
If `/health` or `/ready` returns HTML, fix the Web nginx config so exact health routes proxy to the API before the SPA fallback.

## Automated verification

Every release must set `W2_PUBLIC_RESPONSE_SCHEMA_TOUCHED=YES|NO`. If the value is
`YES`, the same change must pass the API response-schema contract and Web
typecheck/build. The warm switch always performs a real HTTP read through the Web
proxy for `/v1/dashboard/intelligence-workspace`; the release record stores both
the schema-touch declaration and `workspace_http_status`.

```bash
python scripts/verify_release_sync.py \
  --base-url "${W2_PUBLIC_BASE_URL}" \
  --expected-sha "$(git rev-parse HEAD)" \
  --allow-empty-data
```

Use `--min-fixtures N` and omit `--allow-empty-data` when staging is expected to have dashboard rows.

If `api_git_sha` is `UNKNOWN`, check `${W2_DEPLOY_ROOT}/shared/release.env` and the `w2-staging.service` `EnvironmentFile` entry. A plain `systemctl restart w2-staging.service` must preserve the release SHA.

## Persistent release environment

The deploy script writes public release metadata to:

```text
${W2_DEPLOY_ROOT}/shared/release.env
```

Expected keys:

```text
W2_GIT_SHA=<commit>
W2_RELEASE_ID=<commit>
W2_BUILD_TIME=<UTC timestamp>
VITE_GIT_SHA=<commit>
VITE_RELEASE_ID=<commit>
VITE_BUILD_TIME=<UTC timestamp>
```

After a deployment or a systemd restart:

```bash
sudo systemctl restart w2-staging.service
curl -s "${W2_PUBLIC_BASE_URL}/meta.json" | jq .web_git_sha
curl -s "${W2_PUBLIC_BASE_URL}/v1/version" | jq .api_git_sha
python scripts/verify_release_sync.py \
  --base-url "${W2_PUBLIC_BASE_URL}" \
  --expected-sha "$(git rev-parse HEAD)" \
  --allow-empty-data
```

Do not store sensitive values in `release.env`; sensitive runtime values remain in `${W2_DEPLOY_ROOT}/shared/.env`.

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
