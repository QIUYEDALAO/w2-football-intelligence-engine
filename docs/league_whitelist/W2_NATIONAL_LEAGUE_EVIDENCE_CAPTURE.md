# W2 National League Evidence Capture

## Purpose

PR #181 confirmed that the #180 sanitized reports can identify blocker categories, but
cannot safely infer exact league id, season, team-count, fixture query, or bookmaker
mapping changes. This stage adds sanitized observed evidence fields to future league
whitelist audit reports so the next provider audit can diagnose mapping and coverage
issues without committing raw provider payloads.

## Sanitized Fields

Future audit item JSON may include `observed_evidence` with these fields:

- `observed_provider_league_id`
- `observed_provider_league_name`
- `observed_provider_country`
- `observed_provider_season`
- `observed_provider_team_count`
- `observed_fixture_query_params`
- `observed_fixture_response_count`
- `observed_bookmaker_count`
- `observed_ah_ou_market_names`
- `observed_has_ah`
- `observed_has_ou`
- `observed_has_line`

## Safety Boundary

The evidence capture must not include:

- raw provider payloads
- request or response headers
- provider keys
- full provider responses
- database data
- runtime reports committed to git

The next provider audit should still run under the approved daily cap and reserve policy.
This stage does not call provider and does not enable any league.

## Follow-Up Use

After #182 is merged, a new provider audit can use the enhanced reports to decide whether
profile changes are justified. Even with observed values present, profile edits should only
be made after reviewer approval.
