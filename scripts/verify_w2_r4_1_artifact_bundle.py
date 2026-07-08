#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tarfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(REPO_ROOT / "src"))

from build_w2_r4_1_artifact_bundle import (  # noqa: E402
    BUNDLE_SCHEMA_VERSION,
    CANONICAL_PRICING_SHADOW_KEY,
)

from w2.models.r4_1_artifacts import compute_r4_1_artifact_hash  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = verify_artifact_bundle(args.bundle)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(report["status"])
    return 0 if report["status"] == "PASS" else 1


def verify_artifact_bundle(bundle: Path) -> dict[str, Any]:
    blockers: list[str] = []
    manifest: dict[str, Any] = {}
    artifact_reports: list[dict[str, Any]] = []
    try:
        with tarfile.open(bundle, "r:gz") as tar:
            members = {member.name: member for member in tar.getmembers()}
            blockers.extend(_path_blockers(members))
            manifest = _read_json_member(tar, members, "manifest.json", blockers)
            if manifest:
                blockers.extend(_manifest_blockers(manifest))
                artifact_reports.extend(
                    _verify_artifacts(
                        tar=tar,
                        members=members,
                        manifest=manifest,
                        blockers=blockers,
                    )
                )
    except (tarfile.TarError, OSError, json.JSONDecodeError, KeyError, TypeError):
        blockers.append("BUNDLE_UNREADABLE")
    status = "PASS" if not blockers else "FAIL"
    return {
        "status": status,
        "provider_calls": 0,
        "bundle_path": bundle.as_posix(),
        "git_sha": manifest.get("git_sha"),
        "competition_ids": manifest.get("competition_ids", []),
        "canonical_pricing_shadow_key": manifest.get("canonical_pricing_shadow_key"),
        "artifact_count": len(artifact_reports),
        "artifacts": artifact_reports,
        "blockers": blockers,
    }


def _path_blockers(members: dict[str, tarfile.TarInfo]) -> list[str]:
    blockers = []
    for name in members:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            blockers.append(f"UNSAFE_BUNDLE_PATH:{name}")
    return blockers


def _manifest_blockers(manifest: dict[str, Any]) -> list[str]:
    blockers = []
    required = (
        "schema_version",
        "git_sha",
        "artifact_version",
        "competition_ids",
        "artifact_hashes",
        "train_cutoff",
        "protocol_identity_status",
        "canonical_pricing_shadow_key",
        "artifacts",
    )
    for key in required:
        if key not in manifest:
            blockers.append(f"MISSING_MANIFEST_FIELD:{key}")
    if manifest.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        blockers.append("INVALID_BUNDLE_SCHEMA_VERSION")
    if manifest.get("canonical_pricing_shadow_key") != CANONICAL_PRICING_SHADOW_KEY:
        blockers.append("INVALID_CANONICAL_PRICING_SHADOW_KEY")
    competition_ids = manifest.get("competition_ids") or []
    if "brasileirao_serie_a" in competition_ids:
        blockers.append("BRAZIL_GUARD_VIOLATED")
    disabled = manifest.get("disabled_competitions") or []
    if "brasileirao_serie_a" not in disabled:
        blockers.append("BRAZIL_GUARD_MISSING")
    return blockers


def _verify_artifacts(
    *,
    tar: tarfile.TarFile,
    members: dict[str, tarfile.TarInfo],
    manifest: dict[str, Any],
    blockers: list[str],
) -> list[dict[str, Any]]:
    reports = []
    artifacts = manifest.get("artifacts") or []
    hashes = manifest.get("artifact_hashes") or {}
    cutoffs = manifest.get("train_cutoff") or {}
    protocols = manifest.get("protocol_identity_status") or {}
    for item in artifacts:
        if not isinstance(item, dict):
            blockers.append("INVALID_ARTIFACT_MANIFEST_ITEM")
            continue
        competition_id = str(item.get("competition_id") or "")
        path = str(item.get("path") or "")
        if path not in members:
            blockers.append(f"MISSING_ARTIFACT:{competition_id}")
            continue
        payload = _read_json_member(tar, members, path, blockers)
        if not payload:
            blockers.append(f"INVALID_ARTIFACT_JSON:{competition_id}")
            continue
        actual_hash = compute_r4_1_artifact_hash(payload)
        expected_hash = str(hashes.get(competition_id) or item.get("artifact_hash") or "")
        if actual_hash != expected_hash:
            blockers.append(f"ARTIFACT_HASH_MISMATCH:{competition_id}")
        if payload.get("artifact_hash") != actual_hash:
            blockers.append(f"ARTIFACT_PAYLOAD_HASH_MISMATCH:{competition_id}")
        if not cutoffs.get(competition_id) or not payload.get("train_cutoff_utc"):
            blockers.append(f"MISSING_TRAIN_CUTOFF:{competition_id}")
        if protocols.get(competition_id) != "PASS":
            blockers.append(f"PROTOCOL_IDENTITY_NOT_PASS:{competition_id}")
        reports.append(
            {
                "competition_id": competition_id,
                "path": path,
                "artifact_hash": actual_hash,
                "train_cutoff_utc": payload.get("train_cutoff_utc"),
                "protocol_identity_check": protocols.get(competition_id),
            }
        )
    if len(reports) != len(manifest.get("competition_ids") or []):
        blockers.append("ARTIFACT_COUNT_MISMATCH")
    return reports


def _read_json_member(
    tar: tarfile.TarFile,
    members: dict[str, tarfile.TarInfo],
    name: str,
    blockers: list[str],
) -> dict[str, Any]:
    member = members.get(name)
    if member is None:
        blockers.append(f"MISSING_BUNDLE_MEMBER:{name}")
        return {}
    extracted = tar.extractfile(member)
    if extracted is None:
        blockers.append(f"UNREADABLE_BUNDLE_MEMBER:{name}")
        return {}
    payload = json.loads(extracted.read().decode("utf-8"))
    if not isinstance(payload, dict):
        blockers.append(f"INVALID_JSON_OBJECT:{name}")
        return {}
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
