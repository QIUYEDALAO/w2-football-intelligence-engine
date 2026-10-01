"""Independent fixed expectations for the 200-fixture descriptive contract."""

from copy import deepcopy

import pytest

from w2.tracking.ah_ou_v3_monitoring import build_cumulative_report


def facts(count=200, market="ASIAN_HANDICAP"):
    return [{
        "decision_id": f"decision-{i}", "fixture_id": f"fixture-{i:04d}",
        "market": market, "model_version": "frozen-model", "calibration_version": "frozen-cal",
        "eligible": True, "selected": i < 20, "five_state": "WIN" if i % 2 else "LOSS",
        "recommendation_net_units": "0.9" if i % 2 else "-1",
        "pure_market_q": 0.6, "pure_market_net_units": "0.9" if i % 2 else "-1",
        "competition": "allsvenskan", "month": "2026-10", "rps": 0.25,
        "quote_age_seconds": 60,
    } for i in range(count)]


@pytest.mark.parametrize("market", ["ASIAN_HANDICAP", "TOTALS"])
def test_200_is_eligible_ft_fixtures_per_market_not_selected_or_combined(market):
    report = build_cumulative_report(facts(market=market))
    assert report["eligible_settled"] == 200 and report["recommended"] == 20
    assert report["five_state_counts"] == {"LOSS": 10, "WIN": 10}
    assert report["cover_win_rate"] == 0.5
    assert report["net_units"] == "-1.0"
    assert report["mean_rps"] == 0.25
    assert report["quote_age_seconds_mean"] == report["quote_age_seconds_max"] == 60
    assert report["pure_market_equal_coverage"]["recommended"] == 20
    assert len(report["pure_market_equal_coverage"]["eligible_fixture_ids"]) == 200
    assert report["automatic_refit"] is False


def test_monitoring_same_path_control_and_invalid_population():
    rows = facts()
    assert build_cumulative_report(rows) == build_cumulative_report(deepcopy(rows))
    with pytest.raises(ValueError, match="V3_MONITORING_MILESTONE_INVALID"):
        build_cumulative_report(rows[:199])
    for key, value, reason in (
        ("eligible", False, "MILESTONE_INVALID"),
        ("fixture_id", "fixture-0000", "DUPLICATE_FIXTURE"),
        ("market", "TOTALS", "VERSION_SET_CONFLICT"),
        ("model_version", "other-model", "VERSION_SET_CONFLICT"),
    ):
        attack = deepcopy(rows)
        attack[1][key] = value
        with pytest.raises(ValueError, match="V3_MONITORING_" + reason):
            build_cumulative_report(attack)
    assert build_cumulative_report(facts(400))["eligible_settled"] == 400
