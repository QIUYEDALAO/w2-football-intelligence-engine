# W2 统一情报工作台视觉与中文化 Design QA

## Comparison Target

- Source visual truth: `docs/ui/boss-console/golden/v2.1/reference/boss-console-desktop-1440.png`
- Implementation: `docs/ui/intelligence-workspace/golden/intelligence-workspace-1440x900.png`
- Combined comparison evidence: `docs/ui/intelligence-workspace/visual-comparison-1440.jpg`
- Primary Owner evidence: `docs/ui/intelligence-workspace/golden/intelligence-workspace-1536x1024.png`
- Browser: Chromium and Codex in-app Browser, `zh-CN`, `Asia/Shanghai`
- Device scale factor: `1`
- State: deterministic six-fixture workspace; fifth fixture selected; real discrete 2+ snapshot paths; scoreline READY with the existing 10,000-simulation artifact

The source capture is 1440 x 1436 pixels. Its top 1440 x 900 region was cropped by a fixed
16:10 comparison frame and compared with the implementation's native 1440 x 900 capture.
The combined comparison canvas is 1280 x 720 pixels and presents both normalized regions at
the same scale. The implementation is also captured natively at 1536 x 1024, 2048 x 1084,
1920 x 1080, 1366 x 768, and 390 x 844.

## Full-View Comparison

The comparison confirms the intended composition transfer without restoring obsolete Boss
semantics: compact left rail, dense top status strip, three-column first row, match board plus
central selected-match analysis, model lab, validation, league performance, thin borders,
low-elevation panels, and restrained cyan/green/amber/red accents. At 1536 x 1024 the first
viewport contains all nine required primary surfaces, five Attention rows, six Match Board
rows, system health, and the bottom source/status strip.

## Focused Comparison

The native 1536 x 1024 implementation capture was inspected at original resolution for the
Attention feed, selected-match center, market cards, Scoreline Top 3, and validation row.
These regions are readable without enlarging the image, preserve compact numeric hierarchy,
and use bounded internal scrolling. A separate focused composite was unnecessary because
the source is composition authority only and its obsolete recommendation content cannot be
used as field-level fidelity authority.

## Required Fidelity Surfaces

- Fonts and typography: system Chinese font fallbacks, compact 8-14 px hierarchy, numeric
  alignment, truncation, and weights follow the reference density. Canonical codes are not
  primary badge copy; audit codes remain in `技术详情`, attributes, or tooltips.
- Spacing and layout rhythm: 184 px rail, 8 px grid gaps, 6 px panel radii, thin borders,
  internal Attention/Match Board scrolling, and a fixed desktop primary grid reproduce the
  reference cockpit rhythm. Mobile stacks naturally without horizontal viewport overflow.
- Colors and visual palette: near-black green-blue background, low-contrast dividers, and
  restrained semantic colors match the approved direction without decorative gradients.
- Image quality and asset fidelity: the target contains no required product imagery or
  non-standard icon assets. The implementation adds no raster placeholders, custom SVGs,
  CSS illustrations, emoji, or fabricated imagery.
- Copy and content: navigation, panel titles, states, risks, readiness, reasons, market sides,
  empty/error states, health, dates, and controls are Chinese-first. Unknown source team names
  truthfully fall back to source identity. English canonical values remain secondary.
- Interactions and states: match selection updates the central analysis and market evidence;
  `查看全部` exposes all Attention rows; date/refresh controls remain functional; ready,
  unavailable, empty-day, degraded, stale, and endpoint-error states are covered.
- Accessibility: semantic buttons and labels are retained, focus states remain visible,
  mobile controls meet practical sizing, reduced motion is supported by deterministic test
  overrides, and no persistent control is hidden by viewport overflow.

## Comparison History

1. Initial authority state: the deployed implementation was a long English-heavy vertical
   document and did not match the compact Owner composition.
2. First implementation comparison found two P2 issues: the 1536 Attention card exposed only
   about two rows, and several raw external/empty/readiness codes still appeared in the public
   layer. The grid allocation, row density, status maps, reason summaries, and technical-detail
   boundaries were corrected.
3. Post-fix evidence shows five primary Attention rows, six bounded match rows, all required
   first-viewport surfaces, Chinese primary copy, and raw codes confined to secondary audit
   layers. Required viewport screenshots and deterministic visual regression pass.

## Findings

No actionable P0, P1, or P2 visual differences remain. The source is intentionally not a
field-level pixel target because its recommendation/EV/lock semantics are obsolete; only its
composition, density, palette, typography scale, border system, and responsive mechanics were
reused. Very small secondary audit text is retained as a P3 density tradeoff and does not
affect primary Chinese scanning or core controls.

## Implementation Checklist

- [x] Compact multi-column desktop console
- [x] Chinese-first public layer and secondary canonical audit details
- [x] Five primary Attention rows and bounded Match Board
- [x] Central selected match, Market Radar, Model Lab, Scoreline Top 3
- [x] First-viewport validation, league performance, and system health
- [x] Six required deterministic viewport captures
- [x] Empty/error/degraded/0/1/2+ and interaction coverage

final result: passed
