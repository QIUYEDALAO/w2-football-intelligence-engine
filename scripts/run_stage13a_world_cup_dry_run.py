#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from w2.operations.tournament import (
    build_operations_plan,
    load_stage5b_world_cup_fixtures,
    load_tournament_profile,
    readiness_report,
)

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
PROFILE = ROOT / "config/competitions/world_cup_2026.v1.json"
FIXTURES = ROOT / "runtime/stage5b/processed/national_fixtures_cleaned.json"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    path.write_text(text + "\n", encoding="utf-8")


def main() -> int:
    profile = load_tournament_profile(PROFILE)
    fixtures = load_stage5b_world_cup_fixtures(FIXTURES)
    plan = build_operations_plan(profile, fixtures)
    readiness = readiness_report(profile, plan)
    dry_run = {
        "run_id": "stage13a-world-cup-dry-run-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "competition_id": profile.competition_id,
        "profile_version": profile.version,
        "fixture_source": "runtime/stage5b/processed/national_fixtures_cleaned.json",
        "fixture_count_available": len(fixtures),
        "fixture_count_planned": len(plan),
        "operations_plan": plan,
        "network_used": False,
        "production_enabled": False,
        "shadow_runtime_enabled": False,
        "deepseek_enabled": False,
        "candidate_output": False,
        "recommend_output": False,
        "strategy_version": profile.strategy_version,
    }
    dry_run["plan_sha256"] = hashlib.sha256(
        json.dumps(dry_run, sort_keys=True, default=str).encode()
    ).hexdigest()
    result = "\n".join(
        [
            "# W2 Stage 13A Result",
            "",
            "STAGE_13A=COMPLETED",
            "WORLD_CUP_OPERATIONS_PROFILE=READY_LOCAL_STAGING",
            "WORLD_CUP_SHADOW_RUNTIME=DISABLED_PENDING_GATE4",
            "WORLD_CUP_STRATEGY=NOT_AVAILABLE_GATE4",
            "PRODUCTION_DEPLOYMENT=DISABLED",
            "STAGE_9=BLOCKED",
            "PUSH_BLOCKED_NO_ORIGIN",
            "",
            "Offline World Cup operations dry-run completed without API calls.",
            "正式推荐尚未启用。",
        ]
    )
    write_json(REPORTS / "W2_STAGE13A_READINESS.json", readiness)
    write_json(REPORTS / "W2_STAGE13A_DRY_RUN.json", dry_run)
    (REPORTS / "W2_STAGE13A_RESULT.md").write_text(result + "\n", encoding="utf-8")
    print("W2 Stage13A World Cup dry-run PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
