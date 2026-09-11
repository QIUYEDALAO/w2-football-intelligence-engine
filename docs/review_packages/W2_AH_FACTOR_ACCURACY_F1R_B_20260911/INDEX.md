# W2 AH factor accuracy — F1R-B production recording integration

```text
TASK_ID              W2_AH_FACTOR_ACCURACY_F1R_B_PRODUCTION_RECORDING_INTEGRATION_20260911
PARENT_COMMIT        71daa3f5ec17ac3c5484e75a87d6bcac990d4bae
ACCEPTED_BASELINE    db0f2c21b85fde45d67e2da03cb89b212d17d9a5 (F1R-A0 implementation)
FINAL_STATE          BLOCKED_BY_UNPROVABLE_FACTOR_SOURCE
```

## What this round did

Wired the accepted offline four-factor recorder to verifiable interfaces of the
real production sources, with the switch off. Three gaps had to close.

**1. F5/F6 real source-observed time — one closed, one blocked.**

F6 is now provable. `canonical_team_match_history.endpoint_capture_id` points
at the `matchday_endpoint_captures` row whose `provider_captured_at` is the
Provider read that already reported that fixture as finished, so it is a real
observation time for the result. The row's own `captured_at` is refused: it is
the materialisation run's clock and is *earlier* than the read it points at.

F5 is not provable and stays fail-closed. Four code facts, each re-derived from
the tree rather than asserted: no writer emits the markers the AH path
requires, `canonical_historical_ah_facts` has no reader in `src/`, its
`quote_captured_at` is a pre-match odds capture, and `results.confirmed_at` has
two writer semantics with no discriminator. Details in
`FACTOR_SOURCE_MAPPING.json`.

**2. Real `factor_version` for all four factors.**

`src/w2/domain/factor_versions.py` is the single authority. Each version names
the algorithm its builder runs and pins that builder function's source hash and
READY reason code, so changing the algorithm without revising the version fails
a lock test. No `SYNTHETIC_FIXTURE_v1`, no bare `v1`, no commit SHA. Caller
disagreement refuses the whole batch.

**3. Per-factor source capture identity and canonical SHA-256.**

Every observation binds the rows it actually consumed: set identity, content
hash, source version, record ids, observed times and semantics — all inside the
identity preimage, order-independent, and sensitive only to sources the factor
actually read.

## Terminal state

`BLOCKED_BY_UNPROVABLE_FACTOR_SOURCE`, because F5's real availability time
cannot be proven from current production data and code. Per §11 of the order
that state is mandatory regardless of what else completed, so the version
authority, the capture identity, the F6 proof, the migration package and the
test matrix are delivered *inside* a blocked round rather than held back.

The remaining work items — everything that is done, and the one thing that is
not — are listed in `TEST_RESULTS.md` against the 22-item matrix.

## Files

| File | What it is |
|---|---|
| `INDEX.md` | this page |
| `FACTOR_SOURCE_MAPPING.json` | per factor: builder, reader, table, evidence-time rule and its proof; F5's four blocking findings |
| `FACTOR_VERSION_AUTHORITY.json` | the four versions, their builder pins, the binding rules, and the stated limitation |
| `SOURCE_CAPTURE_IDENTITY.md` | how the capture id and hash are built and what they are sensitive to |
| `F1R_B_DATA_FLOW.md` | the path end to end, what is reused, and what is refused |
| `MIGRATION_AND_ROLLBACK.md` | the additive migration, its constraints, the isolated replay and the rollback paths |
| `ISOLATED_REPLAY_RESULT.json` | machine-readable result of upgrade → write → readback → rollback |
| `F1R_B_RESULT.json` | machine-readable result of the whole run, including every refusal code |
| `F1R_B_REFERENCE_LEDGER.jsonl` | the four recorded observations |
| `F1R_B_SOURCE_MANIFESTS.json` | the manifests the capture hashes were taken over |
| `TEST_RESULTS.md` | the 22-item matrix; the full suite under **both** test-path invocations at both commits, reconciled; the Ruff status |
| `HASHES.sha256` | this package's own hashes |
| `OBSIDIAN_UPDATE_PROPOSAL.md` | proposal only; the Vault was not written |

## Code delivered

```text
src/w2/domain/factor_versions.py                          version authority (new)
src/w2/infrastructure/persistence/forward_factor_models.py the table (new)
migrations/versions/0071_forward_ah_factor_observation.py  additive migration (new)
scripts/quant/f1r_b_source_capture.py                      capture identity (new)
scripts/quant/f1r_b_production_ports.py                    read ports, disabled (new)
scripts/quant/f1r_b_production_recording_integration.py    the wiring (new)
scripts/quant/f1r_b_observation_store.py                   the database sink (new)
scripts/quant/f1r_b_fixtures.py                            production-shaped offline rows (new)
scripts/quant/run_f1r_b_production_recording_integration.py the runner (new)
scripts/quant/tests/test_f1r_b_production_recording_integration.py   the matrix (new)
scripts/quant/tests/test_f1r_b_independent_oracle.py       the oracle (new)
```

`src/w2/features/team_factors.py` and `src/w2/features/live_factors.py` are
**not** modified: the frozen F1 package pins their hashes as its
source-code-default evidence.

## Three files outside `scripts/quant/`, and why

`AGENTS.md` and `QUANT_AGENTS.md` require new quant code to live under
`src/w2/quant_research/` or `scripts/quant/`. All the wiring does. Three files
sit elsewhere, deliberately, and each is called out here rather than left for
the acceptor to find:

| File | Why it is not under `scripts/quant/` |
|---|---|
| `src/w2/domain/factor_versions.py` | It is a production version authority for production builders, not quant research code, and §5 of the order requires "明确的、逐因子的版本声明及读取端口". The domain layer is where this codebase already keeps factor policy constants — `src/w2/domain/factor_registry.py` says so in its own comment. Putting it under `scripts/quant/` would make a production computation's version live outside production. |
| `src/w2/infrastructure/persistence/forward_factor_models.py` and `migrations/versions/0071_…` | §8 requires a real, additive, rollback-tested Alembic migration. `AGENTS.md` requires reusing "existing PostgreSQL/Alembic … through explicit ports" and forbids a second database engine. A model in the shared metadata plus one Alembic revision is the only way to satisfy both; a separate `Base` would be the second engine the rule forbids. |
| `tests/contract/test_f1r_b_independent_oracle.py` | `scripts/` is a canonical-serialization production root, and an independent oracle necessarily re-implements the serializer it checks. Leaving it under `scripts/quant/tests/` made `check_canonical_serialization_authority` report an unauthorised writer. Moving it is cleaner than registering a test file in a registry meant for legacy production sites. |

None of them touches `src/w2/prematch/`, `src/w2/strategy/`, V4, the Scheduler,
the Dashboard, the Provider allowlist or an existing future-refresh business
path.

The only two pre-existing files changed at all are
`src/w2/infrastructure/persistence/__init__.py` (six lines of exports) and the
architecture checklist's package matrix (six fields recomputed mechanically
from the source graph by the sanctioned regenerator).

## Full-suite headline

Reported under both test-path invocations, because reporting only one caused a
reconciliation dispute during acceptance. Same interpreter throughout; both
commits run against a clean worktree.

| commit | `pytest tests -q` | `pytest tests scripts/quant/tests -q` |
|---|---|---|
| `71daa3f5` baseline | 9 failed / 3072 passed / 9 skipped | 9 failed / 3452 passed / 10 skipped |
| `c482ccf9` delivered | 9 failed / 3084 passed / 9 skipped | 9 failed / 3588 passed / 10 skipped |

```text
NEW_FAILURES = 0 under both invocations; the same nine nodes fail in all four runs
NET_NEW_PASSING = 12 (tests only) / 136 (both paths) = the tests this task adds
RUFF = 10 errors, EXIT=1, in both trees, node lists identical
```

Ruff is not clean and this package does not claim it is. It exits 1 in both
trees on the same ten pre-existing `E501` nodes; what the commit adds is zero.

Targeted: 136 passed. Full detail, including the skip nodes and the
environment- and worktree-affected causes, is in `TEST_RESULTS.md`.

## Boundaries held

```text
REAL_PROVIDER_CALLS          = 0
PUBLIC_HTTP_FETCH            = 0
PRODUCTION_DB_READS          = 0
PRODUCTION_DB_WRITES         = 0
DEPLOYMENT_EXECUTED          = false
LIVE_CAPTURE_ENABLED         = false
TRACK1_FORWARD_CLOCK         = NOT_STARTED
SCHEDULER_MODIFIED           = false
PROVIDER_ALLOWLIST_MODIFIED  = false
DASHBOARD_MODIFIED           = false
V4_DECISION_BEHAVIOR_CHANGED = false
HISTORICAL_148_BACKFILLED    = false
OBSIDIAN_WRITES              = 0
```

Delivery means the wiring and the migration package can enter independent
acceptance. It does not mean anything is deployed, capturing, or a model
candidate.

`NEXT_TASK = R1-B independent acceptance (Codex)`
