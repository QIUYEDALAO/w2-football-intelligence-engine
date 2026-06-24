from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECISION = ROOT / "reports/W2_GATE3_MARKET_BASELINE_DECISION.json"
ROADMAP = ROOT / "docs/W2_MASTER_ROADMAP.md"
STATUS = ROOT / "reports/W2_ROADMAP_STATUS.json"


def load_decision() -> dict:
    return json.loads(DECISION.read_text(encoding="utf-8"))


def test_one_x_two_reports_all_devig_methods_and_split_policy() -> None:
    payload = load_decision()
    one_x_two = payload["one_x_two"]

    assert set(one_x_two["devig_methods"]) == {
        "PROPORTIONAL",
        "SHIN",
        "POWER",
        "LOGARITHMIC",
    }
    assert one_x_two["method_selection_policy"] == "train_validation_only_test_final_report"
    assert one_x_two["snapshot_semantics"] == "UNKNOWN_PREMATCH_AGGREGATE"


def test_ou_ladder_metrics_and_residual_evidence_are_present() -> None:
    payload = load_decision()
    totals = payload["totals"]
    summary = totals["summary"]

    assert summary["sample_count"] == 128
    assert summary["fit_failures"] == 0
    assert "ladder_mean_absolute_under25_error" in summary
    assert "median_line_mean_absolute_under25_error" in summary
    assert totals["dixon_coles_market_baseline"]["walk_forward"]["fold_count"] > 0


def test_historical_ah_forward_only_blocks_closure() -> None:
    payload = load_decision()

    assert payload["status"] == "PARTIAL"
    assert payload["asian_handicap"]["historical_ah_status"] == "FORWARD_ONLY"
    assert "HISTORICAL_AH_BASELINE_BACKTEST_MISSING" in payload["baselight"][
        "resolved_by_baselight_limited_backtest"
    ]
    assert "BASELIGHT_INTRADAY_TIMESTAMP_UNAVAILABLE" in payload["blockers"]
    assert payload["requirements"]["G3-2-AH_CONSENSUS_PRICING_SETTLEMENT"]["status"] == "PARTIAL"


def test_no_recommendation_candidate_or_formal_output() -> None:
    payload = load_decision()
    status = json.loads(STATUS.read_text(encoding="utf-8"))

    assert payload["recommendation_output"] is False
    assert payload["candidate"] is False
    assert payload["formal_recommendation"] is False
    assert status["candidate"] is False
    assert status["formal_recommendation"] is False


def test_audit_mode_passes_and_closure_mode_fails_for_real_partial_state() -> None:
    audit = subprocess.run(
        [sys.executable, "scripts/check_w2_gate3_market_baseline.py", "--mode", "audit"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    closure = subprocess.run(
        [sys.executable, "scripts/check_w2_gate3_market_baseline.py", "--mode", "closure"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert audit.returncode == 0
    assert closure.returncode != 0
    assert "closure mode requires Gate3 status CLOSED" in closure.stderr


def test_mandatory_requirement_shape_and_closed_with_blocker_guard() -> None:
    payload = load_decision()
    requirements = payload["requirements"]

    assert len(requirements) == 9
    for requirement in requirements.values():
        assert requirement["status"] in {"PASS", "PARTIAL", "BLOCKED", "NOT_APPLICABLE"}
        assert requirement["evidence"]
        assert "metrics" in requirement
        assert "blocker_codes" in requirement
    assert not (payload["status"] == "CLOSED" and payload["blockers"])


def test_master_roadmap_was_not_revised_for_gate3_audit() -> None:
    text = ROADMAP.read_text(encoding="utf-8")

    assert "roadmap_version: 1" in text
    assert "status: ACTIVE" in text
    assert "Gate 3" in text
