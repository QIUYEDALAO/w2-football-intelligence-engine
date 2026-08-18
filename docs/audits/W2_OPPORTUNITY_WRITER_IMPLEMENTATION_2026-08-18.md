# W2 opportunity writer implementation record

- Baseline: `codex/model-forecast-validation-ledger@4c164d1f`.
- Delivery path: local repository only until the six repository red-light tests,
  migration suite, lint, typecheck, and full test suite pass. No GitHub operation
  is part of this change.
- The official denominator is written only from a claimed checkpoint task with
  a real odds response. The writer receives the checkpoint plan id, registered
  evaluation slot, scheduled time, source event identity, and frozen
  ModelForecast capture identity. It never infers a slot from a projected card.
- Opportunities and attempts are separate. A retry updates only the latest
  attempt within one capture track × policy × slot × market opportunity.
- The legacy `MODEL_FORECAST_CAPTURE_SCOPE` sweep producer was removed from the
  worker composition root. Its historical rows remain isolated under
  `LEGACY_POSTHOC_DENOMINATOR_SNAPSHOT_V1`.

## Discovery cost confirmation

Deployment configuration commit `42ce0c72ddd24a91c7fb18d5e71ce1c5ffe2ad98`
changed `W2_FIXTURE_DISCOVERY_MAX_OFFSET_DAYS` from `1` to `7`. The scheduler
cycles inclusively over offset `0..7`, so the daily date scopes rose from 2 to
8. The fixed incremental cost is therefore 6 billable `fixtures` requests per
UTC day. These are GENERAL Provider calls, not POSTMATCH attempts. Against the
observed Pro limit of 7,500/day, the increase is 0.08% and does not consume the
orthogonal POSTMATCH attempt reserve.

No Provider request is issued by this implementation or its tests.
