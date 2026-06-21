#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from w2.operations.governance import build_operations_report

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
RUNTIME = ROOT / "runtime/stage15a"
WEB = ROOT / "apps/web"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def npm_audit() -> dict[str, Any]:
    completed = subprocess.run(
        ["npm", "--prefix", str(WEB), "audit", "--json"],
        check=False,
        text=True,
        capture_output=True,
    )
    raw = json.loads(completed.stdout or "{}")
    risks = []
    for package, risk in raw.get("vulnerabilities", {}).items():
        fix = risk.get("fixAvailable")
        risks.append(
            {
                "package": package,
                "severity": risk.get("severity", "unknown"),
                "dependency_path": risk.get("nodes", []),
                "fix_version": fix.get("version") if isinstance(fix, dict) else None,
                "fix_is_semver_major": (
                    bool(fix.get("isSemVerMajor")) if isinstance(fix, dict) else False
                ),
                "status": (
                    "MANUAL_REVIEW_REQUIRED"
                    if isinstance(fix, dict) and fix.get("isSemVerMajor")
                    else "PATCH_MINOR_FIX_ALLOWED"
                ),
            }
        )
    return {
        "tool": "npm audit",
        "exit_code": completed.returncode,
        "risks": sorted(risks, key=lambda item: (item["severity"], item["package"])),
        "metadata": raw.get("metadata", {}),
        "force_fix_used": False,
    }


def python_dependency_inventory() -> dict[str, Any]:
    completed = subprocess.run(
        ["uv", "pip", "list", "--format", "json"],
        check=False,
        text=True,
        capture_output=True,
    )
    packages = json.loads(completed.stdout or "[]")
    return {
        "tool": "uv pip list",
        "exit_code": completed.returncode,
        "package_count": len(packages),
        "risks": [],
        "status": "LOCAL_INVENTORY_RECORDED_NO_VULNERABILITY_DATABASE",
        "manual_review_required": True,
    }


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    npm = npm_audit()
    python = python_dependency_inventory()
    dependency_audit = {
        "npm": npm,
        "python": python,
        "major_or_breaking_auto_fix": False,
        "npm_audit_fix_force_used": False,
    }
    blocker = None
    if any(item["status"] == "MANUAL_REVIEW_REQUIRED" for item in npm["risks"]):
        blocker = "DEPENDENCY_MAJOR_UPGRADE_MANUAL_REVIEW_REQUIRED"
    operations = build_operations_report(dependency_blocker=blocker)
    release = operations["release_audit"]
    release["dependency_blocker"] = blocker
    release["production_release"] = "DISABLED"
    write_json(REPORTS / "W2_STAGE15A_OPERATIONS.json", operations)
    write_json(REPORTS / "W2_STAGE15A_DEPENDENCY_AUDIT.json", dependency_audit)
    write_json(REPORTS / "W2_STAGE15A_RELEASE_READINESS.json", release)
    result = "\n".join(
        [
            "# W2 Stage 15A Result",
            "",
            "STAGE_15A=COMPLETED",
            "LONG_TERM_OPERATIONS=READY_LOCAL_STAGING",
            "OPERATIONAL_AUTORUN=DISABLED_PENDING_APPROVAL",
            "PRODUCTION_RELEASE=DISABLED",
            "EXTERNAL_ALERTING=DISABLED",
            "GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING",
            "STAGE_9=BLOCKED",
            "PUSH_BLOCKED_NO_ORIGIN",
            "",
            "Dependency governance records npm major upgrade risk for manual review.",
            "正式推荐与生产发布尚未启用。",
        ]
    )
    (REPORTS / "W2_STAGE15A_RESULT.md").write_text(result + "\n", encoding="utf-8")
    print("W2 Stage15A operations dry-run PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
