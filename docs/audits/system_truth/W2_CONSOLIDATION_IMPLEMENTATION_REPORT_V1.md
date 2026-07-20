# W2 Consolidation Implementation Report V1

Status: `SYSTEM_CONSOLIDATION_CODE_COMPLETE_EXTERNAL_BLOCKERS`

Manual approval: `MANUAL_APPROVAL_REQUIRED`

Base SHA: `848281365e94374e03d26c79bd5adc34f02ad9f5`

Branch: `codex/w2-system-consolidation-implementation`

Base branch: `codex/w2-system-consolidation-master`

## Scope

This implementation performs runtime authority cutover and code-side hardening only. It does not call real providers, deploy staging or production, run calibration, enable formal AH/OU, write locks, create production recommendation IDs, change Dashboard visuals, or commit private raw data.

## Implemented Authority Cutover

- Checkpoint planning now has one active canonical policy: `config/policies/matchday_intake.v2.json`.
- Scheduler checkpoint writes now go through `matchday_checkpoint_plans` via `MatchdayRuntimeRepository`.
- Legacy `FutureRefreshCheckpointPlanModel` writes are retired; the compatibility API returns zero writes.
- DB-backed future refresh provider responses are persisted as `MatchdayEndpointCapture` records.
- Endpoint capture identity now includes `fixture_id` and `checkpoint`.
- Market observation identity is derived from capture identity plus fixture, checkpoint, market, line, side, and provider.
- Evidence manifests validate deterministic self-identity and fail closed on fixture/as-of hash conflicts.
- F5 runtime lookup now reads canonical historical AH facts and requires approved team mappings.
- F8 runtime lookup now uses reviewed as-of team value artifacts only; static or unreviewed values remain incomplete.
- `W2DataAssetRegistryV1` records private data assets by storage alias, source hashes, manifest hash, coverage, backup, and restore status.

## Acceptance Answers

1. Checkpoint `ACTIVE_CANONICAL` authority count: `1`.
2. Unique policy file: `config/policies/matchday_intake.v2.json`.
3. Scheduler writes old checkpoint table: no.
4. `FutureFixtureRefreshService` can bypass EndpointCapture: no for DB runtime; non-DB compatibility is marked as non-authoritative.
5. Same raw payload at different checkpoints preserves distinct identity: yes.
6. Freshness authority: recommendation quote freshness is capped at 30 minutes; broader collection freshness stays separately audited.
7. Recommendation `ACTIVE_CANONICAL` count: `1`, centered on `RecommendationDecisionV3.decision_hash`.
8. Legacy `WATCH/SKIP` can enter formal admission: no.
9. API/Dashboard/frozen/report decision hash parity: code-side canonical manifest and V3 hash are wired; deployed parity still requires read-only canary.
10. F5 queries canonical DB facts: yes.
11. F5 team mapping complete: no, external crosswalk review remains required.
12. F8 authority: reviewed as-of artifact only.
13. Code blockers remaining: no known code blockers after local verification.
14. External blockers remaining: yes.
15. Old runtime writers stopped: yes for checkpoint writer and future refresh checkpoint compatibility path.
16. Legacy modules deleted: no; risky deletion is deferred until review confirms zero callers.
17. PostgreSQL verification: CI workflow now performs 0029/0028/0027 round-trip; local PostgreSQL test skipped because `W2_TEST_POSTGRES_URL` was not provided.
18. Formal/lock capability remains closed: yes.
19. Cohort invariant changed: no.
20. P0 checkpoint split remains: no code-side active split remains.

## External Blockers

- `BACKUP_LOCATION_REQUIRED`: private data asset backup and restore drill still need a configured backup root.
- `LICENSE_HUMAN_REVIEW_REQUIRED`: source license review remains manual.
- `TEAM_CROSSWALK_REVIEW_REQUIRED`: F5 cannot be complete for all runtime teams until mappings are reviewed.
- `PLAYER_CROSSWALK_REVIEW_REQUIRED`: F8 formal evidence remains blocked until player/team valuation identity is reviewed.
- `POSTGRES_STAGING_MIGRATION_SMOKE_REQUIRED`: local PostgreSQL URL was unavailable; GitHub/staging must run the migration smoke.
- `READ_ONLY_STAGING_CANARY_REQUIRED`: required before deployment or real provider enablement.
- `MANUAL_APPROVAL_REQUIRED`: required before calibration, formal recommendation, lock, deployment, or public capability opening.

## Verification

- `ruff check .`: PASS
- `mypy src apps`: PASS
- `pytest -q`: `1363 passed, 4 skipped`
- `scripts/check_w2_all.py`: PASS
- credential guard scan: PASS
- `scripts/check_tracked_outputs.py`: PASS
- `npm --prefix apps/web run typecheck`: PASS
- `npm --prefix apps/web run build`: PASS
- `npm --prefix apps/web run test:e2e`: `9 passed`
- `git diff --check`: PASS

## Final Gate

Final state remains `MANUAL_APPROVAL_REQUIRED`. This PR is source review only and is not approval to deploy, enable real provider canaries, run calibration, publish formal recommendations, lock recommendations, or open production capability.
