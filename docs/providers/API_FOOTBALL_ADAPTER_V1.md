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

