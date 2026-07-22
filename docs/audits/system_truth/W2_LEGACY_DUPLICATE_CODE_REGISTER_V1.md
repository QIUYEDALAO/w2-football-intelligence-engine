# W2_LEGACY_DUPLICATE_CODE_REGISTER_V1

- Generated at: `2026-07-20T12:51:47.425145Z`
- Audit SHA: `94ba834559c0beba5b38075bd358a8e92a434a51`
- Provider calls: `0`
- DB writes: `0`
- Final state: `MANUAL_APPROVAL_REQUIRED`

遗留/重复链路登记。审计阶段不删除代码，只给删除条件。

## Duplicate Register

| id | domain | current_classification | risk | delete_condition |
| --- | --- | --- | --- | --- |
| DUP-MATCHDAY-FUTURE-REFRESH | Matchday/provider intake | CONFLICTING_AUTHORITY | Provider calls can happen through future refresh while Matchday V2 remains review-only. | Provider executor routes through MatchdayEndpointCaptureV1 and future refresh discovery is demoted. |
| DUP-CHECKPOINT-POLICIES | Checkpoint | CONFLICTING_AUTHORITY | Different checkpoint names/skip-vs-missed semantics can reappear. | Only V2 policy is loaded; legacy constants removed; regression tests cover missed/no-backfill. |
| DUP-RECOMMENDATION-STATES | Recommendation | CONFLICTING_AUTHORITY | ANALYSIS_PICK/WATCH/SKIP/FORMAL can be interpreted by different surfaces. | All surfaces project from one V3 decision hash. |
| DUP-F5-SOURCE-LOCAL-RUNTIME | F5 | DATA_DEPENDENCY_MISSING | Local JSONL dataset exists but runtime canonical query not ready. | Canonical DB import and query API verified. |
| DUP-F8-STATIC-ARTIFACT-DB | F8/team value | CONFLICTING_AUTHORITY | Static values, artifacts and DB can diverge. | Reviewed as-of artifact/table selected as canonical. |
| DUP-RAW-PAYLOAD | Raw payload | CONFLICTING_AUTHORITY | Different raw hash/identity algorithms for same provider evidence. | Single raw payload identity and compatibility mapping. |
| DUP-SCRIPTS-RECOVERY-OPERATIONAL | Scripts | ACTIVE_COMPATIBILITY | One-time recovery scripts may be reused as runtime path. | Script registry marks ACTIVE_OPERATIONAL vs ONE_TIME_RECOVERY and CI enforces approvals. |
