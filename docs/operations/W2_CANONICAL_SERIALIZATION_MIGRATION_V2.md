# W2 canonical serialization compatibility, migration and rollback

## Compatibility policy

1. A record with `serializer_version` is verified only with that version.
2. A historical record without the field is interpreted as
   `w2.canonical-json.v1` only. The reader never guesses v2 after a v1 mismatch.
   The guard-only identifier `w2.legacy-implicit-json.v1` is stored as
   `legacy_profile_id`; it is not accepted or persisted as `serializer_version`.
3. Existing future-refresh, ledger, Stage7I and read-model writers route through
   the sole authority using explicit v1 domain profiles, so their current
   persisted bytes and hashes do not change in this tranche.
4. EVAL-02B exact pair projection emits
   `schema_version=w2.eval_02b_exact_pair_projection.v2`,
   `serializer_version=w2.canonical-json.v2`, and the pair hash domain as
   separate metadata. Bootstrap seed input uses the same serializer version and
   its own named domain.
5. `HASH_DOMAIN_IN_PREIMAGE=false` and
   `SERIALIZER_VERSION_IN_PREIMAGE=false`. Domain and version are required
   metadata; the digest value by itself does not prove either one.

## Append-only migration

For a domain whose storage schema is later approved for v2:

1. Add nullable `serializer_version_v2` and `sha256_v2` fields or an immutable
   versioned sidecar keyed by the original record identity.
2. Load the historical digest together with its actual stored domain and
   serializer-version metadata. Verify those metadata values before reading the
   preimage; a mismatch fails closed with `HISTORICAL_METADATA_MISMATCH`.
3. Verify the historical digest under its declared/implicit v1 profile.
4. Compute v2 from the original business payload and append the v2 digest and
   version. Do not update or delete the historical digest.
5. Dual-read by declared version. Dual-verify during backfill and reconcile
   artifact, ledger, projection and pair counts before switching a reader.
6. Stop on any missing source payload, v1 mismatch, ambiguous version, missing
   domain metadata, or domain-metadata mismatch. The mismatch is detected by
   comparing stored metadata with the requested domain, not by the digest
   itself. Such a row is not backfilled.

`prepare_hash_migration` accepts the actual stored `VersionedDigest`, compares
its domain and serializer version with the requested migration profile, and
only then verifies bytes. It returns immutable historical and replacement
`VersionedDigest` values. Exact domain/version mismatch tests require the stable
error above and require the input digest to remain byte-for-byte unchanged.

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
`docs/contracts/w2_canonical_serialization_oracle_vectors_v2.schema.json` and
must not import the production serializer. The schema records the production
implementation head/path/SHA-256, production implementer, ADR/version, oracle
author/source path/source SHA-256, reviewer records and mandatory semantic case
matrix. The harness verifies both Git identities, requires the implementer and
oracle author to differ, checks the production and oracle fingerprints, and
statically rejects oracle imports from production. Mandatory legacy vectors
cover the ASCII, read-model, Stage7I supervision and pair-identity v1 profiles.
Errors use stable `error_code` values. The implementer-provided harness only
compares that external output with production behavior.
