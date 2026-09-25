from datetime import UTC, datetime, timedelta

from w2.dashboard.forward_wait_monitor import forward_bias_windows


def test_forward_bias_requires_20_settled_rows_and_uses_five_state_success() -> None:
    now = datetime(2026, 9, 26, tzinfo=UTC)
    rows = [
        (
            now - timedelta(days=2),
            {"model_settlement_distribution": {"WIN": 0.4, "HALF_WIN": 0.2}},
            "WIN",
        )
        for _ in range(19)
    ]
    insufficient = forward_bias_windows(rows, as_of=now)
    assert insufficient["bias_7d"] is None
    assert insufficient["status"] == "INSUFFICIENT_FORWARD_SETTLEMENTS"
    rows.append((now, {"model_settlement_distribution": {"WIN": 0.4, "HALF_WIN": 0.2}}, "PUSH"))
    observed = forward_bias_windows(rows, as_of=now)
    assert observed["n_30d"] == 20
    assert abs(observed["bias_30d"] - (-0.45)) < 1e-12
    assert observed["status"] == "OBSERVED_HUMAN_REVIEW_ONLY"


def test_bad_distribution_never_counts_as_zero_bias() -> None:
    now = datetime(2026, 9, 26, tzinfo=UTC)
    result = forward_bias_windows(
        [(now, {"model_settlement_distribution": {"WIN": "N/A"}}, "WIN")], as_of=now
    )
    assert result["n"] == 0
    assert result["bias_7d"] is None
