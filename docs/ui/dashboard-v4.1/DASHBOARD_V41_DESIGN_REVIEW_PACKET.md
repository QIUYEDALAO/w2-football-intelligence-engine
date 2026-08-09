# Dashboard V4.1 Design Review Packet

```text
OWNER_V41_REFERENCE_SET_REPO_BOUND = PASS
REFERENCE_HASH_MANIFEST = PASS
DESIGN_STATE_MATRIX = PASS
NO_PRODUCT_CODE_CHANGED_DURING_V41_0 = PASS
D16_01_THROUGH_D16_07_DESIGN_CLOSURE = PASS
```

| Owner finding | Frozen V4.1 resolution | Evidence |
|---|---|---|
| Long technical report rather than a decision cockpit | Four-level L1/L2/L3/L4 hierarchy | `reference/normal.png` and exact viewport targets |
| Backend and frontend first-match fallback | Backend focus contract with exact mode/focus pairing | state matrix and V41-1 contract |
| Global incident rendered as an arbitrary match | `BLOCKED + GLOBAL_INCIDENT` | `reference/blocked.png` |
| Calm day still forced into match detail | `CALM + DAY_SUMMARY` | `reference/calm.png` |
| Empty day could imply data failure or borrow another date | `EMPTY + EMPTY_STATE`, explicit adjacent dates only | `reference/empty.png` |
| Stale evidence hidden or presented as current | visible Market Memory plus comparison paused | `reference/stale.png` |
| Many equal-weight panels and repeated governance | primary shortlist/focus; one read-only pill and one system-status entry | all approved references |
| Same-render screenshot did not prove fidelity | stored Owner targets plus Playwright image diff | `targets/` and V41 visual tests |
| CSS remediation layers conflicted | production CSS will be comprehensively replaced | V41-2 acceptance |
| 13-inch layout required nested scrolling | natural-flow 1180 composition | `reference/responsive-1180.png` |
| Normal day conflicted with raw blocked system health | one public day mode plus separately scoped system degradation | `targets/d16-postdeploy-1366x768.png` |
| Non-priority incomplete data inflated priority counts | exact eligible-reason contract plus separate other-attention group | D16 deployed-shape contract and visual tests |
| First-match focus ignored evidence usefulness | deterministic usable-evidence ranking, stale memory ahead of zero evidence | D16 deployed-shape contract and visual tests |
| Raw reason and risk codes dominated public copy | explicit `主因`/`次因` and Chinese-first risk explanations | `targets/d16-postdeploy-1512x982.png` |
| Focus panel owned a nested desktop scrollbar | one natural page scroll at all supported desktop targets | D16 scroll-ownership and 200% zoom tests |
| Quality checkpoint state was temporally incoherent | exact AVAILABLE/STALE/INCOMPLETE/NOT_AVAILABLE fail-closed state machine | D16 four-state contract tests |

Reference assets are self-contained and contain no remote resources, credentials, production payloads, or Provider calls. Prototype CSS remains reference-only and is not production architecture.
