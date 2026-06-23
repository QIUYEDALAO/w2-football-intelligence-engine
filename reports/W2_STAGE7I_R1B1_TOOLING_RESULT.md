# W2 Stage7I-R1B1 Tooling Result

## Summary

- Stage package: W2-STAGE7I-R1B1 successor tooling readiness
- Repository branch: `chore/stage7i-24h-observation`
- Baseline commit before this package: `8fa3001e6d5f5462a19cf0d16b1c6c62783f3a32`
- Server revision baseline: `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- Gate5: `OPEN`
- Candidate output: `false`
- Formal recommendation output: `false`
- Deployment freeze: `ACTIVE`

This package prepares tooling only. It does not select a real successor fixture, does not start or stop an observer, does not deploy, and does not modify W1.

## Findings

- The Stage7I checker had active validation coupled to archive fixture `1489401`.
- The observer used the old Alembic head contract from Stage15A instead of requiring the expected head at runtime.
- The runbook described per-run lock examples, while successor observation requires a single global singleton lock.
- There was no hermetic selector for validating successor fixture eligibility without touching staging or external fixture sources.

## Changes

- `scripts/check_w2_stage7i.py`
  - Added explicit `archive`, `bootstrap`, and `final` validation modes.
  - Kept Run 01 archive validation for fixture `1489401` and observer PID `343187`.
  - Made successor bootstrap/final validation fixture-specific and sourced from start/selection evidence.
  - Rejected `candidate=true`, `formal_recommendation=true`, duplicate events, time reversal, fake actual kickoff, and invalid closing evidence.

- `scripts/run_stage7i_observer.py`
  - Removed active hardcoded Stage15A Alembic head handling.
  - Added required fixture, kickoff, baseline revision, expected Alembic head, and selection JSON inputs.
  - Added global singleton lock support at `/opt/w2/shared/runtime/stage7i/observer-global.lock`.
  - Wrote fixture-specific start/sample metadata and recorded `ACTUAL_KICKOFF_SOURCE_UNAVAILABLE` when no internal source exists.

- `scripts/select_stage7i_successor.py`
  - Added dry-run, read-only successor selector.
  - Restricted API access to localhost.
  - Supported hermetic `--input-json` testing.
  - Required reliable provider mapping, fresh market observation, safe pre/post kickoff windows, non-archive fixture ID, and no active global lock.
  - Used deterministic ranking by freshness, bookmaker coverage, window fit, and fixture ID.

- `docs/runbooks/STAGE7I_24H_OBSERVATION.md`
  - Split R1B into tooling readiness and runtime bootstrap.
  - Documented the global observer lock.
  - Documented selector dry-run use and the actual kickoff/closing evidence boundary.

- `tests/unit/test_stage7i_successor_tooling.py`
  - Added hermetic coverage for archive/bootstrap/final checker behavior, selector eligibility, global lock behavior, observer contract, and Alembic head mismatch handling.

- `reports/W2_CURRENT_HANDOFF.md`
  - Updated to handoff version `6`.
  - Recorded dynamic fixture binding, dry-run selector mode, expected Alembic head, global lock path, and containing-commit CI dependency.

## Validation

Required validation for this package:

- `python3 -m py_compile scripts/check_w2_stage7i.py scripts/run_stage7i_observer.py scripts/select_stage7i_successor.py`
- `python3 scripts/check_w2_stage7i.py --help`
- `python3 scripts/run_stage7i_observer.py --help`
- `python3 scripts/select_stage7i_successor.py --help`
- `uv run --python 3.12 pytest -q tests/unit/test_stage7i_successor_tooling.py`
- `uv run --python 3.12 python scripts/check_w2_stage1_contracts.py`
- `uv run --python 3.12 ruff check .`
- `uv run --python 3.12 mypy src apps`
- `uv run --python 3.12 pytest -q`
- `PYTHONPATH=.:src uv run --python 3.12 python scripts/check_w2_all.py`
- `uv run --python 3.12 python tests/secret_scan.py`
- `git diff --check`
- `rg -n 'FIXTURE_ID = "1489401"|EXPECTED_HEAD = "0016_' scripts tests`

The final command must return no active hardcoded fixture/head matches. Historical archive references to `1489401` remain allowed.

## Remaining Blockers

- `SUCCESSOR_FIXTURE_NOT_SELECTED`
- `SUCCESSOR_OBSERVATION_NOT_STARTED`
- `ACTUAL_KICKOFF_NOT_CAPTURED_BY_CONTINUOUS_FORWARD_RUN`
- `CLOSING_NOT_CAPTURED_BY_CONTINUOUS_FORWARD_RUN`
- `SETTLEMENT_EVALUATION_NOT_CAPTURED`
- `FINAL_SHADOW_DB_AUDIT_PENDING`
- `GATE5_OPEN`

## Next Step

Stage7I-R1B2 dynamic successor selection and observer bootstrap may proceed only after the containing commit passes CI. R1B2 must select the successor fixture from W2 staging/provider evidence and start a real observer under the global singleton lock.

## Rollback

No rollback is required at R1B1 completion if validation and CI pass. The changes are tooling-only and do not alter staging runtime state, database schema, W1, sensitive values, or deployment configuration.
