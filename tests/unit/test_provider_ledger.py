from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.config import get_settings
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.ingestion_models import (
    ProviderRequestLogModel,
    QuotaUsageModel,
)
from w2.providers.ledger import DbProviderRequestLedger

NOW = datetime(2026, 7, 3, 1, 0, tzinfo=UTC)


def test_db_provider_ledger_records_repeated_identical_requests(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ledger.db'}"
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    ledger = DbProviderRequestLedger()

    for index, remaining in enumerate((7000, 6800)):
        observed_at = NOW + timedelta(seconds=index)
        ledger.record_request(
            provider="api_football",
            endpoint="odds",
            params={"fixture": "1489404"},
            live=True,
            status_code=200,
            requested_at=observed_at,
            completed_at=observed_at,
            headers={
                "x-ratelimit-requests-remaining": str(remaining),
                "x-ratelimit-requests-limit": "7500",
            },
            payload={"response": []},
        )

    with Session(engine) as session:
        logs = list(session.scalars(select(ProviderRequestLogModel)))
        usage = session.scalar(select(QuotaUsageModel))

    assert len(logs) == 2
    assert len({log.request_hash for log in logs}) == 2
    assert usage is not None
    assert usage.used == 700
    assert usage.limit == 7500


def test_db_provider_ledger_does_not_infer_usage_without_limit_header(
    monkeypatch,
    tmp_path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ledger.db'}"
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    ledger = DbProviderRequestLedger()

    ledger.record_request(
        provider="api_football",
        endpoint="status",
        params={},
        live=True,
        status_code=200,
        requested_at=NOW,
        completed_at=NOW,
        headers={"x-ratelimit-requests-remaining": "100"},
        payload={"response": []},
    )

    with Session(engine) as session:
        logs = list(session.scalars(select(ProviderRequestLogModel)))
        usage_rows = list(session.scalars(select(QuotaUsageModel)))

    assert len(logs) == 1
    assert usage_rows == []


def test_db_provider_ledger_uses_header_limit_basis_for_quota_usage(
    monkeypatch,
    tmp_path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ledger.db'}"
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    ledger = DbProviderRequestLedger()

    for index, remaining in enumerate((98, 95)):
        observed_at = NOW + timedelta(seconds=index)
        ledger.record_request(
            provider="api_football",
            endpoint="fixtures",
            params={"date": "2026-07-05"},
            live=True,
            status_code=200,
            requested_at=observed_at,
            completed_at=observed_at,
            headers={
                "x-ratelimit-requests-remaining": str(remaining),
                "x-ratelimit-requests-limit": "100",
            },
            payload={"response": []},
        )

    with Session(engine) as session:
        usage = session.scalar(select(QuotaUsageModel))

    assert usage is not None
    assert usage.used == 5
    assert usage.limit == 100
