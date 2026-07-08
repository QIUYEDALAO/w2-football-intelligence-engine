# W2 R4.1 Staging Acceptance - 2026-07-08

## Scope

This is the staging acceptance archive for the R4.1 artifact publisher, bundle
distribution, and serving-loader smoke. It is evidence-only documentation.

- Staging only.
- No production deploy.
- No provider calls.
- No DB writes.
- No scheduler restart.
- No EV / RECOMMEND leg change.
- No `direction_allowed` change.
- Runtime artifacts and bundle files remain outside git.

## Deployed Code

- Target deployed code SHA: `807a6ef2ae4d4aeb45e39f84444a6043f91e7a87`
- `/v1/version` API SHA: `807a6ef2ae4d4aeb45e39f84444a6043f91e7a87`
- `/meta.json` Web SHA: `807a6ef2ae4d4aeb45e39f84444a6043f91e7a87`
- API / web / worker were on the target SHA during acceptance.

## Bundle Evidence

- Bundle source: `/tmp/w2_r4_1_bundle_injection/w2_r4_1_artifacts_807a6ef2ae4d4aeb45e39f84444a6043f91e7a87.tar.gz`
- Bundle SHA-256: `98d1b8a8fc31a65f0ead75b52b38256efa17b56843f6c52a59749ca5531117bc`
- Manifest git SHA: `807a6ef2ae4d4aeb45e39f84444a6043f91e7a87`
- Runtime path: `runtime/model_artifacts/r4_1/`

Runtime artifact files present in staging:

- `allsvenskan.v1.json`
- `bundesliga.v1.json`
- `chinese_super_league.v1.json`
- `bundle_manifest.807a6ef.txt`

Artifact summary:

| Competition | Version | Artifact Hash | Train Cutoff | Protocol Identity |
| --- | --- | --- | --- | --- |
| `allsvenskan` | `v1` | `9fd9993829bdc143f17ca275509436953b0285d18a49dbf2d15eb74023b0aab0` | `2025-12-08T20:00:00Z` | PASS |
| `bundesliga` | `v1` | `d2ffa041ca11f4fdfffaa9577b4961a32965f637d3dc00d8878594095a372ec7` | `2025-05-25T19:00:00Z` | PASS |
| `chinese_super_league` | `v1` | `46b1c8301343961becbbd6cb93fc60596aa7b2df2093257de85b7e061a3c28b8` | `2025-12-08T20:00:00Z` | PASS |

Brazil guard retained:

- `brasileirao_serie_a` has no R4.1 artifact.
- R4.1 is not available for Brazil because the R4.1 evaluation worsened the
  market gap there.

## Loader Acceptance

- `loader_import=PASS`
- Canonical key: `pricing_shadow.r4_1_calibrated`
- `chinese_super_league`: `model_family=R4_1_CALIBRATED`, `fallback_reason=None`
- `allsvenskan`: `model_family=R4_1_CALIBRATED`, `fallback_reason=None`
- `premier_league`: remains `FITTED_CALIBRATED`
- `bundesliga`: covered by artifact presence and unit tests; live runtime card
  may be unavailable out of season.

If real runtime cards are unavailable for a covered league, loader smoke is the
accepted staging artifact evidence. This avoids creating fake cards and avoids
provider calls.

## Safety

- provider_request_logs_delta: `0`
- future_refresh_run_audit_delta: `0`
- scheduler_restart: `false`
- production_deploy: `false`
- scheduler state observed during acceptance: running with existing restart
  policy; this acceptance did not restart or recreate it.
- Celery queue observed as `0`.

## Result

R4.1 artifact staging acceptance is archived as PASS for bundle injection and
serving loader. The next step is R1.1 checkpoint preparation and continued
calendar-time accrual.
