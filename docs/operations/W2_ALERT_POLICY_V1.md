# W2 Alert Policy V1

Internal alert states:

- INFO
- WARNING
- CRITICAL
- RESOLVED

Supported local/staging alert rules include missing upcoming odds, stale data, bookmaker count
drops, provider failures, low quota, scheduler heartbeat loss, mapping conflict, closing snapshot
missing, result sync delay, frozen manifest hash mismatch, and stale backup.

Alerts are idempotent and recoverable. Stage 11A writes only local database/log artifacts and sends
no external messages.
