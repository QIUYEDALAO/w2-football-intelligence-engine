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
```

`ensure_ascii=False` is deliberate. The frozen inventory contains both escaped
ASCII and direct UTF-8 histories. Keeping escaped ASCII would preserve only one
legacy family and would retain two visually different byte forms for the same
Unicode text. V2 instead normalizes text to NFC and hashes its direct UTF-8
bytes. V1 readers reproduce each affected historical family unchanged.

## Type rules

- `None`, booleans and arbitrary-precision integers retain their JSON types.
- Finite floats use a typed `{"$w2_float":"..."}` form. Decimal text is plain,
  exponent-free and has no insignificant trailing zero; `-0.0` becomes `0`.
- Finite `Decimal` uses the distinct typed
  `{"$w2_decimal":"..."}` form under the same numeric normalization.
- `date` uses `{"$w2_date":"YYYY-MM-DD"}`.
- Aware `datetime` is converted to UTC and emitted with six fractional digits
  and `Z` in `{"$w2_datetime":"..."}`. Naive datetime is rejected.
- `bytes` uses unpadded base64url in `{"$w2_bytes":"..."}`.
- Lists and tuples become arrays. Mapping keys must be strings. Unicode key
  collisions after NFC normalization are rejected.
- The five `$w2_*` tag keys are reserved in caller mappings to prevent typed
  scalar/mapping ambiguity.
- Sets, custom objects and all unlisted types are rejected. There is no
  `default=str` fallback in v2.
- Float/Decimal NaN and positive or negative Infinity are rejected before JSON
  encoding; `json.dumps(..., allow_nan=False)` remains the final safeguard.

The type tags are part of v2. They keep `1`, `1.0`, `Decimal("1")` and the
string `"1"` semantically distinct and make independent implementations
possible without relying on a language runtime's floating-point formatter.

## Legacy contract

`w2.canonical-json.v1` is read/verify compatibility only. Its domain profiles
reproduce the frozen `ensure_ascii`, default-hook and NaN behavior. No v1 hash
is relabelled as v2. New EVAL-02B pair identities and bootstrap seeds use v2;
existing persistent writers stay on an explicit v1 profile until their schema
stores the version alongside new writes.

