# Status matrix

| Requirement | Status | Evidence |
|---|---|---|
| exact non-FF merge parents | PASS | `f3265ac0`, parents `ea557bb8` + `f0d201c5` |
| four POINT-EV patch pairs equivalent | PASS | `PATCH_ID_MATRIX.md` |
| POINT-EV content effective once | PASS | one domain authority; deployed first-parent content retained |
| identity v1 compatibility retained | PASS | constant present; direct v2-first then v1-fallback assertion |
| new writes cannot select v1 | PASS | public classifier exposes only `value`; direct signature assertion |
| package matrix fully recomputed | PASS | `_graph()` / `_external_callers()` contract: 5 passed |
| Alembic single head | PASS | `0070_factor_shadow_v2_gate0` only |
| preregistration bytes unchanged | PASS | `cad4b549…36c1`, `5c6b13b5…4c880` |
| successor semantic hash unchanged | PASS | `bf2b539d…4e98` |
| validator wording corrected | PASS | bare invocation documented; nonexistent `--check` removed |
| full suite vs deployed baseline | PASS | exact same five failure IDs; 2975 passed / 9 skipped |
| Ruff lint | PASS | `ruff check .` |
| mypy | PASS | 299 `src apps` files |
| stop lines | PASS | Provider/prod/GitHub/deploy/apply/start all zero |
| Task 6 | NOT STARTED | waits for independent acceptance |

Gate 1 remains `FAIL_PENDING_PROSPECTIVE_CONFIRMATION`; Gate 2 remains `CLOSED`.
