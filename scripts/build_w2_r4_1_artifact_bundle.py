#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(REPO_ROOT / "src"))

from publish_w2_r4_1_artifacts import publish_artifacts  # noqa: E402

BUNDLE_SCHEMA_VERSION = "w2_r4_1_artifact_bundle.v1"
CANONICAL_PRICING_SHADOW_KEY = "pricing_shadow.r4_1_calibrated"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_artifact_bundle(args.out_dir)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(report["bundle_path"])
    return 0 if report["status"] == "PASS" else 1


def build_artifact_bundle(
    out_dir: Path,
    *,
    git_sha: str | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    sha = git_sha or _git_sha()
    created = created_at or datetime.now(UTC)
    with tempfile.TemporaryDirectory(prefix="w2-r4-1-artifacts-") as tmp_name:
        artifact_dir = Path(tmp_name) / "runtime" / "model_artifacts" / "r4_1"
        publish_report = publish_artifacts(artifact_dir)
        artifacts = _artifact_entries(publish_report)
        manifest = _build_manifest(
            git_sha=sha,
            created_at=created,
            publish_report=publish_report,
            artifacts=artifacts,
        )
        manifest_path = Path(tmp_name) / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        bundle_path = out_dir / f"w2_r4_1_artifacts_{sha}.tar.gz"
        with tarfile.open(bundle_path, "w:gz") as tar:
            tar.add(manifest_path, arcname="manifest.json")
            for item in artifacts:
                tar.add(Path(item["source_path"]), arcname=f"artifacts/{item['file_name']}")
    return {
        "status": "PASS",
        "provider_calls": 0,
        "bundle_path": bundle_path.as_posix(),
        "manifest": manifest,
    }


def _artifact_entries(publish_report: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = []
    for item in publish_report.get("artifacts", []):
        path = Path(str(item["artifact_path"]))
        artifacts.append(
            {
                "competition_id": str(item["competition_id"]),
                "file_name": path.name,
                "source_path": path.as_posix(),
                "artifact_hash": str(item["artifact_hash"]),
                "artifact_version": "v1",
                "train_cutoff_utc": str(item["train_cutoff_utc"]),
                "protocol_identity_check": str(item["protocol_identity_check"]),
            }
        )
    return artifacts


def _build_manifest(
    *,
    git_sha: str,
    created_at: datetime,
    publish_report: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    competition_ids = [item["competition_id"] for item in artifacts]
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "git_sha": git_sha,
        "created_at": _iso_utc(created_at),
        "canonical_pricing_shadow_key": CANONICAL_PRICING_SHADOW_KEY,
        "artifact_version": "v1",
        "competition_ids": competition_ids,
        "artifact_hashes": {
            item["competition_id"]: item["artifact_hash"] for item in artifacts
        },
        "train_cutoff": {
            item["competition_id"]: item["train_cutoff_utc"] for item in artifacts
        },
        "protocol_identity_status": {
            item["competition_id"]: item["protocol_identity_check"]
            for item in artifacts
        },
        "artifacts": [
            {
                "competition_id": item["competition_id"],
                "path": f"artifacts/{item['file_name']}",
                "artifact_hash": item["artifact_hash"],
                "artifact_version": item["artifact_version"],
                "train_cutoff_utc": item["train_cutoff_utc"],
                "protocol_identity_check": item["protocol_identity_check"],
            }
            for item in artifacts
        ],
        "protocol_identity": publish_report.get("protocol_identity", []),
        "disabled_competitions": publish_report.get("disabled_competitions", []),
        "provider_calls": 0,
    }


def _git_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
    ).strip()


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
