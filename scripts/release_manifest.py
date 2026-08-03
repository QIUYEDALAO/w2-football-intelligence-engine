#!/usr/bin/env python3
"""Create and verify immutable W2 release-candidate manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REF_RE = re.compile(r"^ghcr\.io/[a-z0-9._/-]+@(sha256:[0-9a-f]{64})$")


def _boolean(value: str) -> bool:
    if value not in {"true", "false"}:
        raise ValueError(f"invalid boolean: {value}")
    return value == "true"


def _pairs(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not key or not item:
            raise ValueError(f"invalid KEY=VALUE: {value}")
        result[key] = item
    return result


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create(args: argparse.Namespace) -> None:
    quality = _pairs(args.quality_job)
    if not quality or any(value != "success" for value in quality.values()):
        raise ValueError("all quality jobs must be present and successful")
    images_required = _boolean(args.images_required)
    deployable = _boolean(args.deployable)
    if deployable and not images_required:
        raise ValueError("deployable release must require images")
    for digest in (args.python_image_digest, args.web_image_digest):
        if not images_required:
            if digest != "NOT_REQUIRED":
                raise ValueError("non-image release digests must be NOT_REQUIRED")
        elif not DIGEST_RE.fullmatch(digest):
            raise ValueError("runtime image digest is invalid")
    for reference, digest in (
        (args.python_image_ref, args.python_image_digest),
        (args.web_image_ref, args.web_image_digest),
    ):
        if not images_required and reference != "NOT_REQUIRED":
            raise ValueError("non-image release references must be NOT_REQUIRED")
        if images_required and (match := REF_RE.fullmatch(reference)) is None:
            raise ValueError("runtime image reference is invalid")
        if images_required and match.group(1) != digest:
            raise ValueError("runtime image reference and digest differ")
    payload: dict[str, Any] = {
        "schema_version": "w2.release-candidate.v1",
        "pr_number": args.pr_number,
        "source_sha": args.source_sha,
        "source_tree_sha": args.source_tree_sha,
        "base_main_sha": args.base_main_sha,
        "workflow_run_id": args.workflow_run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "change_class": args.change_class,
        "quality_required": args.quality_required,
        "images_required": images_required,
        "deployable": deployable,
        "quality_jobs": quality,
        "python_image_digest": args.python_image_digest,
        "web_image_digest": args.web_image_digest,
        "python_image_ref": args.python_image_ref,
        "web_image_ref": args.web_image_ref,
        "full_ci_passed": True,
        "image_smoke_passed": True,
        "provider_calls": 0,
        "candidate": False,
        "formal": False,
        "lock": False,
        "production": False,
        "rehearsal": args.pr_number == 0,
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        f"{sha256(args.output)}  {args.output.name}\n", encoding="utf-8"
    )


def verify(args: argparse.Namespace) -> None:
    sidecar = args.manifest.with_suffix(args.manifest.suffix + ".sha256")
    expected_digest = sidecar.read_text(encoding="utf-8").split()[0]
    if expected_digest != sha256(args.manifest):
        raise ValueError("release manifest SHA-256 mismatch")
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "pr_number",
        "source_sha",
        "source_tree_sha",
        "base_main_sha",
        "workflow_run_id",
        "created_at",
        "change_class",
        "quality_required",
        "images_required",
        "deployable",
        "quality_jobs",
        "python_image_digest",
        "web_image_digest",
        "python_image_ref",
        "web_image_ref",
        "full_ci_passed",
        "image_smoke_passed",
        "provider_calls",
        "candidate",
        "formal",
        "lock",
        "production",
    }
    if required - payload.keys():
        raise ValueError(f"release manifest missing fields: {sorted(required - payload.keys())}")
    if payload["schema_version"] != "w2.release-candidate.v1":
        raise ValueError("unsupported release manifest schema")
    for field in ("source_sha", "source_tree_sha", "base_main_sha"):
        if not SHA_RE.fullmatch(str(payload[field])):
            raise ValueError(f"invalid {field}")
    for field in ("full_ci_passed", "image_smoke_passed"):
        if payload[field] is not True:
            raise ValueError(f"{field} must be true")
    if payload["provider_calls"] != 0 or any(
        payload[field] is not False for field in ("candidate", "formal", "lock", "production")
    ):
        raise ValueError("release manifest safety boundary changed")
    expected = _pairs(args.expect)
    for field, value in expected.items():
        if str(payload.get(field)) != value:
            raise ValueError(f"release manifest {field} mismatch")
    if payload["quality_required"] not in {"DOCS", "FULL"}:
        raise ValueError("invalid quality_required")
    images_required = payload["images_required"]
    deployable = payload["deployable"]
    if not isinstance(images_required, bool) or not isinstance(deployable, bool):
        raise ValueError("release booleans are invalid")
    if deployable and not images_required:
        raise ValueError("deployable release must require images")
    for field in ("python_image_digest", "web_image_digest"):
        value = str(payload[field])
        if not images_required and value != "NOT_REQUIRED":
            raise ValueError(f"non-image {field} must be NOT_REQUIRED")
        if images_required and not DIGEST_RE.fullmatch(value):
            raise ValueError(f"runtime {field} is invalid")
    for reference_field, digest_field in (
        ("python_image_ref", "python_image_digest"),
        ("web_image_ref", "web_image_digest"),
    ):
        reference = str(payload[reference_field])
        if not images_required and reference != "NOT_REQUIRED":
            raise ValueError(f"non-image {reference_field} must be NOT_REQUIRED")
        if images_required and (match := REF_RE.fullmatch(reference)) is None:
            raise ValueError(f"runtime {reference_field} is invalid")
        if images_required and match.group(1) != payload[digest_field]:
            raise ValueError(f"runtime {reference_field} and {digest_field} differ")
    print(expected_digest)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--output", type=Path, required=True)
    create_parser.add_argument("--pr-number", type=int, required=True)
    create_parser.add_argument("--source-sha", required=True)
    create_parser.add_argument("--source-tree-sha", required=True)
    create_parser.add_argument("--base-main-sha", required=True)
    create_parser.add_argument("--workflow-run-id", required=True)
    create_parser.add_argument("--change-class", required=True)
    create_parser.add_argument("--quality-required", choices=("DOCS", "FULL"), required=True)
    create_parser.add_argument("--images-required", required=True)
    create_parser.add_argument("--deployable", required=True)
    create_parser.add_argument("--quality-job", action="append", default=[])
    create_parser.add_argument("--python-image-digest", required=True)
    create_parser.add_argument("--web-image-digest", required=True)
    create_parser.add_argument("--python-image-ref", required=True)
    create_parser.add_argument("--web-image-ref", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--expect", action="append", default=[])
    args = parser.parse_args()
    if args.command == "create":
        create(args)
    else:
        verify(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
