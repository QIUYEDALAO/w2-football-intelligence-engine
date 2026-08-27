# POINT-EV-AUTHORITY-01 — root cause and fix

Protocol `6fdecb95`, frozen before the trace. Evidence in this directory. Nothing
is deployed and nothing is authorised; the branch is local.

## 1. Classification and the single root cause

**Primary root cause — `binding`.** The probability's declared validity was never
bound to the predicates that decide a formal recommendation.

The test is the one the protocol fixed in advance: removing this alone would have
prevented the outcome. The production record for fixture `1570340` shows it
directly. Seven gates ran and all passed:

```
bookmaker_depth  candidate  evaluated  mainline_parsed  model_ready  no_edge  quote_fresh
```

None of them is about calibration. `blockers: []`, `all_failed_gates: []`,
`first_failed_gate: null`, `official_funnel_eligible: true`. The evaluation reached
`ANALYSIS_PICK_ACTIVE` and `EVALUATED_CANDIDATE`, and a `CANDIDATE_T30_CONFIRMED`
notification was **DELIVERED** at `2026-08-26T18:32:56Z`.

Two predicates decide candidacy and neither consulted calibration:

- `lifecycle._state` — the module that emits `ANALYSIS_PICK_ACTIVE` — contained no
  reference to calibration at all;
- `market_candidate._admission_eligible` — evidence completeness, role, EV,
  EV−SE and cashflow edge, and nothing else.

The one function that did check, `round3_intelligence._model_blockers`, sits on the
Round-3 path rather than the candidate path, so it never saw this decision.

**What it is not.** Not `formula`: `0.748131 x 0.92 − 0.251869 = 0.436412` matches
the recorded `+43.6411%` to the digit. Not a five-state binding defect: a `.5` line
admits no push, and `PUSH`/`HALF_WIN`/`HALF_LOSS` are all `0.0` with the states
summing to `1.0`. Not `display`: `workspace.py` already renders `BASELINE_PRIOR` as
`PRIOR_ONLY`, so the surface was telling the truth while the decision ignored it.

The probability itself is unvalidated rather than wrong-given-its-inputs:
`CALIBRATION_STATUS = "BASELINE_PRIOR"` is a hardcoded constant over hand-set
weights (`home_advantage_goals=0.12`, `elo_gap_weight=0.28`, …) that were never
fitted. The record's own devigged market probability is `0.500000` (model
`0.748131` minus the recorded delta `0.248131`), so the model sat **24.8 points**
above the market the system itself computed — the shape of an uncalibrated
probability, not an edge.

## 2. Independent defects, each with its own class

1. **`READY` in a recommendation allowlist** — `binding`.
   `_model_blockers` accepted `{READY, PRODUCTION_VALIDATED, APPROVED_VALIDATED}`
   while `analysis_calculator` accepted only the latter two. `READY` is the
   simulation pipeline's status: it means a distribution was produced, not that the
   probability was validated. Two authorities disagreed and the looser one governed
   its path.
2. **The decision record carried no calibration field** — `binding`. The frozen
   evaluation payload for `1570340` has no `calibration*` key anywhere, so a
   reviewer reading the record behind a delivered recommendation could not tell
   whether the probability had ever been validated.
3. **Calibration was recorded into the candidate payload but never into
   `blockers`** — `binding`. `market_candidate` wrote
   `"calibration": {"status": …}` for display and dropped it from the decision.

All three are the same family — evidence recorded, authority not applied — which is
why one shared authority fixes them together rather than three separate patches.

## 3. The fix

**One authority, imported everywhere.** `w2/domain/calibration_authority.py`
answers a single question: may this calibration status support a formal
recommendation. `RECOMMENDATION_VALIDATED_STATUSES` is `{PRODUCTION_VALIDATED,
APPROVED_VALIDATED}`. `NON_VALIDATION_STATUSES` names `READY`, `BASELINE_PRIOR` and
the rest explicitly, so moving one into the allowlist reads as a change of meaning
rather than a typo. Absent or blank fails closed.

It lives in `w2.domain`, not `w2.strategy`, for two reasons: which states carry
authority is a domain invariant, and
`tests/contract/test_api_projection_read_authority.py` forbids the API's transitive
import graph from reaching `w2.strategy` — `lifecycle` is on that graph. Putting it
in `w2.strategy` first is how I found that constraint.

Wired into five places: `lifecycle` (new gate plus a `calibration_validated` entry
in `gate_results` and `CALIBRATION_VALIDATED` in the failed-gate ordering),
`read_model_projection` (plumbs the status off the simulation),
`market_candidate._admission_eligible`, `round3_intelligence._model_blockers`
(local allowlist deleted), and `analysis_calculator` (its own set deleted).
`analysis_evidence` now stamps every evidence document with the calibration behind
it, which closes defect 2.

**Alternatives considered.** Adding the check to each admission predicate
separately was rejected: two definitions drifting apart is what caused this.
Refusing to emit a distribution when uncalibrated was rejected because it destroys
the analysis evidence the task requires preserved. **No EV cap** — a cap hides an
uncalibrated probability behind a threshold fitted to this fixture, and the protocol
prohibited it in advance.

One deliberate API choice: `_admission_eligible`'s `calibration_status` is a
**required** keyword, not a defaulted one. My first wiring gave it a default, and
both call sites then silently passed `None` and blocked everything including
validated calibrations. Removing the default makes that mistake impossible.

**What is not changed.** The five-state settlement formula, its bindings, historical
recommendations, historical settlements, the outcome ledger, and V1 probability
parameters. `alpha_age_per_day` and `beta_missing` stay `NULL`. EV passes through at
any magnitude.

## 4. Replay of fixture 1570340

`FIXTURE_1570340_REPLAY.json`, same recorded inputs, four calibration states:

| calibration | state | EV | blockers |
|---|---|---|---|
| `BASELINE_PRIOR` (shipped) | `NOT_READY_MODEL_INPUT` | 0.436411 | `MODEL_CALIBRATION_NOT_VALIDATED` |
| `READY` (pipeline status) | `NOT_READY_MODEL_INPUT` | 0.436411 | `MODEL_CALIBRATION_NOT_VALIDATED` |
| absent | `NOT_READY_MODEL_INPUT` | 0.436411 | `MODEL_CALIBRATION_NOT_VALIDATED` |
| `PRODUCTION_VALIDATED` | `ANALYSIS_PICK_ACTIVE` | 0.436411 | — |

`NOT_READY_MODEL_INPUT` maps to `OpportunityState.BLOCKED_BY_GATE`, which is the
NO_CANDIDATE/HOLD outcome. **EV is identical in all four rows** — the authority
moved, the arithmetic did not.

## 5. Regression tests

`tests/unit/test_point_ev_calibration_authority.py`, 29 tests, all passing. R1 and R2 add `tests/unit/test_point_ev_calibration_identity.py`, 35 tests.

| requirement | tests |
|---|---|
| (a) unvalidated forms no recommendation on any path | 15 — every unvalidated status against `lifecycle` and `_model_blockers`, plus `READY` is not a verdict |
| (b) validated still admits | 5 — including that a validated model with negative EV still gets `NO_EDGE_CURRENT`, so authority is a precondition and not a bypass |
| (c) formula, direction, odds format, five-state binding intact | 4 |
| (d) 1570340 yields no candidate under the shipped model | 2 — and admits once validated, showing the block is about provenance |
| (e) analysis evidence preserved | 3 — including an explicit no-EV-cap test |

## 6. Test, lint and type results

| check | result |
|---|---|
| `pytest tests/` | **2,900 passed**, 6 failed, 9 skipped |
| the 6 failures | **pre-existing and environmental** — identical set before and after the change; docker socket unavailable and `python` not on PATH |
| `ruff check .` | All checks passed |
| `mypy src apps` | Success, no issues in 289 source files |
| new regression suites | 64 passed (29 + 35) |

The baseline comparison was run by stashing the change and diffing the failure sets;
they match exactly. 2,836 passed before, 2,900 after — the difference is the 64 new
tests.

Two repository contracts were updated because they track reality and reality moved:
the package matrix file count for `w2.domain` (17→18) and the test-caller counts for
`domain`, `markets`, `prematch` and `strategy` (+1 each). A third contract caught a
real mistake — real team names in a docstring — and those were removed; the frozen
sample is identified by fixture ID.

## 7. Reproduction

```bash
cd /Users/liudehua/.hermes/worktrees/w2-point-ev-authority
V=/Users/liudehua/.hermes/worktrees/w2-ev-se-offline-validation/.venv/bin

PYTHONPATH=src $V/python -m pytest -q tests/unit/test_point_ev_calibration_authority.py
PYTHONPATH=src $V/python -m pytest -q tests/
$V/ruff check .
$V/mypy src apps
git diff fc70b48e --stat
```

The production trace was acquired read-only:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT payload::text FROM dynamic_prematch_evaluations
 WHERE fixture_id LIKE '%1570340%' AND market='TOTALS' AND selection='UNDER'
   AND checkpoint='T-30m_VALIDATION_LOCK' ORDER BY evaluated_at DESC LIMIT 1;
ROLLBACK;
```

Provider calls 0, production writes 0, GitHub 0, deploys 0.

## 8. Evidence

| file | contents |
|---|---|
| `PROTOCOL_FROZEN_20260827.md` | frozen before the trace |
| `FIXTURE_1570340_EVALUATION.json` | the production record, sha256 `7c50b37f9d04630a…` |
| `FIXTURE_1570340_TRACE.json` | the eight-link chain with independent verification |
| `FIXTURE_1570340_REPLAY.json` | post-fix replay, sha256 `2b44380cf79b1b9bec400d6a4ee6a03ae4da3e39342c40edd7bcdb1b10787cd0` |

## 9. What I could not reconstruct

The trace covers the quote, the model input hashes, the five-state distribution,
EV/EV_SE, the gates, the decision and the notification. **The four-field xG, its
windows, and the factor enablement state at that as-of are not recoverable from the
retained evaluation record** — it stores `model_input_hash` and
`model_forecast_capture_identity_hash` rather than the inputs themselves. Rebuilding
them would need the analysis card at that capture, which is a separate read I did
not make. The protocol required unreconstructable links to be reported rather than
inferred, so they are reported.

This does not weaken the root cause: the defect is that no gate consulted the
calibration, which is visible in the gate list regardless of what produced the λ.

## 10. Sequencing after this — my view

**Point EV and factor model V2 are the same question asked twice**, and this task
answers the first half of it. The reason `1570340` produced a 22-point disagreement
is that `BASELINE_PRIOR` is a hand-set prior; V2 exists to replace exactly that. So:

1. **This lands first, on its own.** It is the only change that stops an
   unvalidated probability from reaching a notification, and it is independent of
   whichever model comes next. It should not wait for V2.
2. **V2 should be validated against the same authority it will have to satisfy.**
   V2's Gate 5 asks whether it is promoted; the answer should be expressed as a
   calibration status this module accepts, so promotion and admission are the same
   decision rather than two. Concretely, V2 earns `APPROVED_VALIDATED` and nothing
   else changes.
3. **V1/V2 dual-track settlement comes after that, not before.** Dual-track is
   worth building when two tracks can both carry authority. Until V2 has a validated
   calibration there is one candidate-producing track and one analysis track, which
   is what this change already expresses. Building dual-track settlement first would
   be building a ledger for a comparison that cannot yet happen.
4. **A gap this leaves open, stated plainly.** With the fix in place and
   `BASELINE_PRIOR` shipped, the system produces **no** formal candidates at all.
   That is correct — it was producing them on an unvalidated probability — but it is
   a material change in behaviour and the Owner should decide it knowingly rather
   than discover it. It is the strongest argument for sequencing V2 next.

## 11. R1 — what the first pass left open

Five findings, all confirmed against the code before anything was changed. The R0
commits are kept; this is an append.

**R1-1 `binding`, and the most serious.** Calibration decided admission but never
entered the immutable identity. Same quote, same model input, same checkpoint,
different calibration produced the same `attempt_identity_hash`, and append-only
first-write-wins then swallowed the second, different conclusion. A downgrade from
validated to unvalidated would never have been recorded. R0 saw this trade-off and
resolved it the wrong way: I left calibration out of the identity to avoid changing
hashes, and treated it as a follow-up. It was a correctness bug.

**R1-2 `binding`.** `calibration_status` existed only on `DynamicEvaluationInput`.
It never reached `DynamicEvaluationVersion`, `as_dict`, or the database, so the
persisted record showed a gate's true/false and not the status, the authority
version, or the admission verdict.

**R1-3 audit semantics.** Absent normalised to `BASELINE_PRIOR`. Both fail closed,
but that erased the difference between "declared the hand-set prior" and "declared
nothing" — only one of those tells you the pipeline was working.

**R1-4 a vacuous test.** `assert version.gate_results is None or "calibration_validated"
in version.gate_results` passes without checking anything whenever `gate_results`
is absent, which it was for the non-denominator input the test used.

**R1-5 two reporting errors.** `0.386085` was labelled EV_SE; it is EV−SE, and
EV_SE is `0.050326`. And the "whole market" phrasing above.

## 12. Identity versioning — the design and its trade-offs

Calibration now enters both identities, each with an explicit version key inside the
hashed payload: `EVALUATION_IDENTITY_VERSION` and `ATTEMPT_IDENTITY_VERSION`, both
`…v2`. The version is inside the hash on purpose — an old and a new hash then differ
for a reason a reader can name, instead of differing mysteriously.

**Where it goes, and why there.** Into the **attempt** identity, alongside
`quote_identity_hash` and `model_input_hash`. Calibration is the same category of
thing as those two: part of this attempt's decision basis. The replay confirms the
shape — five calibration states share one `opportunity_identity_hash` (it is the
same betting opportunity) and produce five distinct `attempt_identity_hash` values
(five different bases for a decision).

**Alternatives weighed.**

- *Into the opportunity identity.* Rejected: a calibration change would become a
  different opportunity, which is wrong. The opportunity is the checkpoint for the
  market; re-evaluating it under a new model does not make it a new one.
- *Bump `evaluation_policy_version`.* Rejected as too coarse. It already sits in the
  opportunity hash and expresses "the rules changed", not "this evaluation's basis
  changed". It cannot separate two evaluations under the same policy.
- *A separate `calibration_identity_hash` column.* Rejected: it needs a migration,
  which is out of scope here, and a column that dedup does not key on would not have
  fixed the swallow anyway.
- *Leave it out and rely on `gate_results`.* That is R0, and it is the bug.

**The cost, stated.** Adding a key changes every future hash. Existing rows are
immutable and keep theirs. The first evaluation of an open opportunity after this
lands produces a new attempt hash and therefore one additional append-only row.
That is not a supersession storm and it is not an accident — it is the correct
record that the decision basis changed. Old hashes remain reproducible only under
the v1 payload shape, which is what the version key documents.

## 13. What the record now carries

`DynamicEvaluationVersion` gained four fields, and `as_dict` uses `asdict`, so they
reach the database payload without further plumbing:

| field | meaning |
|---|---|
| `calibration_status_raw` | as received, `null` when nothing was declared |
| `calibration_status` | normalised; `ABSENT` when nothing was declared |
| `calibration_recommendation_admissible` | the verdict this authority reached |
| `calibration_authority` | which authority version reached it |

`ABSENT` is a distinct status, is in `NON_VALIDATION_STATUSES`, and fails closed.

## 14. R1 regression tests

`tests/unit/test_point_ev_calibration_identity.py`, 35 tests, plus the 29 from R0
with the vacuous one replaced by a direct assertion on a denominator-scoped
evaluation.

| requirement | tests |
|---|---|
| (a) BASELINE_PRIOR / READY / UNKNOWN / absent form no candidate and no notification | 10 |
| (b) validated passes and still answers to the EV gates | 4 |
| (c) no identity collision across calibration changes | 4, including that both conclusions survive append-only |
| (d) `as_dict` and database round-trip keep every audit field | 4, including absent vs declared baseline |
| (e) downgrade blocks, upgrade is its own attempt, no stale candidate | 2 |
| (f) `market_candidate`, `read_model_projection`, `repository`, `notification` | 4, exercising each surface for real |
| (g) no vacuous assertions | the R0 one is replaced; no `is None or` remains outside prose |
| (h) EV_SE distinguished from EV−SE, and devig from raw implied | 2 |

**Results after R2**: `2,900 passed`, 6 failed, 9 skipped. The 6 are the same
environmental failures present at `fc70b48e`. `ruff check .` passes; `mypy src apps`
reports no issues in 289 files. The package matrix caller counts were updated again
for the new test file.

## 15. R2 — closing the round-trip

Four findings, all reproduced before anything changed.

**R2-1 `binding`, and mine again.** `_version_from_payload` enumerates fields
explicitly and I never added the four calibration ones, so every reconstruction
from a persisted payload returned them as `None`. Reproduced directly: append the
same evaluation twice, and the second call — the existing-record path used by both
duplicate writes and integrity conflicts — hands back an object whose calibration
audit is blank. The record on disk was right; the object rebuilt from it was not.

**Compatibility, and what a legacy row must reconstruct as.** Rows written before
this authority carry none of these keys. Two rules:

- it must **never** rebuild as validated. `recommendation_admissible` is recomputed
  from the status rather than read from the stored boolean, so a record cannot
  carry its own permission forward across a change in what counts as validated;
- it must stay **distinguishable** from a record that ran under the authority and
  declared nothing. That is the same objection R1-3 raised about `ABSENT` versus
  `BASELINE_PRIOR`, and it applies again one level up.

So a legacy payload rebuilds as `UNRECORDED` with `calibration_authority = None`.
The missing authority stamp is the signal: `ABSENT` means the authority ran and
nothing was declared, `UNRECORDED` means no authority ever looked. Back-stamping a
legacy row with the current authority version would have destroyed exactly that.

**R2-2.** The R1 tests read `row.payload` as JSON, which never exercises
reconstruction. They now go through the repository API and assert on the rebuilt
`DynamicEvaluationVersion`, covering declared-but-unvalidated, `ABSENT`, validated,
and a payload with the keys stripped out.

**R2-3.** The R1 downgrade test used different slots and suffixes, and the context
helper derives the capture identity from the suffix — so it built two *different*
opportunities and proved nothing about a downgrade. Replaced with a fixed context:
same capture, slot, quote, model input, checkpoint and source event, changing only
the calibration.

**R2-4.** Section 1 of this report still carried `52.08%` and `22.7 points` after
R1 corrected them elsewhere, so the document contradicted itself. One set of
numbers now: devigged market `0.500000`, model `24.8` points above, `EV_SE
0.050326`, `EV−SE 0.386085`.

## 16. Does R2 change any number or behaviour?

**No EV value changes.** `current_ev`, `current_delta`, `current_ev_minus_se`, the
five-state distribution and the formula are untouched; the replay artefact is
byte-identical to R1 (`2b44380cf79b1b9b…`).

**No admission or notification behaviour changes.** R2 only fixes what a
reconstructed object reports. Classification, gating, identity and the outbox are
as they were after R1 — which the same-opportunity test now demonstrates end to end
rather than asserting.

**One behaviour is newly *correct* rather than newly *different*:** a caller that
read calibration off a repository-returned existing version used to see `None` and
could not tell an unvalidated record from a validated one. It now sees the record.

## 17. Authorisation

Nothing here is authorised, applied to production, or deployed. `alpha_age_per_day`
and `beta_missing` remain `NULL`. Historical recommendations, settlements and the
outcome ledger are untouched. The match result for `1570340` was not read, and the
current 65 settled picks were not used to select anything. Any production switch
implied by section 10 is a proposal, not a decision taken here.
