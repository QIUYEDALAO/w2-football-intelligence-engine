# API-Football Adapter V1

Supported endpoint adapter names:

- fixtures
- teams
- standings
- odds
- lineups
- injuries
- squads
- fixture_detail
- results
- events
- statistics

The adapter is independent of live network execution. `ApiFootballClient.fetch`
raises unless live execution is explicitly approved in a later checkpoint. Stage
4A only parses offline fixtures.

Rules:

- Only W2 environment names may be used, such as `W2_API_FOOTBALL_API_KEY`.
- W1 and legacy `.env` files must not be read.
- Raw payloads are stored append-only with SHA256.
- Bookmakers are preserved one by one.
- Writes do not aggregate, de-juice, model, recommend, or call AI.
- Pre-match odds captured after kickoff are rejected.
- `first_seen_odds` is distinct from `opening_odds`; Stage 4A does not infer
  opening prices.

## Free-plan fixture scope restriction

- Seed evidence is exact on `(league, season)` and never applies to `id` or
  `fixture` requests.
- Every dispatched league-and-season `fixtures` response is appended to
  `free_plan_fixture_scope_observations` with its timestamp and payload hash.
- Three consecutive responses containing the exact Provider season-access error
  confirm the runtime restriction. The third response reports
  `FREE_PLAN_RESTRICTION_AUTO_DETECTED`; later identical scope requests report
  `SKIPPED_FREE_PLAN_RESTRICTED` without dispatch.
- A non-restricted response resets the consecutive sequence. Runtime observations
  take precedence over seeds.
- Restrictions never cross a season boundary. A previously unseen season is
  probed and can make at most three restricted observations before short-circuiting.
