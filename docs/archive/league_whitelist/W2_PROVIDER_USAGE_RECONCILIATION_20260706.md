# W2 Provider Usage Reconciliation 2026-07-06

## Summary

User-reported API-Football dashboard usage:

- official_dashboard_used_user_reported=36

Local audit files previously showed larger numbers:

- 78: local ledger rows in `/tmp/w2_league_whitelist_evidence_audit_20260706T000732Z`
- 90: 78 evidence rows plus 12 full-scope coverage-inventory rows
- 112: a broad earlier `/tmp` directory-name scan that mixed extra local audit dirs

These values are not equivalent to official provider billing. `audit_ledger.json`
is a local execution ledger. A row proves that the audit code recorded an attempted
provider interaction, but it is not official billing unless provider-side evidence is
also present.

## Reconciliation Helper

The read-only helper is:

```bash
uv run --python 3.12 python scripts/summarize_w2_league_provider_usage.py --dashboard-used 36 --json
```

It does not call provider, does not read `.env`, does not print keys, and does not
read or write DB.

Counting rules:

- `summary.json` and `audit_ledger.json` are never added together.
- `summary.actual_provider_calls_total` is used only to cross-check ledger length.
- `audit_ledger.json` records are deduplicated by endpoint, competition_id, league_id,
  fixture_id, provider_call_index, and captured_at.
- `likely_real_http_calls` requires status_code, allowed endpoint, and captured_at.
- `likely_billing_calls` additionally requires provider quota metadata (`quota_remaining`).
- Rows with status_code but without quota metadata are flagged as
  `POSSIBLE_REAL_HTTP_BUT_NO_QUOTA_HEADER`.
- Rows without status_code, endpoint, or captured_at are reported as local-only
  `non_billing_local_records`.

## Core Four-Directory Result

For the four expected audit dirs:

- `/tmp/w2_league_whitelist_audit_20260705T211336Z`
- `/tmp/w2_league_whitelist_audit_20260705T214858Z`
- `/tmp/w2_league_whitelist_evidence_audit_20260706T000732Z`
- `/tmp/w2_league_whitelist_full_scope_audit_20260706T010537Z`

the helper reports:

- local_ledger_records_total=180
- likely_real_http_calls=90 for 2026-07-06
- likely_billing_calls=36 for 2026-07-06
- official_dashboard_used_user_reported=36
- non_billing_local_records=0
- records_without_quota_headers=54
- summary_ledger_mismatch=false
- provider_calls=0 for reconciliation
- db_reads=0
- db_writes=0

This partially explains why the dashboard can show 36 while local ledger counts show
78 or 90: 36 is the count of 2026-07-06 records that include provider quota metadata
in the core evidence run. However, the core dirs still contain 90 records with HTTP
evidence, so dashboard 36 does not fully reconcile against local HTTP evidence.

## All /tmp Audit Directories Result

When scanning every `/tmp/w2_league_whitelist*audit*` directory, the helper reports:

- audit_dir_count=98
- provider_calls_total_raw=316
- provider_calls_total_deduped=316
- likely_real_http_calls=124 for 2026-07-06
- likely_billing_calls=70 for 2026-07-06
- official_dashboard_used_user_reported=36
- non_billing_local_records=0
- records_with_quota_headers=70
- records_without_quota_headers=54
- records_with_status_code=124
- records_without_status_code=0
- status_code_distribution={"200": 124}
- duplicate_records_count=0
- quota_warning=false for 2026-07-06
- reconciliation_status=RECONCILIATION_REQUIRED
- possible_account_mismatch=true
- possible_dashboard_delay=true
- possible_local_double_count=false

The all-directory scan finds extra local audit runs beyond the four expected dirs.
Some of those extra runs also contain HTTP evidence and quota metadata, so the helper
cannot safely claim that dashboard 36 fully reconciles against all local evidence.

## Mock / Requester Check

Read-only code inspection found:

- CLI `real_provider_audit` does not expose a `requester_factory` argument.
- The command-line real audit path passes `requester_factory=None`.
- `ApiFootballLeagueAuditProvider._perform_request()` uses the injected requester
  only when `self.requester is not None`; otherwise it calls `_default_api_football_request()`.
- `_default_api_football_request()` uses `urllib.request.urlopen` against
  `https://v3.football.api-sports.io`.
- `requester_factory`, `EvidenceRequester`, `Mock`, and `dummy` usages are in unit
  tests or internal test injection paths.

No evidence was found that the CLI real-provider-audit command can receive a mock
requester from command-line flags. However, local ledger rows without quota headers
still cannot be treated as official billing proof.

## Interpretation

Current safest conclusion:

- The core four-directory reconciliation explains why the dashboard 36 matches
  quota-header-backed records, but it does not reconcile dashboard 36 with all
  local HTTP evidence.
- The all-`/tmp` scan still produces `RECONCILIATION_REQUIRED` because it finds
  additional HTTP evidence outside the expected four directories.
- Do not continue provider audit from these local counts alone.
- Do not enable any league from these results.
- Do not rewrite history or delete `/tmp` reports as part of this PR.

## Next Step

Default action: stop.

If the team needs to prove whether a provider call changes the dashboard counter,
request explicit approval for a one-call canary:

- NEED_USER_APPROVAL: API_FOOTBALL_ONE_CALL_CANARY
- endpoint: status or leagues
- provider_calls_cap=1
- no DB writes
- no deploy
- no enabled=true
- no key printing
- no raw payload committed
