# W2 Shadow Comparison V1

Stage 12A establishes only the offline Shadow comparison foundation. It does not
start a live Shadow Run and does not call W1 prediction services.

Adapters:

- `W1SnapshotAdapter`: reads frozen or archived W1 samples.
- `W2SnapshotAdapter`: reads W2 archived market/model samples.
- `ShadowComparisonEngine`: compares snapshots and emits deterministic records.

Allowed comparison fields:

- fixture identity
- kickoff time
- odds snapshot age
- bookmaker coverage
- 1X2 market probability
- OU μ
- lambda_home / lambda_away
- score matrix summary
- W2 independent probability
- WATCH/SKIP state
- data latency and runtime errors

Forbidden behavior:

- runtime import of W1 business code
- W1 prediction server calls
- W2 strategy result generation
- CANDIDATE or RECOMMEND output
- treating W1 recommendations as truth

While Stage 9 is blocked, `strategy_comparison_status=NOT_AVAILABLE_GATE4`.
