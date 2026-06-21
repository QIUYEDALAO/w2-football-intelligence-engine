# ADR-0015: W1 Migration Dry-Run and Shadow Foundation

Status: Accepted for Stage 12A.

## Context

W2 needs a controlled path to understand W1 assets before any migration or
Shadow operation. W1 contains frozen outputs, historical artifacts, runtime
reports, model-derived values, SCOUT/AI output, and audit records. These assets
have different provenance and leakage risk, so Stage 12A establishes inventory,
contracts, quarantine, dry-run validation, and read-only Shadow comparison.

## Decision

Stage 12A introduces a W1 source inventory, transform contracts, a deterministic
dry-run engine, a quarantine registry, and a Shadow comparison engine. It reads
W1 only as frozen files, records hashes and provenance, and does not import W1
runtime code. Dry-run output may use memory, temporary directories, and temporary
test databases only. Formal migration, production database writes, and live
Shadow Runs remain disabled pending approval.

W1 model-derived fields are audit-only. W1 AI/SCOUT output cannot become a
training label. Match cards are not copied as W2 schemas. Fixture aliases and
provider mappings require revalidation. Unknown schema or possible leakage goes
to quarantine.

## Consequences

W2 can now inspect what could be migrated without moving production data. Shadow
comparison can compare W1 frozen samples and W2 archived outputs for identity,
odds freshness, market probability, OU μ, λ values, data completeness, and
runtime availability. Strategy comparison remains `NOT_AVAILABLE_GATE4` while
Stage 9 is blocked and Gate 4 is pending.
