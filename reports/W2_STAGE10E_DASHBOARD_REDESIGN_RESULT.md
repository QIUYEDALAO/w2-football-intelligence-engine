# W2 Stage10E Dashboard Redesign Result

Status: LOCAL_IMPLEMENTATION_READY

## Redesign Goal

The dashboard was redesigned from a flat technical console into a product-grade
matchday research workspace. The first screen now explains the research-only
mode, shows concise KPIs, prioritizes today’s Beijing-time fixtures, and moves
provider/gate/alert information into supporting context.

## Information Architecture

- Global header: product name, research-only status, last update, and global health.
- KPI row: today fixture count, researchable fixtures, data health, provider quota, Gate 4, Gate 5.
- Matchday Center: fixture list with Beijing kickoff, WATCH/SKIP, grade, primary direction, data status, and latest snapshot.
- Fixture Workspace: tabs for overview, market ranking, research card, integrity/timeline, shadow strategy, and comparison.
- Right rail: provider quota, Gate status, data health, coverage, and runtime alerts.

## Key Components

- `DashboardShell`
- `GlobalStatusBar`
- `SummaryKpiRow`
- `MatchdayFixtureList`
- `FixtureListItem`
- `FixtureWorkspace`
- `FixtureOverviewPanel`
- `PrimaryResearchCard`
- `MarketRankingPanel`
- `IntegrityPanel`
- `ShadowStrategyPanel`
- `ComparisonPanel`
- `ProviderQuotaCard`
- `GateStatusCard`
- `SystemHealthCard`
- `EmptyStatePanel`
- `ErrorStatePanel`
- `SkeletonCard`

## Interaction Notes

- Fixture list and detail workspace are linked.
- Fixture switching uses stable loading skeletons.
- Workspace tabs do not change the selected fixture or refetch unnecessary data.
- Market Ranking supports filters for `ALL`, `1X2`, `AH`, `OU`, and `BTTS`.
- Market rows are progressively disclosed with an “expand more” control.
- Error states show endpoint, request id, error code, and retry.
- Empty and stale states are visually distinct from loading.

## Interface Boundary

No backend API was added. The redesign reuses the current read-only endpoints:

- `/api/v1/matchday/{date}`
- `/api/v1/fixtures/{fixture_id}`
- `/api/v1/fixtures/{fixture_id}/market-probabilities`
- `/api/v1/fixtures/{fixture_id}/model-probabilities`
- `/api/v1/fixtures/{fixture_id}/market-ranking`
- `/api/v1/fixtures/{fixture_id}/integrity`
- `/api/v1/providers/status`
- `/api/v1/data-health`
- `/api/v1/forward-holdout/status`
- `/api/ops/matchday-coverage`
- `/api/ops/alerts`
- `/api/ops/gates/5-preflight`
- `/api/ops/shadow-strategy/status`
- `/api/ops/w1-w2-shadow-comparison`

No write endpoint, DeepSeek, candidate state, recommendation route, or production behavior was introduced.

## Improvements Over Previous Version

- Matchday work is now the dominant user path.
- Operational cards no longer overpower the research workflow.
- Primary direction, model odds, risk-adjusted EV, grade, and invalidation context are grouped in a research card.
- Market ranking is readable and filterable instead of raw JSON-first.
- Gate 4 limitations and formal recommendation disabled status are visible without overwhelming the page.
- UI states are consistent across loading, empty, error, stale, and success.

## Visual Verification

Local build succeeded. No staging deployment or server browser validation was performed in this local-only stage.

## Validation

- `npm --prefix apps/web ci`
- `npm --prefix apps/web run typecheck`
- `npm --prefix apps/web run build`

Full repository validation is tracked in the stage terminal logs.

## Deployment

SERVER_DEPLOYMENT=NOT_PERFORMED

PATCH_UPLOAD=NOT_PERFORMED

CURRENT_SWITCH=NOT_PERFORMED

SYSTEMD_RESTART=NOT_PERFORMED

W1_MODIFIED=false

RECOMMENDATION_API=DISABLED
