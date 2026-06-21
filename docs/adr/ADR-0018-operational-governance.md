# ADR-0018: Operational Governance

Status: Accepted for Stage 15A.

Stage 15A establishes local/staging long-term operations governance. It defines
daily, weekly, matchday, round-end, season-end, and model-release dry cycles with
immutable audit hashes.

Production release, external alerting, DeepSeek, CANDIDATE, and RECOMMEND remain
disabled. Release governance rejects production while Gate 4/5/6 are not closed.
Retention is dry-run only and does not delete files.
