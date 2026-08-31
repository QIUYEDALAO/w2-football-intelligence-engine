# V1-SLOPE-FIT-AND-SHIP-01 independent acceptance packet

Status: `CANDIDATE_REJECTED_PENDING_INDEPENDENT_ACCEPTANCE`

Evidence commit: `2bf32f26b12f423d7adcacc9660859ff7925521c`

Runtime effect: none. The candidate was not written to `src/w2/strategy/calibration.py`,
the calibration version was not changed, no ledger record was added, and nothing was deployed.

## Claim to verify

The frozen TRAIN fit produced `raw_delta_scale=1.102038`, but the candidate failed three
pre-declared development shipping gates when replayed with strictly pre-kickoff inputs. It must
not be implemented, authorized, or deployed.

The prior 283-fixture A2 and its market-shape values are withdrawn because its rebuild path used
the target fixture's post-match xG. The corrected cohort is 259 fixtures: 178 production rolling
snapshots plus 81 latest-five pre-kickoff rebuilds. Twenty-four rebuild fixtures are excluded for
insufficient pre-kickoff history.

Only frozen market quote fields are reused from the old market audit: line, two-sided odds,
bookmaker identity/depth, observation identity, raw payload digest, and capture time. Old lambdas,
probabilities, edges, and fair lines are discarded and recomputed. Devig is the actual
`PROPORTIONAL` implementation.

## Immutable artifacts

| Artifact | SHA-256 |
|---|---|
| `A2_PIT_SIMULATION_TRACKS_REDO.json` | `d7c6eaf9ab39a62265438d661cc2f606cf0c7d4dfd4b5ac5fb8a41999c95266f` |
| `PIT_MARKET_SHAPE_XYZ.json` | `e4550c7dc4183a0bc1e0bc9b5e1c1c72540c0174b4569c44dc5b085564363f5b` |
| `PIT_MARKET_SHAPE_XYZ.md` | `e019c8a00c5ce854ac7c44d7829637642277f0bf8904a39df9c1f199ceb6a27c` |

## Binding result

| Gate | Candidate Z | Limit | Result |
|---|---:|---:|---|
| AH underdog cashflow price edge mean | `0.095440` | `<=0.05` | FAIL |
| AH underdog edge above 5% | `142/256 = 0.554688` | `<=0.35` | FAIL |
| AH favorite-strength shortfall absolute mean | `0.349609` goals | `<=0.25` | FAIL |
| No shortfall overshoot | `+0.349609` | `>-0.25` | PASS |
| AH favorite-side edge mean | `-0.243710` | `<=0.05` | PASS |
| Home-favorite absolute worsening vs Y | `-0.010607` goals | `<=0.10` | PASS |
| Away-favorite absolute worsening vs Y | `-0.043956` goals | `<=0.10` | PASS |
| TOTALS fair-minus-market mean change vs Y | `0.000000` goals | `<=0.02` | PASS |

This is development evidence, not production validation. The replay uses the strict-PIT point
estimate and a complete score matrix with sigma zero. It is sufficient for the declared market
shape gates but is not represented as a full production EV-SE uncertainty replay.

## Independent deterministic replay

Requires the frozen local exports whose digests are embedded in A2:

- `/tmp/v1_slope_home_away.csv`
- `/tmp/v1_slope_xg.csv`
- `/tmp/v1_a1_snapshot.csv`

```bash
cd /Users/liudehua/.hermes/worktrees/w2-v1-recalibration-evidence-01
check_dir=$(mktemp -d /private/tmp/v1-strict-pit-review.XXXXXX)

PYTHONPATH=src:. .venv/bin/python scripts/build_v1_pit_simulation_tracks.py \
  --a1 docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/A1_PIT_EVIDENCE_REDO.json \
  --home-away /tmp/v1_slope_home_away.csv \
  --xg /tmp/v1_slope_xg.csv \
  --snapshot /tmp/v1_a1_snapshot.csv \
  --raw-delta-scale 1.102038 \
  --output "$check_dir/a2.json"

cmp docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/A2_PIT_SIMULATION_TRACKS_REDO.json \
  "$check_dir/a2.json"

PYTHONPATH=src:. .venv/bin/python scripts/audit_v1_pit_market_shape.py \
  --a2-pit "$check_dir/a2.json" \
  --frozen-market-audit \
  docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/MARKET_SHAPE_AUDIT.json \
  --output-json "$check_dir/audit.json" \
  --output-report "$check_dir/audit.md"

cmp docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/PIT_MARKET_SHAPE_XYZ.json \
  "$check_dir/audit.json"
cmp docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/PIT_MARKET_SHAPE_XYZ.md \
  "$check_dir/audit.md"
```

Expected builder output: `snapshot=178`, `rebuild=81`, `tracks=777`. Expected audit output:
`all_pass=false` with exactly the three failed primary gates listed above.

## Codex self-verification

Targeted command:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/unit/test_calibration_validation_registry.py \
  tests/unit/test_audit_v1_market_shape.py \
  tests/contract/test_v1_slope_recalibration_preregistration.py \
  tests/contract/test_api_projection_read_authority.py \
  tests/contract/test_src_w2_package_matrix.py
```

Result: `48 passed`.

Ruff and diff check:

```bash
.venv/bin/ruff check scripts/build_v1_pit_simulation_tracks.py \
  scripts/audit_v1_pit_market_shape.py scripts/fit_v1_raw_delta_scale.py \
  scripts/audit_v1_pit_rebuild_coverage.py
git diff --check
```

Result: PASS.

Full suite command: `PYTHONPATH=src .venv/bin/python -m pytest -q`.

Result: `2945 passed / 9 skipped / 5 failed / 5 warnings` in `356.57s`. All five failures are
host limitations already present in the branch's prior acceptance record and outside this diff:

- 2 compose expansion tests: Docker CLI exists but Compose plugin is absent (`docker: unknown
  command: docker compose`).
- 1 SC18 authority test: the host has `python3` but no bare `python`, so its subprocess raises
  `FileNotFoundError`.
- 2 staging-parity runtime ownership tests: Docker bind-mounted macOS temporary directories are
  not materialized back at the expected `/private/...` host path, so the read-only preflight sees
  `MISSING`. This task does not modify Docker or runtime writable preflight code.

Safety boundary: Provider `0`; production reads `0`; production writes `0`; result records loaded
by the market audit `0`; migrations `0`; ledger writes `0`; deployments `0`; GitHub operations `0`.
