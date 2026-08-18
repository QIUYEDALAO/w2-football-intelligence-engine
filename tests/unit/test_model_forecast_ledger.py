from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import canonical_sha256
from w2.infrastructure.persistence.future_refresh_models import (
    TeamXgMatchModel,
    TeamXgRollingSnapshotModel,
)
from w2.infrastructure.persistence.model_forecast_models import (
    ModelForecastCaptureDataVersionModel,
    ModelForecastCaptureModel,
    ModelForecastOutcomeModel,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.tracking.model_forecast_ledger import (
    CAPTURE_POLICY,
    CAPTURE_POLICY_HORIZONS,
    MODEL_FORECAST_CAPTURE_HASH_DOMAIN,
    NO_HORIZON,
    ModelForecastLedgerError,
    ModelForecastLedgerRepository,
    capture_horizon_for_policy,
    model_forecast_lead_time_bucket,
    run_model_forecast_capture,
    settle_model_forecasts,
)

NOW = datetime(2026, 8, 14, 0, 0, tzinfo=UTC)
KICKOFF = NOW + timedelta(hours=12)


def test_model_forecast_capture_and_outcome_do_not_require_candidate(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_xg(repository)

    first = run_model_forecast_capture(
        _day_view(),
        repository=repository,
        captured_at=NOW,
        dry_run=False,
        write_db=True,
    )
    second = run_model_forecast_capture(
        _day_view(),
        repository=repository,
        captured_at=NOW + timedelta(minutes=5),
        dry_run=False,
        write_db=True,
    )

    assert first["provider_calls"] == 0
    assert first["model_eligible_count"] == 1
    assert first["model_forecast_capture_count"] == 1
    assert first["shadow_candidate_count"] == 0
    assert second["model_forecast_capture_count"] == 0
    assert second["already_captured_count"] == 1
    with Session(repository.engine) as session:
        capture = session.query(ModelForecastCaptureModel).one()
        version = session.query(ModelForecastCaptureDataVersionModel).one()
        assert version.data_version == "TEAM_XG_MATCH_ROWS_6"
        assert version.team_xg_match_count == 6
        assert capture.captured_at.replace(tzinfo=UTC) < KICKOFF
        assert capture.lead_time_seconds == 12 * 60 * 60
        assert capture.lead_time_bucket == "H6_TO_LT_24H"
        assert capture.payload["capture_policy"] == "FIRST_ELIGIBLE_FREEZE_IMMUTABLE"
        assert capture.payload["exact_quote_required"] is False
        assert capture.payload["candidate_required"] is False
        assert capture.payload["four_field_xg_identity"]["four_fields"] == {
            "home_xg_for": 1.2,
            "home_xg_against": 0.8,
            "away_xg_for": 0.8,
            "away_xg_against": 1.2,
        }
        session.add(
            ResultModel(
                fixture_id="fixture-1",
                home_goals=1,
                away_goals=0,
                result_status="FT",
                confirmed_at=KICKOFF + timedelta(hours=2),
                source_payload_sha256="a" * 64,
                result_hash="b" * 64,
            )
        )
        session.commit()

    settlement = settle_model_forecasts(
        repository=repository,
        settled_at=KICKOFF + timedelta(hours=3),
        dry_run=False,
        write_db=True,
    )

    assert settlement["provider_calls"] == 0
    assert settlement["model_forecast_settled_count"] == 1
    assert settlement["probability_metrics_sample_count"] == 1
    with Session(repository.engine) as session:
        outcome = session.query(ModelForecastOutcomeModel).one()
        assert outcome.payload["actual_outcome"] == "HOME"
        assert outcome.payload["final_score"] == {"home": 1, "away": 0, "status": "FT"}
        assert outcome.payload["brier"] == 0.38
        assert outcome.lead_time_seconds == 12 * 60 * 60
        assert outcome.lead_time_bucket == "H6_TO_LT_24H"
        assert outcome.payload["lead_time_seconds"] == 12 * 60 * 60
        assert outcome.payload["ece_input"] == {
            "predicted_class": "HOME",
            "confidence": 0.5,
            "actual_class": "HOME",
            "correct": True,
        }
    assert repository.metric_summary_by_data_version_and_lead_time() == {
        "TEAM_XG_MATCH_ROWS_6": {
            "team_xg_match_count": 6,
            "lead_time_buckets": {
                "LT_6H": {
                    "sample_count": 0,
                    "mean_brier": None,
                    "mean_log_loss": None,
                    "mean_rps": None,
                },
                "H6_TO_LT_24H": {
                    "sample_count": 1,
                    "mean_brier": 0.38,
                    "mean_log_loss": pytest.approx(0.6931471805599453),
                    "mean_rps": 0.17,
                },
                "D1_TO_D3": {
                    "sample_count": 0,
                    "mean_brier": None,
                    "mean_log_loss": None,
                    "mean_rps": None,
                },
                "GT_3D": {
                    "sample_count": 0,
                    "mean_brier": None,
                    "mean_log_loss": None,
                    "mean_rps": None,
                },
            },
        },
    }
    integrity = repository.integrity()
    assert integrity["invalid_capture_count"] == 0
    assert integrity["invalid_outcome_count"] == 0
    assert integrity["missing_data_version_count"] == 0
    assert integrity["data_version_counts"] == {"TEAM_XG_MATCH_ROWS_6": 1}
    assert integrity["rederivable_from_current_db_count"] == 1
    assert integrity["capture_rederivability"][0]["REDERIVABLE_FROM_CURRENT_DB"] is True
    assert integrity["capture_rederivability"][0]["REDERIVABILITY_CLASS"] == "CURRENT_DB_MATCH"

    with Session(repository.engine) as session:
        session.execute(
            update(ModelForecastOutcomeModel).values(settled_at=KICKOFF + timedelta(hours=4))
        )
        session.execute(update(ResultModel).values(home_goals=2))
        session.commit()
    assert repository.integrity()["invalid_outcome_count"] == 1

    with Session(repository.engine) as session:
        session.execute(
            update(ModelForecastCaptureModel).values(
                kickoff_utc=KICKOFF + timedelta(hours=1),
                lead_time_seconds=13 * 60 * 60,
            )
        )
        session.commit()
    assert repository.integrity()["invalid_capture_count"] == 1


@pytest.mark.parametrize(
    ("seconds", "bucket"),
    [
        (0, "LT_6H"),
        (6 * 60 * 60, "H6_TO_LT_24H"),
        (24 * 60 * 60, "D1_TO_D3"),
        (3 * 24 * 60 * 60, "D1_TO_D3"),
        (3 * 24 * 60 * 60 + 1, "GT_3D"),
    ],
)
def test_model_forecast_lead_time_buckets(seconds: int, bucket: str) -> None:
    assert model_forecast_lead_time_bucket(seconds) == bucket


def test_without_four_field_xg_only_coverage_is_counted(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    result = run_model_forecast_capture(
        _day_view(),
        repository=repository,
        captured_at=NOW,
        dry_run=False,
        write_db=True,
    )

    assert result["coverage_eligible_count"] == 1
    assert result["model_eligible_count"] == 0
    assert result["no_four_field_xg_count"] == 1
    assert result["model_forecast_capture_count"] == 0


def test_current_db_drift_is_nonblocking_integrity_annotation(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_xg(repository)
    run_model_forecast_capture(
        _day_view(),
        repository=repository,
        captured_at=NOW,
        dry_run=False,
        write_db=True,
    )
    with Session(repository.engine) as session:
        session.add(
            TeamXgMatchModel(
                id="new-history:10",
                fixture_id="new-history",
                team_id="10",
                opponent_team_id="20",
                kickoff_at=NOW - timedelta(days=1),
                captured_at=NOW - timedelta(hours=12),
                xg_for=2.0,
                xg_against=0.5,
                goals_for=2,
                goals_against=0,
                raw_payload_sha256="8" * 64,
                source_system="api_football_statistics",
                candidate=False,
                formal_recommendation=False,
            )
        )
        snapshot = session.get(TeamXgRollingSnapshotModel, "10:fixture-1")
        assert snapshot is not None
        snapshot.rolling_xg_for = 1.4667
        snapshot.rolling_xg_against = 0.7
        session.commit()

    integrity = repository.integrity()

    assert integrity["invalid_capture_count"] == 0
    assert integrity["non_rederivable_from_current_db_count"] == 1
    assert integrity["capture_rederivability"][0]["REDERIVABLE_FROM_CURRENT_DB"] is False
    assert integrity["capture_rederivability"][0]["REDERIVABILITY_CLASS"] == (
        "FOUR_FIELD_VALUE_DRIFT"
    )


def test_as_of_only_drift_is_reported_separately(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_xg(repository)
    run_model_forecast_capture(
        _day_view(),
        repository=repository,
        captured_at=NOW,
        dry_run=False,
        write_db=True,
    )
    with Session(repository.engine) as session:
        for snapshot in session.query(TeamXgRollingSnapshotModel):
            snapshot.as_of_time -= timedelta(minutes=1)
        session.commit()

    integrity = repository.integrity()

    assert integrity["invalid_capture_count"] == 0
    assert integrity["non_rederivable_from_current_db_count"] == 1
    assert integrity["rederivability_class_counts"] == {"AS_OF_TIME_RELABEL_ONLY": 1}
    assert integrity["capture_rederivability"][0]["REDERIVABILITY_CLASS"] == (
        "AS_OF_TIME_RELABEL_ONLY"
    )


def test_capture_uses_canonical_fixture_identity_when_public_provenance_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    _seed_xg(repository)
    day_view = _day_view()
    cards = day_view["cards"]
    assert isinstance(cards, list)
    card = cards[0]
    assert isinstance(card, dict)
    card["frozen_artifact_provenance"] = {}
    monkeypatch.setattr(
        repository.xg_repository,
        "matchday_fixture_identity",
        lambda _fixture_id: {
            "status": "PROVIDER_PRIMARY_READY",
            "fixture_id": "fixture-1",
            "provider": "api_football",
            "provider_fixture_id": "fixture-1",
            "competition_id": "allsvenskan",
            "season": "2026",
            "kickoff_utc": KICKOFF.isoformat(),
            "home_provider_team_id": "10",
            "away_provider_team_id": "20",
            "home_w2_team_id": "w2:team:api_football:10",
            "away_w2_team_id": "w2:team:api_football:20",
            "identity_hash": "a" * 64,
            "raw_payload_sha256": "b" * 64,
        },
    )

    result = run_model_forecast_capture(
        day_view,
        repository=repository,
        captured_at=NOW,
        dry_run=False,
        write_db=True,
    )

    assert result["model_eligible_count"] == 1
    assert result["model_forecast_capture_count"] == 1
    with Session(repository.engine) as session:
        capture = session.query(ModelForecastCaptureModel).one()
        assert capture.payload["fixture_identity"]["identity_hash"] == "a" * 64
        assert capture.payload["source_artifact_hashes"]["fixture_raw_payload_sha256"] == "b" * 64


def _repository(tmp_path: Path) -> ModelForecastLedgerRepository:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'model-forecast.db'}")
    TeamXgMatchModel.__table__.create(engine)
    TeamXgRollingSnapshotModel.__table__.create(engine)
    ModelForecastCaptureModel.__table__.create(engine)
    ModelForecastCaptureDataVersionModel.__table__.create(engine)
    ModelForecastOutcomeModel.__table__.create(engine)
    ResultModel.__table__.create(engine)
    return ModelForecastLedgerRepository(engine)


def _seed_xg(repository: ModelForecastLedgerRepository) -> None:
    with Session(repository.engine) as session:
        for team_id, opponent, xg_for, xg_against in (
            ("10", "20", 1.2, 0.8),
            ("20", "10", 0.8, 1.2),
        ):
            for index in range(3):
                session.add(
                    TeamXgMatchModel(
                        id=f"history-{index}:{team_id}",
                        fixture_id=f"history-{index}",
                        team_id=team_id,
                        opponent_team_id=opponent,
                        kickoff_at=NOW - timedelta(days=4 - index),
                        captured_at=NOW - timedelta(days=3 - index),
                        xg_for=xg_for,
                        xg_against=xg_against,
                        goals_for=1,
                        goals_against=0,
                        raw_payload_sha256=f"{index + 1}" * 64,
                        source_system="api_football_statistics",
                        candidate=False,
                        formal_recommendation=False,
                    )
                )
            session.add(
                TeamXgRollingSnapshotModel(
                    snapshot_id=f"{team_id}:fixture-1",
                    team_id=team_id,
                    as_of_fixture_id="fixture-1",
                    as_of_time=KICKOFF,
                    match_count=3,
                    rolling_xg_for=xg_for,
                    rolling_xg_against=xg_against,
                    rolling_goals_for=1.0,
                    rolling_goals_against=0.0,
                    regression_index=0.0,
                    source_system="team_xg_match",
                    candidate=False,
                    formal_recommendation=False,
                )
            )
        session.commit()


def _day_view() -> dict[str, object]:
    return {
        "cards": [
            {
                "fixture_id": "fixture-1",
                "competition_id": "allsvenskan",
                "kickoff_utc": KICKOFF.isoformat(),
                "decision_tier": "NOT_READY",
                "outcome_tracked": False,
                "frozen_artifact_provenance": {
                    "artifact_hash": "c" * 64,
                    "source_hash": "d" * 64,
                    "fixture_identity": {
                        "fixture_id": "fixture-1",
                        "competition_id": "allsvenskan",
                        "kickoff_utc": KICKOFF.isoformat(),
                        "home_team_id": "10",
                        "away_team_id": "20",
                    },
                    "input_manifest": {"simulation_sha256": "e" * 64},
                },
                "simulation": {
                    "status": "READY",
                    "simulation": {
                        "status": "READY",
                        "model_version": "w2.formal.exact_dc_poisson.v1",
                        "calibration_version": "w2.calibration.v1",
                        "calibration_status": "BASELINE_PRIOR",
                        "calibration": {"simulation_input_hash": "f" * 64},
                        "score_matrix_summary": {
                            "home_win": 0.5,
                            "draw": 0.2,
                            "away_win": 0.3,
                            "score_matrix_hash": "9" * 64,
                            "distribution": [
                                {"home_goals": 0, "away_goals": 0, "probability": 0.2},
                                {"home_goals": 1, "away_goals": 0, "probability": 0.5},
                                {"home_goals": 0, "away_goals": 1, "probability": 0.3},
                            ],
                        },
                        "ah_probabilities": {
                            "ladder": [
                                {
                                    "home_line": -0.5,
                                    "home_settlement_distribution": {
                                        "WIN": 0.5,
                                        "HALF_WIN": 0.0,
                                        "PUSH": 0.0,
                                        "HALF_LOSS": 0.0,
                                        "LOSS": 0.5,
                                    },
                                    "away_settlement_distribution": {
                                        "WIN": 0.5,
                                        "HALF_WIN": 0.0,
                                        "PUSH": 0.0,
                                        "HALF_LOSS": 0.0,
                                        "LOSS": 0.5,
                                    },
                                }
                            ]
                        },
                        "ou_probabilities": {"ladder": [{"line": 2.5}]},
                    },
                },
            }
        ]
    }


def test_capture_identity_columns_do_not_change_frozen_hash(tmp_path: Path) -> None:
    """Widening the relational key must leave the hashed core byte-identical.

    ``capture_policy`` already lived inside the hashed core, so promoting it to a
    column -- alongside the derived ``horizon_id`` -- is purely relational.  If a
    future edit leaks either field into ``_build_capture``'s core dict this test
    fails, because the recorded hash would stop matching the frozen payload.
    """

    repository = _repository(tmp_path)
    _seed_xg(repository)
    run_model_forecast_capture(
        _day_view(), repository=repository, captured_at=NOW, dry_run=False, write_db=True
    )

    with Session(repository.engine) as session:
        capture = session.scalars(select(ModelForecastCaptureModel)).one()

    identity_payload = {
        key: value for key, value in dict(capture.payload).items() if key != "capture_identity_hash"
    }
    assert capture.capture_identity_hash == canonical_sha256(
        identity_payload, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN
    )
    assert "horizon_id" not in capture.payload
    assert capture.capture_policy == CAPTURE_POLICY
    assert capture.horizon_id == NO_HORIZON
    assert repository.integrity()["invalid_capture_count"] == 0


def test_capture_policy_horizon_registry_is_one_to_one() -> None:
    """Two tracks separate by policy alone, which only holds if the map is 1:1.

    ``horizon_id`` is deliberately absent from the hashed core, so a policy that
    mapped to two horizons would produce colliding identity hashes for genuinely
    different captures.
    """

    horizons = list(CAPTURE_POLICY_HORIZONS.values())
    assert len(horizons) == len(set(horizons))
    assert CAPTURE_POLICY_HORIZONS[CAPTURE_POLICY] == NO_HORIZON


def test_unregistered_capture_policy_fails_closed() -> None:
    with pytest.raises(ModelForecastLedgerError, match="POLICY_NOT_REGISTERED"):
        capture_horizon_for_policy("FIXED_HORIZON_FREEZE_IMMUTABLE")


def test_horizon_column_drift_is_caught_by_integrity(tmp_path: Path) -> None:
    """horizon_id sits outside the hash, so only integrity can police it.

    Nothing in the frozen payload changes when this column drifts, which is
    exactly why the crosscheck has to exist alongside the kickoff/captured_at
    assertions rather than relying on the identity hash.
    """

    repository = _repository(tmp_path)
    _seed_xg(repository)
    run_model_forecast_capture(
        _day_view(), repository=repository, captured_at=NOW, dry_run=False, write_db=True
    )
    assert repository.integrity()["invalid_capture_count"] == 0

    with Session(repository.engine) as session:
        session.execute(update(ModelForecastCaptureModel).values(horizon_id="H0"))
        session.commit()

    assert repository.integrity()["invalid_capture_count"] == 1


def test_registered_policy_horizons_are_frozen() -> None:
    """Remapping an existing policy would silently rewrite history.

    Historical captures freeze ``capture_policy`` in their hash but resolve
    ``horizon_id`` through the registry at read time, so changing a published
    mapping would make already-frozen rows resolve to a horizon they were never
    captured under.  New horizons must arrive as new policy names.
    """

    assert CAPTURE_POLICY_HORIZONS == {
        "FIRST_ELIGIBLE_FREEZE_IMMUTABLE": "NONE",
    }


def test_schema_v1_captures_without_capture_policy_stay_valid(tmp_path: Path) -> None:
    """Production holds 9 v1 captures frozen before capture_policy existed.

    Their payload cannot carry the field, so integrity must fall back to the same
    legacy default the 0063 backfill used. A naive payload comparison would mark
    every one of those immutable records as drifted.
    """

    repository = _repository(tmp_path)
    _seed_xg(repository)
    run_model_forecast_capture(
        _day_view(), repository=repository, captured_at=NOW, dry_run=False, write_db=True
    )

    with Session(repository.engine) as session:
        capture = session.scalars(select(ModelForecastCaptureModel)).one()
        legacy_payload = {
            key: value for key, value in dict(capture.payload).items() if key != "capture_policy"
        }
        legacy_payload["schema_version"] = "w2.model_forecast_capture.v1"
        identity = {k: v for k, v in legacy_payload.items() if k != "capture_identity_hash"}
        legacy_payload["capture_identity_hash"] = canonical_sha256(
            identity, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN
        )
        session.execute(
            update(ModelForecastCaptureModel).values(
                payload=legacy_payload,
                capture_identity_hash=legacy_payload["capture_identity_hash"],
                payload_sha256=canonical_sha256(
                    legacy_payload, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN
                ),
            )
        )
        session.commit()

    integrity = repository.integrity()
    assert integrity["invalid_capture_count"] == 0


@pytest.mark.parametrize(
    ("schema_version", "expect_invalid"),
    [
        ("w2.model_forecast_capture.v1", 0),
        ("w2.model_forecast_capture.v2", 1),
    ],
)
def test_missing_capture_policy_is_legal_only_under_schema_v1(
    tmp_path: Path, schema_version: str, expect_invalid: int
) -> None:
    """v1 could not carry the field; v2 omitting it is a defect, not history.

    Healing both cases into the legacy default would let a corrupt writer hide
    behind a compatibility rule written for records that predate the field.
    """

    repository = _repository(tmp_path)
    _seed_xg(repository)
    run_model_forecast_capture(
        _day_view(), repository=repository, captured_at=NOW, dry_run=False, write_db=True
    )

    with Session(repository.engine) as session:
        capture = session.scalars(select(ModelForecastCaptureModel)).one()
        payload = {
            key: value for key, value in dict(capture.payload).items() if key != "capture_policy"
        }
        payload["schema_version"] = schema_version
        identity = {k: v for k, v in payload.items() if k != "capture_identity_hash"}
        payload["capture_identity_hash"] = canonical_sha256(
            identity, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN
        )
        session.execute(
            update(ModelForecastCaptureModel).values(
                payload=payload,
                capture_identity_hash=payload["capture_identity_hash"],
                payload_sha256=canonical_sha256(payload, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN),
            )
        )
        session.commit()

    assert repository.integrity()["invalid_capture_count"] == expect_invalid


def test_unregistered_policy_is_invalid_whatever_the_horizon_says(tmp_path: Path) -> None:
    """A registry miss must fail, not be compared against.

    Matching the column straight against ``registry.get(policy)`` would let an
    unknown policy through wherever both sides resolve to nothing, so the check
    requires a registered horizon before comparing at all.
    """

    repository = _repository(tmp_path)
    _seed_xg(repository)
    run_model_forecast_capture(
        _day_view(), repository=repository, captured_at=NOW, dry_run=False, write_db=True
    )

    with Session(repository.engine) as session:
        capture = session.scalars(select(ModelForecastCaptureModel)).one()
        payload = dict(capture.payload)
        payload["capture_policy"] = "FIXED_HORIZON_T24_FREEZE_IMMUTABLE_V1"
        identity = {k: v for k, v in payload.items() if k != "capture_identity_hash"}
        payload["capture_identity_hash"] = canonical_sha256(
            identity, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN
        )
        session.execute(
            update(ModelForecastCaptureModel).values(
                payload=payload,
                capture_identity_hash=payload["capture_identity_hash"],
                payload_sha256=canonical_sha256(payload, domain=MODEL_FORECAST_CAPTURE_HASH_DOMAIN),
                capture_policy="FIXED_HORIZON_T24_FREEZE_IMMUTABLE_V1",
                horizon_id="NONE",
            )
        )
        session.commit()

    assert repository.integrity()["invalid_capture_count"] == 1
