# W2 Historical Source Registry V1

The source registry records candidate historical providers before import.

Required fields include:

- source/provider identity
- national or club scope
- competitions, seasons, date range
- fixtures, results, 1X2, AH, OU, lineup, and injury coverage
- opening, first_seen, closing capability
- snapshot frequency
- provider IDs
- provenance
- licence and commercial-use status
- acquisition status
- validation status

Allowed statuses:

- `UNVERIFIED`
- `AVAILABLE`
- `PARTIAL`
- `BLOCKED`
- `NOT_SELECTED`

W1 baseline, classification, and decision-register files may be audited as
candidate assets, but Stage 5A does not copy, migrate, or treat them as W2
runtime data.
