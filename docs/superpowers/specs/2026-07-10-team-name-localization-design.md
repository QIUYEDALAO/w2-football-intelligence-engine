# W2 Dashboard Team Name Localization Design

Status: Approved direction, awaiting written-spec review

Date: 2026-07-10

## Objective

Display Chinese team names throughout the W2 Dashboard while preserving the exact
provider English name for traceability. Localization must be owned by the backend
read model so every Dashboard consumer receives the same result.

This change is presentation-only. It must not change fixture identity, market
matching, decision policy, recommendation eligibility, card hashes, provider
requests, database state, or deployment configuration.

## Product Contract

- Chinese is the primary team-name display language.
- The original English provider name remains available as hover text and in L2
  evidence.
- Unknown teams display the original English name. They never display an invented
  translation or a generic placeholder when a provider name exists.
- Localization failures do not block a card and do not change its readiness or
  decision tier.
- All Dashboard surfaces use the same localized fields: Boss View, selected-match
  evidence, post-match validation, league performance, replay, and legacy cards.

## Architecture

### 1. Versioned team localization registry

Add a versioned registry under `config/team_localization/`. Each entry contains:

```json
{
  "competition_id": "world_cup_2026",
  "provider_team_id": "2",
  "provider_name": "France",
  "name_zh": "法国",
  "aliases": ["France"]
}
```

The primary lookup key is `(competition_id, provider_team_id)`. A provider team ID
must not be treated as globally unique without competition context. The fallback
lookup is a normalized provider name or alias within the same competition.

The registry initially covers teams present in cached fixtures for the World Cup
and all 14 whitelist competitions. Coverage is checked in tests and by a read-only
validation helper; no provider call is needed to build or validate it.

### 2. Backend localization service

Add a small domain-neutral localization module with one responsibility:

```python
localize_team_name(
    competition_id,
    provider_team_id,
    provider_name,
) -> LocalizedTeamName
```

The result contains:

- `display_name`: Chinese name when matched, otherwise the provider name.
- `name_zh`: Chinese name or `None`.
- `provider_name`: unchanged English/source name.
- `status`: `MATCHED_BY_ID`, `MATCHED_BY_ALIAS`, or `FALLBACK_PROVIDER_NAME`.

Name normalization is limited to whitespace, case, apostrophe, ampersand, and
known alias handling. It must not use fuzzy matching because an approximate match
can attach the wrong identity to a fixture.

### 3. DayView contract extension

Preserve existing fields:

- `home_team_name`
- `away_team_name`

Add explicit display fields:

- `home_team_name_zh`
- `away_team_name_zh`
- `home_team_display_name`
- `away_team_display_name`
- `home_team_provider_name`
- `away_team_provider_name`
- `home_team_localization_status`
- `away_team_localization_status`

`*_team_name` stays unchanged for backward compatibility and internal matching.
The frontend must use `*_team_display_name` for visible copy. Hover text uses
`*_team_provider_name` only when it differs from the display name.

The fixture projection must also preserve `home_team_id` and `away_team_id` so
localization uses stable identity. These fields are read-only metadata and do not
alter DecisionCard semantic validation or hashes.

### 4. Frontend consumption

Create one frontend display helper that accepts the DayView localized fields.
Every Dashboard surface uses that helper instead of local dictionaries or direct
access to `home_team_name` and `away_team_name`.

Visible behavior:

- Main row: `法国 vs 摩洛哥`.
- Hover/focus accessible label: `France` / `Morocco`.
- L2 evidence: Chinese name with original provider name shown as secondary text.
- Unknown team: provider name is shown unchanged; no blank label.

The existing `TEAM_TRANSLATIONS` table remains only as a temporary compatibility
fallback for payloads that predate the new DayView fields. New mappings are not
added there after this change.

## Data Flow

```text
provider fixture
  -> provider team ID + exact provider name
  -> read-model fixture/card projection
  -> backend localization registry lookup
  -> DayView localized team fields
  -> shared frontend display helper
  -> Boss View / L2 / validation / performance / replay
```

Localization happens when DayView is built, not when provider data is ingested.
This avoids rewriting historical raw data and allows registry corrections to take
effect without mutating stored provider payloads.

## Error Handling

- Missing provider team ID: attempt competition-scoped alias lookup.
- Missing alias match: display the provider name and report
  `FALLBACK_PROVIDER_NAME`.
- Missing provider name: display `主队` or `客队` as the final UI fallback and
  report a contract warning.
- Duplicate registry key, conflicting alias, or blank Chinese name: validation
  fails closed in tests/checker; runtime keeps the provider name.
- Registry load failure: runtime keeps provider names and emits a sanitized
  warning. Dashboard availability is not blocked.

## Validation

Backend tests must cover:

- ID-first match for a World Cup national team.
- ID-first match for a club with aliases or historical spelling.
- Competition-scoped isolation for equal or ambiguous names.
- Alias fallback when team ID is absent.
- Unknown-team provider-name fallback.
- DayView preserving English names while emitting Chinese display fields.
- No changes to decision tier, lock eligibility, odds, card hash, or fixture ID.

Frontend tests must cover:

- Boss View, evidence panel, validation, performance, and replay use Chinese names.
- English provider names appear in hover/focus metadata.
- Old payloads without localized fields remain readable.
- Unknown teams remain visible in English.
- No raw localization status leaks into L1.

The acceptance screenshot set must include at least one World Cup card and club
cards from Chinese Super League plus one non-Chinese league.

## Rollout

1. Add registry, loader, validation, and backend DayView fields.
2. Update all Dashboard consumers and compatibility fallback.
3. Run unit, contract, TypeScript, build, W2 acceptance, tracked-output, lint,
   secret, and migration checks.
4. Open a Draft PR and verify CI.
5. Deploy to staging only after explicit approval and confirm Chinese names across
   Boss View, L2, post-match validation, and replay.

No production deployment or provider call is part of this work.

## Acceptance Criteria

- Dashboard primary team names are Chinese for all mapped teams.
- Original English names remain inspectable.
- The registry covers teams known to the current 14-competition whitelist cache.
- No visible component owns its own independent translation dictionary.
- Unknown teams fail visibly and safely to the provider English name.
- Decision, odds, fixture identity, and historical data are unchanged.
- `provider_calls=0`, `db_writes=0`, `staging_deploy=false`, and
  `production_deploy=false` during implementation and review.
