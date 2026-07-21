**Findings**

- [P0] The protected React implementation and approved golden screenshots are different authorities.
  Location: Dashboard V2 visual fixture route.
  Evidence: the protected component sorts fixtures by `kickoffUtc`, so the two 20:00 matches render before the selected 21:00 match. The 1440 golden places the selected 21:00 match first. The React output also creates separate `07-26` and `07-27` groups, while the golden's hand-authored preview groups both under `07-26`.
  Impact: the required `maxDiffPixelRatio <= 0.0015` cannot pass without changing a protected file, replacing the golden, or testing a different DOM than production.
  Fix: provide a corrected pack whose golden screenshots were captured from the protected React component and fixed fixture, or explicitly approve a protected-source revision that matches the current goldens.

- [P1] The supplied visual test expected locator crops, while the approved goldens are full-page captures.
  Location: `apps/web/e2e/dashboard-v2-visual.spec.ts`.
  Evidence: locator screenshots measured 1920x1201, 1416x949, and 374x4685; approved goldens measure 2048x1202, 1440x950, and 390x4709.
  Impact: the original test could not compare against the supplied goldens.
  Fix: the integration test now uses full-page screenshots and maps directly to the protected golden paths. This exposes the authority conflict above without weakening the 0.15% threshold.

**Open Questions**

- The authority order names the protected React source before the golden screenshots, but the acceptance contract requires the current goldens. Human design authority must choose which one is corrected.
- The pack contains no approved scroll-bottom or scoreline-panel crop goldens. Those states are covered by geometry, visibility, exact-copy, and interaction assertions, but cannot receive an independent pixel verdict without human-supplied baselines.

**Implementation Checklist**

- Protected baseline SHA256 guard: passed.
- Adapter, production entry, and visual route: integrated.
- Fixed visual data is dev/test-only and absent from the production bundle: passed.
- Real V3 `evaluated_candidate.analysis_evidence` survives API normalization and maps exact bookmaker, quote time, model/market probabilities, delta, EV, and uncertainty: passed.
- TypeScript typecheck and production build: passed.
- Full W2 all-stage verification: passed (1411 tests passed, 4 environment-dependent tests skipped).
- 15-fixture internal-scroll reachability: passed.
- Scoreline Top 3 and market-consistency behavior: passed.
- Unified forward-ledger behavior: passed.
- Full-page golden comparison at 2048, 1440, and 390: blocked by source-pack authority conflict.

**Follow-up Polish**

- None. Visual polish is intentionally frozen until the source/golden conflict is resolved.

Source visual truth paths:

- `docs/ui/dashboard-v2/golden/dashboard-v2-wide-2048.png`
- `docs/ui/dashboard-v2/golden/dashboard-v2-desktop-1440.png`
- `docs/ui/dashboard-v2/golden/dashboard-v2-mobile-390.png`

Implementation evidence:

- Playwright run: 15 behavior/contract tests passed; the three official viewport comparisons failed only on the source/golden authority conflict recorded above.
- In-app browser capture: `/tmp/w2-dashboard-v2-inapp-1440.png`
- Side-by-side comparison: `/tmp/w2-dashboard-v2-qa-comparison.png`
- Viewport: 1440x900, zh-CN, Asia/Shanghai, deviceScaleFactor=1.
- State: fixed visual fixture, selected fixture `1494218`, all-schedule filter.
- Primary interactions tested: analysis-only filter (5 visible), all-schedule filter (15 visible), fixture selection and right-rail update.
- Browser console errors: none.
- Full-view comparison: completed with source and implementation in one side-by-side image.
- Focused comparison: scoreline panel is included in the full-page golden and separately verified by exact content and rail-bounds assertions; no additional human-approved crop golden exists.

Comparison history:

1. Repeated comparison found 3% / 4% / 7% full-page differences at 2048 / 1440 / 390, including fixture ordering, date grouping, row copy, and page height.
2. Protected hashes were rechecked and remained unchanged, proving the mismatch is in the supplied reference pack rather than an integration edit.
3. No protected source, golden image, or threshold was changed.

final result: blocked
