# Dashboard Cache-First Performance Design

## Problem

The public shell loads quickly, but a cold `future` DayView response is large and slow. The browser currently treats cached data as expired after one minute, clears the visible view on manual refresh, and retries the same long request once after a failure. Those behaviors turn ordinary API latency into an apparent 20–40 second blank load.

## Design

- Keep the latest valid DayView visible while a new snapshot loads.
- Retain the browser snapshot for 15 minutes and still revalidate it on every page load.
- Do not delete the snapshot or switch to a loading skeleton on manual refresh.
- Use one bounded 12-second DayView attempt rather than two identical 20-second attempts.
- Compress JSON responses larger than 1 KiB with gzip.
- Advertise a 30-second browser cache with five minutes of stale-while-revalidate for DayView.

The existing repository cache remains the calculation cache and recommendation truth stays unchanged.

## Acceptance

- Cached page content appears without waiting for the network refresh.
- Refresh preserves the current view until the replacement succeeds.
- DayView responses support gzip and include the cache contract.
- No provider calls, database writes, scheduler changes, recommendation-policy changes, or production deployment.
