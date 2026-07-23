from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.ingestion_models import (
    IngestionRunModel,
    ProviderRequestLogModel,
    QuotaUsageModel,
)

NOW = datetime(2026, 6, 22, 1, 0, tzinfo=UTC)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as active:
        yield active


def test_ingestion_run_and_request_log_idempotency(session: Session) -> None:
    first = IngestionRunModel(
        provider="api_football",
        endpoint="odds",
        run_key="offline-gate2",
        live=False,
        status="SUCCEEDED",
        started_at=NOW,
        finished_at=NOW,
    )
    duplicate = IngestionRunModel(
        provider="api_football",
        endpoint="odds",
        run_key="offline-gate2",
        live=False,
        status="SUCCEEDED",
        started_at=NOW,
        finished_at=NOW,
    )
    session.add_all([first, duplicate])
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    log = ProviderRequestLogModel(
        provider="api_football",
        endpoint="fixtures",
        request_hash="a" * 64,
        live=False,
        requested_at=NOW,
    )
    duplicate_log = ProviderRequestLogModel(
        provider="api_football",
        endpoint="fixtures",
        request_hash="a" * 64,
        live=False,
        requested_at=NOW,
    )
    session.add_all([log, duplicate_log])
    with pytest.raises(IntegrityError):
        session.commit()


def test_quota_usage_table(session: Session) -> None:
    session.add(
        QuotaUsageModel(
            provider="api_football",
            endpoint="odds",
            used=1,
            limit=10,
            window_start=NOW,
            window_end=NOW + timedelta(days=1),
        )
    )
    session.commit()
    assert session.query(QuotaUsageModel).count() == 1
