from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from w2.competitions.seed import seed_competition_runtime_authority
from w2.factor_model.forward_collection import (
    ForwardCollectionConfig,
    run_forward_collection,
)
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.factor_shadow_models import (
    FactorShadowForecastCaptureModel,
)
from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
from w2.infrastructure.persistence.model_forecast_models import ModelForecastCaptureModel

ROOT = Path(__file__).resolve().parents[2]
CAPTURED_AT = datetime(2026, 8, 22, 10, tzinfo=UTC)
KICKOFF = CAPTURED_AT + timedelta(hours=2)
COMPUTED_AT = CAPTURED_AT + timedelta(hours=1)


def test_delayed_forward_collection_writes_only_v2_with_exact_v1_captured_at(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'forward.db'}")
    Base.metadata.create_all(engine)
    _seed_history_and_v1_capture(engine)
    config = _config(tmp_path, enabled=True)

    report = run_forward_collection(
        config=config,
        engine=engine,
        writer_engine=engine,
        computed_at=COMPUTED_AT,
        write_db=True,
    )

    assert report["status"] == "PASS"
    assert report["provider_calls"] == 0
    assert report["production_worker_used"] is False
    assert report["database_writes"] == 1
    assert report["point_in_time_leakage_violation_count"] == 0
    assert report["candidate_output_count"] == 0
    assert report["notification_output_count"] == 0
    assert report["official_profit_and_loss_output_count"] == 0
    assert report["daily_self_attestation_after"]["v2_forward_new_rows_utc_day"] == 1
    assert (
        report["daily_self_attestation_before"]["v1_authority_table_row_counts"]
        == report["daily_self_attestation_after"]["v1_authority_table_row_counts"]
    )
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ModelForecastCaptureModel)) == 1
        forecast = session.scalar(select(FactorShadowForecastCaptureModel))
        assert forecast is not None
        assert forecast.captured_at.replace(tzinfo=UTC) == CAPTURED_AT
        assert forecast.feature_as_of.replace(tzinfo=UTC) == CAPTURED_AT
        assert forecast.computed_at.replace(tzinfo=UTC) == COMPUTED_AT
        assert forecast.production_capture_identity_hash == "c" * 64
        assert forecast.payload["collection_only"] is True
        assert forecast.payload["gate1_status"] == "FAIL"
        assert forecast.payload["gate2_status"] == "CLOSED"
        assert forecast.payload["candidate_eligible"] is False
        assert forecast.payload["notification_eligible"] is False
        assert forecast.payload["official_profit_and_loss_eligible"] is False
        assert forecast.payload["source_mode"] == "FORWARD_SHADOW"
        assert forecast.payload["provider_league_identity"] == {
            "competition_id": "la_liga",
            "provider": "api_football",
            "provider_league_id": "140",
            "source": "W2_COMPETITION_DB_AUTHORITY",
            "authority_sha256": forecast.payload["provider_league_identity"][
                "authority_sha256"
            ],
            "identity_sha256": forecast.payload["provider_league_identity"][
                "identity_sha256"
            ],
        }
        assert forecast.payload["feature_as_of"] == _iso(CAPTURED_AT)
        assert forecast.payload["computed_at"] == _iso(COMPUTED_AT)

    second = run_forward_collection(
        config=config,
        engine=engine,
        writer_engine=engine,
        computed_at=COMPUTED_AT + timedelta(minutes=30),
        write_db=True,
    )
    assert second["status"] == "ALREADY_COLLECTED_TODAY"
    assert second["database_writes"] == 0


def test_forward_collection_runtime_flag_stops_without_database_access(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, enabled=False)

    report = run_forward_collection(config=config, computed_at=COMPUTED_AT)

    assert report["status"] == "COLLECTION_DISABLED"
    assert report["database_writes"] == 0
    assert report["switch"]["effective_stop_delay"] == "BEFORE_NEXT_FIXTURE_TRANSACTION"


def test_forward_collection_defers_when_v1_near_checkpoint_exists(tmp_path: Path) -> None:
    from w2.infrastructure.persistence.matchday_intake_models import (
        MatchdayCheckpointPlanModel,
    )

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'quiet.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            MatchdayCheckpointPlanModel(
                plan_id="plan-1",
                fixture_id="api_football:target",
                competition_id="la_liga",
                season="2026",
                policy_version="policy-v1",
                checkpoint="T15_ODDS",
                kickoff_utc=COMPUTED_AT + timedelta(minutes=30),
                scheduled_at=COMPUTED_AT + timedelta(minutes=15),
                window_start=COMPUTED_AT + timedelta(minutes=10),
                window_end=COMPUTED_AT + timedelta(minutes=20),
                endpoints=["odds"],
                status="PLANNED",
                attempt_count=0,
                test_only=False,
                blockers=[],
                plan_hash="h" * 64,
            )
        )
        session.commit()

    report = run_forward_collection(
        config=_config(tmp_path, enabled=True),
        engine=engine,
        writer_engine=engine,
        computed_at=COMPUTED_AT,
        write_db=True,
    )

    assert report["status"] == "DEFERRED_FOR_V1_CHECKPOINT_SLOT"
    assert report["database_writes"] == 0
    assert report["quiet_window"]["formal_checkpoint_slot_count"] == 1
    assert report["quiet_window"]["near_checkpoint_slot_count"] == 1


def test_forward_collection_defers_for_active_planned_window(tmp_path: Path) -> None:
    from w2.infrastructure.persistence.matchday_intake_models import (
        MatchdayCheckpointPlanModel,
    )

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'active-window.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            MatchdayCheckpointPlanModel(
                plan_id="plan-active",
                fixture_id="api_football:active",
                competition_id="la_liga",
                season="2026",
                policy_version="policy-v1",
                checkpoint="T-30m_VALIDATION_LOCK",
                kickoff_utc=COMPUTED_AT + timedelta(minutes=25),
                scheduled_at=COMPUTED_AT - timedelta(minutes=1),
                window_start=COMPUTED_AT - timedelta(minutes=5),
                window_end=COMPUTED_AT + timedelta(minutes=5),
                endpoints=["odds", "lineups"],
                status="PLANNED",
                attempt_count=0,
                test_only=False,
                blockers=[],
                plan_hash="a" * 64,
            )
        )
        session.commit()

    report = run_forward_collection(
        config=_config(tmp_path, enabled=True),
        engine=engine,
        writer_engine=engine,
        computed_at=COMPUTED_AT,
        write_db=True,
    )

    assert report["status"] == "DEFERRED_FOR_V1_CHECKPOINT_SLOT"
    assert report["database_writes"] == 0
    assert report["quiet_window"]["formal_checkpoint_slot_count"] == 1


def _config(tmp_path: Path, *, enabled: bool) -> ForwardCollectionConfig:
    control = tmp_path / "enabled"
    control.write_text("ENABLED\n" if enabled else "DISABLED\n", encoding="utf-8")
    return ForwardCollectionConfig(
        enabled=True,
        control_file=control,
        artifact_path=(
            ROOT
            / "config/calibration/factor_model_v2.f3_f7.forward_collection_only.json"
        ),
        preregistration_path=(
            ROOT
            / "docs/operations/FACTOR_V2_FORWARD_COLLECTION_PREREGISTRATION_20260822.json"
        ),
        report_dir=tmp_path / "reports",
        daily_state_file=tmp_path / "last-success-utc-date",
    )


def _seed_history_and_v1_capture(engine) -> None:  # type: ignore[no-untyped-def]
    report = seed_competition_runtime_authority(
        engine,
        environment="test",
        updated_by="factor-v2-forward-collection-test",
    )
    assert report.conflicts == ()
    fixtures = []
    for index in range(5):
        kickoff = CAPTURED_AT - timedelta(days=20 - index * 2)
        fixtures.extend(
            [
                _raw_fixture(100 + index, kickoff, 10, 30, 2, 1),
                _raw_fixture(200 + index, kickoff, 20, 40, 1, 1),
            ]
        )
    raw_captured_at = CAPTURED_AT - timedelta(hours=1)
    component = {
        "identity": "component",
        "fixture_id": "100",
        "kickoff_at": _iso(CAPTURED_AT - timedelta(days=20)),
        "captured_at": _iso(raw_captured_at),
        "xg_for": 1.2,
        "xg_against": 0.8,
        "raw_statistics_sha256": "2" * 64,
    }
    xg_identity = {
        "identity_hash": "x" * 64,
        "fixture_identity": {
            "home_provider_team_id": "10",
            "away_provider_team_id": "20",
        },
        "home": {
            "team_id": "10",
            "component_team_xg_matches": [component],
        },
        "away": {
            "team_id": "20",
            "component_team_xg_matches": [
                {**component, "fixture_id": "200", "identity": "component-away"}
            ],
        },
        "four_fields": {
            "home_xg_for": 1.2,
            "home_xg_against": 0.8,
            "away_xg_for": 0.9,
            "away_xg_against": 1.1,
        },
    }
    payload = {
        "four_field_xg_identity": xg_identity,
        "fixture_identity": {"fixture_id": "api_football:target"},
        "competition_identity": {"competition_id": "la_liga"},
        "captured_at": _iso(CAPTURED_AT),
        "kickoff_utc": _iso(KICKOFF),
    }
    with Session(engine) as session:
        session.add(
            RawPayloadModel(
                sha256="1" * 64,
                endpoint="fixtures",
                captured_at=raw_captured_at,
                inserted_at=raw_captured_at,
                storage_uri="db://raw/fixtures/test",
                payload={"response": fixtures},
            )
        )
        session.add(
            ModelForecastCaptureModel(
                capture_identity_hash="c" * 64,
                fixture_id="api_football:target",
                competition_id="la_liga",
                kickoff_utc=KICKOFF,
                captured_at=CAPTURED_AT,
                lead_time_seconds=7200,
                lead_time_bucket="LT_6H",
                model_family="EXACT_DC_POISSON",
                model_version="v1",
                capture_policy="FIRST_ELIGIBLE_FREEZE_IMMUTABLE",
                horizon_id="NONE",
                model_input_manifest_hash="m" * 64,
                four_field_xg_identity_hash="x" * 64,
                score_matrix_hash="s" * 64,
                payload=payload,
                payload_sha256="p" * 64,
                inserted_at=CAPTURED_AT,
            )
        )
        session.commit()


def _raw_fixture(
    fixture_id: int,
    kickoff: datetime,
    home_team_id: int,
    away_team_id: int,
    home_goals: int,
    away_goals: int,
) -> dict[str, object]:
    return {
        "fixture": {
            "id": fixture_id,
            "date": _iso(kickoff),
            "status": {"short": "FT"},
        },
        "league": {"id": 140, "season": 2026},
        "teams": {"home": {"id": home_team_id}, "away": {"id": away_team_id}},
        "goals": {"home": home_goals, "away": away_goals},
    }


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
