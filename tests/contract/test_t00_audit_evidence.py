from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = (
    ROOT / "docs/operations/W2_T00_GOV_FINAL_20260731.md",
    ROOT / "docs/operations/W2_T00_SAFE_R1_R5_20260731.md",
)
ZERO_MARKERS = (
    "UNCLASSIFIED_WRITE_CAPABLE_WORKFLOWS = 0",
    "UNCLASSIFIED_WORKFLOW_RUNS = 0",
    "UNCLASSIFIED_AUTOMATION_COMMITS = 0",
    "UNEXPLAINED_BRANCH_MUTATIONS = 0",
    "UNCLASSIFIED_FINDINGS = 0",
    "UNCLASSIFIED_COMPUTATION_AUTHORITIES = 0",
    "UNCLASSIFIED_REMOVED_GUARDS = 0",
)
NONZERO_MARKERS = ("UNREVIEWED_MAIN_AUTOMATION_HUNKS = 145",)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _portable_repo(tmp_path: Path, *, include_pr: bool) -> tuple[Path, str, str | None]:
    repo = tmp_path / "portable"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "T00 Test")
    _git(repo, "config", "user.email", "t00@example.invalid")
    guard = repo / "tests/contract/test_delivery_status_documentation.py"
    guard.parent.mkdir(parents=True)
    guard.write_text("def test_guard():\n    assert True\n", encoding="utf-8")
    _git(repo, "add", guard.relative_to(repo).as_posix())
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "remote", "add", "github-w2", ".")
    _git(repo, "update-ref", "refs/remotes/github-w2/main", base)
    if not include_pr:
        return repo, base, None
    guard.write_text(
        "def test_guard():\n    assert True\n\n\ndef test_new_guard():\n    assert 1 == 1\n",
        encoding="utf-8",
    )
    _git(repo, "add", guard.relative_to(repo).as_posix())
    _git(repo, "commit", "-qm", "pr")
    pr_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/github-w2/pull/450/head", pr_head)
    _git(repo, "switch", "-q", "--detach", base)
    return repo, base, pr_head


def test_t00_scanner_is_syntax_valid_and_exact_base_bound() -> None:
    scanner = ROOT / "scripts/audit_t00.py"
    source = scanner.read_text(encoding="utf-8")
    ast.parse(source)
    assert 'BASE_SHA = "dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6"' in source
    assert 'PR450_HEAD = "360931d7d84bcbe1416c7946992b5218b759fc8a"' in source
    assert 'rev-list", "--objects", "--all' in source


def test_t00_reports_match_sha256_sidecars_and_close_all_classifications() -> None:
    combined = ""
    for report in REPORTS:
        content = report.read_bytes()
        expected = (
            report.with_suffix(report.suffix + ".sha256").read_text(encoding="utf-8").split()[0]
        )
        assert hashlib.sha256(content).hexdigest() == expected
        combined += content.decode("utf-8")
    for marker in ZERO_MARKERS:
        assert marker in combined
    for marker in NONZERO_MARKERS:
        assert marker in combined


def test_t00_does_not_remove_historical_delivery_guards() -> None:
    guard = (ROOT / "tests/contract/test_delivery_status_documentation.py").read_text(
        encoding="utf-8"
    )
    assert "test_v3_task_authority_and_next_action_are_consistent" in guard
    assert "test_historical_pr_range_is_explicitly_non_authoritative" in guard
    assert "test_obsolete_staging_ip_is_absent_from_tracked_authority" in guard


def test_t00_safe_supports_github_w2_remote(tmp_path: Path) -> None:
    repo, base, pr_head = _portable_repo(tmp_path, include_pr=True)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/audit_t00.py"),
            "safe",
            "--remote",
            "github-w2",
            "--base-sha",
            base,
            "--pr450-ref",
            "refs/remotes/github-w2/pull/450/head",
            "--pr450-head",
            str(pr_head),
            "--compact",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["remote"] == "github-w2"
    assert payload["counts"]["unclassified_removed_guards"] == 0


def test_t00_missing_pr_ref_has_actionable_error_without_traceback(tmp_path: Path) -> None:
    repo, base, _ = _portable_repo(tmp_path, include_pr=False)
    missing = "refs/remotes/github-w2/pull/450/head"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/audit_t00.py"),
            "safe",
            "--remote",
            "github-w2",
            "--base-sha",
            base,
            "--pr450-ref",
            missing,
            "--pr450-head",
            "0" * 40,
            "--compact",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "PR #450 exact ref/object" in result.stderr
    assert f"git fetch github-w2 refs/pull/450/head:{missing}" in result.stderr
    assert "Traceback" not in result.stderr
