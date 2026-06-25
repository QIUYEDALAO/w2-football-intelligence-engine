# ADR-0021 Daily Matchday And Temporal Integrity

Stage10C introduces a read-only daily matchday pipeline. It separates source capture
time from valuation generation time so a post-kickoff recomputation from locked
prematch data cannot masquerade as a live prematch decision.

Snapshots keep append-only manifests. Historical hash mismatches are reconciled
through a correction ledger instead of mutating old files. New snapshots must use
`SHA256_CANONICAL_JSON_V1`.

Gate 4 remains pending, so published research grades are capped at `C` and every
card keeps `formal_recommendation=false` and `candidate=false`.
