# W2 Delivery Pipeline Lead-Time Recovery

## Decision

```text
DELIVERY_MODEL = RELEASE_CANDIDATE_PROMOTION_V1
MERGE_QUEUE = NOT_AVAILABLE_CURRENT_PERSONAL_REPOSITORY
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY / GHCR_ARCHIVE_AND_FALLBACK
```

One exact PR head receives one complete Release Candidate validation and one Python/Web
immutable image build. A merge commit may promote those digests only when its tree equals the
validated source tree. Missing or mismatched evidence fails closed and dispatches the same Release
Candidate workflow once for the exact main merge SHA.

The post-merge `pr_number=0` rehearsal path is deliberately non-promotable. It accepts only the
current `origin/main`: classification explicitly determines whether images and deployment are
required. `force_full=true` exercises the complete quality matrix. Promotion rejects manifests
whose `rehearsal` field is true.

## Before

Baseline main: `8c6086e37ba62c138bdf059997ca760accef7067`.

GitHub run `30820205036`:

| Stage | Wall time |
| --- | ---: |
| verify | 820 seconds |
| images | 54 seconds |
| complete workflow | 1,012 seconds |

The old workflow ran on both PR and `main`, so an ordinary runtime change could execute Full pytest
twice and build the release images twice. A cold VPS GHCR pull took 1,920 seconds. The existing local
OCI relay reduced immutable-image preheat to 295 seconds and the measured warm service switch to 9
seconds.

## New responsibilities

- `.github/workflows/pr-fast.yml`: change-aware feedback only; no release images.
- `.github/workflows/release-candidate.yml`: the sole complete quality matrix and image builder.
- `.github/workflows/main-promote.yml`: verifies manifest, SHA, tree and digest; never runs Full pytest
  or builds images.
- `scripts/dev_check.py`: local fast feedback; explicitly not a Full CI substitute.
- `scripts/release/finalize_pr.sh`: wait, validate, preheat, merge, promote, deploy and verify without
  intermediate user confirmation.

Generic tests are assigned by deterministic longest-processing-time-first allocation using
`ci/pytest_durations.v1.json`. Four unit/contract shards and two integration shards use independent
runner PostgreSQL/Redis services. Dedicated staging-parity, migration and predeploy tests are
excluded from generic shards and run once in their named jobs. The shard contract fails on missing,
duplicate or invalid assignments.

## Branch protection baseline

Captured before changes on 2026-08-03, with URLs and principals omitted:

```yaml
required_status_checks:
  strict: true
  contexts: [CI_REQUIRED]
required_pull_request_reviews:
  required_approving_review_count: 0
enforce_admins: true
required_linear_history: false
allow_force_pushes: false
allow_deletions: false
rulesets: []
```

After both post-merge rehearsals pass, the only required checks become `PR_FAST_REQUIRED` and
`RELEASE_REQUIRED`; all other protections remain unchanged. `PROMOTION_REQUIRED` is post-merge and
must not be a pre-merge requirement. Auto-merge remains disabled.

## Acceptance receipt

The final measured values come from exact-head PR Fast run `30828165126`, final successful Release
Candidate run `30832166843`, and the existing local OCI relay receipt.

`INITIAL_REHEARSAL_FOUND_COMPATIBILITY_ISSUES = true`

```text
LOCAL_FEEDBACK_TIME = 3.51 seconds (target <= 180 seconds)
PR_FAST_CHECK = 41 seconds (target <= 240 seconds)
FULL_QUALITY_WALL_TIME = 403 seconds (first-run target <= 480 seconds)
FULL_QUALITY_P50 = PENDING_5_RUNTIME_RUNS (target <= 360 seconds)
FULL_CI_EXECUTIONS_PER_RUNTIME_CHANGE = 1
RELEASE_IMAGE_BUILD_COUNT = 1 Python + 1 Web per exact source SHA
SOURCE_SHA = ef53ac3779cbfb4dfc6ef89cd4d3f664c23310c4
SOURCE_TREE_SHA = 26ad90cd0bb627859f7f56b637add77c1b66d62c
SOURCE_TREE_PROMOTION_CHECK = PASS
RELEASE_MANIFEST_SHA256 = 15da77f306199aff1e5690ddd343c84a1f6ee8c10fd219010615110bf54d09a1
VPS_PREHEAT = 295 seconds (target <= 300 seconds)
SERVICE_SWITCH = 9 seconds (target <= 60 seconds)
DUPLICATE_MAIN_FULL_CI = false
DUPLICATE_MAIN_IMAGE_BUILD = false
HUMAN_BABYSITTING_REQUIRED = false
TEST_ASSERTIONS_WEAKENED = false
PROVIDER_CALL_DELTA = 0
SCHEDULER_RESTARTED = false
CANDIDATE_FORMAL_LOCK_PRODUCTION_MODIFIED = false
```
