from __future__ import annotations

from scripts.quant.run_gate3_shadow_diagnostics import _row_metrics, settle_outcome


def test_independent_settlement_handles_quarter_lines() -> None:
    assert settle_outcome("TOTALS", "UNDER", 2.25, 1, 1) == "HALF_WIN"
    assert settle_outcome("TOTALS", "OVER", 2.75, 2, 1) == "HALF_WIN"
    assert settle_outcome("ASIAN_HANDICAP", "HOME", -0.25, 0, 0) == "HALF_LOSS"


def test_shadow_metrics_are_stratified_without_production_imports() -> None:
    rows = [
        {
            "market": "TOTALS", "state": "ANALYSIS_PICK_ACTIVE", "selection": "UNDER",
            "line": "2.5", "home": "1", "away": "0", "odds": "2.0",
            "distribution": '{"WIN":0.6,"HALF_WIN":0,"PUSH":0,"HALF_LOSS":0,"LOSS":0.4}',
        }
    ]
    result = _row_metrics(rows)["TOTALS/ANALYSIS_PICK_ACTIVE"]
    assert result["n"] == 1
    assert result["outcomes"] == {"WIN": 1}
    assert result["profit_units"] == 1.0
