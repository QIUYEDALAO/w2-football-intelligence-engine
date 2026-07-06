# W2 Squad Value Source Requirements

## Purpose

League whitelist enablement requires a squad value or approved squad-strength
mapping source. The current remediation stage does not provide that source and
therefore must keep `squad_value=CANNOT_VERIFY` with blocker
`SQUAD_VALUE_SOURCE_MISSING`.

## Required Properties

An approved source must define:

- source ownership and licensing constraints
- refresh cadence
- stale-data policy
- team identity mapping to W2 competition/team ids
- coverage report by competition
- reproducible export format
- no raw licensed payload committed to git

## Audit Contract

The whitelist audit may pass `squad_value` only when:

- the source is documented
- every enabled candidate team maps deterministically
- stale or missing values are explicit blockers
- generated reports contain only sanitized coverage metadata

Until then, no league may flip to `enabled=true`.
