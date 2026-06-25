# W2 Transfermarkt Dataset Provenance

Status: accepted for WO#13 implementation; final external-data compliance
position remains a user/legal decision.

## Source

W2 consumes `dcaribou/transfermarkt-datasets`, a public GitHub dataset with CSV,
DuckDB, Kaggle, and data.world distribution paths. The upstream README describes
the dataset as automatically updated and refreshed weekly.

Used tables:

- `players.csv.gz`: current player club and current market value.
- `player_valuations.csv.gz`: historical player market-value records.

W2 derives club/team value by summing player market values by Transfermarkt club
id and valuation date. The derived records are append-only and carry raw path,
schema version, ingest timestamp, and sha256 checksum.

Observed public-source coverage on 2026-06-25:

- `player_valuations.csv.gz`: 656,301 rows.
- Transfermarkt club ids in valuation history: 5,426.
- Valuation years present: 2000 through 2026.

W2 coverage is lower until explicit Transfermarkt club to W2 team mappings are
loaded.

## License And Terms Note

The dataset repository license is CC0-1.0. That is favorable for reuse of the
published dataset artifacts.

The underlying facts originate from Transfermarkt. Transfermarkt terms and site
controls may constrain automated extraction or republication. W2 therefore does
not scrape Transfermarkt directly in this package. It syncs only the public
dataset artifacts, records provenance, and keeps this source behind explicit
audit metadata. Production/commercial usage should be reviewed by the user/legal
owner before relying on this source externally.

## Mapping Discipline

Transfermarkt club ids are mapped to W2 team ids through an explicit mapping
table with confidence, source, validity window, and notes. W2 does not invent
team value when a mapping is absent. Unmapped teams are reported as
`VALUE_DATA_UNAVAILABLE`.

## Leakage Policy

Analysis cards must use the latest value observation whose `valid_from` is less
than or equal to the card `as_of` timestamp. Future valuations are blocked and
must never be used for earlier matches.

## Refresh Cadence

The scheduler queues `w2.transfermarkt_team_value_sync` every 604800 seconds
(weekly) by default, matching the upstream README cadence. Operators may disable
the sync with `W2_TRANSFERMARKT_TEAM_VALUE_SYNC_ENABLED=false` or override the
interval with `W2_TRANSFERMARKT_TEAM_VALUE_SYNC_INTERVAL_SECONDS`.
