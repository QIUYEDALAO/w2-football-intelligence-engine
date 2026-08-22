from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from w2.competitions.seed import seed_competition_runtime_authority
from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.factor_model.forward_collection import (
    ForwardCollectionConfig,
    _daily_self_attestation,
    _provider_isolation_audit,
    _runtime_release_identity_audit,
    run_forward_collection,
)
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.factor_shadow_models import (
    FactorShadowForecastCaptureModel,
)
from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
from w2.infrastructure.persistence.model_forecast_models import ModelForecastCaptureModel
from w2.infrastructure.persistence.models import ResultModel

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
        assert (
            forecast.production_capture_identity_hash
            == forecast.payload["production_capture_identity_hash"]
        )
        assert forecast.payload["collection_only"] is True
        assert forecast.payload["gate1_status"] == "FAIL"
        assert forecast.payload["gate2_status"] == "CLOSED"
        assert forecast.payload["candidate_eligible"] is False
        assert forecast.payload["notification_eligible"] is False
        assert forecast.payload["official_profit_and_loss_eligible"] is False
        assert forecast.payload["source_mode"] == "FORWARD_SHADOW"
        assert forecast.payload["xg_pit_semantics_registered"] == "SOURCE_KICKOFF_ONLY"
        assert forecast.payload["xg_pit_semantics_effective"] == "STRICT_CAPTURED_AT"
        assert forecast.payload["xg_method_version"] == "api-football.expected-goals.statistics.v1"
        assert forecast.payload["provider_league_identity"] == {
            "competition_id": "la_liga",
            "provider": "api_football",
            "provider_league_id": "140",
            "source": "W2_COMPETITION_DB_AUTHORITY",
            "authority_sha256": forecast.payload["provider_league_identity"]["authority_sha256"],
            "identity_sha256": forecast.payload["provider_league_identity"]["identity_sha256"],
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


def test_busy_window_does_not_run_writer_role_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from w2.factor_model import forward_collection as module
    from w2.infrastructure.persistence.matchday_intake_models import (
        MatchdayCheckpointPlanModel,
    )

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'busy-no-role.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            MatchdayCheckpointPlanModel(
                plan_id="plan-busy",
                fixture_id="api_football:busy",
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
                plan_hash="b" * 64,
            )
        )
        session.commit()

    def fail_if_called(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("role audit must not run during a V1 checkpoint slot")

    monkeypatch.setattr(module, "_role_audit", fail_if_called)
    report = run_forward_collection(
        config=_config(tmp_path, enabled=True),
        engine=engine,
        writer_engine=engine,
        computed_at=COMPUTED_AT,
        write_db=True,
    )

    assert report["status"] == "DEFERRED_FOR_V1_CHECKPOINT_SLOT"
    assert report["role_audit"]["reason"] == "NOT_RUN_DURING_V1_CHECKPOINT_SLOT"


def test_batch_rechecks_quiet_window_before_computation_and_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from w2.factor_model import forward_collection as module

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'quiet-recheck.db'}")
    Base.metadata.create_all(engine)
    _seed_history_and_v1_capture(engine)
    original = module._quiet_window_audit
    calls = 0

    def close_window_after_initial_check(
        session: Session,
        *,
        now: datetime,
        horizon: timedelta,
    ) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return original(session, now=now, horizon=horizon)
        return {
            "pass": False,
            "checked_from": _iso(COMPUTED_AT),
            "checked_to": _iso(COMPUTED_AT + timedelta(hours=1)),
            "formal_checkpoint_slot_count": 1,
            "near_checkpoint_slot_count": 1,
            "formal_checkpoint_slots": [],
        }

    monkeypatch.setattr(module, "_quiet_window_audit", close_window_after_initial_check)
    config = _config(tmp_path, enabled=True)
    report = run_forward_collection(
        config=config,
        engine=engine,
        writer_engine=engine,
        computed_at=COMPUTED_AT,
        write_db=True,
    )

    assert report["status"] == "DEFERRED_DURING_BATCH_FOR_V1_CHECKPOINT_SLOT"
    assert report["database_writes"] == 0
    assert report["anomalies"] == []
    assert report["stopped_for_v1_checkpoint"] is True
    assert config.control_file.read_text(encoding="utf-8").strip() == "ENABLED"


def test_tampered_frozen_inputs_fail_before_database_access(tmp_path: Path) -> None:
    config = _config(tmp_path, enabled=False)
    preregistration = tmp_path / "preregistration.json"
    preregistration.write_bytes(config.preregistration_path.read_bytes() + b"\n")
    tampered_preregistration = replace(
        config,
        preregistration_path=preregistration,
    )
    with pytest.raises(
        ValueError,
        match="FORWARD_COLLECTION_PREREGISTRATION_HASH_MISMATCH",
    ):
        run_forward_collection(config=tampered_preregistration, computed_at=COMPUTED_AT)

    artifact = tmp_path / "artifact.json"
    artifact.write_bytes(config.artifact_path.read_bytes() + b"\n")
    tampered_artifact = replace(config, artifact_path=artifact)
    with pytest.raises(
        ValueError,
        match="FORWARD_COLLECTION_ARTIFACT_FILE_HASH_MISMATCH",
    ):
        run_forward_collection(config=tampered_artifact, computed_at=COMPUTED_AT)


def test_corrupt_v1_capture_disables_collection_before_any_v2_write(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'corrupt-capture.db'}")
    Base.metadata.create_all(engine)
    _seed_history_and_v1_capture(engine)
    with engine.begin() as connection:
        connection.execute(
            text("update model_forecast_capture set payload_sha256 = :invalid"),
            {"invalid": "0" * 64},
        )
    config = _config(tmp_path, enabled=True)

    report = run_forward_collection(
        config=config,
        engine=engine,
        writer_engine=engine,
        computed_at=COMPUTED_AT,
        write_db=True,
    )

    assert report["status"] == "ANOMALY_COLLECTION_DISABLED"
    assert report["database_writes"] == 0
    assert report["computed_forecast_count"] == 0
    assert report["critical_exclusion_reasons"] == ["FORWARD_PRODUCTION_CAPTURE_INTEGRITY_INVALID"]
    assert config.control_file.read_text(encoding="utf-8").strip() == "DISABLED"
    with Session(engine) as session:
        assert (
            session.scalar(select(func.count()).select_from(FactorShadowForecastCaptureModel)) == 0
        )


def test_completed_pair_attestation_uses_canonical_alias_and_distinct_fixture(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'paired-count.db'}")
    Base.metadata.create_all(engine)
    _seed_history_and_v1_capture(engine)
    report = run_forward_collection(
        config=_config(tmp_path, enabled=True),
        engine=engine,
        writer_engine=engine,
        computed_at=COMPUTED_AT,
        write_db=True,
    )
    assert report["status"] == "PASS"
    with Session(engine) as session:
        for fixture_id, suffix in (
            ("target", "1"),
            ("api_football:target", "2"),
        ):
            session.add(
                ResultModel(
                    fixture_id=fixture_id,
                    home_goals=1,
                    away_goals=0,
                    result_status="FT",
                    confirmed_at=COMPUTED_AT,
                    source_payload_sha256=suffix * 64,
                    result_hash=suffix * 64,
                )
            )
        session.commit()
        attestation = _daily_self_attestation(session, now=COMPUTED_AT)

    assert attestation["v2_forward_completed_pair_count"] == 1


def test_production_runtime_identity_and_provider_isolation_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = {
        "git_sha": "a" * 40,
        "build_time": "2026-08-22T09:05:33Z",
        "release_id": "release-1",
        "image_id": "sha256:" + "b" * 64,
        "oci_digest": "sha256:" + "b" * 64,
        "registry_digest": "sha256:" + "b" * 64,
    }
    assert _runtime_release_identity_audit(identity, required=True)["pass"] is True
    assert (
        _runtime_release_identity_audit(
            {**identity, "oci_digest": "UNAVAILABLE"},
            required=True,
        )["pass"]
        is False
    )

    monkeypatch.setenv("W2_PROVIDER_CALLS_DISABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "false")
    monkeypatch.delenv("W2_API_FOOTBALL_API_KEY", raising=False)
    assert _provider_isolation_audit(required=True)["pass"] is True
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "present")
    assert _provider_isolation_audit(required=True) == {
        "pass": False,
        "required": True,
        "api_football_key_present": True,
        "provider_calls_disabled": True,
        "provider_scheduler_enabled": False,
        "violations": ["API_FOOTBALL_KEY_PRESENT"],
    }


def _config(tmp_path: Path, *, enabled: bool) -> ForwardCollectionConfig:
    control = tmp_path / "enabled"
    control.write_text("ENABLED\n" if enabled else "DISABLED\n", encoding="utf-8")
    return ForwardCollectionConfig(
        enabled=True,
        control_file=control,
        artifact_path=(
            ROOT / "config/calibration/factor_model_v2.f3_f7.forward_collection_only.json"
        ),
        preregistration_path=(
            ROOT / "docs/operations/FACTOR_V2_FORWARD_COLLECTION_PREREGISTRATION_20260822.json"
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
    home_xg = _xg_side(
        team_id="10",
        component=component,
        xg_for=1.2,
        xg_against=0.8,
    )
    away_xg = _xg_side(
        team_id="20",
        component={
            **component,
            "fixture_id": "200",
            "identity": "component-away",
            "xg_for": 0.9,
            "xg_against": 1.1,
        },
        xg_for=0.9,
        xg_against=1.1,
    )
    xg_body = {
        "fixture_identity": {
            "fixture_id": "api_football:target",
            "home_provider_team_id": "10",
            "away_provider_team_id": "20",
        },
        "home": home_xg,
        "away": away_xg,
        "four_fields": {
            "home_xg_for": 1.2,
            "home_xg_against": 0.8,
            "away_xg_for": 0.9,
            "away_xg_against": 1.1,
        },
    }
    xg_identity = {
        **xg_body,
        "identity_hash": canonical_sha256(
            xg_body,
            domain=HashDomain.FUTURE_REFRESH_FIXTURE_IDENTITY,
        ),
    }
    capture_body = {
        "schema_version": "w2.model_forecast_capture.v2",
        "four_field_xg_identity": xg_identity,
        "fixture_identity": xg_identity["fixture_identity"],
        "competition_identity": {"competition_id": "la_liga"},
        "captured_at": _iso(CAPTURED_AT),
        "kickoff_utc": _iso(KICKOFF),
        "lead_time_seconds": 7200,
        "lead_time_bucket": "LT_6H",
        "capture_policy": "FIRST_ELIGIBLE_FREEZE_IMMUTABLE",
        "model_family": "EXACT_DC_POISSON",
        "model_version": "v1",
        "model_input_manifest_hash": "m" * 64,
        "score_matrix_hash": "s" * 64,
        "source_artifact_hashes": {
            "four_field_xg_identity_hash": xg_identity["identity_hash"],
        },
        "candidate_required": False,
        "exact_quote_required": False,
    }
    capture_identity_hash = canonical_sha256(
        capture_body,
        domain=HashDomain.FUTURE_REFRESH_EVIDENCE,
    )
    payload = {**capture_body, "capture_identity_hash": capture_identity_hash}
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
                capture_identity_hash=capture_identity_hash,
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
                four_field_xg_identity_hash=xg_identity["identity_hash"],
                score_matrix_hash="s" * 64,
                payload=payload,
                payload_sha256=canonical_sha256(
                    payload,
                    domain=HashDomain.FUTURE_REFRESH_EVIDENCE,
                ),
                inserted_at=CAPTURED_AT,
            )
        )
        session.commit()


def _xg_side(
    *,
    team_id: str,
    component: dict[str, object],
    xg_for: float,
    xg_against: float,
) -> dict[str, object]:
    body: dict[str, object] = {
        "snapshot_identity": f"{team_id}:target",
        "team_id": team_id,
        "as_of_fixture_id": "target",
        "as_of": _iso(CAPTURED_AT - timedelta(hours=1)),
        "match_count": 1,
        "xg_for": xg_for,
        "xg_against": xg_against,
        "component_team_xg_matches": [component],
    }
    return {
        **body,
        "identity_hash": canonical_sha256(
            body,
            domain=HashDomain.FUTURE_REFRESH_FIXTURE_IDENTITY,
        ),
    }


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
