# W2 R4.1 Artifact Distribution Decision

Status: Decision confirmed.

Decision: Option A confirmed.

Approved by user/boss: `R4_1_ARTIFACT_DISTRIBUTION_OPTION_A`.

Scope:
- Decide how versioned R4.1 model artifacts are delivered to staging/runtime.
- Do not commit generated runtime artifacts to git.
- Do not deploy staging or production as part of this decision package.
- Keep EV / RECOMMEND leg default off and `direction_allowed` unchanged.

## Background

PR #215 adds a reproducible R4.1 artifact publisher, artifact schema, loader, hash and train-cutoff guards, and serving fallback behavior. The publisher writes generated files under:

```text
runtime/model_artifacts/r4_1/
```

Those generated files remain runtime artifacts and are not committed to git. The approved distribution method is Option A: CI generates the artifact bundle, and the staging deploy package distributes that bundle into `runtime/model_artifacts/r4_1/`.

## Option A: CI-Generated Artifact Bundle

Decision: approved distribution option.

Flow:
1. CI or a release job runs `scripts/publish_w2_r4_1_artifacts.py`.
2. The job generates an artifact bundle from the checked-out commit.
3. The staging deploy places that bundle into the agreed runtime path:

```text
runtime/model_artifacts/r4_1/
```

4. The service loads artifacts from that path and records `artifact_version`, `artifact_hash`, `train_cutoff`, and provenance in the pricing shadow path.

Pros:
- Reproducible from the same code revision.
- Traceable through CI/release logs.
- Deployment carries the exact artifacts it needs.
- Reduces environment drift between code, provenance, and loaded artifact hash.

Risks:
- Deployment scripts must support injecting or unpacking the artifact bundle into the runtime path.
- CI/release packaging needs one small explicit artifact step.

Readiness implication:
- #215 can be marked Ready after this decision is recorded.
- The actual deployment-bundle injection can be verified in a later staging deployment task.

## Option B: Runtime Mounted Shared Directory

Flow:
1. An operator or separate task runs the artifact publisher.
2. Generated artifacts are copied to a shared volume.
3. The service mounts that shared directory at:

```text
runtime/model_artifacts/r4_1/
```

Pros:
- Does not require deployment package changes.
- Can be used quickly if the staging runtime already has a managed shared volume.

Risks:
- Higher environment drift risk.
- Harder to prove that loaded artifacts match the deployed code revision.
- Hash/provenance and code synchronization depend on operator discipline.
- Harder to reproduce during incident review.

Readiness implication:
- Acceptable only if operations explicitly owns artifact placement and hash verification.

## Option C: Remote Artifact Store

Flow:
1. CI or a release process uploads the artifact bundle to object storage or a GitHub release asset.
2. The service downloads the selected artifact read-only during startup or deployment.
3. The service validates hash/provenance before use.

Pros:
- Clear version management.
- Artifact lifecycle can be independent from application images.
- Scales better if multiple environments consume the same artifact version.

Risks:
- Requires extra credentials or network access.
- Adds startup/deploy-time dependency on artifact storage availability.
- More moving parts than needed for the current staging gate.

Readiness implication:
- Not recommended for the current fast staging path.
- Better suited for a later production-grade artifact registry design.

## Confirmed Decision

Choose Option A: CI-generated artifact bundle distributed with the deployment package.

Rationale:
- It is the most reproducible and auditable option for the current stage.
- It keeps generated artifacts out of git while still binding artifacts to the code revision that produced them.
- It avoids runtime-only drift and avoids adding a remote artifact-store dependency before it is needed.

Readiness gate:
- #215 may be marked Ready because Option A is confirmed.
- Actual artifact bundle injection and staging acceptance remain a follow-up deployment task.
- Runtime artifacts are still not committed to git.

## Non-Goals

- No provider calls.
- No DB writes.
- No staging deploy.
- No production deploy.
- No scheduler restart.
- No runtime artifact commit.
- No EV / RECOMMEND leg enablement.
- No `direction_allowed` behavior change.
