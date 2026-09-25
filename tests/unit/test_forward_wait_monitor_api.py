from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.api.repository import ReadModelService
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
    ValidationSampleModel,
)
from w2.infrastructure.persistence.forward_evidence_models import (
    ForwardClockModel,
    RecommendationReviewLedgerModel,
)
from w2.tracking.forward_evidence import CLOCK_ID, PREREG_SHA256


def test_forward_wait_monitor_reads_registered_clock_and_evidence_only() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            DynamicPrematchEvaluationModel.__table__,
            ValidationSampleModel.__table__,
            ForwardClockModel.__table__,
            RecommendationReviewLedgerModel.__table__,
        ],
    )
    service = ReadModelService(repository=SimpleNamespace(_database_engine=lambda: engine))
    empty = service.dashboard_forward_wait_monitor()
    assert empty["clock"]["status"] == "NOT_STARTED"
    assert empty["sample_progress"]["sealed_validation"] == 0
    assert empty["bias_drift"]["status"] == "INSUFFICIENT_FORWARD_SETTLEMENTS"

    now = datetime(2026, 9, 26, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            ForwardClockModel(
                clock_id=CLOCK_ID,
                started_at=now,
                code_revision="a" * 40,
                model_identity="candidate-eval.v2",
                preregistration_sha256=PREREG_SHA256,
                input_version="w2.forward_evidence_input.v1",
            )
        )
        session.add(
            RecommendationReviewLedgerModel(
                review_event_id="b" * 64,
                evaluation_id="e",
                event_type="EVALUATION_SNAPSHOT",
                evaluated_at=now,
                pit_status="PIT_UNPROVABLE",
                payload={"exclusion_reasons": ["QUOTE_PAIR_MISMATCH"]},
                payload_sha256="b" * 64,
                created_at=now,
            )
        )
        session.commit()
    result = service.dashboard_forward_wait_monitor()
    assert result["clock"]["status"] == "STARTED"
    assert result["exclusions"]["pit_unprovable"] == 1
    assert result["exclusions"]["write_gap_count"] == 0
    assert result["capture_completeness"]["rate"] == 0
    assert result["shadow"]["status"] == "F1_RUN_NOT_REGISTERED"
