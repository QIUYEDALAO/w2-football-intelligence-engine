from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/operations/V1_SLOPE_RECALIBRATION_PREREGISTRATION_20260831.json"
TOTALS = ROOT / "docs/operations/V1_TOTALS_RECALIBRATION_TASK_BOUNDARY_20260831.json"


def test_slope_preregistration_freezes_ah_acceptance_and_untouched_cohorts() -> None:
    payload = json.loads(PREREG.read_text())

    assert payload["status"] == "FROZEN_BEFORE_ANY_SLOPE_FIT"
    assert payload["authority_boundary"]["authorized_now"] == "preregistration only"
    assert payload["contamination_disclosure"]["historical_8659"]["forbidden_roles"] == [
        "VALIDATION",
        "TEST",
        "FINAL_ACCEPTANCE",
    ]
    assert payload["contamination_disclosure"]["market_283"]["forbidden_roles"] == [
        "VALIDATION",
        "TEST",
        "FINAL_ACCEPTANCE",
    ]
    assert payload["cohort_contract"]["validation"]["required_fixture_count"] == 2500
    assert payload["cohort_contract"]["test"]["required_fixture_count"] == 4000
    assert "kickoff_at > T0" in payload["cohort_contract"]["validation"]["selection"]
    assert "before kickoff" in payload["point_in_time_rules"]["anti_leakage_freeze"]

    ah = payload["acceptance_metrics"]["primary_AH_spread"]
    assert ah["all_required"] is True
    assert ah["net_margin_regression"]["required_point_slope_interval"] == [0.9, 1.1]
    assert ah["fair_minus_market"]["required_absolute_mean_max_goals"] == 0.15
    assert (
        ah["underdog_cashflow_price_edge"]["required_mean_upper_95pct_bootstrap_bound_max"] == 0.05
    )
    one_x_two = payload["acceptance_metrics"]["secondary_1X2"]
    assert "absolute relative bias exceeds 0.05" in one_x_two["binding_guard"]
    assert one_x_two["role"].startswith("binding regression guard only")


def test_totals_is_a_separate_unauthorized_task() -> None:
    prereg = json.loads(PREREG.read_text())
    totals = json.loads(TOTALS.read_text())

    assert prereg["totals_exclusion"]["separate_task_id"] == totals["task_id"]
    assert totals["status"] == "SEPARATE_TASK_NOT_AUTHORIZED"
    assert totals["trigger_evidence"]["fair_minus_market_mean_Y_0_30"] == -0.090106
    assert "TOTALS parameter fitting" in totals["not_authorized"]
