# W2 Forward Holdout Policy V1

Forward holdout predictions must be locked before kickoff.

Each lock stores:

- fixture id
- kickoff UTC
- locked_at
- as_of_time
- data_cutoff
- model version
- prediction hash
- decision status

Locked predictions are append-only. Evaluation is appended only after the fixture result is known.
Allowed statuses are `NOT_READY`, `SKIP`, and `WATCH`.
