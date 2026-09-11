# F1R-B data flow

`W2_AH_FACTOR_ACCURACY_F1R_B_PRODUCTION_RECORDING_INTEGRATION_20260911`
Parent commit `71daa3f5ec17ac3c5484e75a87d6bcac990d4bae`.
Switch state: `LIVE_CAPTURE_ENABLED = false`, `PRODUCTION_CAPTURE_ENABLED = False`.

## The path, end to end

```text
production tables                    read ports (disabled)              recorder
─────────────────                    ─────────────────────              ────────
canonical_team_match_history ──┬──▶ rest_fitness_records  ─┐
  + matchday_endpoint_captures ─┴──▶ h2h_records           ─┤
team_xg_rolling_snapshot ─────────▶ true_xg_records        ─┼─▶ capture_identity
canonical AH settlement fact ─────▶ ah_fact_records ✗ REFUSED           │
                                                                        ▼
                                                        FactorSourceBinding
                                                        (records + declared version)
                                                                        │
w2.domain.factor_versions ─────────────────────────────────────────────▶│ version check
                                                                        ▼
FeatureContribution × 4 ──▶ independent_team_scores_from_contributions ─▶│ participation
                                                                        ▼
                                                        build_production_batch
                                                                        │
                                              ┌─────────────────────────┴───────────┐
                                              ▼                                     ▼
                                  ForwardFactorLedger (JSONL)      ForwardFactorObservationStore
                                  atomic os.replace                forward_ah_factor_observations
```

Nothing on the left of the ports is read in this task. `LiveSourceReadPort`
exists so the integration has one named place to be turned on, and every call
to it raises `LIVE_CAPTURE_DISABLED`. Passing `enabled=True` raises
`LIVE_CAPTURE_NOT_AUTHORISED`: enabling capture is a separate decision that
this code cannot make for itself.

## What is reused rather than re-implemented

| Concern | Authority | How F1R-B reaches it |
|---|---|---|
| eligibility and participation | `w2.pricing.team_score.independent_team_scores_from_contributions` | called through the accepted A0 recorder |
| applied weight and the weight-sum invariant | A0 recorder `_batch_coherence` | called, re-run after enrichment |
| observation identity and PIT | F1P contract `validate` | called |
| canonical hashing | `src/w2/domain/canonical_serialization.py` | called |
| atomic file commit | A0 recorder `_atomic_replace` | called |

F1R-B adds three things and only three: the version check, the capture
identity, and the source-time rules. Everything the R1-A0 acceptance covered is
reached by delegation, not by copy.

## Evidence time, per factor

| Factor | Evidence time | Semantics |
|---|---|---|
| F3 | latest consumed match's `kickoff_utc` | `FIXTURE_EVENT_TIME` |
| F9 | latest consumed snapshot's `as_of_time` | `SOURCE_SNAPSHOT_OBSERVED_AT` |
| F6 | latest consumed row's `provider_captured_at` | `RESULT_DERIVED_REQUIRES_EXPLICIT_SOURCE_OBSERVED_TIME` |
| F5 | the as-of of the lookup that found nothing | `SOURCE_QUERIED_AT_AS_OF` |

A factor is knowable only once every source it consumed was, so a
result-derived factor's evidence time is the **maximum** of its consumed source
times. `test_09_evidence_time_is_the_latest_consumed_source_time`.

`evidence_time_utc < evaluated_at_utc` strictly. Equal fails. Naive fails.
Unparseable fails. The check is on parsed aware-UTC instants; no timestamp is
ever compared as text.

## The F6 chain, in detail

This is the finding that moved F6 from blocked to provable.

```text
FactorModelRemediation._seed_history
  response = client.request_live("fixtures", …)
  capture_id = _persist_capture(response)
      └─ endpoint_capture_contract(provider_captured_at = response.captured_at)
         → matchday_endpoint_captures.provider_captured_at
  for item in finished_fixture_items(response.payload, now):   # FT/AET/PEN only
      fixture_capture_ids[provider_fixture_id] = capture_id
  _upsert_history_fixtures(historical_fixtures, fixture_capture_ids)
      └─ canonical_team_match_history.endpoint_capture_id = that capture_id
```

Each history row points at the very provider read whose payload already showed
that fixture as finished. `provider_captured_at` is therefore a time at which
the result was demonstrably observable. It is conservative in the safe
direction: the result may have been available slightly earlier, never later.

### Why the row's own `captured_at` is refused

`_upsert_history_fixtures` passes `captured_at=self.now` — the clock at the
start of the materialisation run — while `_persist_capture` records
`response.captured_at`, which is later. Treating the row's `captured_at` as an
evidence time would claim the result was knowable *before* the read that
carried it. The port never touches that column, and
`test_07_the_materialisation_clock_is_never_used_as_the_source_time` asserts
the recorded times are disjoint from it.

### Fail-closed conditions

`endpoint_capture_id` is nullable, so a row may carry no capture. That row is
refused rather than defaulted, along with an unresolvable capture, a capture
whose `capture_status` is not `CAPTURED`, and a `provider_captured_at` at or
before the fixture kickoff.

## F3 reads no result

F3's input is match spacing. The port takes an *event-time projection* —
identity plus `kickoff_utc` — and refuses a projection that still carries
`goals_for`, `goals_against`, `result_identity_hash`, `settlement_outcome`,
`ah_result`, `score` or `result_status`, with
`F3_RESULT_FIELD_IN_EVENT_TIME_INPUT`. The whole batch is refused, not just
the factor.

## F5 is refused

`ah_fact_records` raises on every call. It cannot be satisfied because the
canonical AH settlement fact never reaches a factor builder in this tree: no
writer emits the three markers `_canonical_ah_rows` requires, the
`canonical_historical_ah_facts` table has no reader in `src/`, its
`quote_captured_at` is a pre-match odds capture rather than a settlement
observation, and `results.confirmed_at` has two writer semantics with no
discriminator. The four findings, with file and line evidence, are in
`FACTOR_SOURCE_MAPPING.json`.

F5 is still recorded — as an absence, with `applied_weight = 0`,
`signed_score = null`, and the lookup that found nothing as its capture. An
absence is not a zero and not a neutral factor; the batch stays four-of-four so
that the record of *why* F5 did not contribute exists.

## All four or none

The batch is validated completely, conflict-checked and staged before anything
is committed.

* **File ledger.** Serialise, write, flush, `os.fsync` into a sibling temp
  file; `os.replace` is the commit point. A refusal or an I/O failure before it
  leaves the original bytes untouched.
* **Database.** One `session.begin()` around the whole batch. A failure part
  way through rolls back; `test_16_a_database_failure_midway_adds_zero_rows`
  injects one at the third row and asserts zero rows land.

## What this is not

It is not deployed, not capturing, not scheduled, and not a model candidate. It
does not change any decision, weight, direction or recommendation, does not
touch the historical 148, and does not unlock F2, F3, D1, W1 or Shadow.
