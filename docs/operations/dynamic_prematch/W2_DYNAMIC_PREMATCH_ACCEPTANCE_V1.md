# W2 Dynamic Prematch Acceptance V1

Exact code implementation `d44db97abd46c4e78814e4787d61db41ffc2acb7`, based on PR #370 head `c62fa82d883633f3b33ff44810a5fbc294b215c5`, passed 1438 Python tests with 4 environment-dependent skips, Ruff, Mypy, Web typecheck, the protected Boss Console baseline, all 26 Web Playwright tests and the SQLite migration roundtrip.

The eight requested contract assertions pass locally. No staging deployment or provider call is claimed by this artifact; the honest operational state is `WAITING_FOR_REAL_LINEUP_WINDOW`, and the 20-read staging probe remains pending until exact-SHA staging deployment.

Lineup remains `LINEUP_NUMERIC_ADJUSTMENT_DISABLED` and `LINEUP_ADVISORY_ONLY`. PR #370 stays Draft; Formal, Lock and Production remain disabled and require manual approval.
