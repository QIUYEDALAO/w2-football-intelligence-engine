# W2 League Whitelist Provider Root Cause Diagnosis 2026-07-07

## Scope

This note diagnoses why the 2026-07-06 evidence-only provider audit returned
`provider_mapping:FAIL` and `fixtures:FAIL` for all 14 whitelist competitions,
including known-good control ids such as Premier League `39` and Brasileirao
Serie A `71`.

This pass is diagnostic only:

- no profile changes
- no code changes
- no DB reads or writes
- no deployment
- no scheduler restart
- no checkpoint, lock, or settlement writes
- no new provider calls
- no raw provider payload, headers, or key committed

## Evidence Location

Evidence directory is present:

`/tmp/w2_league_whitelist_evidence_only_audit_20260706T161125Z`

Files present:

- 14 sanitized `W2_WHITELIST_AUDIT_<competition_id>.json` reports
- `audit_ledger.json`
- `summary.json`

Important limitation: this audit intentionally did not store raw provider
responses. Therefore this document does not claim direct inspection of raw
`errors`, `seasons[]`, `coverage`, or fixture objects. It relies on the sanitized
ledger fields that were persisted by the audit harness.

## Control Group Findings

### Premier League, provider id 39

Evidence from sanitized ledger:

- endpoint calls: `leagues=1`, `fixtures=2`
- status_code: `200` for all 3 calls
- ledger error: `PROVIDER_PLAN_RESTRICTED` for all 3 calls
- response_count: `0` for all 3 calls
- observed provider id/name/country: empty in report
- observed fixture response count: `0`

Classification: **A - package / authorization / season entitlement**

Reason: the provider returned a plan-restricted error before usable league or
fixture rows were available. Because this happens on the known-good id `39`, it
does not support a profile mapping hypothesis.

### Brasileirao Serie A, provider id 71

Evidence from sanitized ledger:

- endpoint calls: `leagues=1`, `fixtures=2`
- status_code: `200` for all 3 calls
- ledger error: `PROVIDER_PLAN_RESTRICTED` for all 3 calls
- response_count: `0` for all 3 calls
- observed provider id/name/country: empty in report
- observed fixture response count: `0`

Classification: **A - package / authorization / season entitlement**

Reason: Brasileirao is the in-season control, yet the same plan-restricted error
appears before usable rows are available. That makes a simple off-season or
top-five-only season-coverage explanation insufficient for this run.

## 14-League Classification

| Competition | Calls | Endpoints | Status codes | Ledger error | Response counts | Class | Recommendation |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| premier_league | 3 | leagues:1, fixtures:2 | 200:3 | PROVIDER_PLAN_RESTRICTED:3 | [0] | A | Resolve provider plan/season entitlement before profile changes. |
| la_liga | 3 | leagues:1, fixtures:2 | 200:3 | PROVIDER_PLAN_RESTRICTED:3 | [0] | A | Resolve provider plan/season entitlement before profile changes. |
| bundesliga | 3 | leagues:1, fixtures:2 | 200:3 | PROVIDER_PLAN_RESTRICTED:3 | [0] | A | Resolve provider plan/season entitlement before profile changes. |
| serie_a | 3 | leagues:1, fixtures:2 | 200:3 | PROVIDER_PLAN_RESTRICTED:3 | [0] | A | Resolve provider plan/season entitlement before profile changes. |
| ligue_1 | 3 | leagues:1, fixtures:2 | 200:3 | PROVIDER_PLAN_RESTRICTED:3 | [0] | A | Resolve provider plan/season entitlement before profile changes. |
| world_cup_2026 | 3 | leagues:1, fixtures:2 | 200:3 | PROVIDER_PLAN_RESTRICTED:3 | [0] | A | Resolve provider plan/season entitlement before profile changes. |
| brasileirao_serie_a | 3 | leagues:1, fixtures:2 | 200:3 | PROVIDER_PLAN_RESTRICTED:3 | [0] | A | Resolve provider plan/season entitlement before profile changes. |
| argentina_primera | 3 | leagues:1, fixtures:2 | 200:3 | PROVIDER_PLAN_RESTRICTED:3 | [0] | A | Resolve provider plan/season entitlement before profile changes. |
| mls | 3 | leagues:1, fixtures:2 | 200:3 | PROVIDER_PLAN_RESTRICTED:3 | [0] | A | Resolve provider plan/season entitlement before profile changes. |
| chinese_super_league | 3 | leagues:1, fixtures:2 | 200:3 | PROVIDER_PLAN_RESTRICTED:3 | [0] | A | Resolve provider plan/season entitlement before profile changes. |
| allsvenskan | 3 | leagues:1, fixtures:2 | 200:3 | PROVIDER_PLAN_RESTRICTED:3 | [0] | A | Resolve provider plan/season entitlement before profile changes. |
| eliteserien | 3 | leagues:1, fixtures:2 | 200:3 | PROVIDER_PLAN_RESTRICTED:3 | [0] | A | Resolve provider plan/season entitlement before profile changes. |
| eredivisie | 3 | leagues:1, fixtures:2 | 200:3 | PROVIDER_PLAN_RESTRICTED:3 | [0] | A | Resolve provider plan/season entitlement before profile changes. |
| primeira_liga | 3 | leagues:1, fixtures:2 | 200:3 | PROVIDER_PLAN_RESTRICTED:3 | [0] | A | Resolve provider plan/season entitlement before profile changes. |

## A / B / C / D Decision

### A - package / authorization

Current evidence supports A as the root blocker.

The ledger recorded `PROVIDER_PLAN_RESTRICTED` for every provider request in the
audit, including both control groups. The audit harness maps provider
`errors.plan` to `PROVIDER_PLAN_RESTRICTED`; therefore the usable provider
response rows were blocked before `get_league()` could observe id/name/country
or before fixtures could provide fixture ids.

### B - season coverage

B is not ruled out, but it is blocked by A.

Because raw responses were not stored and all calls recorded a plan-restricted
error with `response_count=0`, this pass cannot safely inspect `seasons[]` or
`coverage.fixtures` for the configured 2026 season. Do not change
`api_football_season` from this evidence alone.

### C - national league mapping

C is not supported by this run.

The same failure occurs for known-good control ids `39` and `71`. That means the
run did not establish that national league ids are wrong. Argentina Primera may
still require mapping review later, but not from this evidence alone.

### D - parsing bug

D is not supported by this run.

The sanitized ledger shows response rows were unavailable (`response_count=0`)
and every request carried `PROVIDER_PLAN_RESTRICTED`. The empty
`observed_provider_*` fields are consistent with the parser receiving no usable
league rows, not with a parser failing to extract present id/name/country fields.

## Why Observed Fields Were Empty

The observed fields were empty because the evidence-only run did not receive
usable provider rows:

- `leagues` returned `response_count=0` with `PROVIDER_PLAN_RESTRICTED`
- `fixtures` returned `response_count=0` with `PROVIDER_PLAN_RESTRICTED`
- no fixture ids were available
- no `odds` calls were made because bookmaker evidence requires fixture ids

This explains:

- empty `observed_provider_league_id`
- empty `observed_provider_league_name`
- empty `observed_provider_country`
- `observed_fixture_response_count=0`
- empty `observed_ah_ou_market_names`

## Recommended Next Step

Do not edit profiles yet.

First resolve provider plan / season entitlement:

1. Confirm the API-Football account and subscription can access the configured
   season used by the audit, especially `season=2026`.
2. If the plan only allows specific seasons, document the officially allowed
   season set before changing any profile.
3. After entitlement is confirmed, run a minimal controlled diagnostic probe
   that stores only sanitized observed fields, not raw payloads.
4. Only if known-good controls succeed should national league mapping or season
   remediation begin.

## Stop Condition

This diagnostic stops here because the available evidence is sufficient to
identify A as the current root blocker and insufficient to justify profile or
logic changes.

