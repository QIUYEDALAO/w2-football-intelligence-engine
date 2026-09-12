# F1R-C port revisions

F1R-C was authorised to revise exactly two F1R-B modules, and only these two:

* `scripts/quant/f1r_b_production_ports.py`
* `scripts/quant/f1r_b_production_recording_integration.py`

plus the F1R-B tests that pinned their previous behaviour.

## Digests

| Module | F1R-B delivery (`b4285660`) | F1R-C |
|---|---|---|
| `f1p_forward_factor_contract.py` | `b43adcbb42c3642c1fad4f29a5b1568c1077c175450fd2cc4544160ebc1bb329` | unchanged |
| `f1r_a0_offline_factor_recorder.py` | `3a057699f933f5f0d1a80debafbc4569f056a40743749d1afaacee743287f360` | unchanged |
| `f1r_b_source_capture.py` | `f2451a14da5d442b6fc09fcf79e2ce2141aec6a0b5a19707ba3277a7f95ffea1` | unchanged |
| `f1r_b_production_ports.py` | `e4f84a5010ae81121dc02e42838b8f38868b8c09a6843ad6e7296faced304df2` | `c799efc659fb972fa18ee5aa3e32b04111ae82a57723d8fbfdf58f7bc54a6218` |
| `f1r_b_production_recording_integration.py` | `b383652b7d71adc64d3253a13deda5590e79a0421a6231e5030e65078478c02c` | `fda5734a7d83ec05b309d2b8ebe401a254ee147453da60ebf3f5909a649a3ce2` |
| `f1r_b_observation_store.py` | `4ab1ae874942eabfc2e721ec5c1cc3beefc27dcf541f61ed5314caef2cfb8499` | unchanged |

Three tests enforce the discipline rather than describe it:

1. the historical digests are verified **at the F1R-B delivery commit**, so the
   original evidence stays verifiable instead of being asserted against a tree
   the successor changed;
2. the working tree is verified against the F1R-C digests above;
3. the set of modules whose digest moved is asserted to equal exactly the two
   authorised names. Four modules must still be byte-identical.

The original F1R-B review package and its `HASHES.sha256` are untouched.

## What changed, and what did not

`f1r_b_production_ports.py::ah_fact_records` used to raise unconditionally. It
now converts runtime AH settlement fact rows into consumed-source records,
where:

* `observed_at_utc` is the settlement capture's `provider_captured_at`;
* `observed_time_semantics` is `PROVIDER_CAPTURE_OF_TERMINAL_RESULT`;
* the hashed content binds both capture identities, both payload hashes, the
  selected line, the selected bookmakers and the terminal score.

It still refuses when anything is unprovable: a missing observation time, a
settlement not strictly after kickoff, a quote not strictly before it, a wrong
policy, a missing capture identity, a missing payload hash, or a malformed
digest. Each refusal is batch-wide.

`f1r_b_production_recording_integration.py` gained one check: when F5
participates, its consumed record ids must equal the fact ids the builder
reports having read. Comparing identities, not just counts, is what stops a
right-sized but wrong set. F5's `observed_at` is now also cross-checked against
the latest consumed source time.

`PARTICIPATED_FACTOR_BOUND_TO_ABSENCE_LOOKUP` was **not** removed or weakened:
an F5 that participates while bound to an absence record still refuses the whole
batch, and a test pins that. F3, F6 and F9 were not relaxed.
