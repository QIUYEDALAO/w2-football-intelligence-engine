from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine

from w2.infrastructure.database import Base
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.tracking.forward_outcome_ledger import backfill_outcomes, ledger_fixture_ids
from w2.tracking.forward_result_source import normalized_finished_results

NOW = datetime(2026, 7, 11, 2, 0, tzinfo=UTC)


def _fixture_payload(
    fixture_id: str,
    *,
    status: str = "FT",
    home: int | None = 2,
    away: int | None = 1,
) -> dict[str, object]:
    return {
        "response": [
            {
                "fixture": {"id": fixture_id, "status": {"short": status}},
                "score": {"fulltime": {"home": home, "away": away}},
            }
        ]
    }


def _capture(fixture_id: str) -> dict[str, object]:
    return {
        "schema_version": "w2.forward_outcome_ledger.v2",
        "record_type": "capture",
        "captured_at": "2026-07-10T00:00:00Z",
        "football_day": "2026-07-10",
        "environment": "staging",
        "fixture_id": fixture_id,
        "kickoff_utc": "2026-07-11T00:00:00Z",
        "card_hash": "card-1",
        "shadow_pick": {
            "market": "ASIAN_HANDICAP",
            "selection": "HOME_AH",
        },
        "current_odds": {
            "ah": {
                "home_line": "-0.5",
                "away_line": "+0.5",
                "home_price": 1.91,
                "away_price": 1.95,
            }
        },
    }


def test_normalizes_aet_using_fulltime_score() -> None:
    rows = normalized_finished_results(
        _fixture_payload("fixture-aet", status="AET", home=1, away=1),
        provider="api_football",
        confirmed_at=NOW,
        raw_payload_hash="a" * 64,
    )

    assert rows[0]["result_payload"] == {
        "fixture_id": "fixture-aet",
        "status": "AET",
        "score": {"fulltime": {"home": 1, "away": 1}},
    }


def test_repository_persists_results_idempotently_and_reads_by_fixture(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'results.db'}")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    payload = _fixture_payload("fixture-1")

    assert repository.append_finished_result_events(
        payload=payload,
        captured_at=NOW,
        raw_payload_hash="b" * 64,
    ) == 1
    assert repository.append_finished_result_events(
        payload=payload,
        captured_at=NOW,
        raw_payload_hash="b" * 64,
    ) == 0
    assert repository.result_events_for_fixture_ids(["fixture-1", "missing"]) == [
        {
            "fixture_id": "fixture-1",
            "status": "FT",
            "score": {"fulltime": {"home": 2, "away": 1}},
        }
    ]


def test_repository_reads_sanitized_result_from_existing_raw_fixture_payload(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'raw-results.db'}")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    repository.save_raw_payload(
        sha256="c" * 64,
        endpoint="fixtures",
        captured_at=NOW,
        payload=_fixture_payload("fixture-raw", status="PEN", home=0, away=0),
    )

    assert repository.result_events_for_fixture_ids(["fixture-raw"]) == [
        {
            "fixture_id": "fixture-raw",
            "status": "PEN",
            "score": {"fulltime": {"home": 0, "away": 0}},
        }
    ]


def test_persisted_result_settles_fixture_after_it_left_day_view(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    ledger_root = runtime_root / "forward_outcome_ledger"
    ledger_root.mkdir(parents=True)
    ledger_path = ledger_root / "2026-07-10_staging.jsonl"
    ledger_path.write_text(json.dumps(_capture("fixture-1")) + "\n", encoding="utf-8")

    assert ledger_fixture_ids(runtime_root) == ["fixture-1"]
    first = backfill_outcomes(
        runtime_root,
        {"results": [_fixture_payload("fixture-1")["response"][0]]},
        dry_run=False,
        write_artifacts=True,
        settled_at=NOW,
    )
    second = backfill_outcomes(
        runtime_root,
        {"results": [_fixture_payload("fixture-1")["response"][0]]},
        dry_run=False,
        write_artifacts=True,
        settled_at=NOW,
    )

    assert first["written"] == 1
    assert first["records"] == []
    assert second["written"] == 0
    rows = [json.loads(line) for line in ledger_path.read_text().splitlines()]
    assert rows[-1]["record_type"] == "outcome"
    assert rows[-1]["settlement_outcome"] == "WIN"
    assert rows[-1]["settled_side"] == "shadow_pick"


def test_missing_aet_fulltime_remains_unsettled(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    ledger_root = runtime_root / "forward_outcome_ledger"
    ledger_root.mkdir(parents=True)
    (ledger_root / "2026-07-10_staging.jsonl").write_text(
        json.dumps(_capture("fixture-aet")) + "\n",
        encoding="utf-8",
    )

    fixture = _fixture_payload(
        "fixture-aet",
        status="AET",
        home=None,
        away=None,
    )["response"][0]
    result = backfill_outcomes(
        runtime_root,
        {"results": [fixture]},
        dry_run=True,
        write_artifacts=False,
    )

    assert result["record_count"] == 0
    assert result["unsettled_missing_fulltime"] == 1
