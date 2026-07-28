from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.matchday_intake_models import MatchdayFixtureIdentityModel
from w2.infrastructure.persistence.models import ResultModel
from w2.infrastructure.persistence.outcome_ledger_models import OutcomeLedgerModel
from w2.tracking.outcome_ledger_repository import (
    IMPORT_CONFIRMATION_PHRASE,
    OutcomeLedgerError,
    OutcomeLedgerRepository,
    import_runtime_ledger,
)


def test_outcome_ledger_append_is_idempotent_and_conflicts_fail_closed(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    capture = _capture()

    first = repository.append([capture], dry_run=False, write_db=True)
    second = repository.append([capture], dry_run=False, write_db=True)
    conflict = dict(capture)
    conflict["decision_hash"] = "different"

    assert first["written"] == 1
    assert second["written"] == 0
    assert second["already_imported"] == 1
    with pytest.raises(OutcomeLedgerError, match="LEDGER_IMPORT_IDENTITY_CONFLICT"):
        repository.append([conflict], dry_run=False, write_db=True)
    assert len(repository.records()) == 1


def test_outcome_ledger_orm_update_and_delete_are_blocked(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.append([_capture()], dry_run=False, write_db=True)

    with Session(repository.engine) as session:
        row = session.scalar(select(OutcomeLedgerModel))
        assert row is not None
        row.record_type = "changed"
        with pytest.raises(ValueError, match="append-only"):
            session.commit()
        session.rollback()

    with Session(repository.engine) as session:
        row = session.scalar(select(OutcomeLedgerModel))
        assert row is not None
        session.delete(row)
        with pytest.raises(ValueError, match="append-only"):
            session.commit()


def test_result_model_update_and_delete_are_blocked(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_result(repository)

    with Session(repository.engine) as session:
        row = session.scalar(select(ResultModel))
        assert row is not None
        row.home_goals = 9
        with pytest.raises(ValueError, match="append-only or immutable"):
            session.commit()
        session.rollback()

    with Session(repository.engine) as session:
        row = session.scalar(select(ResultModel))
        assert row is not None
        session.delete(row)
        with pytest.raises(ValueError, match="append-only or immutable"):
            session.commit()


def test_outcome_ledger_canonical_hash_has_deterministic_order(tmp_path: Path) -> None:
    first = _repository(tmp_path / "first")
    second = _repository(tmp_path / "second")
    capture = _capture()
    supersession = _supersession()

    first.append([capture, supersession], dry_run=False, write_db=True)
    second.append([supersession, capture], dry_run=False, write_db=True)

    assert first.canonical_aggregate_sha256() == second.canonical_aggregate_sha256()


def test_runtime_import_reconciles_count_hash_and_second_run_is_noop(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path / "db")
    _seed_identity(repository, "101")
    source = _source_tree(tmp_path / "runtime")

    dry_run = import_runtime_ledger(
        repository,
        source,
        dry_run=True,
        write_db=False,
        confirm_write=None,
    )
    first = import_runtime_ledger(
        repository,
        source,
        dry_run=False,
        write_db=True,
        confirm_write=IMPORT_CONFIRMATION_PHRASE,
    )
    second = import_runtime_ledger(
        repository,
        source,
        dry_run=False,
        write_db=True,
        confirm_write=IMPORT_CONFIRMATION_PHRASE,
    )

    assert dry_run["source_file_count"] == 3
    assert dry_run["source_record_count"] == 5
    assert dry_run["importable_record_count"] == 5
    assert first["source_record_count"] == first["db_record_count"] == 5
    assert first["source_canonical_sha256"] == first["db_canonical_sha256"]
    assert first["result_fixture_count"] == 1
    assert first["reconciliation_status"] == "PASS"
    assert second["importable_record_count"] == 0
    assert second["already_imported_count"] == 5
    assert second["db_writes"] == 0


def test_runtime_import_rejects_malformed_json_without_writes(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "db")
    source = tmp_path / "runtime"
    ledger = source / "forward_outcome_ledger"
    ledger.mkdir(parents=True)
    (ledger / "broken.jsonl").write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(OutcomeLedgerError, match="LEDGER_IMPORT_MALFORMED_RECORD"):
        import_runtime_ledger(
            repository,
            source,
            dry_run=False,
            write_db=True,
            confirm_write=IMPORT_CONFIRMATION_PHRASE,
        )
    assert repository.records() == []


def test_runtime_import_identity_conflict_rolls_back_everything(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "db")
    source = tmp_path / "runtime"
    ledger = source / "forward_outcome_ledger"
    ledger.mkdir(parents=True)
    first = _capture()
    conflict = dict(first)
    conflict["decision_hash"] = "different"
    _write_jsonl(ledger / "conflict.jsonl", [first, conflict])

    with pytest.raises(OutcomeLedgerError, match="LEDGER_IMPORT_IDENTITY_CONFLICT"):
        import_runtime_ledger(
            repository,
            source,
            dry_run=False,
            write_db=True,
            confirm_write=IMPORT_CONFIRMATION_PHRASE,
        )
    assert repository.records() == []


def test_runtime_import_score_conflict_rolls_back_everything(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "db")
    _seed_identity(repository, "101")
    source = tmp_path / "runtime"
    ledger = source / "forward_outcome_ledger"
    ledger.mkdir(parents=True)
    first = _outcome(home=2, away=1)
    conflict = dict(_outcome(home=3, away=1))
    conflict["capture_identity_hash"] = "capture-2"
    _write_jsonl(ledger / "score-conflict.jsonl", [first, conflict])

    with pytest.raises(OutcomeLedgerError, match="RESULT_SOURCE_CONFLICT"):
        import_runtime_ledger(
            repository,
            source,
            dry_run=False,
            write_db=True,
            confirm_write=IMPORT_CONFIRMATION_PHRASE,
        )
    assert repository.records() == []
    with Session(repository.engine) as session:
        assert list(session.scalars(select(ResultModel))) == []


def test_runtime_import_requires_explicit_write_confirmation(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "db")
    with pytest.raises(
        OutcomeLedgerError,
        match="LEDGER_IMPORT_WRITE_REQUIRES_CONFIRMATION",
    ):
        import_runtime_ledger(
            repository,
            tmp_path,
            dry_run=False,
            write_db=True,
            confirm_write=None,
        )


def _repository(root: Path) -> OutcomeLedgerRepository:
    root.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite+pysqlite:///{root / 'ledger.db'}")
    Base.metadata.create_all(engine)
    return OutcomeLedgerRepository(engine)


def _seed_identity(repository: OutcomeLedgerRepository, provider_id: str) -> None:
    with Session(repository.engine) as session:
        session.add(
            MatchdayFixtureIdentityModel(
                fixture_id=f"api_football:{provider_id}",
                provider="api_football",
                provider_fixture_id=provider_id,
                competition_id="premier_league",
                provider_league_id="39",
                season="2026",
                kickoff_utc=datetime(2026, 7, 8, tzinfo=UTC),
                fixture_status="FT",
                home_provider_team_id="1",
                away_provider_team_id="2",
                home_w2_team_id="home",
                away_w2_team_id="away",
                team_identity_status="RESOLVED",
                raw_payload_sha256="a" * 64,
                endpoint_capture_id=None,
                captured_at=datetime(2026, 7, 8, 3, tzinfo=UTC),
                identity_hash="b" * 64,
                payload={},
            )
        )
        session.commit()


def _seed_result(repository: OutcomeLedgerRepository) -> None:
    with Session(repository.engine) as session:
        session.add(
            ResultModel(
                fixture_id="api_football:101",
                home_goals=2,
                away_goals=1,
                result_status="FT",
                confirmed_at=datetime(2026, 7, 8, 3, tzinfo=UTC),
                source_payload_sha256="c" * 64,
                source_capture_id=None,
                result_hash="d" * 64,
            )
        )
        session.commit()


def _source_tree(root: Path) -> Path:
    ledger = root / "forward_outcome_ledger"
    snapshots = root / "formal_recommendation_snapshots"
    settlements = root / "formal_recommendation_settlements"
    ledger.mkdir(parents=True)
    snapshots.mkdir()
    settlements.mkdir()
    legacy_capture = _capture()
    legacy_capture.pop("record_type")
    _write_jsonl(
        ledger / "2026-07-07_staging.jsonl",
        [legacy_capture, _outcome(), _supersession()],
    )
    (snapshots / "snapshot.json").write_text(
        json.dumps(
            {
                "schema_version": "w2_formal_recommendation_snapshot.v1",
                "snapshot_id": "snapshot-1",
                "fixture_id": "api_football:101",
                "captured_at": "2026-07-07T00:00:00Z",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (settlements / "settlement.json").write_text(
        json.dumps(
            {
                "schema_version": "w2_formal_recommendation_settlement.v1",
                "settlement_id": "settlement-1",
                "snapshot_id": "snapshot-1",
                "fixture_id": "api_football:101",
                "evaluated_at": "2026-07-08T03:00:00Z",
                "final_score": {
                    "home_goals": 2,
                    "away_goals": 1,
                    "status": "FT",
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return root


def _capture() -> dict[str, object]:
    return {
        "schema_version": "w2.forward_outcome_ledger.v3",
        "record_type": "capture",
        "fixture_id": "api_football:101",
        "captured_at": "2026-07-07T00:00:00Z",
        "capture_identity_hash": "capture-1",
        "decision_hash": "decision-1",
        "recommendation_scope": "VALIDATION",
    }


def _outcome(home: int = 2, away: int = 1) -> dict[str, object]:
    return {
        "schema_version": "w2.forward_outcome_ledger.v3",
        "record_type": "outcome",
        "fixture_id": "api_football:101",
        "settled_at": "2026-07-08T03:00:00Z",
        "capture_identity_hash": "capture-1",
        "settled_side": "pick",
        "market": "TOTALS",
        "selection": "OVER",
        "final_score": {"home": home, "away": away, "status": "FT"},
        "settlement_outcome": "WIN",
    }


def _supersession() -> dict[str, object]:
    return {
        "schema_version": "w2.forward_outcome_ledger.v3",
        "record_type": "supersession",
        "fixture_id": "api_football:101",
        "superseded_at": "2026-07-07T01:00:00Z",
        "target_capture_identity_hash": "capture-old",
        "reason_code": "REPLACED",
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows),
        encoding="utf-8",
    )
