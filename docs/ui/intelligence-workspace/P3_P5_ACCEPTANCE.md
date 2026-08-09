# Unified Intelligence Workspace P3–P5 Acceptance

## Authority and scope

- Base main: `f14136f07d69ece09e61fec6b1dd546e67c0267c`
- Public schema: `w2.dashboard-intelligence-workspace.v1`
- Public API: `GET /v1/dashboard/intelligence-workspace`
- Public authority: `NEW_INTELLIGENCE_WORKSPACE_ONLY`
- Product mode: 13 leagues, `SHADOW_ONLY`; Candidate, Formal, Lock, and Production remain `OFF`.
- Provider calls, scheduler/cadence, whitelist, model/factor/threshold, Phase 0.5, and Round4 were not changed.

## Phase acceptance

### P3 — unified product

PASS. The public root consumes only the unified P2 read model and presents Attention, Match Board, selected Inspector, Market Radar, Model Lab, Scoreline Top3, External Intelligence, and Data & Operations. The exact seven intelligence states, four risk axes, readiness/reason codes, 0/1/2+ snapshot truth, `ANALYSIS_REFERENCE`, `NOT_PROVEN`, and all runtime `OFF` statuses are rendered directly from the payload.

### P4 — validation and replay

PASS. Probability validation includes Brier, LogLoss, ECE, reliability bins, W2-versus-market values, sample status, and checkpoint metadata. Directional validation includes correct/wrong/PUSH/VOID, accuracy, effective N, and `NOT_DEFINED` market benchmark. League performance and forward history/replay expose known-at evidence, decision and reason summaries, outcome tracking, hashes, and replay gaps.

### P5 — truth, negative, and visual acceptance

PASS. Automated scenarios cover:

1. empty day;
2. zero snapshots;
3. one snapshot;
4. two-or-more discrete snapshots;
5. lineup not expected yet;
6. lineup expected but provider-empty;
7. stale injuries;
8. stale market;
9. collection/provider degradation;
10. model not ready;
11. validation insufficient;
12. `SAMPLE_BUILDING`;
13. external sources `NOT_CONNECTED` and non-blocking;
14. replay evidence;
15. replay gaps.

Negative checks reject synthetic timelines, a second public dashboard, recommendation promotion, commercial metric fields, anonymous live-odds benchmarks, and legacy fallback. Scoreline `READY` displays exactly 10,000 existing simulations, `unconditional_probability`, and `sample_count`; the API read does not simulate.

### Owner Review C bounded remediation

PASS. The final presentation contract now includes:

1. typed `AH` / `OU` Match Board main-line facts with explicit unavailable state;
2. source-bound two-sided Market Radar prices with every missing side explicitly `NOT_AVAILABLE` and never fabricated;
3. Probability Validation checkpoint/cohort identity and explicit missing metadata;
4. League Performance `Decisive N` alongside all previously accepted columns;
5. compact header update time and system-health context from the unified payload;
6. Scoreline model/readiness status and reason for both READY and UNAVAILABLE states.

Focused Owner Review C Playwright acceptance is 26 PASS, including one test per remediation item and all prior truth/negative contracts.

## Visual evidence

- Browser: fixed Chromium, DPR 1, `en-GB`, `Asia/Shanghai`
- Clock: `2026-08-09T06:00:00Z`
- Motion: disabled; scroll position: 0
- Fixed authority: `golden/intelligence-workspace-1536x1024.png`
- Responsive evidence: `golden/intelligence-workspace-1920x1080.png`, `golden/intelligence-workspace-1440x900.png`, `golden/intelligence-workspace-1366x768.png`
- Owner Review C regeneration SHA-256: `1536x1024=9885c74c33274fac4a9f0c8a0e2e64970168b568eb33b48bc8ab7ccaec2760c9`, `1920x1080=6435947e59ec1465715e14c2fbc6df99243532de56b1e867b892addd40fc435f`, `1440x900=00f38ec8eff39f27228ba7fc1bb6756454b78a405eb527e354323a12109b2110`, `1366x768=db2e88fbf9f2fe0ddcf2fd06c3bd1f8d06ce2e56ac8c5deb50123239fe762b3d`.
- Cross-platform CI: each fixed viewport must produce byte-identical repeated screenshots within the same Chromium runtime; committed Owner Review evidence remains the macOS reference and is not compared pixel-for-pixel with Ubuntu font rasterization.
- Geometry: no horizontal page overflow at all required responsive widths.
- Owner reference status: `OWNER_REFERENCE_BINARY_NOT_REPO_BOUND`; acceptance uses the approved product specification plus deterministic generated evidence.

## Repository hygiene classification

| Asset group | Classification | Evidence |
| --- | --- | --- |
| Unified workspace component, API client, types, and scoped CSS | KEEP | Required by the public root runtime chain. |
| Unified truth/negative/visual E2E and updated source-contract test | KEEP | Required by P3–P5 and CI. |
| Four deterministic workspace screenshots and this receipt | RETAIN_FOR_EVIDENCE | Required for visual and acceptance traceability. |
| Legacy Recommendation/Boss L1/L2 and Dashboard V2 product components | DEPRECATE | Removed from public navigation/runtime authority; preserved because P5 forbids legacy deletion and protected baselines/tests retain evidence dependencies. |
| Boss reference fixture and protected pixel baseline | RETAIN_FOR_EVIDENCE | Still invoked by the protected visual contract. |
| Legacy performance public route | DEPRECATE | No longer routed publicly; source retained as historical evidence and reusable internal presentation code. |

```text
REPOSITORY_HYGIENE = PASS
DEAD_ASSETS_FOUND = 0
DEAD_ASSETS_DELETED = 0
OBSOLETE_CODE_LINES_REMOVED = 112
RETAINED_FOR_EVIDENCE = 4 screenshots + protected legacy reference assets
UNRESOLVED_HYGIENE_ITEMS = 0
```
