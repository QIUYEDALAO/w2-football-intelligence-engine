# W1 Migration Validation Policy V1

Migration decisions are restricted to:

- READY_FOR_TRANSFORM
- AUDIT_ONLY
- QUARANTINE
- REJECT
- MANUAL_REVIEW_REQUIRED

Validation rules:

- Raw odds are preferred for transform when source hash and provenance exist.
- Results must remain physically separate from pre-match data.
- W1 model-derived fields are audit-only until W2 validates an independent use.
- W1 AI/SCOUT output cannot be used as a training label.
- Fixture aliases and provider IDs must be revalidated.
- Unknown schema, unclear provenance, or leakage risk enters quarantine.
- Records are never silently dropped.

Dry-run rules:

- W1 is read-only.
- W2 production database is untouched.
- Temporary load uses memory, temporary directories, or temporary test databases.
- Dry-run keeps statistics and hashes, not business data copies.
- Repeated dry-runs must produce deterministic hashes.

Rollback metadata required before any future formal migration:

- batch ID
- source hash
- transform version
- target row IDs
- verification result
- rollback eligibility
