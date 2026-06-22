# W2 Stage10E Dashboard Product Audit

## Current Problems

- The current dashboard reads like a technical monitoring grid: many panels have equal weight, so users cannot quickly tell which match matters now.
- The first viewport is dominated by Forward/Provider/Data Health cards before the matchday task is established.
- Fixture detail is a long fact list with raw JSON blocks, which makes market value, model leaning, data health, and Gate state hard to compare.
- WATCH/SKIP, primary direction, published grade, and formal recommendation state are visually close to operational metadata, creating semantic risk.
- Loading, empty, error, and stale states exist, but they are text-heavy and do not guide recovery or explain user impact.
- Market ranking is not progressively disclosed; the page shows raw rows instead of letting users filter by 1X2, AH, OU, and BTTS.
- Gate, quota, alerts, readiness, and governance are important but visually compete with match research.
- Chinese user copy is present but inconsistent; some panels still lead with English technical labels.

## User Task Flow

1. Open the dashboard and confirm the system is research-only.
2. Check today’s Beijing-time match count and whether any fixture is research-ready.
3. Select the fixture that looks most actionable.
4. Read the fixture overview: kickoff, competition, latest snapshot, action, grade, data health, and lineups.
5. Compare market ranking, model probability, market fair probability, and current primary/secondary research direction.
6. Inspect integrity, stale warnings, Gate limitations, and suppressed secondary reasons before trusting the card.
7. Use provider/quota/gate/alert information only as supporting operational context.

## Redesign Goals

- Make Matchday Center the primary product surface, not a secondary table.
- Give the first viewport a clear research-only status, concise KPIs, and an obvious current fixture.
- Separate user decision lifecycle state from data and operations status.
- Convert JSON-heavy areas into structured cards, badges, filters, and expandable details.
- Keep high data density while improving scanability and confidence.
- Preserve all existing read-only semantics; do not add recommendation, candidate, DeepSeek, or write endpoints.

## Information Architecture Proposal

- Global Header: W2 product title, environment/revision placeholders, last update, health, and research-only status strip.
- KPI Summary Row: today fixtures, researchable fixtures, data health, provider quota, Gate 4, Gate 5.
- Matchday Center: left fixture list with Beijing time, action, grade, primary direction, data status, and snapshot time.
- Fixture Detail Workspace: tabbed workspace with Overview, Market Ranking, Research Card, Integrity/Timeline, Shadow, and Comparison.
- Right Rail: Provider quota, Gate status, runtime alerts, shadow summary, W1/W2 comparison status.

## Component Inventory

- `DashboardShell`
- `GlobalStatusBar`
- `SummaryKpiRow`
- `MatchdayFixtureList`
- `FixtureListItem`
- `FixtureWorkspace`
- `FixtureOverviewPanel`
- `PrimaryResearchCard`
- `MarketRankingPanel`
- `ResearchCardPanel`
- `IntegrityPanel`
- `ShadowStrategyPanel`
- `ComparisonPanel`
- `ProviderQuotaCard`
- `GateStatusCard`
- `SystemHealthCard`
- `EmptyStatePanel`
- `ErrorStatePanel`
- `SkeletonCard`

## State Inventory

- `LOADING`: skeleton layout with stable card dimensions.
- `SUCCESS`: structured product cards and tables.
- `EMPTY`: explicit empty explanation and endpoint context.
- `ERROR`: endpoint, request id, error code, and retry action.
- `STALE`: show last available data with a visible stale badge and operational warning.

## Implementation Boundary

- Reuse current read-only APIs.
- No backend aggregation is required for this local redesign.
- No staging deployment, server restart, W1 access, DeepSeek call, candidate state, or formal recommendation enablement.
