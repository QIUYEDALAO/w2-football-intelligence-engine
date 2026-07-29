# W2 MATCHDAY-LIVE-INTAKE-RECOVERY Progress Context

## GitHub Context

- Repository: `QIUYEDALAO/w2-football-intelligence-engine`
- Branch: `codex/w2-matchday-live-intake-recovery`
- Pull request: `#369`
- Scope: provider credential remediation, live fixture visibility, endpoint capture, canonical odds evidence, fixture identity authority.

## Credential Resolution

`W2_API_FOOTBALL_API_KEY` was present in the local operator environment, but staging `/opt/w2/shared/.env` had an empty value. The key was copied to staging without logging the secret value, then worker/scheduler credential visibility was verified.

Provider canaries after remediation:

- `status`: HTTP 200
- `fixtures`: HTTP 200
- Allsvenskan fixtures canary: league `113`, season `2026`, `2026-07-20` to `2026-08-03`
- Fixture response count: `16`
- Fixture payload SHA-256: `05793353bc8a7a7ec976e0c53c88dde0e35863dae988ccdc91cafd49c950b3bf`

## Staging Facts Observed Before This Migration

The credential fix restored real provider visibility. The initial Allsvenskan refresh produced:

- Future refresh fixture count: `14`
- Provider mappings in audit payload: `14`
- Market snapshot count: `8`
- Ledger appended count: `2699`
- Request count: `10`
- Blockers: none for the successful Allsvenskan run

Allsvenskan endpoint captures:

- `fixtures`: `1`
- `odds`: `8`
- `status`: `1`

Allsvenskan canonical market observations:

- `1X2`: `231`
- `ASIAN_HANDICAP`: `1079`
- `TOTALS`: `1389`

Complete quote groups:

- 1X2 complete triplets: `77`
- AH complete pairs: `438`
- OU complete pairs: `684`
- Fixtures with any complete quote group: `8`

## Source Change In This Context Sync

This PR now adds `MatchdayFixtureIdentityV1` through the `matchday_fixture_identities` table.

Purpose:

- Persist provider fixture identity independently from reviewed W2 team crosswalks.
- Keep `home_w2_team_id` and `away_w2_team_id` nullable until manual team identity review is complete.
- Mark those rows as `team_identity_status=REVIEW_REQUIRED`.
- Link each row to `raw_payload_sha256` and `endpoint_capture_id`.
- Fail closed with `FIXTURE_IDENTITY_CONFLICT` if the same provider fixture changes identity.

This prevents the old failure mode where the provider has fixtures, but the runtime appears to have no usable fixture because canonical W2 team identity is not approved yet.

## Readiness Truth

Restored:

- Provider credential visibility
- Provider status canary
- Provider fixtures canary
- Allsvenskan endpoint captures
- Canonical odds observations for captured odds fixtures
- Source-level fixture identity authority

Still not ready for recommendation:

- Team identity review is still required.
- F5 canonical team-history evidence is not ready for these provider fixtures.
- F8 reviewed as-of team-value evidence is not ready.
- Model evidence is not validated for formal recommendation.
- Matchday evidence manifests are not yet materialized from the new fixture identity authority.

Therefore V3/formal/lock/production remain blocked. The correct final state is:

`MANUAL_APPROVAL_REQUIRED`
