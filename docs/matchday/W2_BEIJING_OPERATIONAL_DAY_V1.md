# W2 Beijing Operational Day V1

The user matchday is based on Beijing time only.

For local date `D`:

- start: `D 00:00:00 Asia/Shanghai`
- end: `D+1 00:00:00 Asia/Shanghai`
- semantics: left-closed, right-open

For `2026-06-23`, the UTC query window is:

- `2026-06-22T16:00:00Z`
- `2026-06-23T16:00:00Z`

Each fixture exposed by the API includes:

- `kickoff_utc`
- `kickoff_beijing`
- `operational_date_beijing`

UTC remains the storage timezone for kickoff, captured, event, ingested and
confirmed timestamps.
