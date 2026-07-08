# W2 R4.1 Artifact Bundle Distribution

Status: Option A implementation wiring.

Decision source: `docs/r4_1/W2_R4_1_ARTIFACT_DISTRIBUTION_DECISION.md`.

## Scope

This PR implements the build and verification wiring for Option A:

- CI generates an R4.1 artifact bundle from the reproducible publisher.
- The deployment package can later inject the bundle into `runtime/model_artifacts/r4_1/`.
- Runtime artifact JSON files and bundle archives are not committed to git.
- This PR does not deploy staging or production.
- This PR does not enable any league, call providers, write DB state, restart scheduler, or change the EV / RECOMMEND leg.

## Bundle Build

Generate a bundle with:

```bash
uv run --python 3.12 python scripts/build_w2_r4_1_artifact_bundle.py \
  --out-dir /tmp/w2_r4_1_bundle_test \
  --json
```

The builder:

1. Runs the existing R4.1 artifact publisher.
2. Generates artifacts under a temporary runtime path.
3. Writes a manifest.
4. Produces a tarball named like:

```text
w2_r4_1_artifacts_<git_sha>.tar.gz
```

The bundle contains:

```text
manifest.json
artifacts/bundesliga.v1.json
artifacts/chinese_super_league.v1.json
artifacts/allsvenskan.v1.json
```

## Manifest Contract

The manifest contains:

- `git_sha`
- `artifact_version`
- `competition_ids`
- `artifact_hashes`
- `train_cutoff`
- `created_at`
- `protocol_identity_status`
- `canonical_pricing_shadow_key = pricing_shadow.r4_1_calibrated`
- `disabled_competitions`, including `brasileirao_serie_a`

Brazil is intentionally excluded because the R4.1 evaluation worsened Brazil.

## Bundle Verification

Verify a bundle with:

```bash
uv run --python 3.12 python scripts/verify_w2_r4_1_artifact_bundle.py \
  --bundle /tmp/w2_r4_1_bundle_test/w2_r4_1_artifacts_<git_sha>.tar.gz \
  --json
```

The verifier checks:

- The bundle can be read.
- The manifest is complete.
- All artifact files are present.
- Artifact hashes match the payloads.
- Train cutoffs are present.
- Protocol identity status is `PASS`.
- Brazil is not in the target set.
- The canonical pricing shadow key is `pricing_shadow.r4_1_calibrated`.

## CI Distribution Path

Recommended CI flow:

1. Run unit and contract checks.
2. Run `scripts/build_w2_r4_1_artifact_bundle.py`.
3. Upload the tarball as a CI artifact or attach it to the deploy package.
4. Run `scripts/verify_w2_r4_1_artifact_bundle.py` against the tarball.
5. During a separately approved staging deploy, unpack the verified bundle into:

```text
runtime/model_artifacts/r4_1/
```

## Staging Acceptance

Staging acceptance is a follow-up deployment task, not part of this PR.

Expected acceptance after bundle injection:

- Chinese Super League cards load `model_family=R4_1_CALIBRATED` with no `fallback_reason`.
- Allsvenskan cards load `model_family=R4_1_CALIBRATED` with no `fallback_reason`.
- Bundesliga is covered by unit tests while it is out of season.
- Premier League remains `FITTED_CALIBRATED`.
- Runtime provenance includes artifact version and hash.
- No provider calls are required for artifact loading.

## Non-Goals

- No staging deploy.
- No production deploy.
- No provider calls.
- No DB reads or writes.
- No scheduler restart.
- No runtime artifact commit.
- No artifact bundle commit.
- No EV / RECOMMEND leg change.
- No `direction_allowed` change.
