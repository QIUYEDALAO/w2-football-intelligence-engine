from __future__ import annotations

import multiprocessing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from w2.infrastructure.atomic_files import read_jsonl
from w2.ingestion.market_timeline import (
    load_timeline_result,
    write_timeline_snapshot,
)
from w2.tracking.forward_ledger_performance import forward_ledger_performance
from w2.tracking.forward_outcome_ledger import backfill_outcomes, run_forward_outcome_ledger


def test_multiprocess_append_deduplicates_capture_and_outcome(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(target=_write_same_capture, args=(str(tmp_path),)) for _ in range(6)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=15)
        assert process.exitcode == 0

    outcome_processes = [
        context.Process(target=_write_same_outcome, args=(str(tmp_path),)) for _ in range(6)
    ]
    for process in outcome_processes:
        process.start()
    for process in outcome_processes:
        process.join(timeout=15)
        assert process.exitcode == 0

    path = tmp_path / "forward_outcome_ledger" / "2026-07-15_staging.jsonl"
    result = read_jsonl(path)
    assert result.status == "PASS"
    assert [row["record_type"] for row in result.records] == ["capture", "outcome"]


def test_truncated_tail_preserves_valid_records_and_reports_degraded(tmp_path: Path) -> None:
    root = tmp_path / "forward_outcome_ledger"
    root.mkdir()
    path = root / "ledger.jsonl"
    path.write_text('{"fixture_id":"fixture-1"}\n{"fixture_id":', encoding="utf-8")

    result = read_jsonl(path)
    performance = forward_ledger_performance(tmp_path)

    assert result.records == [{"fixture_id": "fixture-1"}]
    assert result.status == "DEGRADED"
    assert result.corruption_count == 1
    assert performance["fixture_count"] == 1
    assert performance["source_read_status"] == "DEGRADED"
    assert performance["source_corruption_count"] == 1


def test_timeline_crash_before_replace_keeps_old_complete_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kickoff = datetime(2026, 7, 16, 12, tzinfo=UTC)
    first = _snapshot("opening", "2026-07-15T08:00:00Z", "first")
    path = tmp_path / "fixture-1.json"
    assert write_timeline_snapshot(
        root=tmp_path,
        fixture_id="fixture-1",
        kickoff=kickoff,
        snapshot=first,
    ).written
    old_bytes = path.read_bytes()

    def crash(_source: Path, _target: Path) -> None:
        raise OSError("simulated replace crash")

    monkeypatch.setattr("w2.infrastructure.atomic_files.os.replace", crash)
    with pytest.raises(OSError, match="simulated replace crash"):
        write_timeline_snapshot(
            root=tmp_path,
            fixture_id="fixture-1",
            kickoff=kickoff,
            snapshot=_snapshot("T-24h", "2026-07-15T09:00:00Z", "second"),
        )

    assert path.read_bytes() == old_bytes
    result = load_timeline_result(path)
    assert result.status == "PASS"
    assert result.payload["snapshots"] == [first]
    assert not list(tmp_path.glob("*.tmp"))


def test_fixture_lock_prevents_lost_timeline_updates(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(
            target=_write_timeline_point,
            args=(str(tmp_path), checkpoint, as_of, source_hash),
        )
        for checkpoint, as_of, source_hash in (
            ("opening", "2026-07-15T08:00:00Z", "first"),
            ("T-24h", "2026-07-15T09:00:00Z", "second"),
        )
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=15)
        assert process.exitcode == 0

    result = load_timeline_result(tmp_path / "fixture-1.json")
    assert result.status == "PASS"
    assert {row["checkpoint"] for row in result.payload["snapshots"]} == {
        "opening",
        "T-24h",
    }


def test_corrupt_timeline_is_not_reported_as_empty_or_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "fixture-1.json"
    path.write_text('{"snapshots":', encoding="utf-8")
    result = load_timeline_result(path)

    write = write_timeline_snapshot(
        root=tmp_path,
        fixture_id="fixture-1",
        kickoff=datetime(2026, 7, 16, 12, tzinfo=UTC),
        snapshot=_snapshot("opening", "2026-07-15T08:00:00Z", "first"),
    )

    assert result.status == "CORRUPT"
    assert result.error_class == "JSONDecodeError"
    assert write.status == "INVALID_EXISTING_TIMELINE"
    assert path.read_text(encoding="utf-8") == '{"snapshots":'


def _write_same_capture(root_text: str) -> None:
    run_forward_outcome_ledger(
        _day_view(),
        dry_run=False,
        write_artifacts=True,
        runtime_root=Path(root_text) / "forward_outcome_ledger",
        captured_at=datetime(2026, 7, 15, 9, tzinfo=UTC),
    )


def _write_same_outcome(root_text: str) -> None:
    backfill_outcomes(
        Path(root_text),
        {
            "results": [
                {
                    "fixture_id": "fixture-1",
                    "status": "FT",
                    "score": {"fulltime": {"home": 2, "away": 0}},
                }
            ]
        },
        dry_run=False,
        write_artifacts=True,
        settled_at=datetime(2026, 7, 15, 15, tzinfo=UTC),
    )


def _day_view() -> dict[str, object]:
    return {
        "football_day": "2026-07-15",
        "environment": "staging",
        "cards": [
            {
                "fixture_id": "fixture-1",
                "kickoff_utc": "2026-07-15T12:00:00Z",
                "decision_tier": "ANALYSIS_PICK",
                "pick": {"market": "ASIAN_HANDICAP", "selection": "HOME_AH"},
                "current_odds": {
                    "ah": {
                        "home_line": -1,
                        "away_line": 1,
                        "home_price": 1.91,
                        "away_price": 1.95,
                    }
                },
            }
        ],
    }


def _write_timeline_point(
    root_text: str, checkpoint: str, as_of: str, source_hash: str
) -> None:
    write_timeline_snapshot(
        root=Path(root_text),
        fixture_id="fixture-1",
        kickoff=datetime(2026, 7, 16, 12, tzinfo=UTC),
        snapshot=_snapshot(checkpoint, as_of, source_hash),
    )


def _snapshot(checkpoint: str, as_of: str, source_hash: str) -> dict[str, object]:
    return {
        "schema_version": "w2.market_timeline.v1",
        "fixture_id": "fixture-1",
        "checkpoint": checkpoint,
        "market": "TOTALS",
        "as_of": as_of,
        "kickoff_utc": "2026-07-16T12:00:00Z",
        "line": 2.5,
        "over_price": 1.91,
        "under_price": 1.95,
        "source_hash": source_hash,
        "immutable": True,
    }
