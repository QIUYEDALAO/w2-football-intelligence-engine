# W2 League Whitelist Full Scope Audit 2026-07-06

## Scope Correction

The earlier provider audit covered only `national_leagues_in_season`, a six-league
subset:

- brasileirao_serie_a
- argentina_primera
- mls
- chinese_super_league
- allsvenskan
- eliteserien

That six-league subset must not be reported as completion of the full whitelist.

## Full Whitelist Scope

The full whitelist inventory contains 14 competitions:

Top five:

- premier_league
- la_liga
- bundesliga
- serie_a
- ligue_1

World:

- world_cup_2026

National leagues:

- brasileirao_serie_a
- argentina_primera
- allsvenskan
- eliteserien
- mls
- chinese_super_league
- eredivisie
- primeira_liga

## Already Audited

The six `national_leagues_in_season` competitions have evidence-enabled provider
reports under `/tmp/w2_league_whitelist_evidence_audit_20260706T000732Z`.
They all remain `can_enable=false`.

Common blockers:

- provider_mapping:FAIL
- fixtures:FAIL
- bookmaker_depth:FAIL
- squad_value:CANNOT_VERIFY

## Remaining Scope

The remaining unaudited whitelist scope is:

- premier_league
- la_liga
- bundesliga
- serie_a
- ligue_1
- world_cup_2026
- eredivisie
- primeira_liga

These should run as `coverage-inventory`, not as direct enablement.

## Provider Call Budget

Ledger reconciliation for the three authoritative audit directories:

- `/tmp/w2_league_whitelist_audit_20260705T211336Z`
- `/tmp/w2_league_whitelist_audit_20260705T214858Z`
- `/tmp/w2_league_whitelist_evidence_audit_20260706T000732Z`

shows:

- provider_calls_total_raw=168
- provider_calls_total_deduped=168
- duplicate_records_count=0
- today_provider_calls_used=78
- today_counted_dirs=`/tmp/w2_league_whitelist_evidence_audit_20260706T000732Z`
- quota_warning=false
- 429=false
- daily_audit_hard_cap=90
- remaining_cap=12

The previous `112` number came from a broader `/tmp` directory-name scan, not the
requested ledger reconciliation. It mixed extra local audit directories with the
authoritative evidence run. The provider execution decision must use the reconciled
`remaining_cap=12`.

## Safety

- no enabled=true changes
- no staging deploy
- no production deploy
- no scheduler restart
- no DB writes
- no lock or settlement writes
- provider reports stay under `/tmp`
- raw provider payloads, headers, and provider keys must not be committed

## Next Action

Run `remaining_unaudited_whitelist` as `coverage-inventory` only under the verified
`remaining_cap=12`. If cap is exhausted before all eight competitions complete,
stop and report completed, partial, and unstarted competitions.

## Full Scope Coverage Inventory Run

The remaining scope audit ran under `daily_hard_cap=12`:

- output_dir=`/tmp/w2_league_whitelist_full_scope_audit_20260706T010537Z`
- actual_provider_calls=12
- local_ledger_records=12
- stopped_early=true
- stopped_reason=GLOBAL_PROVIDER_HARD_CAP_REACHED
- cooldown_recommended=false
- 429=false
- quota_warning=false

Completed competitions:

- premier_league
- la_liga
- bundesliga
- serie_a

Partial competitions:

- none

Unstarted competitions:

- ligue_1
- world_cup_2026
- eredivisie
- primeira_liga

All completed coverage-inventory reports remain `can_enable=false`.

Common completed-competition blockers:

- provider_mapping:FAIL
- fixtures:FAIL
- results:FAIL
- xg:FAIL
- lineups_injuries:FAIL
- bookmaker_depth:FAIL
- squad_value:CANNOT_VERIFY

Post-run usage reconciliation shows:

- today_provider_calls_used=90
- remaining_cap=0
- today_429=false
- today_quota_warning=false

No further provider calls may run on 2026-07-06.
