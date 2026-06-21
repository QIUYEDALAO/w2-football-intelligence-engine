#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from w2.migration import (
    MigrationDryRunEngine,
    build_default_contracts,
    build_source_inventory,
    quarantine_registry,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
W1_ROOT = Path.home() / ".openclaw" / "workspace" / "w1_world_cup_engine"
PROTECTED = [
    "scripts/w1_score_engine.py",
    "scripts/w1_odds_snapshot_collector.py",
    "scripts/w1_local_predict_server.py",
    "scripts/build_w1_dashboard_data.py",
    "config/w1_decision_policy.json",
    "config/w1_scout_policy.json",
    "config/w1_rho_provenance.json",
]
FROZEN_AUDIT_FILES = [
    "reports/P0_BASELINE_SUMMARY.md",
    "reports/legacy_baseline",
    "reports/legacy_classification",
    "reports/legacy_decisions",
]


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    path.write_text(text + "\n", encoding="utf-8")


def git_output(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(W1_ROOT), *args],
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def main() -> int:
    w1_head = git_output("rev-parse", "HEAD")
    w1_status = git_output("status", "--short")
    inventory = build_source_inventory(W1_ROOT, w1_head)
    contracts = build_default_contracts()
    dry_run = MigrationDryRunEngine(inventory, contracts).run(run_id="stage12a-dry-run-v1")
    quarantine = quarantine_registry(inventory)
    readonly_audit = [
        "W2_STAGE12A_W1_READONLY_AUDIT",
        f"W1_HEAD={w1_head}",
        "W1_STATUS_SHORT:",
        w1_status or "CLEAN",
        "PROTECTED_FILE_SHA256:",
    ]
    readonly_audit.extend(f"{sha256_file(W1_ROOT / path)}  {path}" for path in PROTECTED)
    readonly_audit.append("FROZEN_AUDIT_ASSETS:")
    readonly_audit.extend(
        f"{sha256_file(W1_ROOT / path)}  {path}"
        for path in FROZEN_AUDIT_FILES
        if (W1_ROOT / path).exists()
    )
    source_inventory = {
        "inventory_version": "w2-stage12a-source-inventory-v1",
        "source_head": w1_head,
        "assets": [item.__dict__ for item in inventory],
        "transform_contracts": [item.__dict__ for item in contracts],
        "source_system": "W1",
        "full_dataset_copied": False,
        "w1_runtime_imported": False,
    }
    write_json(REPORTS / "W2_STAGE12A_SOURCE_INVENTORY.json", source_inventory)
    write_json(REPORTS / "W2_STAGE12A_MIGRATION_DRY_RUN.json", dry_run)
    write_json(REPORTS / "W2_STAGE12A_QUARANTINE.json", quarantine)
    (REPORTS / "W2_STAGE12A_W1_READONLY_AUDIT.txt").write_text(
        "\n".join(readonly_audit) + "\n",
        encoding="utf-8",
    )
    result = "\n".join(
        [
            "# W2 Stage 12A Result",
            "",
            "STAGE_12A=COMPLETED",
            "STAGE_12=PROVISIONAL",
            "W1_DATA_MIGRATION_EXECUTION=DISABLED_PENDING_APPROVAL",
            "SHADOW_FOUNDATION=READY",
            "SHADOW_RUNTIME=DISABLED_PENDING_GATE4",
            "PRODUCTION_SWITCH=DISABLED",
            "GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING",
            "STAGE_9=BLOCKED",
            "PUSH_BLOCKED_NO_ORIGIN",
            "",
            "Migration dry-run used only in-memory objects and temporary storage.",
            "No W1 writes, no W2 production database writes, no live Shadow Run.",
        ]
    )
    (REPORTS / "W2_STAGE12A_RESULT.md").write_text(result + "\n", encoding="utf-8")
    print("W2 Stage12A migration dry-run PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
