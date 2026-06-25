# Stage10D Matchday Coverage Runbook

Stage10D reconciles provider fixtures, normalized data, PostgreSQL read models,
research cards, API responses and Dashboard display counts for a Beijing
operational day.

1. Build the Beijing operational window from `config/policies/matchday_timezone.v1.json`.
2. Query provider UTC dates intersecting the window.
3. Normalize and deduplicate by provider fixture id.
4. Compare authoritative fixtures with read-model and displayed fixtures.
5. Assign every missing fixture exactly one reason.
6. Keep recommendation and candidate output disabled.

No Tokyo or Japan user window is part of the policy.
