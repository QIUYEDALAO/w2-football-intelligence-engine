from __future__ import annotations

import ast
import hashlib
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
    "UNREVIEWED_MAIN_AUTOMATION_HUNKS = 0",
    "UNCLASSIFIED_FINDINGS = 0",
    "UNCLASSIFIED_COMPUTATION_AUTHORITIES = 0",
    "UNCLASSIFIED_REMOVED_GUARDS = 0",
)


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


def test_t00_does_not_remove_historical_delivery_guards() -> None:
    guard = (ROOT / "tests/contract/test_delivery_status_documentation.py").read_text(
        encoding="utf-8"
    )
    assert "test_v3_task_authority_and_next_action_are_consistent" in guard
    assert "test_historical_pr_range_is_explicitly_non_authoritative" in guard
    assert "test_obsolete_staging_ip_is_absent_from_tracked_authority" in guard
