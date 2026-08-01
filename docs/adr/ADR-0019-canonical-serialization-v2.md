# ADR-0019: canonical serialization v2

Status: Accepted for Wave 2 implementer tranche

## Decision

The sole versioned authority is
`src/w2/domain/canonical_serialization.py`.

```text
SERIALIZER_VERSION = w2.canonical-json.v2
ENCODING = UTF-8
UNICODE = NFC_NORMALIZED_KEYS_AND_STRING_VALUES
SORT_KEYS = true
SEPARATORS = (",", ":")
ENSURE_ASCII = false
ALLOW_NAN = false
HASH = SHA-256
HASH_DOMAIN_IN_PREIMAGE = false
SERIALIZER_VERSION_IN_PREIMAGE = false
```

`ensure_ascii=False` is deliberate. The frozen inventory contains both escaped
ASCII and direct UTF-8 histories. Keeping escaped ASCII would preserve only one
legacy family and would retain two visually different byte forms for the same
Unicode text. V2 instead normalizes text to NFC and hashes its direct UTF-8
bytes. V1 readers reproduce each affected historical family unchanged.

## Type rules

- `None`, booleans and arbitrary-precision integers retain their JSON types.
- Finite floats are IEEE-754 binary64 values and use
  `{"$w2_float":"hhhhhhhhhhhhhhhh"}`: the exact eight bytes are encoded in
  big-endian order as 16 lowercase hexadecimal characters. Positive and
  negative zero both use `0000000000000000`; non-finite bit patterns are
  rejected. This representation does not invoke a language float formatter.
- Finite `Decimal` uses the distinct typed
  `{"$w2_decimal":"..."}` form. Text is derived directly from sign,
  coefficient digits and exponent, is exponent-free, and removes insignificant
  trailing zeros. It never calls `normalize()` and never consults the ambient
  decimal context, so arbitrary precision is retained.
- `date` uses `{"$w2_date":"YYYY-MM-DD"}`.
- Aware `datetime` is converted to UTC and emitted with six fractional digits
  and `Z` in `{"$w2_datetime":"..."}`. Naive datetime is rejected.
- `bytes` uses unpadded base64url in `{"$w2_bytes":"..."}`.
- Lists and tuples become arrays. Mapping keys must be strings. Unicode key
  collisions after NFC normalization are rejected. After NFC normalization,
  object keys are ordered by ascending Unicode code point. This is not locale,
  UTF-8 byte, or UTF-16 code-unit order; the contract includes BMP and astral
  keys so independent implementations cannot accidentally substitute one.
- JSON string escaping is exact: quotation mark and reverse solidus are escaped;
  U+0000 through U+001F use JSON escapes (`\b`, `\t`, `\n`, `\f`, `\r` where
  defined and lowercase `\u00xx` otherwise). Non-ASCII code points remain
  literal UTF-8 because `ensure_ascii=false`.
- The entire `$w2_` prefix is reserved in v2 caller mapping keys to prevent
  typed scalar/mapping ambiguity and preserve room for future tags. V2
  currently emits only five typed tags: `$w2_bytes`, `$w2_date`,
  `$w2_datetime`, `$w2_decimal`, and `$w2_float`.
- Sets, custom objects and all unlisted types are rejected. There is no
  `default=str` fallback in v2.
- Float/Decimal NaN and positive or negative Infinity are rejected before JSON
  encoding; `json.dumps(..., allow_nan=False)` remains the final safeguard.

The type tags are part of v2. They keep `1`, `1.0`, `Decimal("1")` and the
string `"1"` semantically distinct and make independent implementations
possible without relying on a language runtime's floating-point formatter or
decimal context.

## Digest metadata boundary

The hash preimage is exactly the canonical UTF-8 bytes. `HashDomain` and
`SerializerVersion` are not prefixed, enveloped or otherwise included in the
preimage. Therefore equal canonical bytes have equal SHA-256 values across
domains. Every stored digest must preserve domain and serializer version as
separate metadata, and readers must validate both metadata fields before
verifying the digest. A digest alone cannot detect a domain/version mismatch.

## Legacy contract

`w2.canonical-json.v1` is read/verify compatibility only. Its domain profiles
reproduce the frozen `ensure_ascii`, default-hook and NaN behavior. No v1 hash
is relabelled as v2. New EVAL-02B pair identities and bootstrap seeds use v2;
existing persistent writers stay on an explicit v1 profile until their schema
stores the version alongside new writes.

The frozen read-model v1 default hook is byte-significant:

- `Decimal` becomes `str(value)`, including trailing zeros;
- `date` becomes `str(value)`;
- aware `datetime` is converted to UTC, serialized with `isoformat()`, and has
  `+00:00` replaced by `Z`;
- naive `datetime` is rejected.

The frozen Stage7I-supervision v1 default hook converts aware `datetime` to UTC
`isoformat()` text with `+00:00` replaced by `Z`; every other unsupported object
becomes `str(value)`.

The `$w2_` reservation is v2-only. Historical v1 profiles use their frozen
plain `json.dumps` behavior and continue to serialize caller mapping keys such
as `$w2_type` unchanged.

The guard manifest value `w2.legacy-implicit-json.v1` is a
`legacy_profile_id`, not a serializer version. The only legacy serializer
version accepted by the runtime is `w2.canonical-json.v1`.

The EVAL-02B exact-pair projector schema is
`w2.eval_02b_exact_pair_projection.v2`; v1 pair projection rows are not
relabelled or overwritten. Every v2 pair emits both
`hash_domain=eval_02b.pair_identity` and
`serializer_version=w2.canonical-json.v2` beside `identity_hash`.

## Independent oracle contract

The v2 oracle schema binds every mandatory category to an exact operation,
hash domain, serializer version, input-node shape, boundary values and declared
success/error outcome. Category labels alone are insufficient. The matrix
includes NFC code-point key ordering, exact JSON escaping, an integer above
64-bit and common decimal limits, both finite and non-finite binary64 edges,
and each distinct critical v1 profile: ASCII, read-model typed default,
Stage7I supervision fallback/datetime, pair identity, and v1 `$w2_` key
passthrough.

The handoff records and verifies the production Git head, production source
path/SHA-256 and commit-author email. It also records the oracle author and
oracle source path/SHA-256, verifies the source's commit-author email, requires
implementer and oracle author to differ, and statically rejects any oracle
source import from `w2`. The implementer supplies only the schema and harness;
independent oracle output bytes and hashes are authored later.
