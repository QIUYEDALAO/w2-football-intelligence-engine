from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from scripts.classify_ci import (
    CI_JOB_NAMES,
    changed_paths,
    ci_required_passes,
    classify,
    resolve_plan,
)

ROOT = Path(__file__).resolve().parents[2]


def test_docs_only_schedules_no_runtime_jobs() -> None:
    plan = classify(
        [
            "PROJECT_STATE.yaml",
            "docs/operations/runbook.md",
            "tests/contract/test_delivery_status_documentation.py",
        ]
    )
    assert not any(
        (
            plan.python_focused,
            plan.web,
            plan.migration,
            plan.compose,
            plan.staging_parity,
            plan.predeploy_e2e,
            plan.verify,
            plan.images,
        )
    )


def test_python_web_migration_and_infra_schedule_their_jobs() -> None:
    assert classify(["src/w2/domain/model.py"]).python_focused
    assert classify(["apps/web/src/page.tsx"]).web

    migration = classify(["migrations/versions/0044_example.py"])
    assert migration.full and migration.migration and migration.verify

    infra = classify(["infra/compose/compose.staging.yml"])
    assert infra.compose and infra.staging_parity and infra.predeploy_e2e
    assert infra.images
    assert not infra.verify


def test_python_scripts_keep_python_domain_and_deploy_python_is_full() -> None:
    assert classify(["scripts/audit_example.py"]).python_focused
    assert classify(["scripts/deploy_example.py"]).full
    shell = classify(["scripts/deploy_example.sh"])
    assert shell.compose and shell.staging_parity and not shell.verify


def test_ci_control_files_always_force_full() -> None:
    for path in (
        ".github/workflows/ci.yml",
        "scripts/classify_ci.py",
        "scripts/check_w2_all.py",
    ):
        assert classify([path]).full


def test_mixed_unknown_empty_and_forced_plans_fail_safe_to_full_ci() -> None:
    for paths in (
        ["src/w2/domain/model.py", "apps/web/src/page.tsx"],
        ["unexpected.bin"],
        [],
    ):
        plan = classify(paths)
        assert plan.full and plan.verify
        assert plan.web and plan.migration
        assert plan.compose and plan.staging_parity and plan.predeploy_e2e
    assert classify(["docs/readme.md"], force_full=True).full


def test_ci_required_strictly_matches_success_and_skipped_results() -> None:
    plan = classify(["infra/compose/compose.staging.yml"])
    expected = {job: getattr(plan, job) for job in CI_JOB_NAMES}
    results = {
        "classify": "success",
        **{job: "success" if expected[job] else "skipped" for job in CI_JOB_NAMES},
    }
    assert ci_required_passes(expected, results)
    for job in ("compose", "staging_parity", "predeploy_e2e"):
        for unexpected in ("skipped", "failure", "cancelled"):
            assert not ci_required_passes(expected, results | {job: unexpected})
    for job in (name for name in CI_JOB_NAMES if not expected[name]):
        for unexpected in ("success", "failure", "cancelled"):
            assert not ci_required_passes(expected, results | {job: unexpected})


def test_rename_classifies_old_and_new_paths_without_runtime_to_docs_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        seen.extend(command)
        return SimpleNamespace(stdout="src/w2/domain/model.py\ndocs/model.md\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    paths = changed_paths("a" * 40, "b" * 40)
    assert "--no-renames" in seen
    assert classify(paths).python_focused


def test_invalid_diff_base_fails_safe_to_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise subprocess.CalledProcessError(128, ["git", "diff"])

    monkeypatch.setattr(subprocess, "run", fail)
    assert resolve_plan("invalid", "b" * 40).full


def test_valid_main_push_range_is_classified_instead_of_forced_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="docs/runbook.md\n"),
    )
    assert not resolve_plan("a" * 40, "b" * 40).full


def test_ci_workflow_has_stable_aggregate_for_real_quality_jobs() -> None:
    ci_path = ROOT / ".github/workflows/ci.yml"
    ci = ci_path.read_text(encoding="utf-8")
    jobs = yaml.safe_load(ci_path.read_text(encoding="utf-8"))["jobs"]
    assert "name: CI_REQUIRED" in ci
    assert "if: always()" in ci
    assert jobs["ci-required"]["needs"] == [
        "classify",
        "python-focused",
        "web",
        "migration",
        "compose",
        "staging-parity",
        "predeploy-e2e",
        "verify",
        "images",
    ]
    assert jobs["images"]["needs"] == [
        "classify",
        "python-focused",
        "web",
        "migration",
        "compose",
        "staging-parity",
        "predeploy-e2e",
        "verify",
    ]
    assert "docker/build-push-action@v6" in ci
    assert "cache-from: type=gha" not in ci
    assert "cache-to: type=gha" not in ci
    for image in ("PYTHON_IMAGE", "WEB_IMAGE"):
        cache_ref = f"type=registry,ref=${{{{ env.{image} }}}}:buildcache"
        assert f"cache-from: {cache_ref}" in ci
        assert f"cache-to: {cache_ref},mode=max" in ci
    assert "steps.python.outputs.digest" in ci
    assert "steps.web-image.outputs.digest" in ci
    for job, output in (
        ("python-focused", "python_focused"),
        ("web", "web"),
        ("migration", "migration"),
        ("compose", "compose"),
        ("staging-parity", "staging_parity"),
        ("predeploy-e2e", "predeploy_e2e"),
        ("verify", "verify"),
        ("images", "images"),
    ):
        if job != "images":
            assert jobs[job]["if"] == f"needs.classify.outputs.{output} == 'true'"
    assert "needs.classify.outputs.images == 'true'" in jobs["images"]["if"]
    assert "PRE_MERGE_READINESS_GATE" not in ci
    assert "POST_MERGE_CHECKLIST_CONSISTENCY_GATE" not in ci
    assert "governance-light" not in ci
    assert "detached acceptance" not in ci.lower()
    assert "types: [opened, synchronize, reopened]" in ci
    assert "github.event_name != 'pull_request'" not in ci
    assert "github.event.before" in ci
    assert "github.event_name == 'workflow_dispatch' && inputs.full" in ci


def test_ci_limits_registry_write_and_preserves_staging_web_feature_args() -> None:
    ci_path = ROOT / ".github/workflows/ci.yml"
    workflow = yaml.safe_load(ci_path.read_text(encoding="utf-8"))

    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["images"]["permissions"] == {
        "contents": "read",
        "packages": "write",
    }
    assert all(
        "packages" not in job.get("permissions", {})
        for name, job in workflow["jobs"].items()
        if name != "images"
    )
    build_args = workflow["jobs"]["images"]["steps"][6]["with"]["build-args"]
    assert "VITE_W2_MARKET_ANCHOR_DISPLAY_ENABLED=true" in build_args
    assert "VITE_W2_MARKET_ANCHOR_MIN_DIVERGENCE=0.05" in build_args
