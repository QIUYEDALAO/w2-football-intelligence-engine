# W2 AH Display Incident · 2026-07-04

## Scope

This incident note records the July 4 matchday AH display failures that were caught before lock or settlement. It is intentionally diagnostic only. The A-146 hotfix blocks non-FORMAL AH recommendation display. Selector consolidation and canonical AH refactoring remain assigned to A-150.

## Naming Ledger

- A task IDs are the canonical audit and communication identifiers.
- GitHub PR numbers are link references only, because they can drift from task IDs.
- GitHub PR #147 corresponds to A-148.
- GitHub PR #148 corresponds to A-149.
- The canonical AH consolidation follow-up that was previously discussed as "#147" is now A-150.

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

### Argentina vs Cape Verde Islands

- Fixture: `1565179`
- Audit trigger: the page showed a match-level as-of around `01:12` CST while the AH mainline still looked surprising to manual review.
- Read-only audit target: `2026-07-03T17:12:00Z` (`01:12` CST).
- Latest AH observation bucket at or before that target: `2026-07-03T13:04:55Z`, not `17:12Z`.
- Provider row freshness in that bucket: `provider_last_update=2026-07-03T08:04:17Z`.
- Selector replay at `01:12` CST chose `Argentina -2.5`, with selector candidate ranks:
  - rank 1: `-2.5`, valid-pair bookmaker_count `7`
  - rank 2: `-2.25`, valid-pair bookmaker_count `6`
  - rank 3: `-2`, valid-pair bookmaker_count `5`
  - rank 4: `-1`, valid-pair bookmaker_count `4`
- Controlled refresh later ran around `2026-07-03T17:22Z` and did fetch/persist an odds raw payload for fixture `1565179`.
- Selector replay after that refresh still chose `Argentina -2.5`, with the same top-line ordering pattern: `-2.5` count `7`, `-2.25` count `6`, `-2` count `5`, `-1` count `4`.
- The raw/API data did contain `-2` and `-2.25` line families. The `-1` family also existed; in selector replay its valid-pair candidate came from bookmaker ids `1`, `32`, `36`, and `5` in the inspected bucket.
- Root classification: not confirmed as a selector tie-break defect from the stored data alone. It is confirmed as an as-of clarity issue plus a canonical AH confidence issue: the page-level as-of can be newer than the AH row data, and the selector currently has no independent cross-market sanity check before exposing the mainline.
- A-150 evidence: freeze this fixture as a stale-as-of / cross-market-confidence specimen only after the canonical AH module defines the ground-truth expected line from raw AH plus 1X2. Do not hard-code a corrected mainline expectation before that ground truth is defined.

## Why the 01:12 Mainline Stayed Pick'em

The read-model current AH snapshot still selected the pick'em family because the available read-model ladder had stronger bookmaker consensus on `0` than on the alternate `+0.25` family. The controlled refresh later showed richer raw odds, but this A-146 hotfix does not change selector or materialization behavior. That follow-up belongs to A-150, where canonical AH sign, mainline selection, and display will be consolidated behind one module and one outlet.

## A-150 Scope Evidence

- Canonical AH must be the single outlet for AH sign, mainline selection, and display.
- A-150 must include the Colombia, Australia/Egypt, and Argentina/Cape Verde specimens as separate regression shapes.
- A-150 must add cross-market consistency checking: if a 1X2-derived approximate handicap line and the selected AH mainline differ by more than `0.75`, emit `AH_MAINLINE_CROSS_MARKET_CONFLICT` and downgrade the market state to not ready.
- If the page mainline differs from manual market review by at least `0.75` goals, operational default is that our read-model is suspect until the audit proves otherwise.
- Dashboard/report surfaces must distinguish page/report generation as-of from row-level AH `captured_at` and provider row `provider_last_update`.
- Every displayed or guarded number must carry its own source and basis. Page as-of, market-line type, and provider quota are separate measurements; cross-checks must compare same-basis values only, not mix inferred limits with provider headers.

## A-146 Contract

- `ANALYSIS_PICK` and `WATCH` recommendation payloads must not carry AH `selection`, `line`, `odds`, or direction-bearing free text.
- FORMAL payloads that fail validation may keep raw direction fields only inside diagnostic table cells marked `INVALID`.
- Cards, text, markdown, static HTML, and oral report output must not emit an actionable AH direction unless the match is valid FORMAL.
- No FORMAL gate, EV threshold, AH selector, lock, settlement, provider, or production behavior is changed by #146.
