# F1R-C successor: the runtime AH settlement fact writer

This document corrects a claim in the F1R-C delivery package and records what
replaced it.

## The correction

The delivery recorded "the natural writer, wired into the Provider capture path
(`FactorModelRemediationService.materialize_runtime_ah_settlement_facts`)". That
was wrong in the way that matters: **it was not a natural writer.**

`materialize_runtime_ah_settlement_facts` had exactly one caller —
`FactorModelRemediationService.run_controlled_provider_capture` — and that
service is instantiated only by `scripts/run_w2_factor_model_remediation.py`, a
manual operator script. No scheduler, cron entry or systemd unit reaches it.
The architecture checklist already classifies that script as
`ONE_TIME_RECOVERY / operator → script`.

So the fact table could not be filled by production, and F5 could only ever be
recorded as an absence. Measured on the deployed release, read-only:

| Evidence | Value |
|---|---|
| `runtime_ah_settlement_facts`, deployment through first 30 min of natural ticks | **0 rows**, 30/30 samples |
| F5 v2 rows evaluated in the same window | 13, every one `INSUFFICIENT_DATA`, `applied_weight=0` |
| F3 / F6 / F9 in the same window | 248/248, 165/248, 242/248 participated |

The rows that were written prove the new code was live. The empty fact table
proves nothing natural wrote a fact. The two together are the defect.

## What the writer is now

`src/w2/historical/runtime_ah_settlement_materializer.py` — the one reusable,
Provider-free materializer.

It takes canonical fixture ids or unambiguous Provider fixture ids and reads
persisted rows only:

| Input | Read from |
|---|---|
| fixture identity, kickoff, w2 team mapping | `matchday_fixture_identities`, else `canonical_team_match_history` |
| terminal result + the capture that observed it | `results` (with its capture), else `canonical_team_match_history` |
| the source-observed instant | `matchday_endpoint_captures.provider_captured_at` |
| the pre-kickoff AH bucket | `matchday_market_observations` via `closing_quote_bucket` |

and then calls the existing authorities — `select_canonical_ah_mainline`,
`project_quote_identity`, `settle_asian_handicap`, `build_ah_settlement_fact`,
`RuntimeAhSettlementRepository.append_facts`. No fact-construction algorithm is
duplicated; `FactorModelRemediationService` now delegates to this function and
the recovery path keeps only its ability to be *a* caller.

It takes no client and has no request path, so it cannot call the Provider. A
test asserts this structurally (the module names no provider import) and
behaviourally (every Provider entry point is armed to raise; the writer still
succeeds with `provider_calls == 0`).

## Precedence, fixed

One fixture must produce one fact, so each provenance has one rule and the rule
does not depend on which row happened to appear first:

1. **identity** — the fixture-identity row, which a natural discovery capture
   maintains; otherwise the canonical history row, which the recovery path
   writes for fixtures outside the discovery window.
2. **terminal evidence** — the `results` row, which is the artefact the result
   materialisation itself just wrote; otherwise the canonical history row.
3. **nothing** — refused.

The two chains are not interchangeable in general: for the newest naturally
confirmed fixtures, `results.source_capture_id` and
`canonical_team_match_history.endpoint_capture_id` name *different* captures
(12/12 sampled). Fixing the order is what keeps the fact identity stable across
replays instead of drifting with whichever chain was populated first.

## Where it runs

| Trigger | Module | When |
|---|---|---|
| `_materialize_outcome_results` (the point named in the task) | `apps/worker/celery_app.py` | after `run_outcome_result_refresh` succeeds, for that round's `confirmed_fixture_ids` |
| `_run_forward_outcome_ledger` | `apps/worker/celery_app.py` | after its own result materialisation, for the same reason |

Both go through one helper, `_materialize_ah_facts_after_results`. The ledger
path is included because it is the other natural result-materialisation path: a
round that materialised results but not the facts they prove would carry fewer
facts than the refresh path for no reason a reader could see.

Guards, in order:

* the result materialisation is `BLOCKED` → no fact is built
  (`SKIPPED_RESULT_MATERIALIZATION_FAILED`); these are the evidence, so a fact
  built without them is the one row the table must never contain;
* no confirmed fixture → `NO_DUE_WORK`, a stated verdict, not a failure;
* the writer itself fails → the report carries the error and the task status
  gains `_WITH_AH_FACT_INCOMPLETE`, exactly as a failed factor recording does;
* individual refusals are summed and stay visible; they are statements about the
  data, so they do not degrade the writer's verdict.

## What a natural round can write

Read-only measurement of the deployed database, using the writer's own
precedence:

| Measure | Count |
|---|---|
| fixtures with terminal evidence (history or result row) | 7,070 |
| …whose terminal capture is a successful `fixtures` capture after kickoff | 7,060 |
| …and that also have a pre-kickoff AH quote bucket — **buildable** | **417** |

Naturally confirmed fixtures in the preceding three days: 11 of 15 carried a
usable terminal capture; 4 carried none and are refused with
`AH_SETTLEMENT_CAPTURE_IDENTITY_MISSING`, which is why that refusal code exists
as a distinct, visible outcome rather than a generic "unavailable".

## Refusal vocabulary

| Code | Meaning |
|---|---|
| `AH_SETTLEMENT_FIXTURE_IDENTITY_UNRESOLVED` | no persisted row names this fixture |
| `AH_SETTLEMENT_TEAM_MAPPING_MISSING` | no w2 team identity, so F5 could never consume the fact |
| `AH_SETTLEMENT_TERMINAL_EVIDENCE_MISSING` | no result row and no history row |
| `AH_SETTLEMENT_CAPTURE_IDENTITY_MISSING` | terminal evidence exists, but nothing identifies the capture that observed it |
| `AH_SETTLEMENT_QUOTE_BUCKET_MISSING` | no pre-kickoff AH quote bucket |
| `AH_SETTLEMENT_MATERIALIZER_ERROR` | the writer could not finish for this fixture |

plus every refusal `build_ah_settlement_fact` already owns
(`AH_SETTLEMENT_NOT_TERMINAL`, `AH_SETTLEMENT_CAPTURE_WRONG_ENDPOINT`, …).

## Read-projection fix

`runtime_ah_settlement_facts` had a second, latent defect that only appears when
the quote bucket is read from the database rather than from a capture sample:
`runtime_ah_settlement._quote_row` returned `captured_at` as the driver's
`datetime`, while the quote identity authority places that field in the digest
preimage. Every database-driven build therefore raised
`TypeError: Object of type datetime is not JSON serializable`.

The row projection now emits the stored text form. No frozen authority was
modified to accommodate it.

## Tests

`tests/integration/test_f1r_c_ah_fact_natural_writer_e2e.py` — 25 tests on
isolated PostgreSQL 16, driving the real writer and the real worker trigger:

* the natural writer appends the terminal fixture's fact, and the fact is
  **byte-identical** to the one the offline constructor builds from the same
  rows (id, hash, quote identity, line, both instants);
* a bare Provider fixture id resolves the same single fact;
* a replay is an idempotent no-op and never a second fact;
* every refusal names its own missing link and is visible in the report;
* a fixture without a w2 team mapping is not written at all;
* no Provider call is made, or possible;
* the result-materialisation path calls the writer, and the refresh task carries
  the report it produced (`appended` equals the table);
* `src/w2/factor_model/remediation.py` is a caller, not the owner, and no longer
  contains the constructor (`test_the_recovery_path_is_not_the_only_writer`);
* a blocked result materialisation writes no fact, and a failed writer cannot
  let a task report a clean pass;
* refusals alone do not degrade the verdict;
* F3/F6/F9 verdicts are compared field by field against an identical world
  without a fact — the only excluded fields are the evaluation instant and the
  two hashes computed over it, which are bound to the recording's clock seam;
* the batch is still one attempt of exactly four rows;
* the writer moves no table it read.

## Digests

The six F1R-B quant modules are unchanged by this successor. Nothing in this
change touches a frozen module: the writer is a new module, the worker and the
recovery service are production callers, and the review package is this
directory. See `PORT_REVISIONS.md`.

## Successor: evidence integrity, and one fixture one fact

The writer trusted the terminal chain it read. It now proves it, and it refuses
to let one fixture be counted twice.

### What is checked before a fact exists

| Guard | Refusal |
|---|---|
| `results.source_payload_sha256 == capture.raw_payload_sha256` | `AH_SETTLEMENT_RESULT_PAYLOAD_HASH_MISMATCH` |
| a capture that names a fixture names *this* one | `AH_SETTLEMENT_CAPTURE_FIXTURE_MISMATCH` |
| a capture that names none proves coverage from its stored payload | `AH_SETTLEMENT_CAPTURE_OWNERSHIP_UNPROVEN` |
| the fixture has no fact from different terminal evidence | `AH_SETTLEMENT_FACT_REVISION_CONFLICT` |

Every one of them is fail-closed: no fact is built, and the refusal is reported
per fixture with the code and a detail.

**Why ownership is not a `fixture_id` equality check.** The natural instruction
was "the capture's `fixture_id` must match the target fixture". Measured on the
deployed database: `matchday_endpoint_captures` holds **2371 `fixtures`-endpoint
captures and not one of them carries a `fixture_id`** — they are bulk responses.
Applied literally, that check refuses all 15 facts that already exist and every
fact a future round could write. So the guard proves the same thing the
requirement asks for, by the route the data actually supports: a capture that
*does* name a fixture must name this one, and a bulk capture must carry this
fixture in its own stored payload. `raw_payload` has the payload for 15/15 of the
settlement captures, and the membership question is asked in SQL so the payload
never crosses into Python.

`status`-endpoint captures also carry no `fixture_id`, and the history branch is
held to the same ownership rule.

### The revision rule

A fact's identity binds its settlement capture, so a *second*, legitimate
terminal capture for the same fixture produces a **different** fact id — and the
append-only store would keep both. F5 would then read the same match twice. The
rule therefore lives in the writer, where the fixture is still known: existing
fact with the same id is an idempotent no-op; existing fact with a different id
is a refusal naming the fact that already holds the fixture. Nothing is
overwritten and nothing is appended.

### Two kinds of refusal, two verdicts

A refusal is not automatically a defect. "No pre-kickoff quote bucket" is a
statement about the data; "the result cites a capture it did not read from" is a
broken chain. So the four integrity codes above raise the writer report to
`INCOMPLETE`, which makes `runtime_ah_fact_writer_status` return `PARTIAL` and a
task result carry `_WITH_AH_FACT_INCOMPLETE`. The data-availability refusals stay
non-degrading, which is what keeps `RUNTIME_AH_FACT_NATURAL_WRITER = PASS`
reachable on an ordinary day.

### Tests

Six new end-to-end tests on the same isolated PostgreSQL harness, which now
builds the **production** capture shape (bulk `fixtures` capture with a null
`fixture_id` plus its stored payload) instead of a convenient one:

* a result whose payload hash disagrees with its capture — refused;
* a capture that names another fixture — refused;
* a capture with no fixture attribution and no payload — refused;
* a payload that exists but omits the fixture — refused;
* the same evidence replayed — idempotent no-op;
* a second terminal capture for one fixture — refused, not counted, and the
  refusal names the fact that already holds it.

Each integrity refusal asserts four things together: zero new facts, the exact
refusal code visible in the report, a non-clean writer verdict, and a task result
that ends `_WITH_AH_FACT_INCOMPLETE` rather than a clean `PASS`.

### Production data

Untouched. The 15 facts already stored were not backfilled, rewritten or
re-derived; the guards apply to what is written from now on.
