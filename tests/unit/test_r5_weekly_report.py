from scripts.quant.r5_weekly_report import render_weekly_report


def test_report_uses_only_supplied_counts_and_never_sends() -> None:
    report = render_weekly_report(
        week="2026-W39",
        shadow={"metrics": {"AH/Track B": {"n": 12, "logloss": 0.9, "bias": 0.02}}},
        forward={
            "calibration_identity": "candidate-eval.v2",
            "eligible_count": 3,
            "validation_count": 3,
            "test_count": 0,
            "fixture_count": 2,
            "exclusions": {"PIT_UNPROVABLE": 1},
        },
        drift={"windows": [{"window_days": 7, "n": 3, "bias": 0.02}]},
    )
    assert "eligible：3" in report
    assert "validation / test：3 / 0" in report
    assert "`PIT_UNPROVABLE`：1" in report
    assert "人工复核" in report
    assert "Brier | RPS" in report
    assert "证据不足" in report  # absent Brier/RPS/CUSUM are not zeroes


def test_report_does_not_convert_missing_evidence_to_success() -> None:
    report = render_weekly_report(week="2026-W39", shadow={}, forward={}, drift={})
    assert "可证明 eligible：证据不足" in report
    assert "validation / test：证据不足 / 证据不足" in report
    assert "未提供 shadow 指标" in report
