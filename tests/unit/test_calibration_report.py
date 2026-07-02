from __future__ import annotations

from w2.backtest.lambda_fit_gate import (
    WALK_FORWARD_REQUIRES_SETTLED_LOCK_SAMPLE_N_GE_200,
    build_lambda_fit_gap_report,
)
from w2.tracking.calibration_report import build_calibration_report


def test_calibration_report_handles_empty_inputs() -> None:
    rows = build_calibration_report(
        lock_rows=[],
        settlement_rows=[],
        generated_at="2026-07-02T01:00:00Z",
    )

    assert rows == []


def test_calibration_report_observes_small_sample_without_percentages_or_rate_terms() -> None:
    rows = build_calibration_report(
        lock_rows=[_lock_row(lock_id="lock-1")],
        settlement_rows=[_settlement_row(lock_id="lock-1", outcome="WIN")],
        generated_at="2026-07-02T01:00:00Z",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["sample_count"] == 1
    assert row["min_bucket_samples_for_rate"] == 30
    assert row["status"] == "OBSERVING"
    assert row["label"] == "观察中 1/30"
    assert row["not_a_formal_gate"] is True
    assert row["posthoc_only"] is True
    assert row["predicted_cover_probability"] is None
    assert row["actual_cover_probability"] is None
    assert row["brier"] is None
    assert row["log_loss"] is None
    rendered = str(row)
    assert "win_rate" not in rendered
    assert "ROI" not in rendered
    assert "命中率" not in rendered
    assert "胜率" not in rendered


def test_calibration_report_skips_legacy_or_unreproducible_locks() -> None:
    rows = build_calibration_report(
        lock_rows=[
            _lock_row(lock_id="legacy", legacy_marker_only=True, reproducible=False),
            _lock_row(lock_id="thin", legacy_marker_only=False, reproducible=False),
        ],
        settlement_rows=[
            _settlement_row(lock_id="legacy", outcome="WIN"),
            _settlement_row(lock_id="thin", outcome="WIN"),
        ],
        generated_at="2026-07-02T01:00:00Z",
    )

    assert rows == []


def test_calibration_report_outputs_metrics_only_after_sample_floor() -> None:
    locks = [_lock_row(lock_id=f"lock-{index}") for index in range(30)]
    settlements = [
        _settlement_row(lock_id=f"lock-{index}", outcome="WIN" if index < 18 else "LOSS")
        for index in range(30)
    ]

    rows = build_calibration_report(
        lock_rows=locks,
        settlement_rows=settlements,
        generated_at="2026-07-02T01:00:00Z",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["sample_count"] == 30
    assert row["status"] == "READY"
    assert row["label"] == "样本已达标 30/30"
    assert row["predicted_cover_probability"] == 0.6
    assert row["actual_cover_probability"] == 0.6
    assert row["brier"] is not None
    assert row["log_loss"] is not None


def test_lambda_fit_gap_report_blocks_until_settled_lock_sample_floor() -> None:
    report = build_lambda_fit_gap_report(
        settled_lock_sample_count=0,
        generated_at="2026-07-02T01:00:00Z",
    )

    assert report["status"] == "BLOCKED_WITH_SAMPLE_GATE"
    assert report["blockers"] == [WALK_FORWARD_REQUIRES_SETTLED_LOCK_SAMPLE_N_GE_200]
    assert report["config_generated"] is False
    assert report["enabled_for_online_path"] is False
    assert report["provider_calls"] == 0
    assert report["db_writes"] == 0
    assert report["market_odds_or_lines_used"] is False


def _lock_row(
    *,
    lock_id: str,
    reproducible: bool = True,
    legacy_marker_only: bool = False,
) -> dict[str, object]:
    return {
        "lock_id": lock_id,
        "release_sha": "release-sha",
        "tier": "FORMAL",
        "pick_line": "-0.5",
        "reproducible": reproducible,
        "legacy_marker_only": legacy_marker_only,
        "market_timeline_json": {"pattern": "STABLE"},
        "ah_settlement_distribution_json": {
            "WIN": 0.55,
            "HALF_WIN": 0.0,
            "PUSH": 0.1,
            "HALF_LOSS": 0.0,
            "LOSS": 0.35,
        },
    }


def _settlement_row(*, lock_id: str, outcome: str) -> dict[str, object]:
    return {
        "lock_id": lock_id,
        "outcome": outcome,
        "movement_pattern": "STABLE",
    }
