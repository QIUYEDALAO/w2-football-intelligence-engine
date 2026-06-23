# W2 Historical Market Source Requirements V1

Status: ACTIVE
Gate: 3
Scope: external or approved internal historical market source evaluation

This contract defines the minimum data evidence required before W2 can close Gate3 for market baselines. It does not approve purchase, trial signup, provider contact, account creation, or commercial terms.

## Decision Boundary

Gate3 requires bookmaker-level, chronologically reconstructable historical market data that can support fixture-level walk-forward evaluation. Public documentation may identify trial candidates, but only an approved acquisition or trial can satisfy license and delivery proof.

Closing-only or aggregate historical odds can support limited closing/aggregate baselines. They cannot be relabeled as early phase captured-at evidence.

## Requirement Classes

MUST requirements are mandatory for Gate3 closure. SHOULD requirements materially reduce integration and audit risk. OPTIONAL requirements are useful but not blocking. DISQUALIFYING items reject a source for Gate3 closure until remediated.

## MUST

- `provider`: stable source identifier.
- `provider_fixture_id`: stable event identifier from the source.
- `competition`: competition or league identity.
- `season`: season identity.
- `kickoff_utc`: scheduled kickoff in UTC.
- `home_team_identity` and `away_team_identity`: source team identities plus original names.
- `bookmaker`: bookmaker identity for each quote; aggregate-only averages are insufficient.
- `market`: at least `1X2`, `ASIAN_HANDICAP`, and `TOTALS`.
- `raw_market_label`: source market text retained for audit.
- `canonical_selection`: normalized selection such as home, draw, away, over, under, or handicap side.
- `ah_ou_line`: exact handicap or total line, including quarter lines.
- `decimal_odds`: odds normalized to decimal while retaining raw odds format where available.
- `suspended`: whether the quote was suspended.
- `live`: whether the quote was live/in-play.
- `provider_event_time`: source event update time when exposed.
- `captured_at`: true provider snapshot time or verified collection time.
- `ingested_at`: W2 ingestion time.
- `opening_closing_semantics`: explicit opening/closing marker or documented derivation source.
- `stable_event_id`: event identity stable across markets and exports.
- `fixture_mapping_evidence`: evidence for mapping provider event/team/bookmaker IDs to W2 IDs.
- `final_result`: final 90-minute result or a linkable result source that W2 can verify.
- `settlement_semantics`: settlement rules sufficient for 1X2, AH quarter lines, and OU quarter lines.
- `source_license`: documented license or contract allowing W2 internal analysis, long-term retention, and model backtesting.
- `source_payload_hash`: SHA256 or reconstructable raw payload hash.

## SHOULD

- Bulk export or batch API that supports fixture-level chronological rebuilds without per-fixture scraping.
- Multi-season club coverage for the top five leagues.
- National team competition coverage, including World Cup, qualifiers, continental tournaments, Nations League, and friendlies where available.
- Bookmaker coverage including at least one sharp/global bookmaker and several recreational books.
- Snapshot cadence sufficient for T-72h, T-48h, T-24h, T-12h, T-6h, T-3h, T-1h, T-30m, T-10m, and closing analysis.
- Explicit opening, intermediate, and closing snapshots rather than only final prices.
- Raw export replay that preserves duplicate/conflicting quote evidence.
- Public schema or sample allowing W2 to validate mapping before commercial approval.
- API or export metadata that includes quota/cost accounting and rate limits.

## OPTIONAL

- BTTS, draw-no-bet, team totals, corners, and player markets.
- Exchange traded volume and liquidity.
- Provider-side bet grading.
- Venue, referee, lineup, injury, and weather joins.
- S3 or object-store delivery.
- Signed manifests or provider checksums.

## DISQUALIFYING

- Aggregate-only odds without bookmaker-level quotes.
- Closing-only data offered as the only historical timeline for early phase backtests.
- Missing captured-at or provider snapshot time.
- Missing AH/OU lines or inability to represent quarter lines.
- Missing final result or settlement linkage.
- License unknown or license forbids retention, internal analysis, or model backtesting.
- Requires scraping, reverse engineering, or use of non-public/unclear-license data.
- Requires accepting terms, creating an account, paying, or contacting a provider before W2 can even verify basic rights; such sources may be trial candidates only, not approved data.
- Data cannot be hashed, replayed, or audited from raw source payloads.

## Gate3 Closure Rule

Gate3 cannot close until a source satisfies all MUST requirements with approved license evidence and W2 has completed a settled chronological or walk-forward backtest for 1X2, AH, and OU without closing leakage.
