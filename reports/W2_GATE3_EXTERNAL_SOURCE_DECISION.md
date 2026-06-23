# W2 Gate3 External Historical Odds Source Decision

Generated at: 2026-06-24

Status: USER_DECISION_REQUIRED

candidate=false

formal_recommendation=false

## Boundary

This report uses only public provider websites, public documentation, and public schema descriptions. No provider was contacted, no account or trial was created, no paid plan was started, no commercial click-through terms were accepted, no provider API was called, and no non-public data was downloaded.

## Why Internal Data Cannot Close Gate3

The previous Gate3 historical market evidence build found useful captured-at market observations, but it did not find usable settled internal historical AH data. Current internal evidence supports:

- 1X2 aggregate/closing-like market baselines with known semantic limits.
- OU closing-subset baseline work.
- Forward captured-at market collection.

It does not yet support:

- Settled historical AH walk-forward evaluation.
- Phase-specific captured-at backtests across T-72h through Closing.
- Multi-season bookmaker-level AH/OU historical timeline replay with verified result settlement.

Gate3 therefore remains PARTIAL.

## Minimum Qualified Data Source

A qualified Gate3 source must satisfy `docs/data/W2_HISTORICAL_MARKET_SOURCE_REQUIREMENTS_V1.md`. The minimum source is bookmaker-level and must include provider fixture IDs, competition/season, kickoff UTC, home/away identity, 1X2/AH/OU markets, raw market labels, canonical selections, AH/OU lines including quarter lines, decimal odds, live/suspended flags, provider event time, captured-at time, ingested-at time, opening/closing semantics, fixture mapping evidence, final result, settlement semantics, source license, and raw payload hashes.

Aggregate-only or closing-only data is not enough for early phase market backtests.

## Public Candidate Review

| Provider | Public Evidence | Fit | Main Blocker |
| --- | --- | --- | --- |
| The Odds API | Historical snapshot endpoint, bookmaker odds, paid historical plans, public sample links. Official docs: https://the-odds-api.com/historical-odds-data/ and https://the-odds-api.com/liveapi/guides/v4/ | Best public schema-fit trial candidate | Paid plan and license review required; soccer AH/OU national-team coverage must be verified |
| TheStatsAPI | Football-specific odds from Bet365/Pinnacle/Betfair/Kambi, 1X2/AH/totals/BTTS, fixtures/results, commercial paid plans. Official page: https://www.thestatsapi.com/ | Best football-specific alternative trial candidate | Public sample unavailable; historical odds timeline depth and retention terms need review |
| OpticOdds | 100+ sportsbooks, fixtures, snapshots, results, grading, full price history claimed. Official docs: https://developer.opticodds.com/docs/odds-api-getting-started-guide | Potential trial candidate | Historical start date, soccer AH/OU coverage, and license terms unknown publicly |
| SportsDataIO | Historical odds, opening/closing/all price changes, API/S3/custom delivery. Official pages: https://sportsdata.io/live-odds-api and https://sportsdata.io/historical-odds | Reference candidate | Soccer/national-team scope and public schema unclear; contact required |
| OddsJam | Historical odds feed with opening/closing/live line changes across markets. Official page: https://oddsjam.com/odds-api | Reference candidate | Contact required; public schema unavailable |
| Betfair Historical Data | Time-stamped exchange price data and settlements. Official pages: https://developer.betfair.com/historical-data-services-api/ and https://betfair-datascientists.github.io/data/usingHistoricDataSite/ | Reference-only for exchange research | Not a bookmaker panel; account/purchase flow required |
| API-Football / API-Sports | Existing W2 provider with pre-match/live odds and broad football coverage. Official pages: https://www.api-football.com/ and https://api-sports.io/ | Forward-only supplement | Existing internal evidence did not close historical AH walk-forward |

## Public Sample Compatibility

The Odds API has public historical endpoint examples and response links. W2 added a synthetic schema fixture shaped from the public documentation to test the probe path, but this is not acquired historical data and is not part of the Gate3 dataset.

Sources without publicly accessible samples are marked `PUBLIC_SAMPLE_UNAVAILABLE`; W2 does not infer compatibility from marketing text alone.

## Route A: Licensed External Historical Source

Expected benefit:

- Fastest route to解除 Gate3 historical AH blocker.
- Can provide settled bookmaker-level chronological data if the provider proves all MUST fields.

Risks:

- Requires user approval for trial, purchase, or provider contact.
- Requires license and retention review.
- Requires schema/sample verification before data enters W2.
- May require fixture/team/bookmaker mapping work.

Minimum user approvals before action:

- Approve the provider to contact or trial.
- Approve account/key handling.
- Approve license/terms review.
- Approve spending or confirm no-cost trial terms.

## Route B: W2 Forward-Only Accumulation

Expected benefit:

- No new procurement or terms risk.
- Uses W2 append-only market ledger and existing API-Football capture.

Limit:

- Does not quickly create multi-year historical walk-forward evidence.
- Gate3 remains PARTIAL for a long time.
- Cannot satisfy historical AH baseline/backtest without waiting for enough settled forward samples.

## Current Trial Candidate

The Odds API is the most suitable first schema/coverage trial candidate because public documentation provides historical snapshot semantics, bookmaker odds, dated snapshots, and public response examples. This is not purchase approval.

TheStatsAPI is the strongest football-specific alternative because public material lists 1X2, Asian handicap, totals, BTTS, fixtures, results, and named books. It needs public or approved sample verification before becoming a stronger recommendation.

## Current Decision

USER_DECISION_REQUIRED

W2 does not choose Route A or Route B in this report. The user must choose one of:

1. Approve a specific provider trial/procurement evaluation.
2. Select forward-only accumulation and accept that Gate3 remains PARTIAL.
3. Explicitly approve a master roadmap scope change for Gate3.

## Gate Status

Gate3 remains PARTIAL.

Gate4 remains OPEN.

Gate5 remains OPEN.

Gate6 remains NOT_READY.
