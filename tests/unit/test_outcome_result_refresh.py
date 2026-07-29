from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
)
from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayEndpointCaptureModel,
    MatchdayFixtureIdentityModel,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.infrastructure.persistence.outcome_ledger_models import OutcomeLedgerModel
from w2.tracking.outcome_ledger_repository import OutcomeLedgerRepository
from w2.tracking.outcome_result_refresh import run_outcome_result_refresh

NOW = datetime(2026, 7, 19, 4, 0, tzinfo=UTC)


@pytest.mark.parametrize("status", ["FT", "AET", "PEN"])
def test_result_materializer_writes_terminal_scores(
    tmp_path: Path,
    status: str,
) -> None:
    repository = _repository(tmp_path)
    _seed_fixture(repository, provider_id="101", status=status, fulltime=(2, 1))

    result = run_outcome_result_refresh(
        repository=repository,
        fixture_ids=["api_football:101"],
        now=NOW,
        dry_run=False,
        write_db=True,
    )

    assert result["status"] == "PASS"
    assert result["materialized_result_count"] == 1
    assert result["provider_calls"] == 0
    assert result["result_db_writes"] == 1
    assert result["scoring_projection_status"] == "PASS"
    assert _result_row(repository, "api_football:101") == (status, 2, 1)


def test_result_materializer_does_not_write_non_terminal_fixture(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_fixture(repository, provider_id="102", status="NS", fulltime=None)

    result = run_outcome_result_refresh(
        repository=repository,
        dry_run=False,
        write_db=True,
    )

    assert result["status"] == "PASS"
    assert result["result_not_finished_count"] == 1
    assert result["db_writes"] == 0


def test_result_materializer_fails_closed_on_terminal_missing_score(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_fixture(repository, provider_id="103", status="FT", fulltime=None)

    result = run_outcome_result_refresh(
        repository=repository,
        dry_run=False,
        write_db=True,
    )

    assert result["status"] == "BLOCKED"
    assert result["result_source_missing_count"] == 1
    assert result["blockers"] == ["api_football:103:RESULT_SOURCE_MISSING"]
    assert result["db_writes"] == 0


def test_committed_valid_result_is_scored_when_peer_source_is_missing(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    _seed_fixture(repository, provider_id="201", status="FT", fulltime=(2, 0))
    _seed_fixture(repository, provider_id="202", status="FT", fulltime=None)

    result = run_outcome_result_refresh(
        repository=repository,
        dry_run=False,
        write_db=True,
    )

    assert result["status"] == "BLOCKED"
    assert result["result_db_writes"] == 1
    assert result["scoring_projection"]["fixture_checkpoint_count"] == 1
    assert result["scoring_projection_status"] == "PASS"


def test_result_materializer_is_idempotent_for_same_score(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_fixture(repository, provider_id="104", status="FT", fulltime=(1, 0))

    first = run_outcome_result_refresh(
        repository=repository,
        dry_run=False,
        write_db=True,
    )
    second = run_outcome_result_refresh(
        repository=repository,
        dry_run=False,
        write_db=True,
    )

    assert first["materialized_result_count"] == 1
    assert second["already_materialized_count"] == 1
    assert second["db_writes"] == 0


def test_result_materializer_fails_closed_on_conflicting_scores(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_fixture(repository, provider_id="105", status="FT", fulltime=(1, 0))
    _seed_raw(repository, provider_id="105", status="FT", fulltime=(2, 0), suffix="conflict")

    result = run_outcome_result_refresh(
        repository=repository,
        dry_run=False,
        write_db=True,
    )

    assert result["status"] == "BLOCKED"
    assert result["result_source_conflict_count"] == 1
    assert result["blockers"] == ["api_football:105:RESULT_SOURCE_CONFLICT"]
    assert result["db_writes"] == 0


@pytest.mark.parametrize("requested", ["106", "api_football:106"])
def test_result_materializer_resolves_bare_and_canonical_provider_id(
    tmp_path: Path,
    requested: str,
) -> None:
    repository = _repository(tmp_path)
    _seed_fixture(repository, provider_id="106", status="FT", fulltime=(3, 2))

    result = run_outcome_result_refresh(
        repository=repository,
        fixture_ids=[requested],
        dry_run=False,
        write_db=True,
    )

    assert result["inspected_fixture_count"] == 1
    assert _result_row(repository, "api_football:106") == ("FT", 3, 2)


def test_result_materializer_does_not_match_by_team_name(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_fixture(repository, provider_id="107", status="FT", fulltime=(1, 1))

    result = run_outcome_result_refresh(
        repository=repository,
        fixture_ids=["Home v Away"],
        dry_run=False,
        write_db=True,
    )

    assert result["inspected_fixture_count"] == 0
    assert result["status"] == "BLOCKED"
    assert result["blockers"] == ["Home v Away:RESULT_SOURCE_MISSING"]
    assert result["db_writes"] == 0


def test_result_materializer_never_imports_or_calls_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    _seed_fixture(repository, provider_id="108", status="FT", fulltime=(2, 2))
    monkeypatch.setattr(
        "builtins.__import__",
        _provider_import_guard,
    )

    result = run_outcome_result_refresh(
        repository=repository,
        dry_run=True,
        write_db=False,
    )

    assert result["provider_calls"] == 0
    assert result["db_writes"] == 0
    assert result["materialized_result_count"] == 0


def _repository(root: Path) -> OutcomeLedgerRepository:
    engine = create_engine(f"sqlite+pysqlite:///{root / 'results.db'}")
    RawPayloadModel.__table__.create(engine, checkfirst=True)
    MatchdayEndpointCaptureModel.__table__.create(engine, checkfirst=True)
    MatchdayFixtureIdentityModel.__table__.create(engine, checkfirst=True)
    ResultModel.__table__.create(engine, checkfirst=True)
    OutcomeLedgerModel.__table__.create(engine, checkfirst=True)
    DynamicPrematchEvaluationModel.__table__.create(engine, checkfirst=True)
    ReadModelCheckpointModel.__table__.create(engine, checkfirst=True)
    return OutcomeLedgerRepository(engine)


def _seed_fixture(
    repository: OutcomeLedgerRepository,
    *,
    provider_id: str,
    status: str,
    fulltime: tuple[int, int] | None,
) -> None:
    raw_hash, payload = _seed_raw(
        repository,
        provider_id=provider_id,
        status=status,
        fulltime=fulltime,
        suffix="identity",
    )
    capture_id = f"capture-{provider_id}"
    with Session(repository.engine) as session:
        session.add(
            MatchdayEndpointCaptureModel(
                capture_id=capture_id,
                fixture_id=f"api_football:{provider_id}",
                competition_id="premier_league",
                checkpoint="RESULT",
                endpoint="fixtures",
                sanitized_params={"id": provider_id},
                params_hash=sha256(provider_id.encode()).hexdigest(),
                request_task_key=f"fixture:{provider_id}",
                attempt=1,
                requested_at=NOW,
                provider_captured_at=NOW,
                status_code=200,
                elapsed_ms=1,
                response_count=1,
                quota_values={},
                raw_payload_sha256=raw_hash,
                provider_event_time=None,
                capture_status="SUCCESS",
                error_code=None,
            )
        )
        session.add(
            MatchdayFixtureIdentityModel(
                fixture_id=f"api_football:{provider_id}",
                provider="api_football",
                provider_fixture_id=provider_id,
                competition_id="premier_league",
                provider_league_id="39",
                season="2026",
                kickoff_utc=NOW,
                fixture_status=status,
                home_provider_team_id="1",
                away_provider_team_id="2",
                home_w2_team_id="home",
                away_w2_team_id="away",
                team_identity_status="RESOLVED",
                raw_payload_sha256=raw_hash,
                endpoint_capture_id=capture_id,
                captured_at=NOW,
                identity_hash=sha256(f"identity:{provider_id}".encode()).hexdigest(),
                payload=payload["response"][0],
            )
        )
        session.commit()


def _seed_raw(
    repository: OutcomeLedgerRepository,
    *,
    provider_id: str,
    status: str,
    fulltime: tuple[int, int] | None,
    suffix: str,
) -> tuple[str, dict[str, Any]]:
    payload = _fixture_payload(
        provider_id=provider_id,
        status=status,
        fulltime=fulltime,
    )
    raw_hash = sha256(f"{provider_id}:{status}:{fulltime}:{suffix}".encode()).hexdigest()
    with Session(repository.engine) as session:
        session.add(
            RawPayloadModel(
                sha256=raw_hash,
                endpoint="fixtures",
                captured_at=NOW,
                storage_uri=f"db://raw_payload/{raw_hash}",
                payload=payload,
            )
        )
        session.commit()
    return raw_hash, payload


def _fixture_payload(
    *,
    provider_id: str,
    status: str,
    fulltime: tuple[int, int] | None,
) -> dict[str, Any]:
    return {
        "response": [
            {
                "fixture": {
                    "id": int(provider_id),
                    "date": "2026-07-10T02:00:00Z",
                    "status": {"short": status},
                },
                "teams": {
                    "home": {"id": 1, "name": "Home"},
                    "away": {"id": 2, "name": "Away"},
                },
                "score": {
                    "fulltime": {
                        "home": fulltime[0] if fulltime else None,
                        "away": fulltime[1] if fulltime else None,
                    }
                },
            }
        ]
    }


def _result_row(
    repository: OutcomeLedgerRepository,
    fixture_id: str,
) -> tuple[str, int, int] | None:
    with Session(repository.engine) as session:
        row = session.scalar(
            select(ResultModel).where(ResultModel.fixture_id == fixture_id)
        )
        if row is None:
            return None
        return (row.result_status, row.home_goals, row.away_goals)


def _provider_import_guard(
    name: str,
    globals: dict[str, Any] | None = None,
    locals: dict[str, Any] | None = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
) -> Any:
    if "provider" in name.lower() or "api_football" in name.lower():
        raise AssertionError(f"provider import forbidden: {name}")
    return _ORIGINAL_IMPORT(name, globals, locals, fromlist, level)


_ORIGINAL_IMPORT = __import__
