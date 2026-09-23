from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from w2.domain.ev_online_contract import FORWARD_START_UTC
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.dynamic_prematch_models import (
    CalibratedValidationSampleModel,
    DynamicPrematchEvaluationModel,
    ValidationSampleModel,
)
from w2.infrastructure.persistence.matchday_intake_models import MatchdayEndpointCaptureModel
from w2.infrastructure.persistence.models import ResultModel
from w2.strategy.online_calibration_filter import (
    LEGAL_STATE,
    PARAM_VERSION,
    evaluate_fast_criteria,
    fast_criteria_rows,
    materialize_calibrated_validation_samples,
)


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _seed(
    session, fixture="f1", evaluation_id="e1", *, settlement="PENDING", profit=None, score=None
):
    evaluated = datetime(2026, 9, 20, tzinfo=UTC)
    session.add(ValidationSampleModel(
        fixture_id=fixture, market="ASIAN_HANDICAP", selection="HOME", exact_line="-0.5",
        decimal_odds=2.0, evaluation_id=evaluation_id, settlement=settlement,
        profit_units=profit, score=score, projected_at=evaluated, evaluated_at=evaluated,
        kickoff_utc=evaluated + timedelta(hours=1), current_ev=0.1,
    ))
    session.add(DynamicPrematchEvaluationModel(
        evaluation_id=evaluation_id, identity_hash=evaluation_id * 64, fixture_id=fixture,
        market="ASIAN_HANDICAP", selection="HOME", checkpoint="FINAL",
        evaluated_at=evaluated, original_state=LEGAL_STATE,
        payload={"model_settlement_distribution": {"WIN": 0.8, "HALF_WIN": 0.0}},
    ))
    session.commit()


def test_b1_v3_decision_fields_freeze_and_conflict_is_counted():
    engine = _session()
    with Session(engine) as session:
        _seed(session)
        materialize_calibrated_validation_samples(session)
        row = session.scalar(select(CalibratedValidationSampleModel))
        assert row is not None and row.param_version == PARAM_VERSION
        frozen = (row.filter_decision, row.bias_at_decision, row.ev_corrected, row.warmup, row.param_version)
        source = session.scalar(select(ValidationSampleModel))
        source.current_ev = 0.9
        session.commit()
        second = materialize_calibrated_validation_samples(session)
        session.refresh(row)
        assert (row.filter_decision, row.bias_at_decision, row.ev_corrected, row.warmup, row.param_version) == frozen
        assert second["frozen_conflicts"] == 1


def test_b2_settlement_fields_sync_while_decision_stays_frozen():
    engine = _session()
    with Session(engine) as session:
        _seed(session)
        materialize_calibrated_validation_samples(session)
        source = session.scalar(select(ValidationSampleModel))
        source.settlement, source.profit_units, source.score = "WIN", 1.0, "1-0"
        session.commit()
        materialize_calibrated_validation_samples(session)
        row = session.scalar(select(CalibratedValidationSampleModel))
        assert (row.settlement, row.profit_units, row.score) == ("WIN", 1.0, "1-0")


def test_b3_orphan_is_deleted_and_counted():
    engine = _session()
    with Session(engine) as session:
        _seed(session)
        materialize_calibrated_validation_samples(session)
        session.query(ValidationSampleModel).delete()
        session.commit()
        report = materialize_calibrated_validation_samples(session)
        assert report["deleted"] == 1
        assert session.scalar(select(CalibratedValidationSampleModel)) is None


def _seed_forward_batch(session, *, bad_filtered_gap=False):
    base = FORWARD_START_UTC + timedelta(hours=1)
    for index in range(54):
        fixture = f"forward-{index}"
        evaluation_id = f"forward-e-{index}"
        evaluated = base + timedelta(minutes=index)
        payload_value = 0.1 if bad_filtered_gap and index == 53 else 0.8
        session.add(ValidationSampleModel(
            fixture_id=fixture, market="ASIAN_HANDICAP", selection="HOME", exact_line="-0.5",
            decimal_odds=2.0, evaluation_id=evaluation_id, settlement="LOSS",
            profit_units=1.0 if index == 52 else (-1.0 if index == 53 else 0.0),
            projected_at=evaluated, evaluated_at=evaluated, kickoff_utc=evaluated + timedelta(minutes=1),
            current_ev=2.0 if index == 52 else (0.1 if index == 53 else 0.0),
        ))
        session.add(DynamicPrematchEvaluationModel(
            evaluation_id=evaluation_id, identity_hash=(evaluation_id + "x") * 64,
            fixture_id=fixture, market="ASIAN_HANDICAP", selection="HOME", checkpoint="FINAL",
            evaluated_at=evaluated, original_state=LEGAL_STATE,
            payload={"model_settlement_distribution": {"WIN": payload_value, "HALF_WIN": 0.0}},
        ))
        capture_id = f"capture-{index}"
        session.add(MatchdayEndpointCaptureModel(
            capture_id=capture_id, fixture_id=fixture, endpoint="fixtures",
            sanitized_params={}, params_hash=(capture_id + "p") * 32, request_task_key=capture_id,
            attempt=1, requested_at=evaluated, provider_captured_at=evaluated + timedelta(minutes=2),
            status_code=200, elapsed_ms=1, response_count=1, quota_values={},
            raw_payload_sha256=(capture_id + "h") * 32, capture_status="SUCCESS",
        ))
        session.add(ResultModel(
            id=f"result-{index}", fixture_id=fixture, home_goals=0, away_goals=1,
            result_status="FINAL", confirmed_at=evaluated + timedelta(minutes=2),
            source_payload_sha256=(fixture + "s") * 32, source_capture_id=capture_id,
            result_hash=(fixture + "r") * 32,
        ))
    session.commit()


def test_b6_fast_criteria_rows_uses_materialized_production_path():
    engine = _session()
    with Session(engine) as session:
        _seed_forward_batch(session)
        materialize_calibrated_validation_samples(session)
        rows = fast_criteria_rows(session)
        assert evaluate_fast_criteria(rows, minimum_kept=1)
        assert any(row["forward"] for row in rows)


def test_b6_fast_criteria_fails_only_calibration_gap_after_materialization():
    engine = _session()
    with Session(engine) as session:
        _seed_forward_batch(session, bad_filtered_gap=True)
        materialize_calibrated_validation_samples(session)
        assert not evaluate_fast_criteria(fast_criteria_rows(session), minimum_kept=1)


def test_c3_unsettled_forward_row_is_excluded_but_missing_prediction_fails_closed():
    rows = [
        {"forward": True, "warmup": False, "settlement": "PENDING", "filter_decision": "KEPT"},
        {"forward": True, "warmup": False, "settlement": "WIN", "filter_decision": "KEPT",
         "market": "ASIAN_HANDICAP", "selection": "HOME", "bias_at_decision": 0.1,
         "profit_units": 1.0, "predicted_success": None, "realized_success": 1.0},
    ]
    assert not evaluate_fast_criteria(rows, minimum_kept=1)


def test_c4_missing_forward_is_not_treated_as_forward():
    assert not evaluate_fast_criteria([{
        "warmup": False, "settlement": "WIN", "filter_decision": "KEPT",
    }], minimum_kept=1)


def test_c2_date_filters_samples_but_forward_progress_uses_all_days(monkeypatch):
    engine = _session()
    first = FORWARD_START_UTC + timedelta(days=1)
    second = FORWARD_START_UTC + timedelta(days=2)
    with Session(engine) as session:
        for index, evaluated in enumerate((first, second)):
            session.add(CalibratedValidationSampleModel(
                fixture_id=f"api-{index}", market="ASIAN_HANDICAP", selection="HOME",
                exact_line="-0.5", decimal_odds=2.0, evaluation_id=f"e-{index}",
                settlement="WIN", projected_at=evaluated, evaluated_at=evaluated,
                kickoff_utc=evaluated + timedelta(hours=1), current_ev=0.1,
                filter_decision="KEPT", param_version=PARAM_VERSION, warmup=False,
            ))
        session.commit()
    class Repo:
        def _database_engine(self):
            return engine
    class Service:
        repository = Repo()
    import w2.api.routers as routers
    monkeypatch.setattr(routers, "service", Service())
    response = routers.dashboard_intelligence_validation_calibrated(
        Request({"type": "http", "method": "GET", "path": "/", "headers": []}),
        date=first.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
    )
    assert response["forward_progress"]["kept"] == 2
    assert len(response["samples"]) == 1
