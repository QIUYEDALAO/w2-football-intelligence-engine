# V1 model repair independent acceptance packet

Status: `IMPLEMENTED_PENDING_CLAUDE_CODE_ACCEPTANCE / NOT_DEPLOYED`

Implementation commit:
`9685514aa684ca0607f27633edf4f71d8378bbe5`

Frozen protocol commits:

- strict-PIT outcome protocol: `2fbb9b05`
- xG uncertainty latest-five protocol: `fa346cbe`

## Acceptance claim

This delivery fixes one deterministic V1 defect: the xG point estimate uses the latest five
pre-kickoff matches, while `empirical_xg_standard_error.v1` used up to twenty. The implementation
retains the latest five only after all existing PIT, source, digest and kickoff checks, and changes
the uncertainty identity to `empirical_xg_standard_error.v2_latest_five`.

It does **not** claim that EV is fully repaired. The frozen `raw_delta_scale=1.102038` candidate
failed the strict OOF NLL gate and was not implemented, registered or deployed.

## Exact implementation boundary

Production code delta from the frozen protocol parent is three lines in
`src/w2/prematch/analysis_calculator.py`:

1. define `XG_POINT_ESTIMATE_WINDOW = 5`;
2. slice validated uncertainty rows to the latest five;
3. bump the method identity to `empirical_xg_standard_error.v2_latest_five`.

Unchanged: xG point estimate, `home_advantage_goals=0.30`, Dixon-Coles rho, lambda formula,
admission thresholds, calibration ledger, allowlist, V2 factors and database schema.

## Corrected evidence claims

### Strict-PIT outcome evidence

Full development set, `n=8,659`:

| scale | net-margin slope | intercept | mean Poisson NLL |
|---:|---:|---:|---:|
| current `1.0` | `1.184837` | `-0.011194` | `2.960601796` |
| candidate `1.102038` | `1.075132` | `0.021717` | `2.960077087` |
| legacy claim `1.848` | `0.642919` | `0.152005` | `2.993250392` |

Rolling-origin OOF, `n=7,159`:

- current slope/intercept: `1.173055/-0.020455`;
- candidate slope/intercept: `1.028712/0.022801`;
- improved folds: `7/10`;
- paired NLL candidate-current mean: `-0.000415741`;
- 95% bootstrap CI: `[-0.001435234,+0.000619995]`.

The upper CI is above zero. The frozen candidate fails and must remain absent from params and
ledger. The earlier `1.848 [1.758,1.939]` statement has no producing script or immutable row
artifact and is not reproducible from repository evidence.

### Market interpretation correction

The strict-PIT market cohort is `178 snapshot + 81 rebuild = 259`; 24 fixtures lack the frozen
minimum pre-kickoff history. Favorite-conditioned metrics choose orientation with the market
itself and therefore condition on market noise. Values such as `0.349609` remain diagnostic only,
not outcome-validity or deployment gates. Signed HOME fair-minus-market means are
X `0.176641`, Y `0.005792`, Z `0.014479`.

### Settled-candidate replay correction

The 121 settled candidates are diagnostic only:

- evaluation→capture identity: `121/121`;
- evaluation→model-input manifest: `121/121`;
- stored EV reproduced from evaluation's frozen five-state distribution and odds:
  `121/121` within `1e-6`;
- original recommendation equals the higher effective-probability side: `121/121`;
- decisive direction: AH `32/64=50.0%`, TOTALS `19/47=40.4%`, total
  `51/111=45.9%`.

The model-capture ladder and a later latest checkpoint are explicitly forbidden as substitutes
for the distribution frozen in the evaluation.

## Immutable hashes

| Artifact | SHA-256 |
|---|---|
| strict-PIT outcome protocol | `3237b4cf2b7dd656f8712de31a0097c5c96b0819b6f96ee6e6f4fe4d5f7b7051` |
| xG uncertainty protocol | `30fc5034d3f09c15dcfdd85c160891c936ba6f37e02a0a9132e53785df355571` |
| strict-PIT outcome JSON | `d9bf28de042de3e47f73996231729819c0442b7a3ba60b84df4ebfeafc263e17` |
| strict-PIT outcome report | `27ec3c9ec458d9221b6fa69762a719ad2a34315bfc13badb538c96af05b09e64` |
| settled input diagnosis | `75523d53a2e238f36f9e8889b4760bf787ae9ad841b47eaad060f73e0998aae1` |
| settled direction rescore | `15218931849bb7416250b7211787504be6077fa1e8f790edd5331db58db288e9` |
| strict-PIT market JSON | `e4550c7dc4183a0bc1e0bc9b5e1c1c72540c0174b4569c44dc5b085564363f5b` |
| strict-PIT market report | `b2872f8c4bf35fd545fe18856333e2313f33e006092460a064d186c773728f57` |

## Independent replay

```bash
cd /Users/liudehua/.hermes/worktrees/w2-v1-recalibration-evidence-01
check_dir=$(mktemp -d /private/tmp/v1-final-review.XXXXXX)

PYTHONPATH=src:. .venv/bin/python scripts/audit_settled_candidate_inputs.py \
  --input /tmp/settled_rescore.csv --output "$check_dir/inputs.json"
cmp docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/SETTLED_CANDIDATE_INPUT_DIAGNOSIS.json \
  "$check_dir/inputs.json"

PYTHONPATH=src:. .venv/bin/python scripts/audit_settled_candidate_direction_rescore.py \
  --input /tmp/settled_rescore.csv --output "$check_dir/direction.json"
cmp docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/SETTLED_CANDIDATE_DIRECTION_RESCORE.json \
  "$check_dir/direction.json"

PYTHONPATH=src:. .venv/bin/python scripts/audit_v1_strict_pit_outcome_correction.py \
  --home-away /tmp/v1_slope_home_away.csv \
  --xg /tmp/v1_slope_xg.csv \
  --market-audit docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/PIT_MARKET_SHAPE_XYZ.json \
  --protocol docs/operations/V1_STRICT_PIT_OUTCOME_CORRECTION_PROTOCOL_20260901.json \
  --output-json "$check_dir/outcome.json" --output-report "$check_dir/outcome.md"
cmp docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/STRICT_PIT_OUTCOME_CORRECTION.json \
  "$check_dir/outcome.json"
cmp docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/STRICT_PIT_OUTCOME_CORRECTION.md \
  "$check_dir/outcome.md"
```

Expected: all three `cmp` groups exit 0; strict outcome reports `all_checks_pass=false`
solely because `paired_oof_nll_upper_95_le_zero=false`.

## Test evidence

Targeted:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest -q \
  tests/unit/test_analysis_card_xg_materialized.py \
  tests/unit/test_settled_candidate_audits.py \
  tests/unit/test_audit_v1_market_shape.py \
  tests/unit/test_calibration_validation_registry.py \
  tests/contract/test_api_projection_read_authority.py \
  tests/contract/test_src_w2_package_matrix.py \
  tests/contract/test_v1_slope_recalibration_preregistration.py
```

Result: `68 passed in 2.93s`.

Full suite:

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest -q
```

Result: `2949 passed / 9 skipped / 5 failed / 5 warnings in 335.56s`.

The five failures are unchanged host limitations outside this diff:

- 2 × `test_compose_expansion_matches_authorized_runtime_delta`: Docker CLI exists but the
  Compose plugin is absent;
- 1 × `test_sc18_authority_artifacts_are_complete_and_self_checking`: host has `python3`
  but no bare `python`;
- 2 × `test_future_refresh_staging_parity`: macOS Docker bind-mounted temporary directories
  are not materialized back to the expected `/private/...` host path.

Ruff and `git diff --check`: PASS.

## Stop line

Provider 0; production reads 0; production writes 0; migrations 0; ledger writes 0;
deployments 0; GitHub operations 0. This package requests independent acceptance only.
