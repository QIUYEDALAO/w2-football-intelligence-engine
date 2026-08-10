from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "docs" / "review_packages" / "SC18_INPUT_AUTHORITY_CONVERGENCE"


def test_sc18_authority_artifacts_are_complete_and_self_checking() -> None:
    required = {
        "SC18_INPUT_AUTHORITY_TRACE.json",
        "STAGE14_COVERAGE_MATRIX.json",
        "PUBLIC_LABEL_COVERAGE_MATRIX.json",
        "PUBLIC_ENUM_LABEL_COVERAGE.json",
        "PUBLIC_LABEL_COVERAGE_REPORT.md",
        "STAGE14_COVERAGE_REPORT.md",
    }
    assert {path.name for path in REPORTS.iterdir()} == required
    completed = subprocess.run(
        ["python", "scripts/check_sc18_input_authority.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "SC18 input authority check PASS" in completed.stdout


def test_sc18_trace_is_read_only_and_preserves_zero_candidate_truth() -> None:
    trace = json.loads((REPORTS / "SC18_INPUT_AUTHORITY_TRACE.json").read_text())
    assert trace["provider_calls"] == trace["db_writes"] == 0
    target = next(row for row in trace["fixtures"] if row["fixture_id"] == "1493049")
    assert target["match_market_aggregate_status"] == "PARTIAL"
    assert target["markets"]["ASIAN_HANDICAP"]["bookmaker_count"] == 1
    assert target["markets"]["TOTALS"]["bookmaker_count"] == 7
    assert {
        market["candidate_eligibility_status"] for market in target["markets"].values()
    } == {"NOT_READY"}


def test_final_dashboard_uses_backend_public_labels_and_no_read_side_effects() -> None:
    console = (ROOT / "apps/web/src/components/IntelligenceConsole.tsx").read_text()
    repository = (ROOT / "src/w2/api/repository.py").read_text()
    workspace = (ROOT / "src/w2/dashboard/workspace.py").read_text()

    assert "translateTeam" not in console
    assert "match.home_team_label.display_name" in console
    assert "public_team_labels_for_fixtures" in repository
    assert "provider_client" not in workspace
    assert "session.commit" not in workspace
    assert '"provider_calls": int(day_view.get("provider_calls") or 0)' in workspace
    assert '"db_writes": int(day_view.get("db_writes") or 0)' in workspace
