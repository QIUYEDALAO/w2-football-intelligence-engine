# W2 Direct Hotpatch Deployment Context - 2026-07-21

## User instruction

The user cancelled the exact-SHA Docker image rebuild/deployment path and instructed Codex to switch to direct code replacement deployment.

```text
你取消这个部署吧，改为直接替换代码部署
```

The user then clarified that the exact-SHA image rebuild should be performed after understanding the tradeoff:

```text
那你还是重新构建镜像部署一次把
```

This file intentionally preserves both instructions in chronological order. The direct hotpatch happened first; the follow-up action is to replace that temporary hotpatch state with an auditable rebuilt-image staging deployment.

## GitHub source context

PR: #370

Branch:

```text
codex/w2-factor-model-remediation-master
```

Current pushed head used for the direct hotpatch:

```text
612548d73dad77147abe9dd70a870cb4b9bab630
```

This commit includes the analysis-side promotion fix after:

- real empirical xG uncertainty wiring;
- read-model market evidence projection;
- Docker package mirror build arguments.

## Deployment method actually used

The remote Docker rebuild was stopped before completion. The running staging API container was then hotpatched by replacing the installed Python package code directly:

```text
local src/ -> /opt/w2/current/src/
/opt/w2/current/src/w2/ -> running API container site-packages/w2/
```

The API container was restarted after copying the code.

Verified inside the running container:

```text
hotpatch marker: /app/runtime/HOTPATCH_SHA
hotpatch sha:    612548d73dad77147abe9dd70a870cb4b9bab630
api health:      healthy
/ready:          200
```

## Important evidence limitation

This is not an exact-SHA Docker image deployment.

The running container image and process environment still report the previous image SHA:

```text
W2_GIT_SHA=cb8ee66d961e7e3ca68ed3ff325d7e70e2fd1b66
```

The runtime Python code was directly replaced with PR head code and marked separately:

```text
HOTPATCH_SHA=612548d73dad77147abe9dd70a870cb4b9bab630
```

Therefore any expert review should treat the current staging runtime as:

```text
DIRECT_CODE_HOTPATCH
IMAGE_SHA_NOT_UPDATED
EXACT_IMAGE_RELEASE_NOT_PROVEN
```

## Provider and scheduler posture

After the controlled provider window and manual odds materialization:

```text
W2_PROVIDER_CALLS_DISABLED=true
W2_PROVIDER_SCHEDULER_ENABLED=false
W2_RECOMMENDATION_ENABLED=false
W2_PRODUCTION_RELEASE=false
```

The scheduler container remains stopped.

## Fresh provider/materialization evidence

A controlled provider window was opened after the hotpatch and closed again.

Provider refresh report:

```text
/opt/w2/current/runtime/reports/provider_future_refresh_hotpatch_612548d_20260721T065303Z.json
```

The automated future refresh still returned:

```text
MatchdayRepositoryError
```

Manual odds materialization from the latest raw provider captures succeeded without new provider calls.

Manual materialization report:

```text
/opt/w2/current/runtime/reports/materialize_latest_odds_hotpatch_612548d_20260721T065346Z.json
```

Materialized fixtures:

```text
1494224, 1494218, 1494221, 1494223,
1494217, 1494222, 1494219, 1494220
```

Total canonical market observations inserted:

```text
2938
```

## Compact read-model canary after hotpatch

Report:

```text
/opt/w2/current/runtime/reports/read_model_canary_hotpatch_612548d_COMPACT_20260721T065620Z.json
```

Result:

```text
fixture count: 8
lambda_uncertainty_status: ANALYSIS_READY for all 8
lambda_uncertainty_method: empirical_xg_standard_error.v1
model_probability present: yes
market_probability present: yes
probability_delta present: yes
expected_value present: yes
uncertainty present: yes
V3 outcome: NO_EDGE for all 8
```

Important interpretation:

Some AH/OU market rows contained `analysis_direction_allowed=true` and `MODEL_MARKET_EDGE_READY`, but V3 still returned `NO_EDGE` with no selected candidate. This means the read-model evidence fields and uncertainty source are present, but the final V3 candidate-selection consumption path still needs verification/fix before claiming an analysis recommendation chain closure.

## Current truth status

```text
DIRECT_HOTPATCH_DEPLOYED: YES
STAGING_API_HEALTHY: YES
PROVIDER_DISABLED_AFTER_WINDOW: YES
SCHEDULER_STOPPED: YES
FORMAL_DISABLED: YES
LOCK_DISABLED: YES
PRODUCTION_DISABLED: YES

EXACT_IMAGE_RELEASE: NO
AUTO_FUTURE_REFRESH_MATERIALIZATION: FAILS_WITH_MatchdayRepositoryError
V3_ANALYSIS_PICK_CHAIN: NOT_CLOSED
MANUAL_APPROVAL_REQUIRED
```

## Follow-up exact-image deployment instruction

Required next action after this context update:

```text
REBUILD_STAGING_IMAGES_FOR_SHA=612548d73dad77147abe9dd70a870cb4b9bab630
RECREATE_RUNNING_CONTAINERS_FROM_REBUILT_IMAGES
VERIFY_CONTAINER_ENV_W2_GIT_SHA_EQUALS_HEAD
VERIFY_API_READY_AND_VERSION_SHA
KEEP_PROVIDER_CALLS_DISABLED
KEEP_SCHEDULER_STOPPED
KEEP_RECOMMENDATION_LOCK_PRODUCTION_DISABLED
```

## First rebuild attempt and Dockerfile cache fix

The first exact-image rebuild attempt was cancelled before replacing containers because the Python dependency installation layer was too slow on the staging VPS.

Observed cause:

```text
Dockerfile copied src/apps/config before uv sync
therefore every source-only change invalidated the dependency install layer
uv sync had to redownload/reinstall runtime dependencies
```

Remediation applied before retrying the image deployment:

```text
Dockerfile.api
Dockerfile.worker
Dockerfile.migrations
```

The Python images now perform dependency installation before copying application source:

```text
COPY pyproject.toml uv.lock README.md ...
RUN pip install uv && uv sync --no-dev --frozen --no-editable --no-install-project
COPY source/config/apps/migrations ...
RUN uv sync --no-dev --frozen --no-editable
```

This is a deployment build-layer fix only. It does not alter recommendation, market, factor, provider, lock, or production business logic.

Second rebuild observation:

```text
migration dependency layer did not share cache with api because alembic.ini was copied before uv sync
scheduler still used the old one-step dependency/source install pattern
```

Follow-up deployment-only correction:

```text
Dockerfile.migrations now copies alembic.ini after the shared dependency layer
Dockerfile.scheduler now has PIP_INDEX_URL/UV_INDEX_URL build args
Dockerfile.scheduler now uses the same dependency-before-source layer split
```

## Exact-image fresh canary exposed V3 candidate consumption bug

After rebuilding and deploying exact image SHA:

```text
2d86c3456f16c84020fc743f8d00803c1e5e9c63
```

The staging runtime had fresh odds, empirical xG uncertainty, model probability, market probability, probability delta, EV, and uncertainty fields populated. However V3 still returned `NO_EDGE` for all 8 fixtures.

Root cause:

```text
market_candidate selected the best analysis side from side_evidence
but then rebuilt analysis_evidence with market_row.tendency instead of the promoted selection
```

Consequence:

```text
market rows showed MODEL_MARKET_EDGE_READY
candidate analysis_evidence stayed NO_EDGE
V3 selected_candidate stayed null
```

Fix:

```text
market_candidate now passes the promoted selection into build_analysis_market_evidence
unit test added for best-side evidence promotion into executable analysis candidate
```

Validation before redeploy:

```text
ruff: PASS
mypy: PASS
pytest tests/unit/test_market_candidate.py tests/unit/test_recommendation_decision_v3.py tests/unit/test_analysis_card_xg_materialized.py: 24 passed
```

## Final Docker cache correction

An additional exact-image rebuild attempt showed that dependency cache was still invalidated for every new SHA because release metadata was written into `ENV` before dependency installation.

Root cause:

```text
W2_GIT_SHA / W2_BUILD_TIME / W2_RELEASE_ID were set before uv sync
VITE_GIT_SHA / VITE_BUILD_TIME / W2_RELEASE_ID were set before npm ci
changing the release SHA invalidated dependency layers
```

Fix:

```text
Python Dockerfiles now set only PATH/PIP_INDEX_URL/UV_INDEX_URL before dependency install
Python Dockerfiles set W2_GIT_SHA/W2_BUILD_TIME/W2_RELEASE_ID after dependency and project install
Dockerfile.web now runs npm ci before VITE/W2 release ENV is set
```

Expected property:

```text
new release SHA changes the final runtime metadata layer
new release SHA no longer forces dependency redownload/reinstall
```

Additional cache root cause found during the next exact-image rebuild:

```text
Docker ARG W2_GIT_SHA / W2_BUILD_TIME / W2_RELEASE_ID were still declared before dependency RUN layers
Docker includes in-scope build args in cache evaluation for RUN
therefore each new SHA still invalidated uv sync
```

Final cache correction:

```text
Release metadata ARG declarations are now placed after dependency install layers
Python dependency layers only see PIP_INDEX_URL/UV_INDEX_URL
Web npm ci layer no longer sees VITE/W2 release args
```

## Final V3 contract consumption fix

After exact-image deployment of:

```text
7eff948677a2ffe172d1d43cec30f160864fd658
```

Direct candidate inspection showed the candidate itself was now correct:

```text
candidate_analysis_evidence_status=COMPLETE
candidate_analysis_direction_allowed=true
candidate_ev_eligible=true
candidate_quote_status=COMPLETE
candidate_quote_usage=EXECUTABLE
candidate_selection=AWAY / OVER
```

But the public market row and V3 decision contract still remained non-pick:

```text
market_decision=SKIP
decision_contract.decision_tier=SKIP
V3 outcome=NO_EDGE
```

Root cause:

```text
candidate evidence was ready
but read-model projection did not raise the market decision_score to the selector threshold
apply_market_selection therefore left primary_market empty
decision contract received no selected market
```

Fix:

```text
When market_candidate is COMPLETE and analysis_direction_allowed:
  market.decision=ANALYSIS_PICK
  market.analysis_decision=ANALYSIS_PICK
  market.tendency=candidate.selection
  market.decision_score>=PRIMARY_THRESHOLD
  market.signal_strength=market.decision_score
```

Validation before redeploy:

```text
ruff src/w2/api/repository.py: PASS
mypy src/w2/api/repository.py: PASS
pytest tests/unit/test_analysis_card_xg_materialized.py tests/unit/test_market_candidate.py tests/unit/test_recommendation_decision_v3.py: 24 passed
```
