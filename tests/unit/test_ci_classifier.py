from __future__ import annotations

from pathlib import Path

import yaml
from scripts.classify_ci import CI_JOB_NAMES, ci_required_passes, classify

ROOT = Path(__file__).resolve().parents[2]


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


def test_ci_required_fails_when_any_scheduled_job_is_mutated_to_failure() -> None:
    plan = classify(["infra/compose/compose.staging.yml"])
    expected = {job: getattr(plan, job) for job in CI_JOB_NAMES}
    results = {
        "classify": "success",
        **{job: "success" if expected[job] else "skipped" for job in CI_JOB_NAMES},
    }
    assert ci_required_passes(expected, results)
    for job in ("governance", "compose", "staging_parity", "predeploy_e2e"):
        mutated = results | {job: "failure"}
        assert not ci_required_passes(expected, mutated)


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
