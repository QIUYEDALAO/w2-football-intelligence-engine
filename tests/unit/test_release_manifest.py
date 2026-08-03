from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from scripts.release_manifest import create, verify


def _args(path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        output=path,
        pr_number=480,
        source_sha="1" * 40,
        source_tree_sha="2" * 40,
        base_main_sha="3" * 40,
        workflow_run_id="123",
        change_class="runtime",
        quality_job=["static-contract=success", "unit-contract=success"],
        python_image_digest="sha256:" + "4" * 64,
        web_image_digest="sha256:" + "5" * 64,
        python_image_ref="ghcr.io/example/python@sha256:" + "4" * 64,
        web_image_ref="ghcr.io/example/web@sha256:" + "5" * 64,
    )


def test_release_manifest_round_trip_and_exact_identity(tmp_path: Path) -> None:
    path = tmp_path / "release-manifest.json"
    create(_args(path))
    verify(
        argparse.Namespace(
            manifest=path,
            expect=["source_sha=" + "1" * 40, "source_tree_sha=" + "2" * 40],
        )
    )


def test_release_manifest_rejects_tampering_and_safety_drift(tmp_path: Path) -> None:
    path = tmp_path / "release-manifest.json"
    create(_args(path))
    tampered = path.read_text(encoding="utf-8").replace(
        '"provider_calls": 0', '"provider_calls": 1'
    )
    path.write_text(tampered, encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        verify(argparse.Namespace(manifest=path, expect=[]))


def test_docs_manifest_requires_not_required_image_identity(tmp_path: Path) -> None:
    path = tmp_path / "release-manifest.json"
    args = _args(path)
    args.change_class = "docs"
    args.python_image_digest = "NOT_REQUIRED"
    args.web_image_digest = "NOT_REQUIRED"
    args.python_image_ref = "NOT_REQUIRED"
    args.web_image_ref = "NOT_REQUIRED"
    create(args)
    verify(argparse.Namespace(manifest=path, expect=[]))
