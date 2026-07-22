# W2 Dynamic Prematch Acceptance V1

Exact code implementation `401b82d46c5afb5b907c396c67dcf1fef97c0f53`, based on PR #370 head `c62fa82d883633f3b33ff44810a5fbc294b215c5`, passed 1438 Python tests with 4 environment-dependent skips, Ruff, Mypy, Web typecheck and the SQLite migration roundtrip.

The eight requested contract assertions pass locally. No staging deployment or provider call is claimed by this artifact; the honest operational state is `WAITING_FOR_REAL_LINEUP_WINDOW`, and the 20-read staging probe remains pending until exact-SHA staging deployment.

Lineup remains `LINEUP_NUMERIC_ADJUSTMENT_DISABLED` and `LINEUP_ADVISORY_ONLY`. PR #370 stays Draft; Formal, Lock and Production remain disabled and require manual approval.
