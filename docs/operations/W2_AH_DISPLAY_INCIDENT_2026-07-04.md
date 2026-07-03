# W2 AH Display Incident · 2026-07-04

## Scope

This incident note records the July 4 matchday AH display failures that were caught before lock or settlement. It is intentionally diagnostic only. The #146 hotfix blocks non-FORMAL AH recommendation display. Selector consolidation and canonical AH refactoring remain assigned to #147.

## Specimens

### Colombia vs Ghana

- Fixture: `1567310`
- Symptom: a low-consensus balanced deep line family (`-2.5`) appeared ahead of the four-bookmaker consensus family (`-1.25`) before the #143/#144 hotfixes.
- Permanent regression: `tests/unit/test_market_timeline_snapshots.py::test_ah_mainline_consensus_prefers_four_books_over_balanced_two_book_deep_line`
- Expected selector behavior: choose the `-1.25` family by bookmaker consensus first, then use price balance only as a tie-breaker.
- Runtime expectation: after the mainline correction, Colombia can still remain WATCH if EV or fair-market sanity gates block it. That is the intended result.

### Australia vs Egypt

- Fixture: `1567306`
- Symptom: non-FORMAL UI text displayed an AH direction as `客队方向 0.25`, which can be read as Egypt receiving a quarter goal.
- Raw provider specimen: API-Football produced same-bookmaker paired values such as `Home +0.25` and `Away +0.25`.
- Ground-truth interpretation: within the same bookmaker and same line family, those two values are paired sides of the same handicap. The canonical home line is `+0.25`; the away side is therefore `-0.25`. In Chinese AH display this means Egypt gives a quarter goal, not Egypt receives a quarter goal.
- Permanent regression: `tests/unit/test_dashboard_recommendation_loop.py::test_egypt_api_football_away_plus_quarter_is_canonical_away_favorite`

## Why the 01:12 Mainline Stayed Pick'em

The read-model current AH snapshot still selected the pick'em family because the available read-model ladder had stronger bookmaker consensus on `0` than on the alternate `+0.25` family. The controlled refresh later showed richer raw odds, but this #146 hotfix does not change selector or materialization behavior. That follow-up belongs to #147, where canonical AH sign, mainline selection, and display will be consolidated behind one module and one outlet.

## #146 Contract

- `ANALYSIS_PICK` and `WATCH` recommendation payloads must not carry AH `selection`, `line`, `odds`, or direction-bearing free text.
- FORMAL payloads that fail validation may keep raw direction fields only inside diagnostic table cells marked `INVALID`.
- Cards, text, markdown, static HTML, and oral report output must not emit an actionable AH direction unless the match is valid FORMAL.
- No FORMAL gate, EV threshold, AH selector, lock, settlement, provider, or production behavior is changed by #146.
