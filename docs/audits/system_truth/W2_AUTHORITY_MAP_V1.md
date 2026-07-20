# W2_AUTHORITY_MAP_V1

- Generated at: `2026-07-20T12:51:47.425145Z`
- Audit SHA: `94ba834559c0beba5b38075bd358a8e92a434a51`
- Provider calls: `0`
- DB writes: `0`
- Final state: `MANUAL_APPROVAL_REQUIRED`

每个核心概念的 authority 分类。任何 `CONFLICTING_AUTHORITY` 在能力开放前都要收口。

## Authority Entries

| concept | classification | canonical_authority | severity | required_resolution |
| --- | --- | --- | --- | --- |
| fixture discovery | CONFLICTING_AUTHORITY | target: w2.matchday.intake_v2.fixture_discovery_from_payloads | P0 | Route all runtime discovery through Matchday V2 or demote future_refresh discovery to compatibility with explicit deletion condition. |
| team identity | ACTIVE_CANONICAL | team_identity_crosswalks + MatchdayTeamCrosswalkV1 contract | P1 | Materialize reviewed crosswalk for runtime F5/F8 consumers. |
| checkpoint policy | CONFLICTING_AUTHORITY | target: config/policies/matchday_intake.v2.json | P0 | Make V2 the only active scheduler policy; remove fallback offsets after tests prove zero callers. |
| provider request | CONFLICTING_AUTHORITY | target: MatchdayEndpointCaptureV1 | P0 | Single provider front door must create endpoint capture first; all scheduler/worker paths consume that contract. |
| raw payload | CONFLICTING_AUTHORITY | target: endpoint capture/raw payload hash registry | P1 | Choose one raw payload identity and map old tables as compatibility. |
| odds observation | CONFLICTING_AUTHORITY | target: MatchdayMarketObservationV2 / canonical OddsObservation | P1 | Normalize provider odds into one observation table/read model with shared quote hash. |
| canonical AH/OU | ACTIVE_COMPATIBILITY | w2.markets.market_candidate + w2.markets.analysis_evidence | P1 | Unify AH/OU candidate identity before formal unlock. |
| quote identity | ACTIVE_CANONICAL | w2.markets.quote_identity | P2 | Backfill all read models to expose same quote hash. |
| freshness | CONFLICTING_AUTHORITY | target: authoritative captured_at only | P1 | Use V2 freshness status as one read-model input. |
| market selection | ACTIVE_CANONICAL | src/w2/strategy/market_selector.py | P2 | Document compatibility rules for older analysis_recommendation outputs. |
| model probability | SHADOW_ONLY | src/w2/models/independent.py + calibration artifacts | P1 | Do not promote beyond BASELINE_PRIOR/SHADOW until approved hashes exist. |
| market probability | ACTIVE_COMPATIBILITY | devig market baseline, not independent model evidence | P1 | Add explicit field-level provenance labels across V3 projection. |
| analysis direction | ACTIVE_CANONICAL | same-market analysis_evidence comparison | P1 | Keep market_movement.direction_allowed advisory only, not recommendation authority. |
| lineup policy | ACTIVE_CANONICAL | config/policies/lineup_market_policy.v1.json + w2.lineups.intelligence | P2 | Deprecate old F10/injuries paths once callers are proven zero. |
| F5 | DATA_DEPENDENCY_MISSING | target: canonical team-history query backed by Football-Data facts | P0 | Import reviewed facts into canonical DB/read service and bind to code/data asset registry. |
| F8 | DATA_DEPENDENCY_MISSING | target: reviewed as-of team value artifact/DB identity | P0 | Make one reviewed F8 artifact/table canonical and mark config snapshots compatibility. |
| formal readiness | ACTIVE_CANONICAL | src/w2/formal/readiness.py | P1 | No formal unlock until audit P0s are closed. |
| recommendation | CONFLICTING_AUTHORITY | target: RecommendationDecisionV3 | P0 | Enforce one V3 decision hash as source for API, Dashboard, frozen artifact, tracking and reporting. |
| lock | ACTIVE_COMPATIBILITY | recommendation_lock_snapshot requires V3 FORMAL_RECOMMEND | P1 | Prove old lock ledgers cannot be written from ANALYSIS_PICK before unlock. |
| settlement | ACTIVE_COMPATIBILITY | settlement/history + forward outcome ledger | P1 | Bind settlement to decision_hash/lock_id identity and demote legacy utilities. |
| performance cohort | ACTIVE_COMPATIBILITY | forward_ledger_performance cohort rules | P1 | One cohort membership table/read model keyed by decision_hash. |
| Dashboard projection | ACTIVE_COMPATIBILITY | canonical_decision_projection should be sole display adapter | P1 | Dashboard must read one V3 projection, never recompute or override canonical status. |
