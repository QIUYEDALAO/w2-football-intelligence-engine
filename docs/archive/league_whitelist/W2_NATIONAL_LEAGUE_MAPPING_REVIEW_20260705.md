# W2 National League Mapping Review 20260705

## Scope

This document summarizes the offline diagnosis that follows PR #180 provider coverage audit.
It uses only sanitized audit reports already written under `/tmp`:

- `/tmp/w2_league_whitelist_audit_20260705T211336Z`
- `/tmp/w2_league_whitelist_audit_20260705T214858Z`

No provider call, database read or write, deployment, scheduler restart, lock write, or
settlement write is part of this review.

## Audit Summary

PR #180 used 90 provider calls total:

- First run: 25 calls, stopped by `PROVIDER_HTTP_429`.
- Resume run: 65 calls, stopped by `GLOBAL_PROVIDER_HARD_CAP_REACHED`.
- Six in-scope national league reports exist.
- All six reports have `can_enable=false`.
- No `enabled=true` profile flip was made.
- Audit reports remain under `/tmp` and are not committed.

## Blockers Table

| League | can_enable | provider_mapping | fixtures | results | xg | lineups_injuries | bookmaker_depth | squad_value | Warnings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| brasileirao_serie_a | false | FAIL | FAIL | PASS | PASS | PASS | FAIL | CANNOT_VERIFY | `AUDIT_SEASON_FALLBACK: configured=2026 audited=2024` |
| argentina_primera | false | FAIL | FAIL | PASS | PASS | PASS | FAIL | CANNOT_VERIFY | `ARGENTINA_PRIMERA_PLANNED_CHECK`, `AUDIT_SEASON_FALLBACK: configured=2026 audited=2024` |
| mls | false | FAIL | FAIL | PASS | PASS | PASS | FAIL | CANNOT_VERIFY | `MLS_WORLD_CUP_CALENDAR_PERTURBATION_REVIEW_REQUIRED_BEFORE_ENABLEMENT`, `AUDIT_SEASON_FALLBACK: configured=2026 audited=2024` |
| chinese_super_league | false | FAIL | FAIL | PASS | PASS | PASS | FAIL | CANNOT_VERIFY | `CHINESE_SUPER_LEAGUE_ENABLEMENT_REQUIRES_PER_MATCH_INTEGRITY_GATE_FOR_ABNORMAL_ODDS_OR_DEAD_MARKETS`, `AUDIT_SEASON_FALLBACK: configured=2026 audited=2024` |
| allsvenskan | false | FAIL | FAIL | PASS | PASS | PASS | FAIL | CANNOT_VERIFY | `AUDIT_SEASON_FALLBACK: configured=2026 audited=2024` |
| eliteserien | false | FAIL | FAIL | PASS | PASS | PASS | FAIL | CANNOT_VERIFY | `AUDIT_SEASON_FALLBACK: configured=2026 audited=2024` |

## Findings

- `provider_mapping:FAIL` means the configured league id, season, country, name, or team-count profile does not fully match the audited provider rows.
- `AUDIT_SEASON_FALLBACK: configured=2026 audited=2024` means the coverage probe found usable historical coverage, but the configured 2026 season was not validated as enablement-ready.
- `fixtures:FAIL` means upcoming fixture coverage did not pass the audit for the configured enablement path.
- `bookmaker_depth:FAIL` means AH/OU bookmaker market depth was not confirmed for the sampled fixture coverage.
- `squad_value:CANNOT_VERIFY` means no approved squad value mapping source is available yet.

These findings keep all six leagues blocked from enablement.

## Evidence Gap

This PR can confirm blocker categories, but the current sanitized #180 audit reports do
not contain enough observed provider values to safely infer specific profile edits. In
particular, the reports do not include sanitized observed league id, league name, country,
season, team count, fixture query parameters, fixture response counts, bookmaker counts,
or AH/OU market names.

Because of that evidence gap, do not guess league id, season, team-count, or bookmaker
mapping changes from category-level blockers alone. The next provider audit should record
these sanitized observed fields:

- `observed_provider_league_id`
- `observed_provider_league_name`
- `observed_provider_country`
- `observed_provider_season`
- `observed_provider_team_count`
- `observed_fixture_query_params`
- `observed_fixture_response_count`
- `observed_bookmaker_count`
- `observed_ah_ou_market_names`

Do not rerun provider today; the 90-call hard cap has already been used.

## Recommended Next PRs

1. Verify API-Football league id and season per national league profile offline using provider docs/source notes.
2. Add or repair the squad value mapping source before any enablement PR.
3. Review odds bookmaker market mapping for AH/OU coverage.
4. Update fixture query logic or season profiles so the audit can validate upcoming fixtures for the intended season.
5. Keep `enabled=false` until the seven-item audit can pass for each league.

## Explicit Safety

- No `enabled=true` changes.
- No staging deploy.
- No production deploy.
- No scheduler restart.
- No database read or write.
- No lock or settlement write.
- Do not rerun provider today; the daily audit cap was already reached.
