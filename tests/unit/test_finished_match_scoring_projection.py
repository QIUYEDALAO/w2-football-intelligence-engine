from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayFixtureIdentityModel,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.infrastructure.persistence.outcome_ledger_models import OutcomeLedgerModel
from w2.tracking import finished_match_scoring_cli
from w2.tracking.finished_match_scoring_projection import (
    WRITE_CONFIRMATION_PHRASE,
    run_finished_match_scoring_projection,
)
from w2.tracking.forward_ledger_performance import (
    CLV_METHOD,
    _brier,
    _log_loss,
    _probability_vector,
    _rps,
)
from w2.tracking.outcome_ledger_repository import OutcomeLedgerRepository
from w2.tracking.performance_scoring import brier, log_loss, probability_vector, rps

KICKOFF = datetime(2026, 7, 20, 16, 0, tzinfo=UTC)


def test_latest_complete_prekickoff_capture_scores_watch_without_pick(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    _seed_result(repository, "fixture-1", home=2, away=1)
    _seed_identity(repository, "fixture-1", kickoff=KICKOFF)
    old = _capture("fixture-1", KICKOFF - timedelta(hours=2), identity="old")
    latest = _capture(
        "fixture-1",
        KICKOFF - timedelta(minutes=5),
        identity="latest",
        model=(0.6, 0.2, 0.2),
        market=(0.4, 0.3, 0.3),
    )
    post = _capture("fixture-1", KICKOFF, identity="post")
    repository.append([old, latest, post], dry_run=False, write_db=True)

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, "performance:fixture:fixture-1")

    assert result["status"] == "PASS"
    assert result["scored_count"] == 1
    assert payload["status"] == "SCORED"
    assert payload["source_capture_identity_hash"] == "latest"
    assert payload["model_probabilities"] == [0.6, 0.2, 0.2]
    assert payload["clv_status"] == "NOT_APPLICABLE_NO_PICK"
    assert payload["clv_method"] == CLV_METHOD


def test_superseded_capture_is_excluded_and_missing_vector_is_checkpointed(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    _seed_result(repository, "fixture-2", home=1, away=1)
    _seed_identity(repository, "fixture-2", kickoff=KICKOFF)
    complete = _capture(
        "fixture-2",
        KICKOFF - timedelta(minutes=5),
        identity="superseded",
    )
    incomplete = _capture(
        "fixture-2",
        KICKOFF - timedelta(minutes=10),
        identity="active",
        model=None,
    )
    repository.append(
        [
            complete,
            incomplete,
            {
                "schema_version": "w2.forward_outcome_ledger.v3",
                "record_type": "supersession",
                "fixture_id": "fixture-2",
                "captured_at": (KICKOFF - timedelta(minutes=1)).isoformat(),
                "supersession_status": "SUPERSEDED",
                "target_capture_identity_hash": "superseded",
                "supersession_hash": "supersession-2",
            },
        ],
        dry_run=False,
        write_db=True,
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, "performance:fixture:fixture-2")

    assert result["status"] == "PASS"
    assert result["not_scorable_count"] == 1
    assert payload["status"] == "NOT_SCORABLE"
    assert payload["reason_codes"] == ["MODEL_PROBABILITY_VECTOR_MISSING"]


def test_equal_timestamp_different_identity_is_blocked(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_result(repository, "fixture-3", home=0, away=2)
    _seed_identity(repository, "fixture-3", kickoff=KICKOFF)
    captured = KICKOFF - timedelta(minutes=10)
    repository.append(
        [
            _capture("fixture-3", captured, identity="capture-a"),
            _capture(
                "fixture-3",
                captured,
                identity="capture-b",
                model=(0.2, 0.2, 0.6),
            ),
        ],
        dry_run=False,
        write_db=True,
    )

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, "performance:fixture:fixture-3")

    assert result["status"] == "BLOCKED"
    assert payload["status"] == "BLOCKED"
    assert payload["reason_codes"] == [
        "EQUAL_TIMESTAMP_DIFFERENT_BUSINESS_IDENTITY"
    ]


def test_fixture_clv_uses_existing_selection_and_method(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_result(repository, "fixture-clv", home=2, away=0)
    _seed_identity(repository, "fixture-clv", kickoff=KICKOFF)
    entry = _capture(
        "fixture-clv",
        KICKOFF - timedelta(hours=24),
        identity="clv-entry",
        kickoff=KICKOFF,
    )
    closing = _capture(
        "fixture-clv",
        KICKOFF - timedelta(minutes=5),
        identity="clv-closing",
        kickoff=KICKOFF,
    )
    for record, price in ((entry, 2.0), (closing, 1.9)):
        record["pick"] = {"market": "ASIAN_HANDICAP", "selection": "HOME_AH"}
        record["recommendation_scope"] = "VALIDATION"
        record["current_odds"] = {
            "ah": {
                "home_line": "-1",
                "away_line": "+1",
                "home_price": price,
                "away_price": 1.9,
            }
        }
    repository.append([entry, closing], dry_run=False, write_db=True)

    run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    payload = _checkpoint(repository, "performance:fixture:fixture-clv")

    assert payload["clv_status"] == "AVAILABLE"
    assert payload["clv_decimal"] == 0.1
    assert payload["clv_method"] == CLV_METHOD


def test_same_source_with_different_payload_fails_closed(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_result(repository, "fixture-conflict", home=1, away=0)
    _seed_identity(repository, "fixture-conflict", kickoff=KICKOFF)
    repository.append(
        [
            _capture(
                "fixture-conflict",
                KICKOFF - timedelta(minutes=5),
                identity="stable-source",
                kickoff=KICKOFF,
            )
        ],
        dry_run=False,
        write_db=True,
    )
    run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    with Session(repository.engine) as session:
        row = session.scalar(
            select(ReadModelCheckpointModel).where(
                ReadModelCheckpointModel.checkpoint_key
                == "performance:fixture:fixture-conflict"
            )
        )
        assert row is not None
        row.payload = {**row.payload, "model_log_loss": 999.0}
        session.commit()

    result = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )

    assert result["status"] == "BLOCKED"
    assert any(
        "SAME_SOURCE_PAYLOAD_CONFLICT" in blocker
        for blocker in result["blockers"]
    )
    assert (
        _checkpoint(
            repository,
            "performance:fixture:fixture-conflict",
        )["model_log_loss"]
        == 999.0
    )


def test_projection_and_cohorts_are_idempotent_and_windowed(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    for index, days in enumerate((0, 7, 8, 30, 31), start=1):
        fixture_id = f"window-{index}"
        kickoff = KICKOFF - timedelta(days=days)
        _seed_result(repository, fixture_id, home=1, away=0)
        _seed_identity(repository, fixture_id, kickoff=kickoff)
        repository.append(
            [_capture(fixture_id, kickoff - timedelta(hours=1), identity=f"capture-{index}")],
            dry_run=False,
            write_db=True,
        )

    first = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    hashes = _performance_hashes(repository)
    second = run_finished_match_scoring_projection(
        engine=repository.engine,
        dry_run=False,
        write_db=True,
    )
    cohort = _checkpoint(repository, "performance:cohort:all")

    assert first["fixture_checkpoint_count"] == 5
    assert second["db_writes"] == 0
    assert _performance_hashes(repository) == hashes
    assert cohort["windows"]["7d"]["finished_result_count"] == 2
    assert cohort["windows"]["30d"]["finished_result_count"] == 4
    assert cohort["windows"]["90d"]["finished_result_count"] == 5
    assert cohort["windows"]["7d"]["scored_count"] == 2


@pytest.mark.parametrize(
    ("home", "away", "actual"),
    [(2, 1, 0), (1, 1, 1), (0, 2, 2)],
)
def test_shared_scoring_math_matches_existing_golden_semantics(
    home: int,
    away: int,
    actual: int,
) -> None:
    record = {
        "probability_identity": {
            "model_probabilities": {
                "one_x_two": {
                    "probabilities": {"HOME": 0.5, "DRAW": 0.3, "AWAY": 0.2}
                }
            }
        }
    }
    vector = probability_vector(record, "model_probabilities")

    assert actual == (0 if home > away else (1 if home == away else 2))
    assert vector == _probability_vector(record, "model_probabilities")
    assert vector is not None
    assert log_loss(vector, actual) == _log_loss(vector, actual)
    assert brier(vector, actual) == _brier(vector, actual)
    assert rps(vector, actual) == _rps(vector, actual)


def test_operator_cli_exit_and_confirmation_semantics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = {
        "status": "PASS",
        "finished_result_count": 1,
        "fixture_checkpoint_count": 1,
        "cohort_checkpoint_count": 4,
        "scored_count": 1,
        "not_scorable_count": 0,
        "blocked_count": 0,
        "db_writes": 0,
        "provider_calls": 0,
    }
    monkeypatch.setattr(
        finished_match_scoring_cli,
        "run_finished_match_scoring_projection",
        lambda **_kwargs: payload,
    )

    assert finished_match_scoring_cli.main(["--json"]) == 0
    assert '"status": "PASS"' in capsys.readouterr().out
    assert (
        finished_match_scoring_cli.main(
            [
                "--no-dry-run",
                "--write-db",
                "--confirm-write",
                WRITE_CONFIRMATION_PHRASE,
            ]
        )
        == 0
    )
    with pytest.raises(SystemExit):
        finished_match_scoring_cli.main(
            ["--no-dry-run", "--write-db"]
        )
    monkeypatch.setattr(
        finished_match_scoring_cli,
        "run_finished_match_scoring_projection",
        lambda **_kwargs: {**payload, "status": "BLOCKED"},
    )
    assert finished_match_scoring_cli.main([]) == 1


def _repository(root: Path) -> OutcomeLedgerRepository:
    engine = create_engine(f"sqlite+pysqlite:///{root / 'scoring.db'}")
    for table in (
        ResultModel.__table__,
        OutcomeLedgerModel.__table__,
        MatchdayFixtureIdentityModel.__table__,
        DynamicPrematchEvaluationModel.__table__,
        ReadModelCheckpointModel.__table__,
    ):
        table.create(engine, checkfirst=True)
    return OutcomeLedgerRepository(engine)


def _seed_result(
    repository: OutcomeLedgerRepository,
    fixture_id: str,
    *,
    home: int,
    away: int,
) -> None:
    identity = sha256(f"{fixture_id}:{home}:{away}".encode()).hexdigest()
    with Session(repository.engine) as session:
        session.add(
            ResultModel(
                fixture_id=fixture_id,
                home_goals=home,
                away_goals=away,
                result_status="FT",
                confirmed_at=KICKOFF + timedelta(hours=2),
                source_payload_sha256=identity,
                source_capture_id=None,
                result_hash=identity,
            )
        )
        session.commit()


def _seed_identity(
    repository: OutcomeLedgerRepository,
    fixture_id: str,
    *,
    kickoff: datetime,
) -> None:
    digest = sha256(fixture_id.encode()).hexdigest()
    with Session(repository.engine) as session:
        session.add(
            MatchdayFixtureIdentityModel(
                fixture_id=fixture_id,
                provider="api_football",
                provider_fixture_id=fixture_id,
                competition_id="premier_league",
                provider_league_id="39",
                season="2026",
                kickoff_utc=kickoff,
                fixture_status="FT",
                home_provider_team_id="1",
                away_provider_team_id="2",
                home_w2_team_id="home",
                away_w2_team_id="away",
                team_identity_status="COMPLETE",
                raw_payload_sha256=digest,
                endpoint_capture_id=None,
                captured_at=kickoff + timedelta(hours=2),
                identity_hash=digest,
                payload={},
            )
        )
        session.commit()


def _capture(
    fixture_id: str,
    captured_at: datetime,
    *,
    identity: str,
    model: tuple[float, float, float] | None = (0.5, 0.3, 0.2),
    market: tuple[float, float, float] | None = (0.4, 0.35, 0.25),
    kickoff: datetime | None = None,
) -> dict[str, Any]:
    def probabilities(
        values: tuple[float, float, float] | None,
    ) -> dict[str, Any]:
        if values is None:
            return {}
        return {
            "one_x_two": {
                "probabilities": dict(
                    zip(("HOME", "DRAW", "AWAY"), values, strict=True)
                )
            }
        }

    resolved_kickoff = kickoff or (
        KICKOFF
        if fixture_id in {"fixture-1", "fixture-2", "fixture-3"}
        else captured_at + timedelta(hours=1)
    )
    return {
        "schema_version": "w2.forward_outcome_ledger.v3",
        "record_type": "capture",
        "fixture_id": fixture_id,
        "captured_at": captured_at.isoformat(),
        "kickoff_utc": resolved_kickoff.isoformat(),
        "competition_id": "premier_league",
        "competition_name": "Test League",
        "home_team_name": "Home",
        "away_team_name": "Away",
        "fixture_identity": {
            "fixture_id": fixture_id,
            "kickoff_utc": resolved_kickoff.isoformat(),
            "competition_id": "premier_league",
            "competition_name": "Test League",
            "home_team_name": "Home",
            "away_team_name": "Away",
        },
        "capture_identity_hash": identity,
        "card_hash": f"card-{identity}",
        "artifact_provenance": {"artifact_hash": f"artifact-{identity}"},
        "probability_identity": {
            "model_probabilities": probabilities(model),
            "market_probabilities": probabilities(market),
        },
        "evaluation_tier": "STRICT",
        "decision_tier": "WATCH",
        "recommendation_scope": "NONE",
        "pick": None,
    }


def _checkpoint(
    repository: OutcomeLedgerRepository,
    key: str,
) -> dict[str, Any]:
    with Session(repository.engine) as session:
        row = session.scalar(
            select(ReadModelCheckpointModel).where(
                ReadModelCheckpointModel.checkpoint_key == key
            )
        )
        assert row is not None
        return dict(row.payload)


def _performance_hashes(repository: OutcomeLedgerRepository) -> dict[str, str]:
    with Session(repository.engine) as session:
        return {
            row.checkpoint_key: row.source_hash
            for row in session.scalars(
                select(ReadModelCheckpointModel).where(
                    ReadModelCheckpointModel.checkpoint_key.like("performance:%")
                )
            )
        }
