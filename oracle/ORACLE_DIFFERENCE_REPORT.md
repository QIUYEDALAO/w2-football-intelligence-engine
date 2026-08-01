# Independent oracle difference report

Oracle author: Claude Code (`claude-oracle@w2.independent.invalid`)
Production implementation head: `af64ef9ec416ce9a9b166a1ddccdb601abac9447`
Result: **CHANGES_REQUIRED** — two cases differ. No expected value in
`w2_canonical_serialization_oracle_vectors_v2.json` was altered to match
production. The oracle output stands as authored.

## D-1 `reserved-tag-rejected.0` — production contradicts its own schema

The mandatory semantic contract in
`docs/contracts/w2_canonical_serialization_oracle_vectors_v2.schema.json`
declares, for a caller mapping containing the key `$w2_type`:

```json
{"status": "error", "error_code": "RESERVED_TAG"}
```

The oracle rejects it. The production harness reports
`expected error but production succeeded`, so production accepts the key.

Underlying ambiguity: ADR-0019 says "the five `$w2_*` tag keys are reserved",
naming `$w2_float`, `$w2_decimal`, `$w2_date`, `$w2_datetime` and `$w2_bytes`.
`$w2_type` is not one of the five, yet the schema requires it to be rejected.
The oracle resolves this by reserving the whole `$w2_` prefix namespace, which
satisfies both documents; production appears to reserve only the five exact
names.

This must be adjudicated, not silently aligned. Either the ADR should state
that the `$w2_` prefix is reserved and production should reject the prefix, or
the schema's mandatory case is wrong. Reserving only the exact five leaves
`$w2_type` and any future tag name available to a caller, which is the typed
scalar/mapping ambiguity the reservation exists to prevent.

## D-2 `legacy-v1-read-model.0` — v1 typed default hook is underspecified

Oracle output for the `prematch_read_model.generic` v1 profile:

```json
{"date":"2026-08-01","price":"1.2300","team":"上海","updated_at":"2026-08-01T12:34:56+08:00"}
```

The production harness reports `oracle mismatch`.

Root cause is a specification gap rather than a disagreement about a stated
rule. ADR-0019 says v1 domain profiles "reproduce the frozen `ensure_ascii`,
default-hook and NaN behavior", and the SER-01 frozen inventory records that
this domain uses `ensure_ascii=False`, implicit `allow_nan=True` and a "typed
default hook". Neither document states the text that hook produces for
`Decimal`, `date` or aware `datetime`. The oracle therefore had to choose an
interpretation: `str(Decimal)` preserving trailing zeros, `date.isoformat()`
and `datetime.isoformat()` with the original offset retained.

An independent implementer cannot derive the byte-exact v1 read-model output
from the frozen specification set. Until the hook's output text is written into
ADR-0019 or the frozen inventory, this category cannot be independently
verified, and a mismatch here is not by itself evidence of a production defect.

## Categories that agree

The remaining 25 of 27 cases match production, including NFC code-point key
ordering, Unicode key collision rejection, exact JSON escaping, the large
integer, context-independent large `Decimal`, all six binary64 boundary cases,
NaN and both infinities rejected, `bytes`, aware datetime, naive datetime
rejection, unsupported type rejection, the ASCII, Stage7I-supervision and pair
identity v1 profiles, v2 pair identity, bootstrap order independence and
invalid pair hash rejection.

## Required action

Adjudication by the final reviewer. The oracle author does not approve, reject
or re-run its own vectors against an adjusted expectation.
