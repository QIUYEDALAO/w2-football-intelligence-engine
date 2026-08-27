# POINT-EV-AUTHORITY-01 — status matrix

Protocol `6fdecb95`. Every `DONE` row names a file or a test that exists.

## Task objectives

| # | Objective | Status | Where |
|---|---|---|---|
| 1 | Trace and replay fixture 1570340 end to end | **PARTIAL** | 8 links traced; the xG windows and factor enablement are not recoverable from the retained record — report §9 |
| 2 | Classify, and name one primary root cause | DONE | `binding`; report §1, three independent defects in §2 |
| 3 | Unify calibration readiness authority across candidate paths | DONE | `w2/domain/calibration_authority.py`, imported by 5 modules |
| 4 | Five-state formula and historical ledger unchanged; no EV cap | DONE | report §3; tests (c) and the explicit no-cap test |
| 5 | Independent proposal with alternatives and trade-offs | DONE | report §3 alternatives, §10 sequencing |

## Trace links

| link | status | evidence |
|---|---|---|
| 1 quote and PIT inputs | DONE | bookmaker_count 5, odds 1.92, line 3.5, capture_at, quote_identity_hash |
| 2 four-field xG and windows | **NOT RECONSTRUCTABLE** | record stores `model_input_hash`, not the inputs |
| 3 factor enablement at as-of | **NOT RECONSTRUCTABLE** | same |
| 4 λ / σ | **NOT RECONSTRUCTABLE** from this record | referenced by `model_forecast_capture_identity_hash` |
| 5 score matrix | **NOT RECONSTRUCTABLE** from this record | — |
| 6 five-state distribution | DONE | WIN 0.74813, LOSS 0.25187, others 0.0, sums to 1.0 |
| 7 EV / EV_SE | DONE | EV `0.436411`, **EV_SE `0.050326`**, EV−SE `0.386085` — R0 mislabelled the third as the second |
| 8 candidate and notification decision | DONE | `ANALYSIS_PICK_ACTIVE`, `EVALUATED_CANDIDATE`, `CANDIDATE_T30_CONFIRMED` **DELIVERED** |

Links 2–5 are reported as unreconstructable rather than inferred, as the protocol
requires. The root cause does not depend on them: no gate consulted calibration
regardless of what produced the λ.

## Regression tests

| requirement | status | count |
|---|---|---|
| (a) unvalidated forms no formal recommendation | DONE | 15 |
| (b) approved validated path still admits | DONE | 5 |
| (c) EV formula, direction, odds format, five-state binding intact | DONE | 4 |
| (d) 1570340 yields NO_CANDIDATE / HOLD | DONE | 2 |
| (e) analysis evidence preserved | DONE | 3 |
| total (R0 file) | | **29 passed** |

## Deliverables

| item | status |
|---|---|
| Frozen protocol | DONE — `PROTOCOL_FROZEN_20260827.md` |
| Input evidence + SHA | DONE — `FIXTURE_1570340_EVALUATION.json`, sha256 `7c50b37f9d04630a…` |
| Output evidence + SHA | DONE — `FIXTURE_1570340_REPLAY.json`, sha256 `2b44380cf79b1b9b…` |
| Trace document | DONE — `FIXTURE_1570340_TRACE.json` |
| Root-cause report | DONE — `REPORT.md` |
| Status matrix | DONE — this file |
| Local commit and exact diff | DONE — `git diff fc70b48e --stat` |
| Regression proof (a)–(e) | DONE — 29 tests (R0) + 35 (R1/R2) = 64 |
| Sequencing view on V2 and dual-track | DONE — report §10 |

## Checks

| check | result |
|---|---|
| `pytest tests/` | **2,900 passed** / 6 failed / 9 skipped |
| the 6 failures | pre-existing, environmental, **identical set before and after** |
| `ruff check .` | All checks passed |
| `mypy src apps` | Success, 289 source files |
| API import-graph contract | passes — authority placed in `w2.domain`, not `w2.strategy` |
| package matrix contract | passes — counts updated for `domain`, `markets`, `prematch`, `strategy` |
| no-hardcoded-real-teams contract | passes — team names removed, sample identified by fixture ID |

## R1 findings and resolution

| # | Finding | Verdict | Resolution |
|---|---|---|---|
| 1 | calibration absent from the immutable identity; append-only swallows a different conclusion | CONFIRMED — R0 saw the trade-off and resolved it wrongly | in both identities with explicit version keys; report §12 |
| 2 | status never reached Version / as_dict / database | CONFIRMED | four audit fields on `DynamicEvaluationVersion`; report §13 |
| 3 | absent normalised to BASELINE_PRIOR, losing audit meaning | CONFIRMED | distinct `ABSENT`, still fails closed |
| 4 | `gate_results is None or …` could pass vacuously | CONFIRMED | replaced with a direct assertion on a denominator-scoped evaluation |
| 5 | 0.386085 labelled EV_SE; "whole market" overclaim | CONFIRMED | EV_SE is `0.050326`; devigged market is `0.500000`, model `24.8` points above |

## R1 acceptance tests

| id | requirement | status | count |
|---|---|---|---|
| a | BASELINE_PRIOR / READY / UNKNOWN / absent form no candidate or notification | DONE | 10 |
| b | validated passes and still faces the EV gates | DONE | 4 |
| c | no identity collision on calibration change | DONE | 4 |
| d | `as_dict` and database round-trip keep the audit fields | DONE | 4 |
| e | downgrade blocks and leaves no stale candidate; upgrade is its own attempt | DONE | 2 |
| f | market_candidate / read_model_projection / repository / notification exercised for real | DONE | 4 |
| g | no vacuous assertions | DONE | R0's replaced; none remain outside prose |
| h | EV_SE distinguished from EV−SE, devig from raw implied | DONE | 2 |
| | **total (identity file, after R2)** | | **35** |
| | R0 file, vacuous assertion replaced | | 29 |

## Identity separation, measured

Five calibration states over identical inputs:

| | value |
|---|---|
| shared `opportunity_identity_hash` | yes — it is the same betting opportunity |
| distinct `attempt_identity_hash` | 5 of 5 |
| `current_ev` across all five | `0.436411`, unchanged |

Frozen in `FIXTURE_1570340_REPLAY.json`, sha256
`2b44380cf79b1b9bec400d6a4ee6a03ae4da3e39342c40edd7bcdb1b10787cd0`.

## R2 findings and resolution

| # | Finding | Verdict | Resolution |
|---|---|---|---|
| 1 | repository rebuild drops the four calibration fields | CONFIRMED — reproduced on the duplicate-append path | `_version_from_payload` rebuilds them via `calibration_authority.reconstruct_from_payload` |
| — | legacy payloads without the keys | addressed | rebuild as `UNRECORDED` with no authority stamp; admissibility recomputed, never read from storage |
| 2 | tests read `row.payload`, not the rebuilt object | CONFIRMED | 5 tests now go through the repository API and assert on the rebuilt version |
| 3 | downgrade test used two different opportunities | CONFIRMED | fixed context; same capture, slot, quote, model input, checkpoint |
| 4 | REPORT §1 still carried the superseded market numbers | CONFIRMED — the document contradicted itself | one set of numbers throughout |

## R2 evidence SHA-256

| file | sha256 |
|---|---|
| `FIXTURE_1570340_EVALUATION.json` | `7c50b37f9d04630a88546e0e3a53363139df2b5a91ece34f456e81c92eae8cc1` |
| `FIXTURE_1570340_REPLAY.json` | `2b44380cf79b1b9bec400d6a4ee6a03ae4da3e39342c40edd7bcdb1b10787cd0` |
| `FIXTURE_1570340_TRACE.json` | `00ed1db160db2e0e3cc2f5bbec6b88c1d9ef9a93ba025631dac1da1d3eade009` |

## Same-opportunity downgrade, measured

| property | observed |
|---|---|
| `opportunity_identity_hash` unchanged | yes |
| `attempt_identity_hash` distinct | yes |
| evaluation rows appended | 2 — `ANALYSIS_PICK_ACTIVE`, then `NOT_READY_MODEL_INPUT` |
| latest attempt | the unvalidated one |
| opportunity final state | `BLOCKED_BY_GATE` |
| outbox | `CANDIDATE_FORMED`, then `CANDIDATE_WITHDRAWN` (`EVALUATED_CANDIDATE` → `BLOCKED_BY_GATE`) |
| duplicate notifications or identity conflict | none |

## Boundaries

| constraint | status |
|---|---|
| Provider calls 0 | HELD |
| Production database writes 0 | HELD — reads only, `REPEATABLE READ READ ONLY`, rolled back |
| GitHub 0 | HELD |
| Deploy 0 | HELD |
| Separate worktree, main workspace Dashboard untouched | HELD — `/Users/liudehua/.hermes/worktrees/w2-point-ev-authority` on `claude/point-ev-authority-01` from `fc70b48e` |
| Match result not read | HELD |
| Current 65 picks not used | HELD |
| Historical recommendations / settlements / V1 params unchanged | HELD |
| α/β remain NULL | HELD — not touched; EV-SE is a separate line |
| Contract 1 / production formula not implemented | HELD |
| Model-parameter or switch needs submitted as proposal only | HELD — report §10 |

## Known deviations

1. **Links 2–5 of the trace are not reconstructable** from the retained evaluation
   record. Reported, not inferred. Recovering them needs the analysis card at that
   capture, a read not made here.
2. **The fix changes shipped behaviour materially**: with `BASELINE_PRIOR` in place,
   no formal candidates form at all. Correct, but the Owner should decide this
   knowingly — report §10 item 4.
3. **Two repository inventory contracts were updated** (package file and caller
   counts) because adding a module and a test file changed the counts they track.
