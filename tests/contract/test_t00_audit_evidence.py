from __future__ import annotations

import ast
import hashlib
import json
import runpy
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
G10_S07_MARKERS = (
    "SCRIPT_MATRIX_ROWS = 145",
    "SCRIPT_MATRIX_FIELDS = 1160",
    "IMPLEMENTER_VERIFIED_FIELDS = 1160",
    "PENDING_INDEPENDENT_REVIEW_FIELDS = 1160",
    "CONFLICTING_FIELDS = 0",
    "TOTAL_R2_R3_CANDIDATES = 521",
    "GATE_A_FINAL = 30",
    "GATE_B_FINAL = 38",
    "GATE_C_FINAL = 223",
    "GATE_D_FINAL = 17",
    "SAFE_DEGRADATION = 6",
    "ACCEPTED_WITH_REASON = 207",
    "MAPPED_TO_C1_C11 = 35",
    "NEW_FINDING_IDS = 0",
    "GATE_A_TEST_CONTRACTS = 30",
)


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
    for marker in G10_S07_MARKERS:
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


def test_g10_6_matrix_is_implementer_verified_but_not_self_closed() -> None:
    scanner = runpy.run_path(str(ROOT / "scripts/audit_t00.py"))
    report = scanner["checklist_review"](scanner["BASE_SHA"])
    assert report["script_matrix_rows"] == 145
    assert report["script_matrix_fields"] == 1160
    assert report["implementer_verified_fields"] == 1160
    assert report["pending_independent_review_fields"] == 1160
    assert report["conflicting_fields"] == 0
    assert report["unreviewed"] == 145


def test_s07_adjudicates_every_r2_r3_candidate_without_new_findings() -> None:
    scanner = runpy.run_path(str(ROOT / "scripts/audit_t00.py"))
    files = scanner["python_files"](scanner["BASE_SHA"])
    risks = scanner["risk_candidates"](files)
    candidates = scanner["adjudicate_s07"](risks["R2"] + risks["R3"])
    assert len(risks["R2"]) == 375
    assert len(risks["R3"]) == 146
    assert len(candidates) == 521
    assert all(row["final_target_gate"] in scanner["FINAL_TARGET_GATES"] for row in candidates)
    assert all(row["target_gate"] != "PENDING_S07" for row in candidates)
    assert all(row["independent_review"] == "PENDING_S07_8" for row in candidates)
    assert sum(row["mapped_existing_blocker"] is not None for row in candidates) == 35
    gate_a = [row for row in candidates if row["final_target_gate"] == "GATE_A"]
    assert len(gate_a) == 30
    assert all(all(row["gate_a_admission_conditions"].values()) for row in gate_a)
    assert all(
        set(row["gate_a_admission_evidence"])
        == set(row["gate_a_admission_conditions"])
        for row in gate_a
    )
    contracts = [row["gate_a_test_contract"] for row in gate_a]
    assert len({contract["test_id"] for contract in contracts}) == 30
    assert all((ROOT / contract["target_test_file"]).is_file() for contract in contracts)
    assert all(contract["expected_terminal_status"] == "BLOCKED" for contract in contracts)
    assert all(contract["expected_business_write_delta"] == 0 for contract in contracts)
    assert all(contract["expected_evidence_delta"] == 1 for contract in contracts)

    no_raise_sites: set[tuple[str, int]] = set()
    for path, source in files.items():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        no_raise_sites.update(
            (path, node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.ExceptHandler)
            and not any(isinstance(child, ast.Raise) for child in ast.walk(node))
        )
    assert no_raise_sites <= {(row["path"], row["line"]) for row in risks["R2"]}


def test_r2_enumerates_call_only_and_all_no_raise_handler_shapes() -> None:
    scanner = runpy.run_path(str(ROOT / "scripts/audit_t00.py"))
    source = """
def handlers(db, logger, metrics):
    try: work()
    except ValueError: pass
    try: work()
    except TypeError: return None
    for _ in range(1):
        try: work()
        except KeyError: continue
    try: work()
    except RuntimeError: db.rollback()
    try: work()
    except OSError: logger.warning("failed")
    try: work()
    except LookupError: recover_state()
    try: work()
    except ArithmeticError: metrics.increment()
"""
    rows = scanner["risk_candidates"]({"src/w2/synthetic.py": source})["R2"]
    assert {row["handler_action"] for row in rows} == {
        "PASS",
        "RETURN",
        "CONTINUE",
        "ROLLBACK_THEN_CONTINUE",
        "DIAGNOSTIC_THEN_CONTINUE",
        "RECOVERY_CALL_THEN_CONTINUE",
        "CALL_ONLY_THEN_CONTINUE",
    }
    assert all(row["may_continue_after_handler"] for row in rows)
    assert all(not row["has_explicit_raise"] for row in rows)


def test_r2_required_wave_1_regression_sites_are_classified() -> None:
    scanner = runpy.run_path(str(ROOT / "scripts/audit_t00.py"))
    files = scanner["python_files"](scanner["BASE_SHA"])
    risks = scanner["risk_candidates"](files)
    candidates = scanner["adjudicate_s07"](risks["R2"] + risks["R3"])
    by_site = {(row["path"], row["line"]): row for row in candidates}

    ledger = by_site[("src/w2/providers/ledger.py", 98)]
    assert ledger["handler_action"] == "ROLLBACK_THEN_CONTINUE"
    assert ledger["mapped_existing_blocker"] == "C11-A"
    assert ledger["final_target_gate"] == "GATE_A"
    assert ledger["classification"] == "MAPPED_EXISTING_BLOCKER"

    settlement = by_site[("src/w2/dashboard/validation.py", 67)]
    assert settlement["handler_action"] == "DIAGNOSTIC_THEN_CONTINUE"
    assert settlement["final_target_gate"] == "GATE_C"
    assert settlement["classification"] == "DEFERRED_REVIEWED_BOUNDARY"

    identity = by_site[("src/w2/tracking/finished_match_scoring_projection.py", 394)]
    assert identity["handler_action"] == "CALL_ONLY_THEN_CONTINUE"
    assert identity["final_target_gate"] == "GATE_C"
    assert identity["classification"] == "DEFERRED_REVIEWED_BOUNDARY"
