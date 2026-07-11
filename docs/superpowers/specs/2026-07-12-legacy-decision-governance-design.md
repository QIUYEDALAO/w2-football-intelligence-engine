# Legacy Decision Governance Design

## Scope

Protect Decision Contract V2 from legacy decision-field backflow without
deleting historical snapshots, migration readers, or compatibility adapters.
This PR does not change recommendation thresholds, three-track semantics,
provider behavior, deployment, or production settings.

## Design

- A JSON allowlist names every source file permitted to read the legacy
  `candidate` or `formal_recommendation` fields and records why the exception
  exists.
- A syntax-aware checker discovers Python and TypeScript reads. New readers
  fail CI unless they are explicitly categorized as a compatibility shim,
  migration, or historical reader.
- Decision, pick, L1, forward ledger, and policy modules are authoritative
  paths and cannot be allowlisted.
- Old documents remain available but carry an explicit `SUPERSEDED` marker and
  link to Decision Contract V2.
- The offline acceptance fixture describes lineup as advisory; its WATCH card
  is blocked by the missing fair-market estimate instead of by lineup status.

## Verification

Run the checker directly and through CI. Contract tests prove the existing
legacy shim remains read-only, authoritative paths remain legacy-free, and the
latest offline Dashboard fixture no longer presents lineup absence as the
primary blocker.
