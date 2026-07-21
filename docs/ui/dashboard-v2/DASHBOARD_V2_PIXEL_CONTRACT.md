# W2 Dashboard V2 Pixel-Locked Contract

## Official renderer

- Playwright Chromium pinned by the repository lockfile
- `deviceScaleFactor=1`
- locale `zh-CN`
- timezone `Asia/Shanghai`
- system font stack only
- animations and transitions disabled during capture
- fixed fixture clock `2026-07-21T12:33:00Z`

## Baseline viewports

- Wide desktop: `2048 x 1152`
- Desktop: `1440 x 900`
- Mobile: `390 x 844`
- Scroll-bottom crop for 15 fixtures
- Selected scoreline panel crop

## Tolerances

- Full component screenshot: `maxDiffPixelRatio <= 0.0015`
- Critical bounding-box variance: `<= 1 px`
- Required copy: exact string match
- Fixture counts and ledger identities: exact numeric match

## Protected source

The following files are design authority and may not be modified by Codex without explicit human approval:

- `DashboardV2Reference.tsx`
- `dashboard-v2-reference.css`
- `dashboard-v2-reference.fixture.ts`
- `dashboard-v2-model.ts`
- all golden images
- copy and behavior contracts

Backend changes belong in `dashboard-v2-adapter.ts`.

## Forbidden implementation shortcuts

- screenshot background
- canvas recreation
- absolute-positioned tracing of a screenshot
- mock data on the production route
- hidden duplicate DOM
- row truncation
- baseline regeneration to hide a regression
- relaxed screenshot threshold
- skipped visual tests
