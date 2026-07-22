# W2 Dynamic Quote EV Lifecycle V1

Implementation `8132afd6bc16b7426c58184528111d443baf4b53` adds immutable evaluation versions and a separate supersession relation. A new quote or model-input identity recomputes the current evidence; `NO_EDGE` may upgrade and an active analysis pick may downgrade or become stale.

Local contract and persistence tests prove idempotent recapture, supersession, robust EV gates, source-absent wording and lineup invalidation. The fixture in the JSON is explicitly offline test evidence, not a live claim.

Status: `DYNAMIC_QUOTE_LIFECYCLE_PASS`, `CURRENT_EV_SNAPSHOT_SEMANTICS_PASS`, `NO_EDGE_REEVALUATION_PASS`, `SOURCE_ABSENT_TRUTH_CONTRACT_PASS`.

Safety remains `PR_370_KEEP_DRAFT`, `FORMAL_DISABLED`, `LOCK_DISABLED`, `PRODUCTION_DISABLED`.
