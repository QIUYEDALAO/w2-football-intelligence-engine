# W2 Boss Decision Console V2.1 Design QA

## Comparison Target

- Source visual truth: `docs/ui/boss-console/w2_boss_decision_console_prototype.html`
- Reference captures: `docs/ui/boss-console/golden/v2.1/reference/`
- React captures: `docs/ui/boss-console/golden/v2.1/actual/`
- Pixel diffs: `docs/ui/boss-console/golden/v2.1/diff/`
- Combined comparison evidence: `docs/ui/boss-console/golden/v2.1/qa/`
- Browser: Playwright Chromium, `zh-CN`, `Asia/Shanghai`
- Device scale factor: `1`
- State: fixed visual dataset, analysis-priority filter, first fixture selected

## Viewport Evidence

| CSS viewport | Reference pixels | React pixels | Differing-pixel ratio |
| --- | --- | --- | --- |
| 2048 x 1152 | 2048 x 1476 | 2048 x 1476 | 0.00002415 |
| 1440 x 900 | 1440 x 1436 | 1440 x 1436 | 0.00003240 |
| 390 x 844 | 390 x 4119 | 390 x 4119 | 0.00000187 |

All ratios pass the unchanged `0.0015` maximum. Reference and implementation dimensions
match at every viewport.

## Full-View Comparison

The combined desktop and mobile evidence compares the HTML authority and React output in
the same image. Composition, workspace proportions, typography, spacing, palette, borders,
date-first rows, scoreline placement, unified ledger, league table, and responsive stacking
match without actionable P0/P1/P2 drift.

## Focused Comparison

`boss-console-detail-combined.png` compares the selected-fixture rail at native size. The
match title, Shanghai kickoff hierarchy, exact quote, four model/market metrics, EV standard
error, 10,000-sample Top 3, sample counts, probabilities, and market-consistency evidence
match the source authority.

## Fidelity Surfaces

- Fonts and typography: matching family, weights, sizes, line heights, wrapping, numeric
  alignment, and zero negative letter spacing.
- Spacing and layout: matching grid tracks, fixed desktop workspace height, internal queue
  and detail scrolling, panel padding, gaps, borders, and radii.
- Color palette: matching dark green panel system and semantic blue, green, amber, and
  red states.
- Image and asset quality: this console contains no product imagery; no raster placeholder,
  screenshot background, or newly approximated visual asset is used.
- Copy and content: date, snapshot, model EV, EV standard error, scoreline, unified ledger,
  and league labels match the V2.1 product contract.

## Interaction Evidence

- Filters, selection, system drawer, and Escape close behavior pass.
- 5, 15, and 30 fixtures remain reachable; the desktop workspace height is stable.
- Desktop queue scrolling preserves the header and selected-row state.
- Mobile uses natural document scrolling and exposes all 30 fixtures.
- The client clock advances once per minute without changing the API refresh timestamp.
- A reversed global-odds/page-refresh timestamp fails visibly and exposes exact fields in L2.
- Browser console: no application errors during the Playwright suite.
- The market contract fixture proves separate market mainline, analysis selection, and
  execution quote labels; the full ladder expands without hiding `2.75` or its rejection
  evidence.
- Queue order is labelled `A1...` sequence rather than a false priority score.
- Scheduler-off copy states that the prematch review is planned and controlled capture is
  not yet arranged.
- Data, market identity, lineup, and numeric EV standard-error risks remain separate.

## Comparison History

1. Initial V2.1 implementation exposed legacy expectations for mobile nested scrolling,
   whitespace in countdown copy, and public recovery wording.
2. The implementation and HTML authority were corrected to natural mobile scrolling,
   the frozen date-first copy, and one public ledger without recovery/cohort language.
3. Post-fix source-to-React comparison passed all three viewports and all interaction tests.

## Findings

No actionable P0, P1, or P2 visual differences remain. HTTPS and authentication are a
separate staging security task and are not part of this UI fidelity result.

final result: passed
