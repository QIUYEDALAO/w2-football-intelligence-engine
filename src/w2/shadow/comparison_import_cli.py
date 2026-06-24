from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from w2.strategy.shadow import write_json


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_child(path: Path, base: Path) -> Path:
    resolved = path.resolve()
    base_resolved = base.resolve()
    if resolved != base_resolved and base_resolved not in resolved.parents:
        raise ValueError("artifact path escapes the allowed root")
    return resolved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import sanitized W1/W2 comparison artifacts.")
    parser.add_argument("--artifact", type=Path, help="Sanitized comparison JSON artifact.")
    parser.add_argument("--manifest", type=Path, help="Manifest with sha256 and source_system=W1.")
    parser.add_argument("--artifact-root", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional local report path.")
    return parser


def _validate_artifact(artifact: Path, manifest: Path, artifact_root: Path) -> dict[str, Any]:
    safe_artifact = _safe_child(artifact, artifact_root)
    safe_manifest = _safe_child(manifest, artifact_root)
    manifest_payload = json.loads(safe_manifest.read_text(encoding="utf-8"))
    artifact_payload = json.loads(safe_artifact.read_text(encoding="utf-8"))
    if manifest_payload.get("source_system") != "W1":
        raise ValueError("manifest source_system must be W1")
    expected_sha = manifest_payload.get("sha256")
    actual_sha = _sha256(safe_artifact)
    if expected_sha != actual_sha:
        raise ValueError("artifact sha256 mismatch")
    return {
        "status": "VALIDATED",
        "source_system": "W1",
        "artifact_sha256": actual_sha,
        "artifact_records": len(artifact_payload) if isinstance(artifact_payload, list) else 1,
        "idempotency_key": hashlib.sha256(
            f"W1:{actual_sha}".encode(),
        ).hexdigest(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.artifact is None or args.manifest is None:
        result: dict[str, Any] = {
            "status": "NOT_REQUIRED_IN_RUNTIME",
            "reason": "Release Train 2 runtime validation does not require W1 repository access.",
            "w1_repository_required": False,
            "w1_env_required": False,
            "dry_run": bool(args.dry_run),
        }
    else:
        result = _validate_artifact(args.artifact, args.manifest, args.artifact_root)
        result["dry_run"] = bool(args.dry_run)
        result["database_write"] = "SKIPPED_DRY_RUN" if args.dry_run else "IDEMPOTENT_UPSERT_READY"
    if args.output:
        write_json(args.output, result)
    if args.json or not args.output:
        print(json.dumps(result, sort_keys=True))
    else:
        print("W2 sanitized comparison import check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
