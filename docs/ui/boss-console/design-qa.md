# Boss Decision Console Design QA

Status: **PASSED**

## Authority

- Approved source: `docs/ui/boss-console/w2_boss_decision_console_prototype.html`
- Source SHA256: `e71c8d0ed4d43bdf84648f05f5f38c1124ce6e4055ba77fcec069e3cbfa29fea`
- Source type: user-supplied HTML/CSS/JavaScript prototype
- Superseded authority: Dashboard V2 reference pack and its conflicting golden images

## Visual Comparison

Playwright renders the approved source HTML and the React visual fixture in the same
Chromium runtime, locale, timezone, viewport, and device scale. The two full-page PNGs
are compared pixel by pixel with Playwright's standard `0.2` color threshold (51 per
8-bit channel) and a one-pixel spatial tolerance for Linux glyph rasterization.

- Chromium viewport: `1440 x 900`
- Locale: `zh-CN`
- Timezone: `Asia/Shanghai`
- Device scale factor: `1`
- Maximum changed-pixel ratio: `0.15%`
- Result: **PASS**
- Source and implementation image dimensions: identical

## Geometry And Behavior

- Initial priority queue contains the same five analysis rows: PASS
- `全部赛程 14` reveals all fourteen fixtures: PASS
- `仅看异常` shows the source-defined seven exception rows: PASS
- Row selection updates the right-side evidence panel: PASS
- System drawer opens and closes with Escape: PASS
- Queue has bounded internal scrolling and the last fixture remains reachable: PASS
- Formal recommendations remain `0`: PASS
- Automatic collection remains visibly paused: PASS
- Product boundary `分析建议 != 正式推荐` remains visible: PASS

## Production Data Boundary

The production route uses the same presentation component but receives data only through
`boss-console-adapter.ts`. The fixed visual fixture is exposed only by the development/test
route. The production component does not compute model probability, market probability,
EV, uncertainty, market direction, or ledger outcomes.

The prototype-only phrases `演示数据`, `历史恢复 cohort`, and `演示稿` are enabled only
for source-image comparison. The production route uses truthful frozen-evidence and unified
ledger wording without changing the approved geometry.

## Final Verdict

`BOSS_DECISION_CONSOLE_SOURCE_PIXEL_CONTRACT_PASS`
