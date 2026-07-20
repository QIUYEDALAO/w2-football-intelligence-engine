# MATCHDAY_LIVE_GATE_DIAGNOSIS_V1

Final reason code: `LIVE_GATE_API_KEY_NOT_VISIBLE`.

The precise failing path is:

```text
worker
-> w2.providers.api_football.ApiFootballClient.request_live()
-> endpoint=status
-> LiveNetworkDisabledError("provider credential is not visible to the process")
```

This is not a `fetch()` interface misuse. The live diagnostic used `request_live()`, `allow_live=True`, `W2_PROVIDER_CALLS_DISABLED=false`, and an allowlist containing `status`, `fixtures`, `odds`, and `lineups`.

No API key value, length, or reversible fingerprint was logged.

Provider HTTP calls consumed: 0.
