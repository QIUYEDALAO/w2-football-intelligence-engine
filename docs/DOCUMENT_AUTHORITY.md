# W2 Document Authority

When W2 sources disagree, use this order:

1. Current code and passing tests.
2. `PROJECT_STATE.yaml`.
3. `docs/consolidation/W2_DECISION_CONTRACT_V2.md`.
4. The latest entries in `docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md`.
5. Historical implementation documents, roadmaps, and `README.md`.

Historical files remain useful evidence but do not override a newer contract.
A document marked `SUPERSEDED` must link to its replacement and must not be
used as a runtime requirement.

Legacy decision fields such as `candidate` and `formal_recommendation` are not
authority for new decisions. Their permitted readers are recorded in the
machine-readable `config/legacy_decision_allowlist.json`; additions require a
specific compatibility, migration, or historical-read justification.
