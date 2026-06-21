# W2 Identity and Time Policy V1

## Identity

All internal records use UUIDs. Provider JSON aliases, raw payload labels, and
external IDs are never the primary identity system.

Provider mapping must include:

- provider
- external_id
- source
- confidence
- valid_from
- valid_to

The provider mapping unique key is provider, entity type, external ID, and
valid_from. This supports external identity changes without mutating internal
UUIDs.

## Time

All business datetimes must be timezone-aware and normalized to UTC.

Required meanings:

- `event_time`: when the described match or domain event happened.
- `provider_updated_at`: when a provider says its object changed.
- `ingested_at`: when W2 captured or accepted the provider object.
- `as_of_time`: the pre-match knowledge boundary for features and predictions.
- `confirmed_at`: when a fact such as lineup or result was confirmed.

File mtime is not a business time source.

