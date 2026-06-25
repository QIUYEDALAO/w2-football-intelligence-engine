# W2 1X2 Aggregate Semantics V1

`UNKNOWN_PREMATCH_AGGREGATE` means the source contains pre-match 1X2 prices, but does not
prove the exact observation time, capture cadence, or last provider update for each row.

Allowed use:

- aggregate market baseline backtests
- chronological splits that use only match date ordering
- closing-like comparisons explicitly labeled as aggregate, not captured-at

Forbidden use:

- phase movement claims such as T-24h, T-1h, T-30m, or T-10m
- as-of samples that require an `as_of_time`
- forward evidence or lifecycle evidence

This limitation is source-specific. It does not block separate `CAPTURED_AT` sources from making
as-of claims when those rows carry kickoff and capture timestamps and pass leakage checks.

Gate3 remains `PARTIAL` while 1X2 evidence only has `UNKNOWN_PREMATCH_AGGREGATE` semantics. The
blocker is retained as `UNKNOWN_PREMATCH_AGGREGATE_NOT_AS_OF`, which means the aggregate 1X2 source
is understood and safely fenced rather than ambiguous.
