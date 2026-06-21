# Ingestion Offline Replay

Run the脱敏 Gate 2 rehearsal:

```bash
uv run python scripts/replay_provider_fixture.py
```

The replay uses `fixtures/provider/api_football/offline_gate2_fixture.json`.
It writes no live data and makes no network calls. The expected gate status is
`PROVISIONAL`.

The replay validates:

- raw payload SHA256 stability
- append-only raw reference semantics
- provider ID mapping
- bookmaker-by-bookmaker odds preservation
- odds canonicalization
- replay idempotency
- pre-match time checks
- freshness alert generation
- no result leakage into feature snapshots

Do not run `--live` during Stage 4A.

