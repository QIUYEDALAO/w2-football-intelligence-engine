from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "fah_master_evidence_closure"
MISSING_INPUTS = [
    "captured-at historical market data",
    "licensed source metadata",
    "canonical fixture/team identities",
    "90-minute results",
    "same-batch 1X2/AH/OU",
    "closing quotes",
    "team crosswalks",
    "player crosswalks",
    "registered roster snapshots",
    "historical valuations",
]


def main() -> None:
    data_root = os.environ.get("W2_FAH_DATA_ROOT", "")
    data_root_path = Path(data_root) if data_root else None
    data_available = bool(data_root_path and data_root_path.is_dir())
    if data_available:
        raise SystemExit(
            "REAL_DATA_INTAKE_NOT_RUN_BY_DEFAULT: use the audited importer workflow "
            "with an isolated database"
        )

    OUT.mkdir(parents=True, exist_ok=True)
    code_sha = _git("rev-parse", "HEAD")
    capability_sha = _blob_sha("config/capabilities/recommendation_capabilities.v1.json")
    factor_sha = _blob_sha("config/factors/factor_registry.v1.json")
    allsvenskan_sha = _blob_sha("config/competitions/national_leagues/allsvenskan.v1.json")
    apps_web_tree = _git("rev-parse", "HEAD:apps/web")

    data_request = {
        "schema_version": "w2.fah.data_request.v1",
        "status": "DATA_REQUIRED",
        "source_status": "SOURCE_NOT_AVAILABLE",
        "w2_fah_data_root": data_root,
        "data_root_exists": False,
        "missing_inputs": MISSING_INPUTS,
        "instructions": [
            "Provide W2_FAH_DATA_ROOT only after private licensed files are placed "
            "under that directory.",
            "Do not commit raw data, license files, or crosswalk files to GitHub.",
        ],
    }
    source_audit = {
        "schema_version": "w2.fah.source_audit.v1",
        "status": "SOURCE_NOT_AVAILABLE",
        "approved_source_count": 0,
        "source_files": [],
        "file_hashes": {},
        "license_statuses": {},
        "blocked_reasons": {"W2_FAH_DATA_ROOT_MISSING": 1},
    }
    canonical_fact_audit = _empty_audit(
        "w2.fah.canonical_fact_audit.v1",
        "SOURCE_NOT_AVAILABLE",
        canonical_fact_count=0,
        imported_rows=0,
        conflicts=0,
    )
    f5_audit = _empty_audit(
        "w2.fah.f5_audit.v1",
        "MISSING_AH_EVIDENCE",
        real_decisive_samples=0,
        pushes=0,
    )
    f8_audit = _empty_audit(
        "w2.fah.f8_audit.v1",
        "SOURCE_NOT_AVAILABLE",
        team_mapping_coverage=0,
        player_mapping_coverage=0,
        roster_snapshots=0,
        valuation_coverage=0,
    )
    market_baseline = _empty_audit(
        "w2.fah.market_baseline_audit.v1",
        "SOURCE_NOT_AVAILABLE",
        fitted_coverage=0,
        method="FIVE_STATE_FAIR_ODDS_ZERO_EV_RESIDUALS",
    )
    calibration = {
        "schema_version": "w2.calibration_artifact.v1",
        "status": "INSUFFICIENT_EVIDENCE",
        "publicly_active": False,
        "production_active": False,
        "train_count": 0,
        "validation_count": 0,
        "holdout_count": 0,
        "accepted_row_count": 0,
        "rejected_row_count": 0,
        "artifact_hash": "",
    }
    offline_report = {
        "schema_version": "w2.fah.offline_evidence_report.v1",
        "conclusion": "INSUFFICIENT_EVIDENCE",
        "accepted": 0,
        "rejected": 0,
        "train_count": 0,
        "validation_count": 0,
        "holdout_count": 0,
        "blockers": ["DATA_REQUIRED", "SOURCE_NOT_AVAILABLE"],
    }
    forward_report = {
        "schema_version": "w2.forward_shadow_evidence_report.v1",
        "conclusion": "INSUFFICIENT_EVIDENCE",
        "real_formal_evidence_count": 0,
        "remaining_count": 200,
        "report_hash": "",
    }
    formal_readiness = {
        "schema_version": "w2.formal_ah_readiness.v1",
        "global_evidence_ready": False,
        "fixture_evidence_ready": False,
        "human_approved": False,
        "capability_enabled": False,
        "formal_eligible": False,
        "blockers": [
            "DATA_REQUIRED",
            "SOURCE_NOT_AVAILABLE",
            "FORMAL_ACTUAL_ARTIFACT_HASH_MISSING",
            "FORMAL_HUMAN_APPROVAL_MISSING",
            "FORMAL_AH_CAPABILITY_DISABLED",
        ],
    }

    payloads = {
        "DATA_REQUEST": data_request,
        "SOURCE_AUDIT": source_audit,
        "FAH_CODE_AUDIT": {
            "schema_version": "w2.fah.code_audit.v1",
            "status": "CODE_COMPLETE_DATA_PENDING",
            "code_sha": code_sha,
            "capability_manifest_sha": capability_sha,
            "factor_registry_sha": factor_sha,
            "allsvenskan_config_sha": allsvenskan_sha,
            "apps_web_tree_hash": apps_web_tree,
            "provider_calls": 0,
            "staging_writes": 0,
            "production_access": 0,
            "recommendation_writes": 0,
            "lock_writes": 0,
            "official_writes": 0,
        },
        "FAH_SOURCE_AUDIT": source_audit,
        "FAH_CANONICAL_FACT_AUDIT": canonical_fact_audit,
        "FAH_F5_AUDIT": f5_audit,
        "FAH_F8_AUDIT": f8_audit,
        "FAH_MARKET_BASELINE_AUDIT": market_baseline,
        "FAH_CALIBRATION_ARTIFACT": calibration,
        "FAH_OFFLINE_EVIDENCE_REPORT": offline_report,
        "FAH_FORWARD_SHADOW_REPORT": forward_report,
        "FAH_FORMAL_READINESS": formal_readiness,
    }
    sha_manifest: dict[str, str] = {}
    for name, payload in payloads.items():
        payload = dict(payload)
        payload.setdefault("sha256", _stable_hash(payload))
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (OUT / f"{name}.md").write_text(_md(name, payload), encoding="utf-8")
        sha_manifest[f"{name}.json"] = _file_sha(path)

    approval_package = {
        "schema_version": "w2.fah.approval_package.v1",
        "status": "MANUAL_APPROVAL_REQUIRED",
        "code_sha": code_sha,
        "pr_number": None,
        "capability_manifest_sha": capability_sha,
        "factor_registry_sha": factor_sha,
        "source_manifest_sha": sha_manifest["FAH_SOURCE_AUDIT.json"],
        "canonical_fact_manifest_sha": sha_manifest["FAH_CANONICAL_FACT_AUDIT.json"],
        "f5_manifest_sha": sha_manifest["FAH_F5_AUDIT.json"],
        "f8_manifest_sha": sha_manifest["FAH_F8_AUDIT.json"],
        "market_baseline_manifest_sha": sha_manifest["FAH_MARKET_BASELINE_AUDIT.json"],
        "calibration_artifact_sha": sha_manifest["FAH_CALIBRATION_ARTIFACT.json"],
        "offline_evidence_report_sha": sha_manifest["FAH_OFFLINE_EVIDENCE_REPORT.json"],
        "forward_report_sha": sha_manifest["FAH_FORWARD_SHADOW_REPORT.json"],
        "formal_readiness_sha": sha_manifest["FAH_FORMAL_READINESS.json"],
        "sample_counts": {"train": 0, "validation": 0, "holdout": 0, "forward": 0},
        "all_blockers": ["DATA_REQUIRED", "SOURCE_NOT_AVAILABLE"],
        "all_conclusions": [
            "DATA_REQUIRED",
            "SOURCE_NOT_AVAILABLE",
            "CODE_COMPLETE_DATA_PENDING",
            "MANUAL_APPROVAL_REQUIRED",
        ],
        "capabilities": {
            "formal_ah": False,
            "formal_ou": False,
            "lineup_numeric_adjustment_ah": False,
            "lineup_numeric_adjustment_ou": False,
            "recommendation_lock": False,
            "production_recommendation": False,
        },
        "writes_and_calls": {
            "provider_calls": 0,
            "staging_writes": 0,
            "production_access": 0,
            "official_captures": 0,
            "new_recommendation_ids": 0,
            "new_locks": 0,
        },
        "sha256_manifest": sha_manifest,
    }
    approval_package["sha256"] = _stable_hash(approval_package)
    approval_path = OUT / "FAH_APPROVAL_PACKAGE.json"
    approval_path.write_text(
        json.dumps(approval_package, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (OUT / "FAH_APPROVAL_PACKAGE.md").write_text(
        _md("FAH_APPROVAL_PACKAGE", approval_package),
        encoding="utf-8",
    )


def _empty_audit(schema: str, status: str, **values: Any) -> dict[str, Any]:
    return {"schema_version": schema, "status": status, **values}


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _blob_sha(path: str) -> str:
    return _git("rev-parse", f"HEAD:{path}")


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _md(name: str, payload: dict[str, Any]) -> str:
    lines = [f"# {name}", "", f"- status: {payload.get('status') or payload.get('conclusion')}"]
    for key in ("source_status", "code_sha", "sha256", "formal_eligible"):
        if key in payload:
            lines.append(f"- {key}: {payload[key]}")
    blockers = payload.get("blockers") or payload.get("all_blockers")
    if blockers:
        lines.append(f"- blockers: {blockers}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
