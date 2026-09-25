from __future__ import annotations

from datetime import UTC, datetime

from scripts.quant.gate3_readonly_diagnostics import (
    attribution,
    attribution_top3,
    drift_observation,
)


def _row(fixture: str, at: str, *, score: str = "1") -> dict[str, str]:
    return {
        "fixture_id": fixture, "market": "TOTALS", "selection": "UNDER",
        "state": "ANALYSIS_PICK_ACTIVE", "line": "2.5", "home": score, "away": "0",
        "evaluated_at": at,
        "distribution": '{"WIN":0.6,"HALF_WIN":0,"PUSH":0,"HALF_LOSS":0,"LOSS":0.4}',
    }


def test_attribution_reports_missingness_and_small_sample() -> None:
    rows = [_row("1", "2026-09-24T00:00:00+00:00")]
    rows.append({**_row("2", "2026-09-24T00:00:00+00:00"), "home": ""})
    groups = attribution(rows)
    market = next(item for item in groups if item["dimension"] == "market")
    assert market["n"] == 1
    assert market["fixture_count"] == 2
    assert market["missing_rate"] == 0.5
    assert market["evidence"] == "证据不足"
    assert attribution_top3(rows) == []


def test_drift_observation_has_no_automatic_decision_or_market_imputation() -> None:
    rows = [_row("1", "2026-09-24T00:00:00+00:00")]
    result = drift_observation(rows, as_of=datetime(2026, 9, 25, tzinfo=UTC))
    assert [item["window_days"] for item in result] == [7, 30]
    assert all(item["market_delta"] is None for item in result)
    assert all(item["decision"] == "HUMAN_REVIEW_ONLY" for item in result)
