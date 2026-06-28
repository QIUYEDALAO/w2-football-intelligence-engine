from __future__ import annotations

from w2.backtest.handicap_walkforward import (
    RealWalkForwardInputs,
    build_real_handicap_walkforward_report,
)


def test_real_walkforward_without_lock_artifacts_is_not_authoritative(tmp_path) -> None:
    report = build_real_handicap_walkforward_report(
        RealWalkForwardInputs(timeline_root=tmp_path, fixture_rows=[])
    )

    assert report["authoritative"] is False
    assert report["samples"] == 0
    assert report["beats_market"] is False
    assert report["formal_enabled"] is False
    assert report["candidate_enabled"] is False
    assert "INSUFFICIENT_VALIDATED_SAMPLES" in report["blockers"]


def test_real_walkforward_skips_unreadable_timeline_root() -> None:
    class UnreadableRoot:
        def glob(self, pattern: str) -> list[object]:
            raise PermissionError("blocked")

    report = build_real_handicap_walkforward_report(
        RealWalkForwardInputs(timeline_root=UnreadableRoot())  # type: ignore[arg-type]
    )

    assert report["authoritative"] is False
    assert report["samples"] == 0
    assert report["beats_market"] is False
