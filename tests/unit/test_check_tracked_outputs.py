from __future__ import annotations

import subprocess

from scripts import check_tracked_outputs


def test_find_tracked_outputs_flags_runtime_and_build_artifacts() -> None:
    paths = [
        "src/w2/api/repository.py",
        "reports/W2_RESULT.md",
        "runtime/reports/report.md",
        "dist/index.js",
        "apps/web/dist/index.js",
        "packages/foo/dist/bundle.js",
    ]

    assert check_tracked_outputs.find_tracked_outputs(paths) == [
        "apps/web/dist/index.js",
        "dist/index.js",
        "packages/foo/dist/bundle.js",
        "reports/W2_RESULT.md",
        "runtime/reports/report.md",
    ]


def test_find_tracked_outputs_allows_source_directories_named_distribution() -> None:
    paths = [
        "src/w2/distribution/model.py",
        "docs/distribution/README.md",
        "apps/web/src/App.tsx",
    ]

    assert check_tracked_outputs.find_tracked_outputs(paths) == []


def test_generated_system_truth_is_forbidden_but_human_evidence_is_allowed() -> None:
    paths = [
        "docs/audits/system_truth/W2_AUTHORITY_MAP_V4.json",
        "docs/audits/system_truth/W2_AUTHORITY_MAP_V4.md",
        "docs/audits/system_truth/W2_NEW_MACHINE_REPORT_V1.json",
        "docs/audits/system_truth/W2_CONSOLIDATION_IMPLEMENTATION_REPORT_V1.json",
        "docs/audits/system_truth/W2_CONSOLIDATION_IMPLEMENTATION_REPORT_V1.md",
        "docs/audits/system_truth/W2_SIMPLIFICATION_PLAN_V1.md",
    ]

    assert check_tracked_outputs.find_tracked_outputs(paths) == [
        "docs/audits/system_truth/W2_AUTHORITY_MAP_V4.json",
        "docs/audits/system_truth/W2_AUTHORITY_MAP_V4.md",
        "docs/audits/system_truth/W2_NEW_MACHINE_REPORT_V1.json",
    ]


def test_main_fails_with_listed_violations(monkeypatch, capsys) -> None:
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="reports/W2_RESULT.md\nsrc/w2/api/repository.py\n",
            stderr="",
        )

    monkeypatch.setattr(check_tracked_outputs.subprocess, "run", fake_run)

    assert check_tracked_outputs.main() == 1
    captured = capsys.readouterr()
    assert "reports/W2_RESULT.md" in captured.out
