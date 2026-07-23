#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "src/w2/operations/tournament.py",
    "config/competitions/world_cup_2026.v1.json",
    "migrations/versions/0014_create_stage13a_tournament_ops.py",
    "docs/adr/ADR-0016-world-cup-operations.md",
    "docs/operations/W2_TOURNAMENT_OPERATIONS_V1.md",
    "docs/operations/WORLD_CUP_2026_PROFILE.md",
    "docs/runbooks/WORLD_CUP_DRY_RUN.md",
    "scripts/run_stage13a_world_cup_dry_run.py",
    "scripts/check_w2_stage13a.py",
    "scripts/check_w2_all.py",
]
REPORT_ARTIFACTS = [
    "reports/W2_STAGE13A_READINESS.json",
    "reports/W2_STAGE13A_DRY_RUN.json",
    "reports/W2_STAGE13A_RESULT.md",
]


def fail(message: str) -> None:
    print(f"W2 Stage13A check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def load(path: str) -> object:
    return json.loads(read(path))


def main() -> int:
    for path in REQUIRED:
        if not (ROOT / path).is_file():
            fail(f"missing {path}")
    combined = "\n".join(read(path) for path in REQUIRED if path.endswith((".py", ".md", ".json")))
    for token in [
        "TournamentProfile",
        "TournamentStage",
        "GroupDefinition",
        "KnockoutRound",
        "QualificationRule",
        "MatchContext",
        "MatchImportanceContext",
        "OperationsSchedule",
        "EXPLANATORY_ONLY_UNVALIDATED",
        "NOT_AVAILABLE_GATE4",
    ]:
        if token not in combined:
            fail(f"missing token {token}")
    profile = load("config/competitions/world_cup_2026.v1.json")
    if profile["strategy_version"] != "NOT_AVAILABLE_GATE4":  # type: ignore[index]
        fail("strategy_version must stay NOT_AVAILABLE_GATE4")
    if all((ROOT / path).is_file() for path in REPORT_ARTIFACTS):
        readiness = load("reports/W2_STAGE13A_READINESS.json")
        dry_run = load("reports/W2_STAGE13A_DRY_RUN.json")
        result = read("reports/W2_STAGE13A_RESULT.md")
        if dry_run["network_used"] or dry_run["production_enabled"]:  # type: ignore[index]
            fail("dry-run must stay offline and non-production")
        if dry_run["candidate_output"] or dry_run["recommend_output"]:  # type: ignore[index]
            fail("dry-run must not output candidate or recommend")
        if readiness["strategy_version"] != "NOT_AVAILABLE_GATE4":  # type: ignore[index]
            fail("readiness strategy status mismatch")
        if readiness["fixture_coverage_count"] <= 0:  # type: ignore[index]
            fail("World Cup fixture coverage missing")
        for item in dry_run["operations_plan"][:5]:  # type: ignore[index]
            if item["importance_context"]["validation_status"] != "EXPLANATORY_ONLY_UNVALIDATED":
                fail("importance context must be explanatory-only")
            if item["importance_context"]["model_feature_enabled"]:
                fail("importance context must not enter model features")
        for token in [
            "STAGE_13A=COMPLETED",
            "WORLD_CUP_OPERATIONS_PROFILE=READY_LOCAL_STAGING",
            "WORLD_CUP_SHADOW_RUNTIME=DISABLED_PENDING_GATE4",
            "WORLD_CUP_STRATEGY=NOT_AVAILABLE_GATE4",
            "PRODUCTION_DEPLOYMENT=DISABLED",
            "STAGE_9=BLOCKED",
            "PUSH_BLOCKED_NO_ORIGIN",
        ]:
            if token not in result:
                fail(f"missing status {token}")
    print("W2 Stage13A check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
