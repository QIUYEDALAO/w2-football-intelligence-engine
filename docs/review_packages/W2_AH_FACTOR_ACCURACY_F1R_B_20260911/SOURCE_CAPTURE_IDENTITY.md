# F1R-B source capture identity

`W2_AH_FACTOR_ACCURACY_F1R_B_PRODUCTION_RECORDING_INTEGRATION_20260911`
Parent commit `71daa3f5ec17ac3c5484e75a87d6bcac990d4bae`.

## What a factor observation now binds

Every observation carries the source set the factor actually consumed:

| Field | Where it lives | What it is |
|---|---|---|
| `source_capture_id` | protected field | identity of the consumed **set** |
| `source_capture_sha256` | protected field | hash of the consumed set's **content** |
| `source_version` | protected field | the source system's own schema version |
| `source_record_ids` | `factor_inputs` | every consumed row's real production id |
| `source_observed_times` | `factor_inputs` | every consumed row's real source-observed time |
| `source_observed_time_semantics` | `factor_inputs` | what each of those times means |
| `consumed_source_count` | `factor_inputs` | how many rows the factor read |

All seven are inside the identity preimage: the first three directly, the rest
through `factor_inputs`. Changing any of them changes `factor_input_hash`, and
therefore `factor_verdict_hash` and `observation_id`.

## How the two hashes are built

`scripts/quant/f1r_b_source_capture.py` builds a manifest and hashes it:

```text
manifest = {
  contract:           "w2.f1r_b_source_capture.v1"
  hash_domain:        "future_refresh.evidence"
  serializer_version: "w2.canonical-json.v2"
  factor_id:          <the factor that consumed these rows>
  records:            [ {record_id, content_sha256, source_version,
                         observed_at_utc, observed_time_semantics, synthetic}, ... ]
}

source_capture_sha256 = canonical_sha256(manifest)
source_capture_id     = "w2.consumed_source_set.v1:" + canonical_sha256(
                            {contract, factor_id, record_ids})
```

`canonical_sha256` is `src/w2/domain/canonical_serialization.py` under
`w2.canonical-json.v2`. There is no second serializer and no second hash
writer: `f1r_b_source_capture.py`, `f1r_b_production_ports.py` and
`f1r_b_production_recording_integration.py` contain no `hashlib` import and
define no function whose name mentions canonical, sha256 or identity hash.

`record.content_sha256` is itself a canonical hash of the row's
actually-consumed content — the field lists are in `FACTOR_SOURCE_MAPPING.json`
under `content_hash_over`. It is never a hash of a path, a timestamp or an
empty metadata shell.

### Why the id and the content hash are separate

They answer different questions. The id answers *which rows did this factor
read*; the content hash answers *what did those rows say*. Keeping them apart
means a corrected score in a row the factor already consumed moves the content
hash while the set id stays put, which is exactly what an auditor wants to see.
Both are in the preimage, so either moving moves the observation identity.

### Order independence

Records are sorted by `record_id` before hashing, so reading the same rows in a
different order gives the same identity. `test_10_reordering_the_consumed_set_does_not_change_identity`.

### Consumed-only sensitivity

The manifest contains the consumed rows and nothing else. A row that exists in
the database but that this factor never read is not in the manifest, so it
cannot move the hash — and a row the factor did read cannot change its content,
identity, version or observed time without moving it.
`test_10_changing_a_consumed_source_changes_the_observation_identity` and
`test_10_a_source_the_factor_never_consumed_changes_nothing`.

### The consumed set is cross-checked against the builder

A caller could otherwise hand over a plausible set that is not the one the
factor scored. `_check_consumed_set` refuses:

* F3 and F9 unless there are exactly two rows **and** the latest consumed
  source time equals the instant the builder reports as its `observed_at`;
* F6 unless the row count equals the builder's own `meeting_count`.

`test_10_a_wrong_sized_consumed_set_refuses` and
`test_10_a_right_sized_but_wrong_consumed_set_refuses` — the second passes the
count check and still fails, because the two rows are not the two the builder
read.

## Synthetic capture identity

`ConsumedSourceRecord.synthetic` marks a **fabricated** identity — the
A0-style `synthetic-capture-f3_rest_fitness` / `3333…` placeholders. Such a
record:

* is labelled in the record, in the manifest entry, and in the capture id,
  which becomes `w2.synthetic_source_set.v1:…` instead of
  `w2.consumed_source_set.v1:…`;
* is refused by the production branch with
  `SYNTHETIC_SOURCE_IN_PRODUCTION_BRANCH`.

`test_10_a_synthetic_record_cannot_reach_the_production_branch`,
`test_10_a_synthetic_capture_id_is_labelled`.

### An honest note about the fixture rows in this package

The rows in `scripts/quant/f1r_b_fixtures.py` are offline test vectors shaped
exactly like the production projections. They were not read from a database, a
Provider or a VPS: `PRODUCTION_DB_READS = 0`.

They are **not** marked `synthetic`, and the distinction is deliberate. The
`synthetic` flag means *this identity was invented*. These identities are not
invented — they are the true canonical hashes of the content shown in
`F1R_B_SOURCE_MANIFESTS.json`, computed by the same production ports that will
run against real rows. That is precisely what makes them usable to prove the
identity rules: an invented hash proves nothing about whether tampering moves
it.

What the reference ledger is evidence *of* is the contract, not any match.
`F1R_B_RESULT.json` says so in `fixture_kind` and `fixture_note`.

## The absence case

A factor that found nothing still consumed something: a lookup that returned no
usable rows. `absence_records` hashes that lookup — factor id, query identity,
queried-at, reason, `rows_returned: 0` — with semantics
`SOURCE_QUERIED_AT_AS_OF`.

This is how F5 is recorded. It is not a stand-in for a source time, and the
integration refuses to let it become one: a factor the scoring authority
*scored* whose consumed set is an absence lookup is refused with
`PARTICIPATED_FACTOR_BOUND_TO_ABSENCE_LOOKUP`. Without that guard a
participating F5 would have silently inherited the query time as its evidence
time — exactly the substitution this task exists to prevent.
`test_06_f5_participating_without_a_source_time_refuses_the_batch`.

## Independent verification

`tests/contract/test_f1r_b_independent_oracle.py` re-derives every hash in the
published package without importing the recorder, the integration, the capture
module, the F1P contract or the production serializer. It re-implements
`w2.canonical-json.v2` from the written rules and transcribes the preimage
field lists from the frozen `F1P_SCHEMA_CONTRACT.json`. `test_the_oracle_imports_no_production_implementation`
proves by AST that it neither imports nor side-loads any of them.

### E2 and SER-05 point opposite ways; here is where the line falls

Freeze A0 Errata E2 forbids "a second serializer, a local `canonical_json`, or
direct `json.dumps + hashlib.sha256` identity writer". `AGENTS.md` SER-05
requires an oracle whose author "does not import production serializer". An
independent oracle necessarily re-implements what it checks, so the two rules
appear to collide.

The repository's own enforcement draws the line, and this package follows it
rather than arguing with it: `scripts/check_canonical_serialization_authority.py`
scans `src/w2`, `apps`, `scripts` and `migrations`, and not `tests`. The oracle
therefore lives under `tests/contract/`. It is also not an identity *writer* in
E2's sense — it persists nothing and hands no hash to any consumer; it
recomputes published values and asserts. The wiring modules themselves import
no `hashlib` and define no canonical or hash function, which
`test_20_no_second_serializer_or_hash_writer_is_defined` checks.
