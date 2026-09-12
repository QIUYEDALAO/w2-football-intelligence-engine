# Migration 0072 — `runtime_ah_settlement_facts`

Revision `0072_runtime_ah_settlement_fact`, revising
`0071_forward_ah_factor_observation`.

## Additive

A new table only. No existing table, column, index or constraint is touched, so
every historical row keeps its identity and its hashes. There is **no backfill**:
the table is populated only by the natural capture writer, from a pre-kickoff
odds quote paired with the terminal-result capture that observed the fixture
finish. The pre-existing `canonical_historical_ah_facts` chain is left exactly as
it was, so legacy rows keep producing F5 absence rather than being promoted by
inference.

## Constraints the database enforces

| Constraint | Meaning |
|---|---|
| `ck_runtime_ah_settlement_terminal_status` | `terminal_status in ('FT','AET','PEN')` |
| `ck_runtime_ah_settlement_point_in_time` | `quote_captured_at < kickoff_utc < settlement_observed_at` |
| `ck_runtime_ah_settlement_observed_semantics` | the observation semantics is exactly `PROVIDER_CAPTURE_OF_TERMINAL_RESULT` |
| `ck_runtime_ah_settlement_policy` | the policy is `canonical_bookmaker_mainline_majority_v1` |
| `ck_runtime_ah_settlement_identities_present` | quote identity hash, source-set hash, settlement capture id and settlement payload hash are all non-empty |
| `uq_runtime_ah_settlement_fact_hash` | one fact hash, one fact |
| `uq_runtime_ah_settlement_fact_natural` | one fact per fixture, policy, line, quote identity and settlement capture |

A row whose source-observed time is not strictly after kickoff is precisely the
fabrication this table exists to prevent, so the database refuses it rather than
accepting a default.

## Rollback

`downgrade` drops the table only when it is empty, and raises
`RUNTIME_AH_SETTLEMENT_FACT_DOWNGRADE_WOULD_DESTROY_FACTS` otherwise. These are
immutable business facts; a populated downgrade would destroy them. The
documented path when rows exist is the forward-compatible one: stop the writer,
leave the table and its rows in place, and roll the application back without the
schema.

## Verified

On an isolated PostgreSQL 16:

* `upgrade head` → `0072_runtime_ah_settlement_fact`, table present, 5 indexes;
* `downgrade 0071` on the empty table → table absent;
* `upgrade head` again → table present;
* a valid row is accepted; a settlement before kickoff, a quote after kickoff, a
  non-terminal status and a query-time semantics are each rejected by the named
  constraint;
* with one row present, `downgrade` raises the refusal and the row survives.

The isolated replay in `scripts/quant/run_f1r_b_production_recording_integration.py`
runs the same upgrade/downgrade cycle on a file-backed database, with the
pre-migration state built without either migration-added table so the upgrade
does not collide with its own `CREATE TABLE`.
