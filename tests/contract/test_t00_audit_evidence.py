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
    "UNCLASSIFIED_COMPUTATION_AUTHORITIES = 0",
    "UNCLASSIFIED_REMOVED_GUARDS = 0",
)
NONZERO_MARKERS = ("UNREVIEWED_MAIN_AUTOMATION_HUNKS = 145",)
G10_S07_MARKERS = (
    "SCRIPT_MATRIX_ROWS = 145",
    "SCRIPT_MATRIX_FIELDS = 1160",
    "SCRIPT_MATRIX_EVIDENCE_ATTACHED = 1160",
    "INDEPENDENTLY_VERIFIED_FIELDS = 0",
    "CONFLICTING_FIELDS = 0",
    "R2_HANDLER_DENOMINATOR = 441",
    "R3_SIDE_EFFECT_DENOMINATOR = 837",
    "UNCLASSIFIED_IO_PRIMITIVES = 429",
    "PROPOSED_GATE_A = 30",
    "FINAL_GATE_A = 0",
    "INDEPENDENT_REVIEW_PENDING = 1278",
    "MAPPED_TO_C1_C11 = 35",
    "NEW_FINDING_IDS = 0",
    "PROPOSED_TEST_CONTRACTS = 30",
    "INDEPENDENTLY_ACCEPTED_TEST_CONTRACTS = 0",
    "PR450_REPAIR_REQUIRED_GUARDS = 145",
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


def test_g10_6_matrix_attaches_evidence_but_is_not_self_verified() -> None:
    scanner = runpy.run_path(str(ROOT / "scripts/audit_t00.py"))
    report = scanner["checklist_review"](scanner["BASE_SHA"])
    assert report["script_matrix_rows"] == 145
    assert report["script_matrix_fields"] == 1160
    assert report["evidence_attached_pending_independent_review_fields"] == 1160
    assert report["independently_verified_fields"] == 0
    assert report["pending_independent_review_fields"] == 1160
    assert report["conflicting_fields"] == 0
    assert report["unreviewed"] == 145


def test_s07_emits_only_pending_candidate_gate_proposals() -> None:
    scanner = runpy.run_path(str(ROOT / "scripts/audit_t00.py"))
    files = scanner["python_files"](scanner["BASE_SHA"])
    risks = scanner["risk_candidates"](files)
    call_manifest = scanner["call_edge_manifest"](files)
    candidates = scanner["adjudicate_s07"](risks["R2"] + risks["R3"], call_manifest)
    assert len(risks["R2"]) == 441
    assert len(risks["R3"]) == 837
    assert len(candidates) == 1278
    assert len({row["candidate_id"] for row in candidates}) == len(candidates)
    assert all(
        row["proposed_target_gate"] in scanner["PROPOSED_TARGET_GATES"]
        for row in candidates
    )
    assert all(row["final_target_gate"] == "PENDING_INDEPENDENT_REVIEW" for row in candidates)
    assert all(row["independent_review"] == "PENDING_S07_8" for row in candidates)
    assert all(row["accepted_by_independent_reviewer"] is False for row in candidates)
    assert sum(row["mapped_existing_blocker"] is not None for row in candidates) == 35
    proposed_a = [
        row for row in candidates if row["proposed_target_gate"] == "PROPOSED_GATE_A"
    ]
    assert len(proposed_a) == 30
    assert all(
        row["gate_a_admission_conditions"]["accepted_by_independent_reviewer"] is False
        for row in proposed_a
    )
    contracts = [row["proposed_test_contract"] for row in proposed_a]
    assert len({contract["test_id"] for contract in contracts}) == 30
    assert all((ROOT / contract["target_test_file"]).is_file() for contract in contracts)
    assert all(contract["contract_status"] == "PROPOSED_TEST_CONTRACT" for contract in contracts)
    assert all(contract["accepted_by_independent_reviewer"] is False for contract in contracts)
    assert all(contract["expected_terminal_status"]["value"] == "BLOCKED" for contract in contracts)
    assert any(
        contract["expected_provider_call_delta"]["value"] == "PENDING_REVIEW"
        for contract in contracts
    )
    assert any(contract["expected_provider_call_delta"]["value"] == 0 for contract in contracts)
    assert all(
        contract["expected_evidence_delta"]["value"] == "PENDING_REVIEW"
        for contract in contracts
    )

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
    assert all(row["denominator_status"] == "ENUMERATED_HANDLER" for row in rows)


def test_r2_conditional_and_nested_raises_do_not_hide_fallthrough() -> None:
    scanner = runpy.run_path(str(ROOT / "scripts/audit_t00.py"))
    source = """
def handlers(flag):
    try: work()
    except ValueError:
        if flag:
            raise
        recover_state()
    try: work()
    except TypeError:
        def nested():
            raise RuntimeError()
        recover_state()
"""
    rows = scanner["risk_candidates"]({"src/w2/synthetic.py": source})["R2"]
    conditional, nested = rows
    assert conditional["handler_action"] == "CONDITIONAL_RAISE_WITH_FALLTHROUGH"
    assert conditional["direct_raise_count"] == 1
    assert conditional["may_fallthrough"] is True
    assert nested["direct_raise_count"] == 0
    assert nested["nested_scope_raise_count"] == 1
    assert nested["may_fallthrough"] is True


def test_r3_covers_actual_transports_and_write_primitives() -> None:
    scanner = runpy.run_path(str(ROOT / "scripts/audit_t00.py"))
    source = """
def writes(session, client, path, bucket, mystery, request):
    urllib.request.urlopen(request)
    client.send(request)
    session.execute(statement)
    session.flush()
    session.commit()
    path.write_text("evidence")
    bucket.put_object(Key="x", Body=b"x")
    mystery.save_payload({})
"""
    rows = scanner["risk_candidates"]({"src/w2/synthetic.py": source})["R3"]
    operations = {row["operation"] for row in rows}
    assert {
        "NETWORK_TRANSPORT",
        "DB_EXECUTE",
        "DB_FLUSH",
        "DB_COMMIT",
        "FILE_WRITE",
        "OBJECT_STORE_WRITE",
        "UNCLASSIFIED_IO_PRIMITIVE",
    } <= operations
    unclassified = [row for row in rows if row["operation"] == "UNCLASSIFIED_IO_PRIMITIVE"]
    assert len(unclassified) == 1
    assert unclassified[0]["status"] == "UNCLASSIFIED"

    files = scanner["python_files"](scanner["BASE_SHA"])
    actual = scanner["risk_candidates"](files)["R3"]
    assert any(
        row["path"] == "src/w2/providers/api_football.py"
        and row["line"] == 139
        and row["call"] == "urllib.request.urlopen"
        and row["operation"] == "NETWORK_TRANSPORT"
        for row in actual
    )


def test_candidate_call_edges_are_rooted_and_candidate_id_bound() -> None:
    scanner = runpy.run_path(str(ROOT / "scripts/audit_t00.py"))
    files = scanner["python_files"](scanner["BASE_SHA"])
    manifest = scanner["call_edge_manifest"](files)
    assert manifest["root"] == "scripts/run_prematch_refresh.py:main"
    assert manifest["accepted_by_independent_reviewer"] is False
    assert "src/w2/providers/api_football.py:request_live" in manifest["chains"]
    assert "src/w2/providers/ledger.py:record_request" in manifest["chains"]
    assert any(
        edge["caller_id"] == "scripts/run_prematch_refresh.py:main"
        and edge["line"] == 138
        and edge["callee_id"]
        == "src/w2/ingestion/future_refresh.py:run_future_refresh_task"
        for edge in manifest["edges"]
    )


def test_r2_required_wave_1_regression_sites_are_classified() -> None:
    scanner = runpy.run_path(str(ROOT / "scripts/audit_t00.py"))
    files = scanner["python_files"](scanner["BASE_SHA"])
    risks = scanner["risk_candidates"](files)
    candidates = scanner["adjudicate_s07"](
        risks["R2"] + risks["R3"], scanner["call_edge_manifest"](files)
    )
    by_site = {(row["path"], row["line"]): row for row in candidates}

    ledger = by_site[("src/w2/providers/ledger.py", 98)]
    assert ledger["handler_action"] == "ROLLBACK_THEN_CONTINUE"
    assert ledger["mapped_existing_blocker"] == "C11-A"
    assert ledger["proposed_target_gate"] == "PROPOSED_GATE_A"
    assert ledger["accepted_by_independent_reviewer"] is False
    assert ledger["blocker_mapping_basis"] == f"EXACT_CANDIDATE_ID:{ledger['candidate_id']}"

    settlement = by_site[("src/w2/dashboard/validation.py", 67)]
    assert settlement["handler_action"] == "DIAGNOSTIC_THEN_CONTINUE"
    assert settlement["proposed_target_gate"] == "PROPOSED_GATE_C"

    identity = by_site[("src/w2/tracking/finished_match_scoring_projection.py", 394)]
    assert identity["handler_action"] == "CALL_ONLY_THEN_CONTINUE"
    assert identity["proposed_target_gate"] == "PROPOSED_GATE_C"


def test_pr450_guard_matrix_uses_exact_objects_and_leaves_repair_on_pr450() -> None:
    scanner = runpy.run_path(str(ROOT / "scripts/audit_t00.py"))
    config = scanner["AuditConfig"](
        scanner["BASE_SHA"],
        "origin",
        "refs/remotes/origin/main",
        scanner["PR450_REF"],
        scanner["PR450_HEAD"],
    )
    matrix = scanner["guard_matrix"](config)
    assert matrix["source_mode"] == "EXACT_GIT_OBJECTS_ONLY"
    assert matrix["pr458_changes_delivery_test"] is False
    assert matrix["repair_required_guards"] == 145
    assert matrix["unclassified_removed_guards"] == 0
    assert all(row["classification"] == "LOST_IN_PR450" for row in matrix["removed_guards"])
    assert all(
        row["trusted_main_classification"] == "RETAINED_ON_TRUSTED_MAIN"
        and row["repair_requirement"] == "REPAIR_REQUIRED_IN_PR450"
        for row in matrix["removed_guards"]
    )
