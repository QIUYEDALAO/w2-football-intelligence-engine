# ADR-0017: Top Five League Onboarding

Status: Accepted for Stage 14A.

Stage 14A adds a local/staging onboarding framework for Premier League, La Liga,
Bundesliga, Serie A, and Ligue 1. Profiles are configuration-driven and do not
embed teams, fixtures, or seasons in Python or TypeScript.

The framework audits local Stage5B club results, separates results readiness
from market readiness, and produces manual-review rollover plans. League model
scope is isolated from national-team scope and final league parameters are not
shared across leagues.

Strategy validation, Shadow, and production remain blocked while Gate 4 and
Stage 9 are unavailable. No CANDIDATE or RECOMMEND output is produced.
