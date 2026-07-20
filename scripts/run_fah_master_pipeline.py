#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.formal.readiness import evaluate_formal_ah_readiness
from w2.historical.formal_ah import (
    audit_formal_ah_sources,
    build_canonical_ah_facts,
    stable_hash,
    write_audit_outputs,
)
from w2.lineups.value_identity import identity_value_audit, write_json_and_md

STATUS_DATA_REQUIRED = "DATA_REQUIRED"
STATUS_SOURCE_NOT_AVAILABLE = "SOURCE_NOT_AVAILABLE"
STATUS_MANUAL_APPROVAL_REQUIRED = "MANUAL_APPROVAL_REQUIRED"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the FAH master private-data pipeline.")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--database-url")
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True)
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()

    dry_run = not args.write
    if args.write and not args.database_url:
        parser.error("--write requires --database-url")
    data_root = args.data_root or _env_data_root()
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    started_at = _now()
    head = _git("rev-parse", "HEAD")
    source_tree_manifest_sha = _tree_hash()
    capability_sha = _file_hash(Path("config/capabilities/recommendation_capabilities.v1.json"))
    factor_sha = _file_hash(Path("config/factors/factor_registry.v1.json"))

    if data_root is None or not data_root.is_dir():
        return _write_no_data_package(
            artifact_root=args.artifact_root,
            pr_number=args.pr_number,
            started_at=started_at,
            head=head,
            source_tree_manifest_sha=source_tree_manifest_sha,
            capability_sha=capability_sha,
            factor_sha=factor_sha,
            dry_run=dry_run,
        )

    registry_path = data_root / "formal_ah_source_registry.v1.json"
    source_audit = audit_formal_ah_sources(source_root=data_root, registry_path=registry_path)
    write_audit_outputs(
        source_audit,
        json_path=args.artifact_root / "SOURCE_AUDIT.json",
        md_path=args.artifact_root / "SOURCE_AUDIT.md",
    )
    canonical = build_canonical_ah_facts(source_root=data_root, registry_path=registry_path)
    write_audit_outputs(
        canonical["audit"],
        json_path=args.artifact_root / "FAH_CANONICAL_FACT_AUDIT.json",
        md_path=args.artifact_root / "FAH_CANONICAL_FACT_AUDIT.md",
    )
    f8 = identity_value_audit(crosswalks=[], artifacts=[], source_root=data_root)
    write_json_and_md(f8, args.artifact_root / "FAH_F8_AUDIT.json")
    status = (
        "PASS_FOR_SHADOW"
        if canonical["audit"].get("canonical_fact_count", 0) > 0
        else "INSUFFICIENT_EVIDENCE"
    )
    package = _approval_package(
        artifact_root=args.artifact_root,
        pr_number=args.pr_number,
        head=head,
        source_tree_manifest_sha=source_tree_manifest_sha,
        capability_sha=capability_sha,
        factor_sha=factor_sha,
        status=status,
        conclusions=[
            status,
            "FORWARD_POLICY_UNVALIDATED_OR_INSUFFICIENT",
            STATUS_MANUAL_APPROVAL_REQUIRED,
        ],
        dry_run=dry_run,
    )
    _write_json(args.artifact_root / "FAH_APPROVAL_PACKAGE.json", package)
    _write_md(args.artifact_root / "FAH_APPROVAL_PACKAGE.md", package)
    return 0


def _write_no_data_package(
    *,
    artifact_root: Path,
    pr_number: int,
    started_at: str,
    head: str,
    source_tree_manifest_sha: str,
    capability_sha: str,
    factor_sha: str,
    dry_run: bool,
) -> int:
    data_request = {
        "schema_version": "w2.fah_private_data_request.v1",
        "status": STATUS_DATA_REQUIRED,
        "source_status": STATUS_SOURCE_NOT_AVAILABLE,
        "manual_stop": STATUS_MANUAL_APPROVAL_REQUIRED,
        "started_at": started_at,
        "required_env": "W2_FAH_DATA_ROOT",
        "expected_private_root": "/Users/liudehua/.hermes/data/w2/fah",
        "required_contracts": [
            "formal_ah_source_registry.v1.schema.json",
            "historical_market_observation.v1.schema.json",
            "historical_result.v1.schema.json",
            "team_crosswalk.v1.schema.json",
            "player_crosswalk.v1.schema.json",
            "registered_roster_snapshot.v1.schema.json",
            "player_valuation.v1.schema.json",
        ],
        "provider_calls": 0,
        "database_writes": 0,
        "staging_writes": 0,
        "production_access": 0,
    }
    source_audit = audit_formal_ah_sources(source_root=None, registry_path=None)
    calibration = _fail_closed_report(
        "w2.fah_calibration_artifact.v1",
        "INSUFFICIENT_EVIDENCE",
        code_sha=head,
        factor_registry_sha=factor_sha,
    )
    f5 = _fail_closed_report("w2.fah_f5_manifest.v1", STATUS_SOURCE_NOT_AVAILABLE)
    f8 = _fail_closed_report("w2.fah_f8_manifest.v1", STATUS_SOURCE_NOT_AVAILABLE)
    offline = _fail_closed_report("w2.fah_offline_evidence_report.v1", "INSUFFICIENT_EVIDENCE")
    forward = _fail_closed_report("w2.fah_forward_shadow_report.v1", "INSUFFICIENT_EVIDENCE")
    readiness = evaluate_formal_ah_readiness(
        calibration=calibration,
        f5_historical_ah=f5,
        f8_identity_value=f8,
        offline_evidence=offline,
        forward_shadow=forward,
        approval_manifest=None,
        capability_enabled=False,
    )
    outputs = {
        "DATA_REQUEST": data_request,
        "SOURCE_AUDIT": source_audit,
        "FAH_CALIBRATION_ARTIFACT": calibration,
        "FAH_F5_AUDIT": f5,
        "FAH_F8_AUDIT": f8,
        "FAH_OFFLINE_EVIDENCE_REPORT": offline,
        "FAH_FORWARD_SHADOW_REPORT": forward,
        "FAH_FORMAL_READINESS": readiness,
    }
    for name, payload in outputs.items():
        _write_json(artifact_root / f"{name}.json", payload)
        _write_md(artifact_root / f"{name}.md", payload)
    package = _approval_package(
        artifact_root=artifact_root,
        pr_number=pr_number,
        head=head,
        source_tree_manifest_sha=source_tree_manifest_sha,
        capability_sha=capability_sha,
        factor_sha=factor_sha,
        status=STATUS_DATA_REQUIRED,
        conclusions=[
            STATUS_DATA_REQUIRED,
            STATUS_SOURCE_NOT_AVAILABLE,
            "CODE_PIPELINE_READY_FOR_PRIVATE_DATA",
            STATUS_MANUAL_APPROVAL_REQUIRED,
        ],
        dry_run=dry_run,
    )
    _write_json(artifact_root / "FAH_APPROVAL_PACKAGE.json", package)
    _write_md(artifact_root / "FAH_APPROVAL_PACKAGE.md", package)
    return 0


def _approval_package(
    *,
    artifact_root: Path,
    pr_number: int,
    head: str,
    source_tree_manifest_sha: str,
    capability_sha: str,
    factor_sha: str,
    status: str,
    conclusions: list[str],
    dry_run: bool,
) -> dict[str, Any]:
    files = sorted(path for path in artifact_root.glob("*") if path.is_file())
    file_hashes = {
        path.name: _file_hash(path)
        for path in files
        if path.name != "FAH_APPROVAL_PACKAGE.json"
    }
    payload = {
        "schema_version": "w2.fah_master_approval_package.v1",
        "status": status,
        "manual_stop": STATUS_MANUAL_APPROVAL_REQUIRED,
        "implementation_head_sha": head,
        "pr_number": pr_number,
        "source_tree_manifest_sha": source_tree_manifest_sha,
        "capability_manifest_sha": capability_sha,
        "factor_registry_sha": factor_sha,
        "artifact_file_hashes": file_hashes,
        "sample_counts": {"formal_ah": 0, "forward_shadow": 0},
        "blockers": [item for item in conclusions if item != "PASS_FOR_SHADOW"],
        "conclusions": conclusions,
        "dry_run": dry_run,
        "provider_calls": 0,
        "provider_call_count": 0,
        "staging_writes": 0,
        "staging_write_count": 0,
        "production_access": 0,
        "production_write_count": 0,
        "recommendation_writes": 0,
        "lock_writes": 0,
        "lock_attempt_count": 0,
        "official_writes": 0,
        "official_status_count": 0,
        "generated_at": _now(),
    }
    payload["approval_package_hash"] = stable_hash(payload)
    return payload


def _fail_closed_report(
    schema_version: str,
    status: str,
    *,
    code_sha: str | None = None,
    factor_registry_sha: str | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": schema_version,
        "status": status,
        "conclusion": status,
        "sample_count": 0,
        "accepted_row_count": 0,
        "rejected_row_count": 0,
        "blockers": [status],
        "provider_calls": 0,
    }
    if code_sha is not None:
        payload["code_sha"] = code_sha
    if factor_registry_sha is not None:
        payload["factor_registry_sha"] = factor_registry_sha
    payload["report_hash"] = stable_hash(payload)
    payload["artifact_hash"] = payload["report_hash"]
    payload["manifest_hash"] = payload["report_hash"]
    return payload


def _env_data_root() -> Path | None:
    value = os.getenv("W2_FAH_DATA_ROOT")
    return Path(value) if value else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_md(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        f"# {payload.get('schema_version', path.stem)}",
        "",
        f"- status: {payload.get('status')}",
    ]
    if "manual_stop" in payload:
        lines.append(f"- manual_stop: {payload['manual_stop']}")
    if "conclusions" in payload:
        lines.append(f"- conclusions: {payload['conclusions']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_hash() -> str:
    tracked = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        text=True,
    ).splitlines()
    rows = []
    for raw_path in sorted(tracked):
        path = Path(raw_path)
        if path.is_file() and ".git" not in path.parts:
            rows.append({"path": str(path), "sha256": _file_hash(path)})
    return stable_hash({"files": rows})


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def _now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
