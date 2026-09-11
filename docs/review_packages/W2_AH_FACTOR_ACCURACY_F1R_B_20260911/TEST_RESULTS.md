# F1R-B test results

`W2_AH_FACTOR_ACCURACY_F1R_B_PRODUCTION_RECORDING_INTEGRATION_20260911`
Parent commit `71daa3f5ec17ac3c5484e75a87d6bcac990d4bae`.

```text
PYTHON   /Users/liudehua/Documents/Projects/W2-workspaces/w2-official-candidate-accuracy-20260909/.venv/bin/python
         Python 3.12.13
PYTEST   8.4.2
RUFF     0.15.18
```

Two test-path invocations are reported, because they are the source of an
earlier reporting discrepancy and both are legitimate:

```bash
./.venv/bin/python -m pytest tests -q                        # A
./.venv/bin/python -m pytest tests scripts/quant/tests -q    # B
```

Every figure below was produced at the delivered commit `c482ccf9` with a clean
worktree, and at the baseline `71daa3f5`, with the **same interpreter** in both.
The baseline is a detached worktree
(`/Users/liudehua/Documents/Projects/W2-workspaces/w2-r1b-baseline-71daa3f5`);
under pytest its own `src` wins over the editable install, verified by importing
`w2` inside a pytest run there and confirming both the path and the absence of
`w2.domain.factor_versions`.

Full stdout/stderr for all four runs, both collect-only runs and both Ruff runs:

```text
/Users/liudehua/Desktop/W2文档/W2_R1B_TEST_RECONCILIATION_20260911/
  COMMANDS.md                exact commands, interpreter, and the results table
  collect_<sha>_tests.txt     collect-only, path set A
  collect_<sha>_both.txt      collect-only, path set B
  run_<sha>_tests.txt         full run, path set A   (ends with EXIT=<code>)
  run_<sha>_both.txt          full run, path set B   (ends with EXIT=<code>)
  ruff_<sha>.txt              ruff concise output    (ends with EXIT=<code>)
```

## The mandatory matrix

| # | Requirement | Where |
|---|---|---|
| 1 | F3/F5/F6/F9 complete batch | `test_01_a_complete_batch_records_all_four_factors`, `test_01_each_factor_carries_its_own_version_capture_and_time`, `test_01_the_four_evidence_semantics_are_distinct_and_correct` |
| 2 | each factor missing `factor_version` | `test_02_a_missing_factor_version_refuses_the_batch` (×4) |
| 3 | caller version ≠ builder version | `test_03_a_caller_version_that_is_not_the_builders_refuses` (4 factors × 4 impostors incl. `v1` and a commit SHA), `test_03_the_version_authority_matches_the_executed_builder`, `test_03_there_is_exactly_one_version_mapping` |
| 4 | each factor missing capture id / hash / version | `test_04_a_missing_capture_field_refuses_the_batch` (4 × 3), `test_04_an_empty_consumed_set_refuses` |
| 5 | capture hash illegal, uppercase, wrong length, tampered content | `test_05_an_illegal_capture_hash_refuses` (×6), `test_05_an_uppercase_hash_is_refused_not_normalised`, `test_05_tampering_with_consumed_content_changes_the_capture_hash` |
| 6 | F5 missing result time, missing AH fact time, only `confirmed_at` | `test_06_the_f5_ah_fact_port_refuses_every_call`, `test_06_f5_blocking_evidence_names_all_four_findings`, `test_06_no_production_writer_emits_a_canonical_ah_fact_row`, `test_06_f5_participating_without_a_source_time_refuses_the_batch` |
| 7 | F6 missing result time | `test_07_an_f6_row_with_no_endpoint_capture_refuses`, `test_07_an_unresolvable_capture_refuses`, `test_07_an_unsuccessful_capture_is_not_evidence` (×2), `test_07_the_materialisation_clock_is_never_used_as_the_source_time` |
| 8 | F5/F6 kickoff masquerading as a source time | `test_08_a_capture_time_equal_to_kickoff_refuses`, `test_08_a_capture_time_before_kickoff_refuses`, `test_08_f6_evidence_time_is_not_the_contributions_observed_at`, `test_08_f3_may_not_read_a_result_field` |
| 9 | `evidence_time = max(consumed source times)` | `test_09_evidence_time_is_the_latest_consumed_source_time`, `test_09_a_later_consumed_source_moves_the_evidence_time`, `test_09_f9_uses_the_latest_of_both_team_snapshots` |
| 10 | unconsumed change inert, consumed change moves identity | `test_10_reordering_…`, `test_10_changing_a_consumed_source_changes_the_observation_identity`, `test_10_a_source_the_factor_never_consumed_changes_nothing`, `test_10_a_wrong_sized_consumed_set_refuses`, `test_10_a_right_sized_but_wrong_consumed_set_refuses`, `test_10_a_synthetic_record_cannot_reach_the_production_branch`, `test_10_a_synthetic_capture_id_is_labelled` |
| 11 | evidence time equal/later, naive, mixed zones | `test_11_evidence_time_equal_to_evaluated_at_refuses`, `test_11_evidence_time_after_evaluated_at_refuses`, `test_11_a_naive_source_time_refuses`, `test_11_mixed_zones_are_the_same_instant_and_the_same_identity` |
| 12 | participation and applied weight follow the authority | `test_12_participation_is_the_scoring_authoritys_verdict`, `test_12_a_non_participating_factor_applies_no_weight_and_carries_no_score`, `test_12_a_participating_factors_applied_weight_is_the_authoritys` |
| 13 | batch weight closure, tamper refuses | `test_13_applied_weights_sum_to_what_the_authority_used`, `test_13_a_tampered_applied_weight_refuses_the_batch` |
| 14 | missing / duplicated / mixed identity | `test_14_a_missing_factor_binding_refuses` (×4), `test_14_a_missing_contribution_refuses`, `test_14_a_batch_may_not_mix_identities` (×4), `test_14_a_duplicated_factor_refuses` |
| 15 | idempotent, conflict, revision chain, dangling, cycle | `test_15_replaying_a_batch_into_the_store_is_a_no_op`, `test_15_the_same_identity_with_different_content_conflicts`, `test_15_a_revision_chain_appends_and_leaves_the_old_rows`, `test_15_a_dangling_supersedes_refuses`, `test_15_a_supersedes_cycle_refuses` |
| 16 | zero rows on validation / first write / mid write / fsync / commit point / DB transaction failure | **database**: `test_16_a_refused_batch_adds_zero_rows_to_the_store` (validation), `test_16_a_database_failure_on_the_first_row_adds_zero_rows` (first write), `test_16_a_database_failure_midway_adds_zero_rows` (mid write), `test_16_a_failure_at_the_database_commit_point_adds_zero_rows` (commit point), `test_16_zero_rows_survive_a_second_attempt_after_a_failure` (retry writes all four). **file ledger**: `test_16_a_refused_batch_leaves_the_file_ledger_byte_identical`, `test_16_an_fsync_failure_adds_no_lines`, plus the retained A0 injections `test_atomicity_a_failure_on_the_first_write_leaves_the_ledger_untouched`, `test_atomicity_a_failure_midway_through_leaves_the_ledger_untouched`, `test_atomicity_a_failure_at_the_commit_point_leaves_the_ledger_untouched`, `test_atomicity_no_temporary_file_survives_a_failure` |
| 17 | migration upgrade / readback / rollback / repeat | `test_17_the_isolated_replay_upgrades_writes_reads_back_and_rolls_back`, `test_17_the_migration_is_additive_only`, `test_17_a_populated_downgrade_refuses_rather_than_destroying_facts`, `test_17_every_meaningful_column_is_not_null` |
| 18 | historical payload / identity / hash unchanged | `test_18_the_migration_touches_no_existing_table`, `test_18_historical_no_factor_verdict_identity_still_means_what_it_meant`, `test_18_the_frozen_f1p_reference_ledger_still_validates` |
| 19 | F0/F1/F1P/F1R-A0 frozen hashes unchanged | `test_19_frozen_package_hashes_are_unchanged` (×4 packages), `test_19_the_pinned_builder_sources_are_still_the_frozen_f1_evidence` |
| 20 | no network / Provider / production DB / VPS / Scheduler / Dashboard / V4 side effect | `test_20_no_network_provider_or_vps_reference` (×5 modules), `test_20_the_live_capture_switch_is_off`, `test_20_enabling_the_port_is_still_not_authorised`, `test_20_the_production_chain_does_not_import_this_wiring`, `test_20_no_scheduler_dashboard_or_v4_module_was_modified`, `test_20_no_second_serializer_or_hash_writer_is_defined` |
| 21 | independent oracle, no import of the production recorder | `tests/contract/test_f1r_b_independent_oracle.py` — 12 tests, including `test_the_oracle_imports_no_production_implementation` which proves by AST that it neither imports nor side-loads any of them |
| 22 | runner byte-identical across two temporary directories | `test_22_two_runs_in_different_directories_are_byte_identical`, `test_22_the_published_result_states_what_is_not_done` |

Targeted result:

```text
scripts/quant/tests/test_f1r_b_production_recording_integration.py   124 passed
tests/contract/test_f1r_b_independent_oracle.py                       12 passed
                                                                     ------------
                                                                     136 passed
```

The commit-point injection is worth one note. Patching `Session.commit` made
the test pass while proving nothing: the store commits through
`with session.begin()`, which calls `SessionTransaction.commit`. The test
patches that instead, and the first version of it failed with
`DID NOT RAISE` — which is how the wrong seam was caught.

All four published artifacts are byte-identical across two runs in different
directories and identical to the copies in this package:
`F1R_B_REFERENCE_LEDGER.jsonl`, `F1R_B_RESULT.json`,
`F1R_B_SOURCE_MANIFESTS.json`, `ISOLATED_REPLAY_RESULT.json`.

## Two defects the matrix caught in my own work

Recorded because they are the reason those two tests exist.

**A plain unique constraint outlawed the revision chain.** The first version of
the migration made `(evaluation_id, attempt_id, fixture_id, market, factor_id,
evaluated_at_utc)` unique outright. `test_15_a_revision_chain_appends_and_leaves_the_old_rows`
failed with an `IntegrityError`: a correction is an append that supersedes an
earlier row, so the same factor legitimately reappears on the same attempt. The
index is now partial — unique only where `supersedes_observation_id is null`.

**A participating factor could inherit an absence lookup's query time.**
`test_06_f5_participating_without_a_source_time_refuses_the_batch` was written
expecting a refusal and got a recorded observation: an F5 that the scoring
authority scored was being handed the "we looked and found nothing" record as
its source, whose `observed_at` is the as-of. That is exactly the substitution
this task exists to prevent. The integration now refuses with
`PARTICIPATED_FACTOR_BOUND_TO_ABSENCE_LOOKUP`.

## Full suite — both test-path invocations, both commits

An earlier version of this page reported only path set B, and reported it from
the *uncommitted* tree. An independent re-run used path set A on the committed
tree and got different numbers. Neither was wrong; they were different scopes.
Both are now reported, and they reconcile exactly.

### Collection

| commit | `tests` (A) | `tests scripts/quant/tests` (B) |
|---|---|---|
| `71daa3f5` baseline | 3090 collected | 3471 collected |
| `c482ccf9` delivered | 3102 collected | 3607 collected |

```text
3102 - 3090 = 12    tests/contract/test_f1r_b_independent_oracle.py
3607 - 3102 = 505   scripts/quant/tests at c482ccf9
3471 - 3090 = 381   scripts/quant/tests at 71daa3f5
 505 -  381 = 124   scripts/quant/tests/test_f1r_b_production_recording_integration.py
  12 +  124 = 136   the tests this task adds
```

### Results

| commit | paths | collected | failed | passed | skipped | pytest exit |
|---|---|---|---|---|---|---|
| `71daa3f5` | A | 3090 | 9 | 3072 | 9 | 1 |
| `71daa3f5` | B | 3471 | 9 | 3452 | 10 | 1 |
| `c482ccf9` | A | 3102 | 9 | 3084 | 9 | 1 |
| `c482ccf9` | B | 3607 | 9 | 3588 | 10 | 1 |

Each row closes: `3072+9+9 = 3090`, `3452+9+10 = 3471`, `3084+9+9 = 3102`,
`3588+9+10 = 3607`.

```text
NEW_FAILURES              = 0   (path set A and path set B)
FIXED_OR_NEWLY_PASSING    = 0
NET_NEW_PASSING  path A   = 12    3084 - 3072
NET_NEW_PASSING  path B   = 136   3588 - 3452
```

The failure set is **the same nine nodes in all four runs**, and all nine live
under `tests/`, which is why path set A sees every one of them:

```text
tests/contract/test_api_projection_read_authority.py::test_missing_projection_is_explicit_system_degraded_not_empty
tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path0]
tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path1]
tests/contract/test_production_odds_reads.py::test_api_dashboard_card_keeps_historical_v3_identity_immutable
tests/contract/test_sc18_input_authority.py::test_sc18_authority_artifacts_are_complete_and_self_checking
tests/integration/test_future_refresh_staging_parity.py::test_preflight_fails_root_0700_runtime_for_worker_uid
tests/integration/test_future_refresh_staging_parity.py::test_preflight_passes_worker_owned_0750_runtime
tests/regression/test_stage3_contracts.py::test_no_hardcoded_real_teams_leagues_or_fixtures
tests/unit/test_ev_migration_2b.py::test_frozen_29601_rows_match_exactly
```

The skip set is nine nodes under `tests/` in all four runs, plus one more when
`scripts/quant/tests` is included — which is the whole of the 9-versus-10
skipped difference:

```text
[2] tests/integration/test_gate_a_staged_canary.py:145   W2_TEST_POSTGRES_URL is required for staged CLI E2E
[1] tests/integration/test_migrations.py:727             W2_TEST_POSTGRES_URL is required for PostgreSQL staging-state migration
[3] tests/integration/test_migrations.py:1291            W2_TEST_POSTGRES_URL is required for PostgreSQL dependency mutation
[1] tests/unit/test_gate_a_offline.py:485                W2_TEST_POSTGRES_URL is required for PostgreSQL task-key fencing
[1] tests/unit/test_gate_a_offline.py:521                W2_TEST_POSTGRES_URL is required for fixture binding fencing
[1] tests/unit/test_stage7i_successor_tooling.py:397     SKIPPED_REQUIRES_PRIVILEGE
[1] scripts/quant/tests/test_f1p_forward_factor_contract.py:255   market is pinned to ASIAN_HANDICAP   <- path set B only
```

### What is environment- or worktree-affected, and why

Named by cause rather than labelled, because "pre-existing" is not by itself an
explanation. All of these fail or skip identically at `71daa3f5`, so none
contributes to the delta.

| Node | Cause | Kind |
|---|---|---|
| `test_sc18_input_authority` | shells out to a bare `python`; fails with `FileNotFoundError: [Errno 2] No such file or directory: 'python'` | PATH |
| `test_ev_migration_2b::test_frozen_29601_rows_match_exactly` | needs `docs/review_packages/EV_CONTRACT_2A_20260906/differences.json`, which is untracked in git and absent from **both** worktrees | worktree state |
| `test_future_refresh_staging_parity` ×2 | host uid/gid/mode preflight against a runtime directory | host permissions |
| `test_compose_env_dedup` ×2, `test_api_projection_read_authority`, `test_production_odds_reads`, `test_stage3_contracts` | pre-existing at the baseline; `test_stage3_contracts` flags `Premier League` in `tests/unit/test_task3_t30_checkpoint.py`, a file this task did not touch | pre-existing |
| the five `W2_TEST_POSTGRES_URL` skips | that variable is unset here | environment |

That last row is also the concrete way to close the residual PostgreSQL gap
recorded in `MIGRATION_AND_ROLLBACK.md`: this repository already has
PostgreSQL-only migration tests that skip without `W2_TEST_POSTGRES_URL`, so a
reviewer with a PostgreSQL instance can exercise migration 0071 on that dialect
by setting it. This package does not do so — reaching a PostgreSQL instance was
out of scope for this task.

### Five failures I introduced, all fixed before delivery

The first working-tree run had 14 failures under path set B. Five were mine.
They are listed because "fixed before delivery" is still something the acceptor
should be able to see and re-check.

| Failure | Cause | Fix |
|---|---|---|
| `test_canonical_serialization_static_guard::test_canonical_serialization_authority_guard` | the independent oracle re-implements the serializer, and `scripts/` is a canonical-serialization production root | moved the oracle to `tests/contract/`, which is not a production root, rather than registering a test file in the legacy-exception registry |
| `test_src_w2_package_matrix::test_matrix_rows_match_the_current_dependency_graph` | two new modules changed the package graph | regenerated the six mechanical fields with `scripts/quant/regenerate_src_w2_package_matrix.py`; judgement columns untouched |
| `test_src_w2_package_matrix::test_matrix_callers_entrypoints_and_classifications_are_complete` | same | same |
| `test_infrastructure_literal_guard::test_active_scripts_and_runbooks_have_no_public_ipv4_literals` | my own test spelled out the VPS address in order to forbid it, and that literal is itself the violation | the test now asserts no address-shaped literal by pattern |
| `test_ah_factor_accuracy_f0.py::test_f0_touches_no_production_path` | reads `git status --porcelain=v1` and refuses uncommitted paths under `migrations/`; this task adds a migration | resolved by committing. It is absent from the failure list in every run above, all of which ran against the clean committed tree |

The package matrix change is the only edit to an existing artifact, and it is
mechanical: six fields recomputed from the source graph, `DRIFT_ROWS=6` before,
`0` after.

## Ruff

```text
./.venv/bin/ruff check . --output-format=concise
BASELINE 71daa3f5   Found 10 errors   EXIT=1
DELIVERED c482ccf9  Found 10 errors   EXIT=1
NEW = 0   FIXED = 0   node diff = empty
```

**Ruff exits 1 in both trees.** It is not clean and this package does not claim
it is; what it claims is that the delivered commit adds nothing to it.

The ten are node-for-node identical in both trees — all `E501` in
`tests/unit/test_ev_canonical_contract.py` and `tests/unit/test_ev_migration_2b.py`:

```text
tests/unit/test_ev_canonical_contract.py:28,98,108,118
tests/unit/test_ev_migration_2b.py:14,20,23,32,35,40
```

Every file this task added or changed passes `ruff check` cleanly. Exit 0 was
not claimed and no rule was disabled.

## Nothing was weakened

No test was deleted, skipped, xfailed or loosened. The two tests I changed are
tests I wrote in this task, and both were made stricter, not weaker: one now
asserts a specific refusal code instead of accepting any of three, and the
other checks the migration's DDL calls by AST instead of grepping its prose.
