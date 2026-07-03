# Learnings

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---
## [LRN-20260703-001] correction

**Logged**: 2026-07-03T04:05:00+08:00
**Priority**: high
**Status**: pending
**Area**: tests

### Summary
When adding a new artifact guard, do not replace existing contract checkers unless the task explicitly says to retire them.

### Details
For W2-CD-136, the tracked-output guard is additive. Existing Stage 1 contract semantics must be preserved by updating the checker to stop depending on removed report artifacts, not by removing the checker from CI or aggregate checks.

### Suggested Action
For cleanup PRs, prefer migrating/checker requirements away from removed artifacts while preserving core contract assertions and CI entry points.

### Metadata
- Source: user_feedback
- Related Files: .github/workflows/ci.yml, scripts/check_w2_all.py, scripts/check_w2_stage1_contracts.py
- Tags: ci, cleanup, contract-tests

---
