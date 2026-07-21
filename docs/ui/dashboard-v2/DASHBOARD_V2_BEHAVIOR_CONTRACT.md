# W2 Dashboard V2 Behavior Contract

## Authority

The approved reference component, stylesheet, fixed visual fixture, and golden screenshots are the authority. Production code may adapt data but must not reinterpret the layout.

## Desktop behavior

- The dashboard workspace has a viewport-relative stable height.
- The left schedule panel scrolls internally.
- The filter bar, table header, and date headers remain sticky inside the schedule panel.
- The right evidence rail remains visible and has its own bounded scroll when required.
- All fixtures remain in the DOM and are reachable. No `slice`, `nth-child` hiding, top-N cap, or collapsed-row removal is allowed.
- A 15-fixture fixture must show `15 / 15 场` and the final row must be reachable by scrolling.

## Mobile behavior

- At widths below 900 px, nested viewport scrolling is disabled.
- The page uses normal document scrolling.
- All fixtures remain accessible.
- The evidence rail appears after the schedule.

## Selection behavior

- Clicking a row changes only the selected-match evidence rail.
- The selected row remains highlighted.
- The scoreline panel displays exactly the backend `scoreline_projection`; the frontend may not infer or alter the score order.

## Time behavior

- All dates and times use `Asia/Shanghai`.
- Matches more than 24 hours away show absolute date and weekday as primary information.
- Relative time is secondary.
- A client clock updates once per minute without requiring an API refresh.

## Scoreline behavior

- `ANALYSIS_PICK` displays a scoreline panel only when `scoreline_projection.status=READY`.
- The panel states `10,000 次模拟` and shows sample-count-derived probabilities.
- The panel shows the exact primary/secondary market consistency label.
- `NO_EDGE`, `NOT_READY`, `WATCH`, and `SKIP` do not show recommendation scorelines.

## Unified ledger behavior

The public accounting is one ledger:

- validation total
- settled
- pending
- eligible
- evidence repair pending
- hit/miss/push/void
- decisive denominator
- hit rate
- CLV sample count

Do not expose a separate historical-restoration performance cohort.
