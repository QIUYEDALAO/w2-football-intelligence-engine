# Dashboard V4.1 Design QA

## Comparison target

- Source visual truth path: `docs/ui/dashboard-v4.1/targets/`
- Source authority: `docs/ui/dashboard-v4.1/reference/` plus `DESIGN_REFERENCE_SHA256SUMS.txt`
- Implementation screenshot paths: `apps/web/test-results/**/actual-*.png`
- Combined full-view evidence: `apps/web/test-results/v41-state-reference-actual-contact-sheet-pass4.png`
- Combined focused evidence: `apps/web/test-results/v41-normal-header-focus-pass4.png` and `apps/web/test-results/v41-blocked-main-focus-pass2.png`
- D16 deployed-shape implementation targets: `docs/ui/dashboard-v4.1/targets/d16-postdeploy-1366x768.png` and `docs/ui/dashboard-v4.1/targets/d16-postdeploy-1512x982.png`
- D16 combined side-by-side review evidence: `/tmp/d16-design-qa-comparison-1366.png`
- Route/state: public unified intelligence workspace, dark theme, unauthenticated local Playwright render with deterministic real-shape contract payloads

## Viewports and normalization

| State | CSS viewport | Source pixels | Implementation pixels | Density normalization |
|---|---:|---:|---:|---|
| normal | 1280 x 720 | 1280 x 720 | 1280 x 720 | deviceScaleFactor 1; none |
| normal | 1366 x 768 | 1366 x 768 | 1366 x 768 | deviceScaleFactor 1; none |
| normal | 1512 x 982 | 1512 x 982 | 1512 x 982 | deviceScaleFactor 1; none |
| normal | 1536 x 1024 | 1536 x 1024 | 1536 x 1024 | deviceScaleFactor 1; none |
| responsive normal | 1180 x 1300 | 1180 x 1300 | 1180 x 1300 | deviceScaleFactor 1; none |
| D16 deployed shape | 1366 x 768 | 1366 x 768 | 1366 x 768 | deviceScaleFactor 1; none |
| D16 deployed shape | 1512 x 982 | 1512 x 982 | 1512 x 982 | deviceScaleFactor 1; none |
| blocked/calm/stale/empty | 1440 x 900 | 1440 x 900 | 1440 x 900 | deviceScaleFactor 1; none |

The contact sheet scales each equal-density source/implementation pair equally for review only. Playwright compares the original equal-pixel captures.

## Findings

- No actionable P0, P1, or P2 difference remains.
- [P3] Deterministic implementation fixtures use contract-level team names, timestamps, and reason text rather than copying every literal mock value. Information hierarchy, state semantics, density, and component placement remain equivalent; this is expected dynamic-content variance.

## Required fidelity surfaces

- Fonts and typography: the implementation matches the approved system sans/monospace hierarchy, weights, compact line heights, uppercase micro-labels, numeric emphasis, wrapping, and truncation behavior. No remote font dependency was introduced.
- Spacing and layout rhythm: the header, L1 summary, 360 px priority rail, dominant match/global focus, L4 quality rail, borders, radii, and compact gaps align with the approved desktop composition. At 1180 px the main regions stack in natural flow without nested primary scrolling.
- Colors and visual variables: background, panel, line, accent, warning, critical, and muted-text variables preserve the approved dark cockpit palette and semantic state mapping. Representative text contrast is at least 4.5:1.
- Image quality and asset fidelity: the approved interface contains no visible photographic, logo, illustration, or bespoke icon assets. No image was replaced with CSS art, inline SVG, emoji, or placeholder imagery; the reference HTML/PNG set is stored byte-for-byte with checksums.
- Copy and content: product-specific labels preserve market fact, model diagnostic, formal-authority separation, Market Memory, fail-closed language, and Provider no-call-on-read wording. Blocked, calm, empty, and stale states use factual rather than promotional copy.
- Interactions and accessibility: date navigation, Today, Refresh, match selection, keyboard focus, responsive flow, 200% zoom, expandable details, empty state, blocked state, stale state, and endpoint failure were exercised. Controls retain semantic buttons/links and visible focus. No browser console error was observed during the Playwright run.

## Full-view comparison evidence

- Normal: approved targets and implementation captures were compared at five exact viewports. The four-level hierarchy, information density, rail proportions, focus dominance, and quality footer are preserved.
- Blocked/calm/stale/empty: all four approved 1440 x 900 targets were placed beside their matching implementation captures in `v41-state-reference-actual-contact-sheet-pass4.png`. The final pass preserves the intended state-specific hierarchy and does not fall back to a match focus.
- Automated evidence: nine approved-target screenshot comparisons pass with `maxDiffPixelRatio: 0.2`; this tolerance accommodates deterministic dynamic copy while still failing structural drift.

## Focused region comparison evidence

- `v41-normal-header-focus-pass4.png` compares the top 220 px at 1280 x 720 and confirms navigation, status, L1 count hierarchy, football-day window, shortlist alignment, and focused match header.
- `v41-blocked-main-focus-pass2.png` compares the 1440 x 520 blocked-state main region and confirms zero priority count, one global incident group, top-aligned incident focus, semantic critical color, recovery copy, and read-protection treatment.
- `d16-design-qa-comparison-1366.png` places the approved normal target and D16 deployed-shape capture at equal 1366 x 768 density. It confirms one authoritative normal-day mode, a scoped partial-degradation badge, one useful stale-evidence focus, auditable primary/secondary reasons, Chinese-first risk copy, and natural page flow without a nested focus scrollbar.

## Comparison history

### Pass 1 — blocked

- Earlier finding [P1]: the affected fixture count was incorrectly rendered as the priority-match count, and the shortlist had no aggregated global incident.
- Fix: the backend summary now keeps blocked-day priority counts at zero, while `global_focus` retains affected fixture/competition counts; the frontend renders one global collection-incident group.
- Post-fix evidence: focused backend contracts pass 38/38 and the blocked capture shows `0 场优先查看` plus `采集异常 · 11 场`.

### Pass 2 — blocked/calm/empty

- Earlier finding [P2]: the global focus was vertically centered with excessive whitespace and omitted the approved factual/stat/recovery hierarchy; calm and empty shortlists did not distinguish valid observation from missing work.
- Fix: global focus is top-aligned and includes mode-specific fact/result cards, three factual statistics, recovery/explanation blocks, and truthful aggregate shortlist rows.
- Post-fix evidence: `v41-state-reference-actual-contact-sheet-pass4.png`; all four state screenshot tests pass.

### Pass 3 — final

- No P0/P1/P2 finding remained after comparing the same state, viewport, theme, crop, CSS size, and density.
- All 21 V4.1-specific Playwright contract/visual/accessibility tests and all 39 repository Web E2E tests pass.

### Pass 4 — D16 bounded remediation

- Earlier finding [P1]: the public header could show a normal match day while also exposing the raw `BLOCKED_DAY` system code; priority counts included local data-incomplete items; the first match could win focus despite having no usable market evidence.
- Fix: the public mode is now singular and authoritative, scoped system degradation is separate, priority eligibility is limited to current market movement, source-bound model diagnostics, or stale market memory, and focus ranks usable evidence deterministically.
- Earlier finding [P1]: primary and subordinate reasons were not visually distinguished, and raw risk codes leaked into the public explanation.
- Fix: the shortlist now labels `主因` and `次因`, excludes other-attention rows from the priority count, and renders Chinese causal risk explanations with raw codes confined to technical details.
- Earlier finding [P2]: the right focus region retained an internal desktop scrollbar and the global quality rail could present an unavailable checkpoint with an apparently current timestamp.
- Fix: the focus region follows natural page flow at 1180/1280/1366/1512/1536 widths, while checkpoint status is fail-closed to exactly AVAILABLE, STALE, INCOMPLETE, or NOT_AVAILABLE.
- Post-fix evidence: 26 focused D16/V4.1 Playwright tests pass, including the deployed real shape, all four checkpoint states, 200% zoom, desktop scroll ownership, reason-count auditability, technical risk details, and zero read-side calls/writes.

## Implementation checklist

- [x] Approved source and implementation opened and compared side by side.
- [x] Normal, blocked, calm, stale, empty, and 1180 responsive states covered.
- [x] Fonts, spacing, colors, image assets, and copy explicitly reviewed.
- [x] Date controls, refresh, selection, keyboard focus, details, zoom, and fail-closed endpoint behavior tested.
- [x] Earlier P1/P2 findings fixed and re-captured.
- [x] D16-01 through D16-07 semantics and deployed-shape rendering re-captured at 1366 x 768 and 1512 x 982.

final result: passed

---

## Blocked-day evidence wording — local review, 2026-08-10

- Source visual truth: `/Users/liudehua/Desktop/网页截图.png`
- Implementation screenshot: `/tmp/w2-evidence-wording-local-1440x900.png`
- Side-by-side comparison: `/tmp/w2-evidence-wording-comparison.png`
- Viewport/state: 1440 × 900 CSS px, device scale 1, `2026-08-10`, real read-only `BLOCKED` payload through the local Vite proxy
- Source/implementation pixels: 1440 × 900 each; no density normalization required
- Primary interactions: page load and real selected-day read passed
- Console errors/warnings: none

**Comparison history**

- Earlier P1: the source repeated “阻塞” and “等待既有调度”, making an intentionally disabled market-evidence path look like a broken application with an active recovery schedule.
- Fix: preserved the technical `BLOCKED` contract while changing public copy to “仅赛程 / 市场证据未就绪”, explicitly separating 2 visible fixtures from 0 market analyses and removing the false scheduler promise.
- Post-fix evidence: the right side of the comparison keeps the exact frame, spacing, typography, colors, controls and section proportions while presenting the truthful read-only state.

**Required fidelity surfaces**

- Fonts and typography: unchanged from the source implementation; hierarchy and wrapping remain stable.
- Spacing and layout rhythm: unchanged; header, shortlist, focus card and validation panel retain the same geometry.
- Colors and styles: existing semantic styles are reused; no new visual system was introduced.
- Image quality and assets: no image assets are present or changed.
- Copy and content: the actionable P1 mismatch is resolved; technical reason codes remain available only inside collapsed details.
- Focused-region comparison: top status pills, left match list and the main focus card were readable in the combined comparison; no additional crop was required.

**Remaining findings**

- No actionable P0/P1/P2 findings.

final result: passed

## Owner rereview remediation — 2026-08-10

- Reference screenshot: `/Users/liudehua/Desktop/网页截图.png`
- Rendered screenshot: `docs/ui/dashboard-v4.1/owner-rereview-remediation-1440x900.png`
- Side-by-side comparison: `docs/ui/dashboard-v4.1/owner-rereview-comparison.png`
- Viewport: `1440 × 900`
- Browser: Codex in-app browser
- Data source during visual QA: existing public unified read model through the local Vite proxy
- Read behavior: one selected football-day read; no Provider call or write was initiated by the page

### Comparison iterations

1. Made affected blocked matches and kickoff times visible in the primary left column.
2. Replaced the ambiguous `0 场优先 / 共 2 场` combination with `2 场今日比赛 / 0 场具备完整评估证据 / 2 场证据阻塞`.
3. Compressed duplicated blocked-day explanations and moved raw reason/read-contract codes into collapsed technical detail.
4. Displayed the complete scheduled-evaluation timestamp and explicitly marked an expired schedule record as expired.
5. Added a single-read seven-day navigator and a prominent post-match validation center.
6. Collapsed stale model-quality evidence instead of rendering a full row of empty metrics.
7. Raised primary date/history controls to 38–42 px and retained visible keyboard focus.
8. Re-ran the 1440 × 900 side-by-side comparison, responsive checks, contrast checks and full Web E2E after the final copy change.

### Acceptance checks

- Blocked-day match identity and kickoff: passed
- Multi-day navigation and one-read behavior: passed
- Post-match validation discoverability: passed
- Public technical-code containment: passed
- Repeated blocked-state dominance: passed
- Scheduled recovery clarity: passed
- Stale empty-metric rail: passed
- Primary control target sizes and keyboard focus: passed
- 1180 px and 200% zoom natural-flow check: passed
- Representative text contrast at least 4.5:1: passed
- Focused decision-contract E2E: 37 passed
- Full Web E2E: 55 passed

final result: passed
