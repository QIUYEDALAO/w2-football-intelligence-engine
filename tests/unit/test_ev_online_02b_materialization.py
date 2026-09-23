from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.dynamic_prematch_models import (
    CalibratedValidationSampleModel,
    DynamicPrematchEvaluationModel,
    ValidationSampleModel,
)
from w2.strategy.online_calibration_filter import (
    LEGAL_STATE,
    PARAM_VERSION,
    materialize_calibrated_validation_samples,
)


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _seed(session, fixture="f1", evaluation_id="e1", *, settlement="PENDING", profit=None, score=None):
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
        first = materialize_calibrated_validation_samples(session)
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
