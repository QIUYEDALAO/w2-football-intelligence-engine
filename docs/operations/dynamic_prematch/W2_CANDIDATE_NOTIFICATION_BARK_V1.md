# W2 Candidate Notification Bark V1

## Scope

This channel delivers immutable candidate-attempt outbox events. It does not poll the
current `dynamic_prematch_opportunities` projection, change model gates, backfill old
matches, or mutate capture, outcome, raw, or evaluation ledgers.

The scheduler handles four event types: first candidate formation, material change,
withdrawal, and T-30m confirmation. It also emits a plan summary two hours before the
first kickoff of the Beijing operational football day and a closeout summary after all
fixtures in that day have terminal evidence.

## Configuration boundary

The runtime reads:

- `W2_BARK_ENDPOINT`, normally `https://api.day.app`;
- `W2_BARK_DEVICE_KEY`, stored only in the protected VPS environment file;
- `W2_DASHBOARD_PUBLIC_BASE_URL`, used to build an absolute fixture deep link.

If either Bark setting is absent, delivery remains `CHANNEL_NOT_CONFIGURED` and no
outbox delivery state is changed. The device key must never be committed, placed in a
URL, logged, copied into an outbox payload, or returned by a health endpoint. The sender
uses Bark's JSON `POST /push` form so the key is carried in the request body. Requests
set `group` to `W2候选`, `level` to `timeSensitive`, and `url` to the fixture deep link;
the GET path form is not used.

## Delivery semantics and SLO

Bark has no delivery-receipt query API. External exactly-once delivery therefore cannot
be guaranteed. The database provides idempotent event creation and durable retry state;
delivery to Bark is explicitly `AT_LEAST_ONCE`. If the process stops after Bark accepts a
request but before the database commit, the client can receive a duplicate.

Each row gets one initial attempt plus at most three retries. Retry due times use 5, 10,
and 20 second exponential backoff. A dedicated scheduler thread checks delivery every
five seconds so slower fixture/outcome work cannot block notification delivery. The target
from outbox creation to successful delivery is P95 at or below 30 seconds; pending age
above 60 seconds is an SLO breach. Five consecutive failed attempts place channel health
in `DEGRADED`.

`GET /ops/notification-outbox-health` exposes at least:

- `channel: "bark"`;
- `delivery_mode: "AT_LEAST_ONCE"`;
- configuration state, last successful delivery, failure/retry counts and consecutive
  failures;
- pending backlog and oldest pending age;
- enqueue breaches, delivery target/SLO breaches, and delivery latency P95.

The endpoint never treats zero candidates as proof that delivery is healthy.

## Summary rules

The plan summary lists every fixture that has both a model forecast capture and a
registered odds-evaluation plan for the current operational football day. The closeout
summary lists candidate recommendations, their final candidate status, final score, and
read-only settlement result. Settlement is computed for the message only and is not
written to any recommendation or settlement ledger.

Both summary event IDs are deterministic per operational football day. Their five-minute
forward-only scheduling windows prevent a new deployment from backfilling historical
matches.

## Activation and verification

Activation requires the Owner-provided credential on the authoritative VPS. Release
must use the `w2-staging` Compose project, runtime-base plus source-layer structure, and
pass `w2-release-preflight`. A test message may target only the Owner device.

The unrelated `w2-staging-watchdog.service` sudo failure is not part of this change and
must not be repaired in the same release.
