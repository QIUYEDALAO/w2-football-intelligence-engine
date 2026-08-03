from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest
from scripts.classify_ci import changed_paths, classify, resolve_plan


def test_docs_only_requires_docs_quality_without_images_or_deploy() -> None:
    plan = classify(["PROJECT_STATE.yaml", "docs/operations/runbook.md"])
    assert plan.outputs() == {
        "change_class": "docs",
        "quality_required": "DOCS",
        "images_required": "false",
        "deployable": "false",
    }


def test_delivery_paths_require_full_quality_without_images_or_deploy() -> None:
    paths = (
        ".github/workflows/release-candidate.yml",
        "scripts/release/finalize_pr.sh",
        "scripts/ci_shards.py",
        "scripts/release_manifest.py",
        "scripts/dev_check.py",
        "scripts/classify_ci.py",
        "ci/pytest_durations.v1.json",
        "tests/contract/test_delivery_pipeline.py",
        "tests/contract/test_arch_p2_05_final_acceptance.py",
        "tests/unit/test_ci_classifier.py",
        "tests/unit/test_ci_shards.py",
        "tests/unit/test_release_manifest.py",
        "docs/operations/W2_DELIVERY_PIPELINE_LEAD_TIME_RECOVERY.md",
    )
    for path in paths:
        plan = classify([path])
        assert plan.change_class == "delivery"
        assert plan.quality_required == "FULL"
        assert not plan.images_required
        assert not plan.deployable


def test_runtime_web_and_python_are_deployable_full_quality() -> None:
    for path, expected in (
        ("src/w2/domain/model.py", "python"),
        ("apps/web/src/page.tsx", "web"),
        ("migrations/versions/0044_example.py", "runtime"),
        ("infra/compose/compose.staging.yml", "runtime"),
    ):
        plan = classify([path])
        assert plan.change_class == expected
        assert plan.quality_required == "FULL"
        assert plan.images_required and plan.deployable


def test_mixed_unknown_empty_and_invalid_diff_fail_closed() -> None:
    for paths in (["src/w2/domain/model.py", "apps/web/src/page.tsx"], ["unexpected.bin"], []):
        plan = classify(paths)
        assert plan.change_class == "unknown"
        assert plan.quality_required == "FULL"
        assert plan.images_required and plan.deployable


def test_force_full_keeps_docs_non_deployable() -> None:
    plan = classify(["docs/readme.md"], force_full=True)
    assert plan.change_class == "docs"
    assert plan.quality_required == "FULL"
    assert not plan.images_required and not plan.deployable


def test_rename_classifies_old_and_new_paths_without_runtime_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        seen.extend(command)
        return SimpleNamespace(stdout="src/w2/domain/model.py\ndocs/model.md\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    paths = changed_paths("a" * 40, "b" * 40)
    assert "--no-renames" in seen
    assert classify(paths).change_class == "python"


def test_invalid_diff_base_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise subprocess.CalledProcessError(128, ["git", "diff"])

    monkeypatch.setattr(subprocess, "run", fail)
    assert resolve_plan("invalid", "b" * 40).change_class == "unknown"


def test_valid_main_push_range_is_classified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="docs/runbook.md\n"),
    )
    assert resolve_plan("a" * 40, "b" * 40).quality_required == "DOCS"
