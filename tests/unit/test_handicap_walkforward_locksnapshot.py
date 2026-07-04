from __future__ import annotations

from datetime import UTC, datetime, timedelta

from w2.backtest.handicap_walkforward import (
    RealWalkForwardInputs,
    build_real_handicap_walkforward_report,
)
from w2.ingestion.market_timeline import select_mainline_snapshot, write_timeline_snapshot


def _write_lock(tmp_path, fixture_id: str = "fx1") -> None:
    kickoff = datetime(2026, 6, 28, 12, tzinfo=UTC)
    as_of = kickoff - timedelta(minutes=20)
    observations = [
        {
            "fixture_id": fixture_id,
            "captured_at": as_of.isoformat().replace("+00:00", "Z"),
            "canonical_market": "ASIAN_HANDICAP",
            "raw_market_label": "Asian Handicap",
            "selection": "HOME",
            "line": -0.25,
            "decimal_odds": 1.94,
            "bookmaker_id": "book-a",
        },
        {
            "fixture_id": fixture_id,
            "captured_at": as_of.isoformat().replace("+00:00", "Z"),
            "canonical_market": "ASIAN_HANDICAP",
            "raw_market_label": "Asian Handicap",
            "selection": "AWAY",
            "line": 0.25,
            "decimal_odds": 1.97,
            "bookmaker_id": "book-a",
        },
    ]
    snapshot = select_mainline_snapshot(
        observations=observations,
        fixture_id=fixture_id,
        kickoff=kickoff,
        checkpoint="lock",
        market="ASIAN_HANDICAP",
    )
    assert snapshot is not None
    write_timeline_snapshot(
        root=tmp_path,
        fixture_id=fixture_id,
        kickoff=kickoff,
        snapshot=snapshot,
    )


def test_valid_lock_snapshot_unblocks_missing_as_of(tmp_path) -> None:
    _write_lock(tmp_path)
    report = build_real_handicap_walkforward_report(
        RealWalkForwardInputs(
            from_date=datetime(2026, 6, 1, tzinfo=UTC).date(),
            to_date=datetime(2026, 7, 31, tzinfo=UTC).date(),
            timeline_root=tmp_path,
            fixture_rows=[
                {
                    "fixture_id": "fx1",
                    "kickoff_utc": "2026-06-28T12:00:00Z",
                    "fair_ah": -0.25,
                    "final_result": {"home": 1, "away": 0},
                    "settlement_outcome": "WIN",
                }
            ],
        )
    )

    row = report["sample"]["rows"][0]
    assert "MISSING_AS_OF" not in row["exclusion_reasons"]
    assert row["sample_included"] is True
    assert row["market_ah"] == -0.25
    assert report["samples"] == 1
    assert report["beats_market"] is False
    assert report["formal_enabled"] is False
    assert report["candidate_enabled"] is False


def test_missing_lock_snapshot_keeps_missing_as_of(tmp_path) -> None:
    report = build_real_handicap_walkforward_report(
        RealWalkForwardInputs(
            timeline_root=tmp_path,
            fixture_rows=[
                {
                    "fixture_id": "fx2",
                    "kickoff_utc": "2026-06-28T12:00:00Z",
                    "fair_ah": -0.25,
                    "final_result": {"home": 1, "away": 0},
                    "settlement_outcome": "WIN",
                }
            ],
        )
    )

    row = report["sample"]["rows"][0]
    assert row["sample_included"] is False
    assert "MISSING_AS_OF" in row["exclusion_reasons"]
    assert report["beats_market"] is False
