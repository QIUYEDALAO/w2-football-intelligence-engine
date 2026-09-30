from datetime import date

import pytest

from w2.dashboard.ah_ou_v3_public import public_v3_home_projection


def _decision(identity: str, market: str, state: str, outcome=None, net=None):
    return {
        "decision_id": identity,
        "decision_contract": "w2.ah_ou_decision.v3.1",
        "fixture_id": "1489404",
        "kickoff_utc": "2026-09-30T18:00:00+00:00",
        "competition_id": "allsvenskan",
        "home": "主队",
        "away": "客队",
        "market": market,
        "selection": "HOME" if market == "ASIAN_HANDICAP" else "OVER",
        "exact_line": "-0.25" if market == "ASIAN_HANDICAP" else "2.5",
        "decimal_odds": "1.90",
        "score": "0.336",
        "model_version": "model-v3",
        "calibration_version": "cal-v3",
        "quote_capture_id": "capture",
        "quote_raw_sha256": "a" * 64,
        "terms_hash": "b" * 64,
        "state": state,
        "settlement": outcome,
        "net_units": net,
        "settlement_hash": "c" * 64 if outcome else None,
    }


def test_v3_home_counts_decisions_not_fixtures_and_excludes_pending_from_hit_rate():
    ah = _decision("ah", "ASIAN_HANDICAP", "SETTLED", "HALF_WIN", "0.45")
    ou = _decision("ou", "TOTALS", "SETTLED", "LOSS", "-1")
    pending = _decision("later", "TOTALS", "PENDING")
    pending["fixture_id"] = "later-fixture"
    result = public_v3_home_projection([ah, ou, pending], anchor=date(2026, 9, 30))
    summary = result["performance_summary"]
    assert len(result["today_recommendations"]) == 3
    assert summary["selected_count"] == 3
    assert summary["settled_count"] == 2
    assert summary["pending_count"] == 1
    assert summary["last_7_days"]["match_count"] == 2
    assert summary["last_7_days"]["hit_rate_denominator"] == 2
    assert summary["last_7_days"]["hit_rate"] == 0.25
    assert summary["total_profit_units"] == -0.55
    assert summary["by_market"]["ASIAN_HANDICAP"]["profit_units"] == 0.45
    assert summary["by_market"]["TOTALS"]["profit_units"] == -1


def test_all_time_market_counts_include_future_pending_without_hit_rate_inflation():
    future = _decision("future", "TOTALS", "PENDING")
    future["kickoff_utc"] = "2026-10-02T18:00:00+00:00"
    summary = public_v3_home_projection([future], anchor=date(2026, 9, 30))[
        "performance_summary"
    ]
    market = summary["by_market"]["TOTALS"]
    assert market["selected_count"] == 1
    assert market["pending_count"] == 1
    assert market["hit_rate_denominator"] == 0
    assert market["hit_rate"] is None
    assert summary["last_7_days"]["selected_count"] == 0


@pytest.mark.parametrize("mutation,reason", [
    ({"decision_contract": "w2.ah_ou_decision_ledger.v3"}, "V3_PUBLIC_CONTRACT_MISMATCH"),
    ({"state": "UNKNOWN"}, "V3_PUBLIC_STATE_INVALID"),
    ({"kickoff_utc": "2026-09-30T18:00:00"}, "V3_PUBLIC_KICKOFF_TZ_MISSING"),
])
def test_v3_home_fails_closed_on_invalid_public_identity(mutation, reason):
    row = _decision("ah", "ASIAN_HANDICAP", "PENDING")
    row.update(mutation)
    with pytest.raises(ValueError, match=reason):
        public_v3_home_projection([row], anchor=date(2026, 9, 30))


def test_v3_home_rejects_duplicate_decision_id_across_markets():
    rows = [
        _decision("same", "ASIAN_HANDICAP", "PENDING"),
        _decision("same", "TOTALS", "PENDING"),
    ]
    with pytest.raises(ValueError, match="V3_PUBLIC_DUPLICATE_DECISION_ID"):
        public_v3_home_projection(rows, anchor=date(2026, 9, 30))
