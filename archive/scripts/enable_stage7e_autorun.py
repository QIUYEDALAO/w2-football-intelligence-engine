#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.models.forward_autorun import ForwardAutorunSettings

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
RUNTIME = ROOT / "runtime/stage7e"

EXPECTED_HASHES = {
    "stage7b_frozen_manifest": (
        REPORTS / "W2_STAGE7B_FROZEN_MODEL_MANIFEST.json",
        "c9bca779968962eb8d8dc46cc29b1448634300a8e66827ecb85d25983bf32204",
    ),
    "stage7b_forward_protocol": (
        REPORTS / "W2_STAGE7B_FORWARD_HOLDOUT_PROTOCOL.json",
        "400e8d8e66bf22bd65215619925f65486031bd84584da6a488d51f13f3958062",
    ),
    "stage7c_gate_decision": (
        REPORTS / "W2_STAGE7C_GATE4_DECISION.json",
        "d5ea4e053f7537901135358eccf0b25805c20486d4688b2104bda59973198d32",
    ),
    "stage7c_power_analysis": (
        REPORTS / "W2_STAGE7C_POWER_ANALYSIS.json",
        "fabc4b8d023b74a0766842bfb96836e1d46e27898e333379a8f076c10be28c4b",
    ),
    "stage7d_automation_plan": (
        REPORTS / "W2_STAGE7D_AUTOMATION_PLAN.json",
        "559591de06bd118e67ab06facf58722419d98e424369d65fc004904214157329",
    ),
    "stage7d_power_progress": (
        REPORTS / "W2_STAGE7D_POWER_PROGRESS.json",
        "30d5d01e5017965e734c6fd9fa2ab9d87745bf4c2c8af07ef384ca71fc3aaded",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    path.write_text(content, encoding="utf-8")


def hash_audit() -> dict[str, Any]:
    observed = {
        name: {"sha256": sha256(path), "expected": expected}
        for name, (path, expected) in EXPECTED_HASHES.items()
    }
    blockers = [
        f"{name.upper()}_HASH_CHANGED"
        for name, item in observed.items()
        if item["sha256"] != item["expected"]
    ]
    return {"observed": observed, "blockers": blockers}


def main() -> int:
    environment = os.environ.get("W2_ENVIRONMENT", "local")
    settings = ForwardAutorunSettings(
        environment=environment,
        autorun_enabled=True,
        network_enabled=True,
        deepseek_enabled=False,
        recommendation_enabled=False,
    )
    settings.validate()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    hashes = hash_audit()
    if hashes["blockers"]:
        raise SystemExit(f"Stage7E frozen hash blocker: {hashes['blockers']}")
    runtime_config = {
        "environment": environment,
        "W2_FORWARD_HOLDOUT_AUTORUN": True,
        "W2_FORWARD_HOLDOUT_NETWORK": True,
        "W2_DEEPSEEK_ENABLED": False,
        "W2_RECOMMENDATION_ENABLED": False,
        "daily_hard_budget": settings.daily_hard_budget,
        "minimum_reserve": settings.minimum_reserve,
        "per_cycle_cap": settings.per_cycle_cap,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "credential_values": "not_persisted",
    }
    write_json(RUNTIME / "local_autorun_config.json", runtime_config)
    report = {
        "environment": environment,
        "api_key_status": "PRESENT" if os.environ.get("W2_API_FOOTBALL_API_KEY") else "ABSENT",
        "autorun_enabled": True,
        "network_enabled": True,
        "deepseek_enabled": False,
        "recommendation_enabled": False,
        "production_config_modified": False,
        "runtime_config_path": "runtime/stage7e/local_autorun_config.json",
        "runtime_config_gitignored": True,
        "hash_audit": hashes,
    }
    write_json(REPORTS / "W2_STAGE7E_ENABLEMENT.json", report)
    print("W2 Stage7E autorun enablement prepared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
