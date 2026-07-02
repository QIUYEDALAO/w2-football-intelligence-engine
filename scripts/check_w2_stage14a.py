#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "src/w2/operations/leagues.py",
    "migrations/versions/0015_create_stage14a_league_onboarding.py",
    "docs/adr/ADR-0017-top-five-league-onboarding.md",
    "docs/leagues/W2_LEAGUE_ONBOARDING_V1.md",
    "docs/leagues/W2_SEASON_ROLLOVER_V1.md",
    "docs/leagues/W2_LEAGUE_MODEL_SCOPE_V1.md",
    "scripts/run_stage14a_league_audit.py",
    "scripts/check_w2_stage14a.py",
]
REPORT_ARTIFACTS = [
    "reports/W2_STAGE14A_COVERAGE.json",
    "reports/W2_STAGE14A_ROLLOVER.json",
    "reports/W2_STAGE14A_READINESS.json",
    "reports/W2_STAGE14A_RESULT.md",
]
PROFILE_DIR = ROOT / "config/competitions/top_five"


def fail(message: str) -> None:
    print(f"W2 Stage14A check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def load(path: str) -> object:
    return json.loads(read(path))


def main() -> int:
    for path in REQUIRED:
        if not (ROOT / path).is_file():
            fail(f"missing {path}")
    profiles = sorted(PROFILE_DIR.glob("*.json"))
    if len(profiles) != 5:
        fail("expected five top-five league profiles")
    combined = "\n".join(read(path) for path in REQUIRED if path.endswith((".py", ".md")))
    for token in [
        "LeagueProfile",
        "LeagueSeason",
        "SeasonLifecycle",
        "LeagueTeamMembership",
        "PromotionRelegationMapping",
        "LeagueReadinessAudit",
        "LeagueOnboardingChecklist",
        "SeasonRolloverPlan",
        "GLOBAL",
        "COUNTRY",
        "LEAGUE",
        "SEASON",
        "TEAM",
        "BLOCKED_GATE4",
        "league_profile",
        "league_readiness_audit",
    ]:
        if token not in combined:
            fail(f"missing token {token}")
    if all((ROOT / path).is_file() for path in REPORT_ARTIFACTS):
        coverage = load("reports/W2_STAGE14A_COVERAGE.json")
        rollover = load("reports/W2_STAGE14A_ROLLOVER.json")
        readiness = load("reports/W2_STAGE14A_READINESS.json")
        result = read("reports/W2_STAGE14A_RESULT.md")
        if set(coverage) != set(readiness) or len(coverage) != 5:  # type: ignore[arg-type]
            fail("coverage/readiness league mismatch")
        for competition_id, payload in readiness.items():  # type: ignore[union-attr]
            checklist = payload["checklist"]
            if len(checklist) != 15:
                fail(f"{competition_id} checklist must have 15 items")
            if checklist["strategy_validation"] != "BLOCKED_GATE4":
                fail(f"{competition_id} strategy validation must be Gate 4 blocked")
            if checklist["production"] != "DISABLED":
                fail(f"{competition_id} production must be disabled")
            if payload["model_scope_policy"]["national_to_club_parameter_reuse"] != "FORBIDDEN":
                fail(f"{competition_id} national parameters must not be reused")
        if not any(item["status"] == "MANUAL_REVIEW_REQUIRED" for item in rollover.values()):  # type: ignore[union-attr]
            fail("rollover must require manual review for unresolved promotion/relegation")
        for token in [
            "STAGE_14A=COMPLETED",
            "TOP_FIVE_LEAGUE_PROFILES=READY_LOCAL_STAGING",
            "CLUB_RESULTS_DATASET=AVAILABLE",
            "CLUB_MARKET_DATASET=PARTIAL",
            "LEAGUE_STRATEGY=BLOCKED_GATE4",
            "LEAGUE_PRODUCTION=DISABLED",
            "PUSH_BLOCKED_NO_ORIGIN",
        ]:
            if token not in result:
                fail(f"missing status {token}")
    print("W2 Stage14A check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
