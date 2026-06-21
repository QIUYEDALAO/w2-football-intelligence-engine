# W1 to W2 Mapping V1

Stage 12A maps W1 assets into W2 target layers without executing a production
migration.

| W1 domain | W2 target | Default decision |
| --- | --- | --- |
| competition / season / fixture | NORMALIZED Competition, Season, Fixture | MANUAL_REVIEW_REQUIRED |
| team / player / provider mapping | NORMALIZED Team, Player, ProviderEntityMapping | MANUAL_REVIEW_REQUIRED |
| raw odds payload | RAW RawPayloadReference | READY_FOR_TRANSFORM |
| bookmaker odds snapshots | NORMALIZED OddsObservation | READY_FOR_TRANSFORM |
| match cards | quarantine/manual review | QUARANTINE |
| lineups / injuries | NORMALIZED Lineup, Injury | MANUAL_REVIEW_REQUIRED |
| weather / venue | NORMALIZED WeatherObservation, Venue | MANUAL_REVIEW_REQUIRED |
| results | NORMALIZED Result | MANUAL_REVIEW_REQUIRED |
| Forward Ledger | audit evidence | AUDIT_ONLY |
| W1 model outputs | audit evidence | AUDIT_ONLY |
| W1 AI/SCOUT outputs | audit evidence | AUDIT_ONLY |
| recommendation/audit records | audit evidence | AUDIT_ONLY |

Each source asset records `source_system=W1`, original path, schema version,
source SHA256, W1 HEAD, provenance quality, target layer, transform version,
migration eligibility, validation status, and record count.

Transform contracts require source fields, target fields, ID mapping, UTC time
normalization, Decimal conversion, null policy, deduplication key, provenance,
validation rules, and rollback metadata. Complete W1 match cards are never used
as W2 schema objects.
