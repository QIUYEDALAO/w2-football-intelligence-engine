# Independent oracle difference report

Oracle author: Claude Code (`claude-oracle@w2.independent.invalid`)
Production implementation head: `ff0db4f874b263434290d502b7b787adfcde2964`
Oracle head: `6e6f876891c2fea7e8972b78bce33e7c56d66900`

**Result: 30 of 30 cases agree. Zero mismatches.**

## History of this report

The first run against `af64ef9e` found two differences. Both were
specification problems, not oracle errors, and both were closed by the
implementer without touching any oracle file or expected value.

**D-1 `reserved_tag_rejected` — closed.** ADR-0019 named five reserved tags
while the vector schema required a sixth key, `$w2_type`, to be rejected. The
oracle reserved the whole `$w2_` prefix so both documents were satisfied.
ADR-0019 now states that the entire `$w2_` prefix is reserved in v2 and that
the reservation is v2-only, with a new mandatory
`legacy_v1_reserved_prefix_passthrough` category proving v1 still serializes
such keys unchanged. The oracle's reading was adopted.

**D-2 `legacy_v1_read_model` — closed.** The frozen documents recorded that the
v1 read-model profile used a "typed default hook" but never stated the text it
produced, so the output was not independently derivable. ADR-0019 now specifies
it byte-for-byte: `Decimal` becomes `str(value)` with trailing zeros, `date`
becomes `str(value)`, aware `datetime` is converted to UTC and emitted as
`isoformat()` with `+00:00` replaced by `Z`, and naive `datetime` is rejected.
The Stage7I-supervision hook is documented on the same terms. The oracle was
updated from the specification; production output was not consulted.

## Author identity contamination — my error, remediated

Setting an independent Git identity with `git config user.email` inside a
worktree writes to the shared repository config, so the production worktree
inherited the oracle identity and one production commit was authored under it.
`main` was never affected and no production content changed. The implementer
re-authored the tip as `ff0db4f8` with an identical tree
(`77b126ce…`, zero content diff), and my worktree now uses
`extensions.worktreeConfig` so the identity cannot leak again.

## Current state

Every mandatory category agrees: NFC code-point key ordering, Unicode key
collision rejection, exact JSON escaping, large integer, context-independent
large `Decimal`, all binary64 boundaries including min subnormal, max finite,
adjacent values, the power-of-ten boundary, 0.1 and negative zero, NaN and both
infinities rejected, `bytes`, aware datetime, naive datetime rejection,
unsupported type rejection, `$w2_` prefix rejection in v2 and passthrough in
v1, the ASCII, read-model, Stage7I-supervision and pair-identity v1 profiles,
v2 pair identity, bootstrap order independence and invalid pair hash rejection.

`review_status` remains `PENDING`. The oracle author does not approve its own
vectors; adjudication belongs to the final reviewer.
