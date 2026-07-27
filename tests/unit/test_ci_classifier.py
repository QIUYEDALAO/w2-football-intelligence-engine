from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from scripts.classify_ci import (
    CI_JOB_NAMES,
    changed_paths,
    ci_required_passes,
    classify,
    required_ci_plan,
    resolve_plan,
)

ROOT = Path(__file__).resolve().parents[2]


def _workflow_step(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


def _step_runs(step: dict[str, Any], event: str, verify: bool) -> bool:
    condition = " ".join(str(step.get("if", "")).split())
    if not condition:
        return True
    if condition == "github.event_name == 'pull_request'":
        return event == "pull_request"
    if condition == (
        "github.event_name == 'pull_request' && "
        "needs.classify.outputs.verify == 'true'"
    ):
        return event == "pull_request" and verify
    raise AssertionError(f"untested workflow condition: {condition}")


def test_docs_only_schedules_only_lightweight_governance() -> None:
    plan = classify(
        [
            "PROJECT_STATE.yaml",
            "docs/operations/runbook.md",
            "tests/unit/test_architecture_governance.py",
        ]
    )
    assert plan.governance
    assert not any(
        (
            plan.python_focused,
            plan.web,
            plan.migration,
            plan.compose,
            plan.staging_parity,
            plan.predeploy_e2e,
            plan.verify,
        )
    )


def test_python_web_migration_and_infra_schedule_their_jobs() -> None:
    assert classify(["src/w2/domain/model.py"]).python_focused
    assert classify(["apps/web/src/page.tsx"]).web

    migration = classify(["migrations/versions/0044_example.py"])
    assert migration.full and migration.migration and migration.verify

    infra = classify(["infra/compose/compose.staging.yml"])
    assert infra.compose and infra.staging_parity and infra.predeploy_e2e
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
        "scripts/check_architecture_governance.py",
        "scripts/check_w2_all.py",
    ):
        assert classify([path]).full


def test_python_implementation_requires_full_receipt_but_docs_closure_is_light() -> None:
    assert required_ci_plan(["src/w2/domain/model.py"], "IMPLEMENTATION").full
    assert not required_ci_plan(["docs/runbook.md"], "CLOSURE").full


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
    for job in ("governance", "compose", "staging_parity", "predeploy_e2e"):
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


def test_ci_workflow_has_stable_aggregate_and_independent_governance_gates() -> None:
    ci_path = ROOT / ".github/workflows/ci.yml"
    ci = ci_path.read_text(encoding="utf-8")
    governance = (
        ROOT / ".github/workflows/architecture-governance.yml"
    ).read_text(encoding="utf-8")
    jobs = yaml.safe_load(ci_path.read_text(encoding="utf-8"))["jobs"]
    assert "name: CI_REQUIRED" in ci
    assert "if: always()" in ci
    assert jobs["ci-required"]["needs"] == [
        "classify",
        "governance",
        "python-focused",
        "web",
        "migration",
        "compose",
        "staging-parity",
        "predeploy-e2e",
        "verify",
    ]
    for job, output in (
        ("governance", "governance"),
        ("python-focused", "python_focused"),
        ("web", "web"),
        ("migration", "migration"),
        ("compose", "compose"),
        ("staging-parity", "staging_parity"),
        ("predeploy-e2e", "predeploy_e2e"),
        ("verify", "verify"),
    ):
        assert jobs[job]["if"] == f"needs.classify.outputs.{output} == 'true'"
    assert "PRE_MERGE_READINESS_GATE" not in ci
    assert "POST_MERGE_CHECKLIST_CONSISTENCY_GATE" not in ci
    assert "name: PRE_MERGE_READINESS_GATE" in governance
    assert "name: POST_MERGE_CHECKLIST_CONSISTENCY_GATE" in governance
    assert "types: [opened, synchronize, reopened]" in ci
    assert "issue_comment:" in governance
    assert "github.event_name != 'pull_request'" not in ci
    assert "github.event.before" in ci
    assert "github.event_name == 'workflow_dispatch' && inputs.full" in ci


@pytest.mark.parametrize(
    ("event", "plan", "verify"),
    [
        ("pull_request", "FULL", True),
        ("pull_request", "PATH_AWARE_FULL", True),
        ("pull_request", "PATH_AWARE_FOCUSED", False),
        ("pull_request", "LIGHTWEIGHT", False),
        ("push", "MAIN", True),
        ("workflow_dispatch", "FULL", True),
    ],
)
def test_ci_workflow_event_plan_matrix_initializes_trusted_runtime(
    event: str,
    plan: str,
    verify: bool,
) -> None:
    jobs = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )["jobs"]
    aggregate = jobs["ci-required"]
    verify_job = jobs["verify"]
    checkout = _workflow_step(aggregate, "Checkout trusted governance compiler")
    select = _workflow_step(aggregate, "Select trusted governance runtime")
    require = _workflow_step(aggregate, "Require every scheduled job to succeed")
    detached_names = (
        "Receive detached result source",
        "Build detached acceptance artifacts",
        "Upload detached implementation result",
        "Upload detached evidence index",
    )

    assert aggregate["if"] == "always()"
    assert aggregate["env"]["W2_GOVERNANCE_ROOT"] == "${{ github.workspace }}"
    assert "classify" in aggregate["needs"]
    assert _step_runs(checkout, event, verify) == (event == "pull_request")
    assert _step_runs(select, event, verify) == (event == "pull_request")
    assert _step_runs(require, event, verify)
    assert all(
        _step_runs(_workflow_step(aggregate, name), event, verify)
        == (event == "pull_request" and verify)
        for name in detached_names
    ), plan

    root = (
        "$GITHUB_WORKSPACE/.w2-trusted-governance"
        if _step_runs(select, event, verify)
        else "${{ github.workspace }}"
    )
    assert root
    assert checkout["with"]["path"] == ".w2-trusted-governance"
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.base.sha }}"
    assert (
        select["run"].strip()
        == 'echo "W2_GOVERNANCE_ROOT=$GITHUB_WORKSPACE/.w2-trusted-governance" >> "$GITHUB_ENV"'
    )
    assert 'cd "$W2_GOVERNANCE_ROOT"' in require["run"]
    assert 'python3 "$W2_GOVERNANCE_ROOT/scripts/classify_ci.py"' in require["run"]
    assert "env -u PYTHONPATH PYTHONNOUSERSITE=1" in require["run"]

    collector_checkout = _workflow_step(
        verify_job, "Checkout trusted measurement collector"
    )
    collector_select = _workflow_step(
        verify_job, "Select trusted measurement collector"
    )
    assert _step_runs(collector_checkout, event, verify) == (
        event == "pull_request"
    )
    assert _step_runs(collector_select, event, verify) == (
        event == "pull_request"
    )
    assert (
        collector_select["run"].strip()
        == 'echo "W2_GOVERNANCE_ROOT=$GITHUB_WORKSPACE/.w2-trusted-governance" >> "$GITHUB_ENV"'
    )
    reachable_runs = [
        str(step.get("run", ""))
        for job in (aggregate, verify_job)
        for step in job["steps"]
        if _step_runs(step, event, verify)
    ]
    if event != "pull_request":
        assert not any("github.event.pull_request" in run for run in reachable_runs)
    assert not any("ARCH-GOVERNANCE-03" in run for run in reachable_runs)
