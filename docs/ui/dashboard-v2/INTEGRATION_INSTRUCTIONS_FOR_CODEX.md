# Codex Integration Instructions

## Goal

Replace the current `BossDecisionView` presentation with the frozen Dashboard V2 reference while preserving the existing backend/read-model contracts.

## Required file operations

1. Copy `apps/web/src/reference/dashboard-v2/` into the repository.
2. Keep `DashboardV2Reference.tsx`, CSS, fixture, and model files unchanged.
3. Review and finish only `dashboard-v2-adapter.ts` against the exact current API types.
4. In `DashboardPage.tsx`, replace the `BossDecisionView` import/render with `DashboardV2` from the reference pack.
5. Add the dev/test-only visual route from `App.visual-routing.example.tsx`.
6. Copy the Playwright visual specification and commit the approved golden screenshots.
7. Add a hash guard for the protected files.

## Production replacement

Replace:

```tsx
import { BossDecisionView } from "./BossDecisionView";
```

with:

```tsx
import { DashboardV2 } from "../reference/dashboard-v2";
```

and replace both `BossDecisionView` renders with:

```tsx
<DashboardV2
  dayView={view.day_view}
  legacyMatches={legacyMatches}
  performance={view.performance}
  release={view.release}
/>
```

Do not delete the old component until visual, accessibility, typecheck, build, and E2E gates pass. Keep it temporarily for rollback only.

## Non-negotiable gates

- visual diff within contract
- all 15 fixed-fixture rows reachable
- no public `历史恢复 cohort` wording
- scoreline Top 3 exact backend order
- market consistency label visible
- provider/scheduler truth reflected in health strip
- zero changes to model weights, thresholds, formal, lock, or production capabilities
