# W2 canonical serialization compatibility, migration and rollback

## Compatibility policy

1. A record with `serializer_version` is verified only with that version.
2. A historical record without the field is interpreted as
   `w2.canonical-json.v1` only. The reader never guesses v2 after a v1 mismatch.
3. Existing future-refresh, ledger, Stage7I and read-model writers route through
   the sole authority using explicit v1 domain profiles, so their current
   persisted bytes and hashes do not change in this tranche.
4. EVAL-02B exact pair projection emits
   `serializer_version=w2.canonical-json.v2`. Bootstrap seed input uses the same
   version and its own named domain.

## Append-only migration

For a domain whose storage schema is later approved for v2:

1. Add nullable `serializer_version_v2` and `sha256_v2` fields or an immutable
   versioned sidecar keyed by the original record identity.
2. Verify the historical digest under its declared/implicit v1 profile.
3. Compute v2 from the original business payload and append the v2 digest and
   version. Do not update or delete the historical digest.
4. Dual-read by declared version. Dual-verify during backfill and reconcile
   artifact, ledger, projection and pair counts before switching a reader.
5. Stop on any missing source payload, v1 mismatch, ambiguous version or
   domain mismatch. Such a row is not backfilled.

`prepare_hash_migration` models this operation as immutable historical and
replacement `VersionedDigest` values. Tests require the input and old digest to
remain unchanged.

## Rollback

Rollback switches the read pointer to the preserved v1 digest/field or removes
only the new sidecar row. It does not recompute v1, copy v2 over v1, rewrite an
artifact, or change the business payload. `HashMigration.rollback()` returns
the exact verified historical reference.

```text
HISTORICAL_HASH_OVERWRITE = FORBIDDEN
DUAL_READ_GUESSES_VERSION = false
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_PROVIDER = OFF
REAL_CANARY = NOT_AUTHORIZED
PERSISTENT_SCHEDULER = OFF
```

The independent oracle/golden vector author must use
`docs/contracts/w2_canonical_serialization_oracle_vectors_v1.schema.json` and
must not import the production serializer. The implementer-provided harness
only compares that external output with production behavior.

