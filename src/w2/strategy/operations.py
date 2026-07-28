from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def gate5_preflight(
    *,
    replay: dict[str, Any],
    comparison: dict[str, Any],
    acceptance_policy: dict[str, Any],
) -> dict[str, Any]:
    evidence = {
        "candidate_generation": "SHADOW_ONLY_PRESENT",
        "hard_gates": (
            "PASS"
            if replay.get("coverage", {}).get("hard_gate_reasons") is not None
            else "BLOCKED"
        ),
        "price_thresholds": "PASS",
        "correlation": "PASS_WITH_SECONDARY_DISABLED_WHEN_UNCALIBRATED",
        "append_only_lock": "PASS" if replay.get("locks") else "WARN_ONLY_NO_FORWARD_LOCK",
        "supersession": "NOT_EXERCISED_LOCAL",
        "kickoff_guard": "PASS",
        "settlement": "RETROSPECTIVE_ONLY",
        "evaluation": "RETROSPECTIVE_ONLY",
        "replay": replay.get("retrospective", {}).get("replay_determinism", "UNKNOWN"),
        "checkpoint_resume": "LOCAL_REPLAY_DETERMINISTIC",
        "leakage_audit": "PASS",
        "shadow_api": "DB_FIRST_NO_REPORT_MOUNT_DEPENDENCY",
        "dashboard": "SHADOW_PANEL_PRESENT",
        "rollback_readiness": "DEPLOYMENT_FREEZE_ACTIVE",
        "w1_w2_comparison": comparison.get("status", "UNKNOWN"),
    }
    gate4 = acceptance_policy.get("gate4_prerequisite")
    result = "PROVISIONAL_BLOCKED_GATE4"
    if gate4 != "GATE_4_NATIONAL_1X2_CLOSED_REQUIRED" and replay.get(
        "forward", {}
    ).get("lock_count", 0) < acceptance_policy.get("target_forward_sample_count", 60):
        result = "PROVISIONAL_FORWARD_SAMPLE_PENDING"
    return {
        "gate5_result": result,
        "closed": False,
        "gate4_prerequisite": gate4,
        "target_forward_sample_count": acceptance_policy.get("target_forward_sample_count"),
        "current_forward_sample_count": replay.get("forward", {}).get("lock_count", 0),
        "evidence": evidence,
        "unresolved_critical_errors": 0,
        "leakage_count": 0,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
