# Dashboard V4.1 Design Specification

```text
AUTHORITY = W2_DASHBOARD_V41_OWNER_APPROVED_REFERENCE
BASE_MAIN = d2740a573c748cfaef38c66e951618e8782e09d0
PUBLIC_ENDPOINT = GET /v1/dashboard/intelligence-workspace
PUBLIC_SCHEMA = w2.dashboard-intelligence-workspace.v1
PRODUCT_ROLE = FOOTBALL_INTELLIGENCE_REVIEW_NOT_RECOMMENDATION
```

## Frozen hierarchy

The first screen has four levels only:

1. **L1 Today Summary** — football day, match and priority totals, source-bound evidence summary, one immutable/read-only indicator, and one system-status link.
2. **L2 Priority Shortlist** — three to six matches or grouped incidents ordered by information usefulness. Every entry states its primary reason; secondary reasons do not increase L1 counts.
3. **L3 Primary Focus** — exactly one of Match, Global Incident, Day Summary, or Empty State, selected by the backend contract.
4. **L4 Global Model Quality** — compact checkpoint-backed LogLoss/Brier/ECE/sample evidence. Missing or stale checkpoints fail closed.

Validation detail, league/tournament performance, replay, external intelligence and data operations remain available as secondary destinations. Empty external-intelligence cards never occupy the first screen.

## Visual system

- Background `#0B1013`; rail `#0E151A`; panels `#131A1F`; selected surface `#17222A`.
- Primary text `#E6EDF0`; secondary `#9DAEB6`; accent `#5BA8BE`; warning `#CBA05A`; incident `#D07A6F`; nominal `#6FA687`.
- Compact square controls and restrained borders; no rounded consumer-card styling, gradients, or decorative imagery.
- Football conclusions outrank technical codes. Technical/audit content remains in secondary links or disclosure controls.
- Primary body text is at least 13 CSS px, secondary explanation at least 12 CSS px, and visible technical text at least 11 CSS px.
- Normal text contrast is at least 4.5:1. All keyboard-operable controls have a visible focus state.

## Responsive behavior

- `>=1201px`: L2 is a 360px shortlist rail and L3 is the flexible primary workspace. L4 stays at the bottom of the viewport when content permits.
- `<=1200px`: natural document flow; shortlist rows precede the primary focus; secondary grouped attention collapses to one summary affordance; the match focus stacks market evidence before meaning/diagnostics.
- No horizontal page overflow. At 200% zoom, primary actions and data remain in natural flow. No nested scroll is required for primary content at or below 1200px.

## Match focus truth rules

- The focus comes from `selected_fixture_id`; neither backend nor frontend may use the first array element as policy.
- AH and OU show only persisted observations. A single snapshot may support same-time cross-sectional comparison but never a trend claim.
- STALE market memory remains visible, labels its age and threshold, and pauses model comparison authority.
- Model status and explanation are a single source reused in every visible model surface.
- Risk explanations are dimension-specific and source-bound.
- Scoreline Top 3 appears only when model and identity readiness are proven and `simulations_completed` is exactly 10,000. It renders `unconditional_probability` and `sample_count`; no simulation occurs on read.

## Forbidden public semantics

No opportunity, value, edge, expected profit, ROI, CLV, bookmaker intent, real-volume, or betting-worthiness claims. Candidate, Formal, Lock and Production remain OFF. External intelligence remains NOT_CONNECTED and cannot affect match readiness.

## Stored targets

The `reference/` directory holds the exact Owner-approved editable HTML and PNG files. `targets/` contains deterministic Chromium renders at 1280x720, 1366x768, 1512x982, 1536x1024 and the 1180 responsive viewport. `DESIGN_REFERENCE_SHA256SUMS.txt` is the immutable integrity manifest.
