from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.config import get_settings
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.ingestion_models import (
    ProviderQuotaObservationModel,
    ProviderRequestLogModel,
    QuotaUsageModel,
)
from w2.providers.ledger import (
    DbProviderRequestLedger,
    ProviderLedgerError,
    provider_timeout_count_since,
)

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
                "x-ratelimit-limit": "10",
                "x-ratelimit-remaining": "6",
            },
            payload={"response": []},
        )

    with Session(engine) as session:
        logs = list(session.scalars(select(ProviderRequestLogModel)))
        usage = session.scalar(select(QuotaUsageModel))
        observations = list(session.scalars(select(ProviderQuotaObservationModel)))

    assert len(logs) == 2
    assert len({log.request_hash for log in logs}) == 2
    assert usage is not None
    assert usage.used == 700
    assert usage.limit == 7500
    assert usage.observed_at.replace(tzinfo=UTC) == NOW + timedelta(seconds=1)
    assert usage.burst_limit == 10
    assert usage.burst_remaining == 6
    assert len(observations) == 2
    assert [row.burst_remaining for row in observations] == [6, 6]


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


def test_db_provider_ledger_persists_burst_only_observation(
    monkeypatch,
    tmp_path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ledger.db'}"
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)

    DbProviderRequestLedger().record_request(
        provider="api_football",
        endpoint="status",
        params={},
        live=True,
        status_code=200,
        requested_at=NOW,
        completed_at=NOW,
        headers={"x-ratelimit-limit": "10", "x-ratelimit-remaining": "4"},
        payload={"response": {"requests": {}}},
    )

    with Session(engine) as session:
        observation = session.scalar(select(ProviderQuotaObservationModel))
        usage_rows = list(session.scalars(select(QuotaUsageModel)))

    assert observation is not None
    assert observation.daily_limit is None
    assert observation.daily_remaining is None
    assert observation.burst_limit == 10
    assert observation.burst_remaining == 4
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


def test_db_provider_ledger_accepts_provider_reset_inside_utc_window(
    monkeypatch,
    tmp_path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ledger.db'}"
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    ledger = DbProviderRequestLedger()

    for index, remaining in enumerate((2743, 7497)):
        observed_at = NOW.replace(hour=0, minute=1) + timedelta(minutes=15 * index)
        ledger.record_request(
            provider="api_football",
            endpoint="odds",
            params={"fixture": str(1494246 + index)},
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
        usage = session.scalar(select(QuotaUsageModel))

    assert usage is not None
    assert usage.used == 3
    assert usage.observed_at.replace(tzinfo=UTC) == NOW.replace(hour=0, minute=16)


def test_db_provider_ledger_accepts_only_exact_duplicate(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ledger.db'}"
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    ledger = DbProviderRequestLedger()
    kwargs = {
        "provider": "api_football",
        "endpoint": "odds",
        "params": {"fixture": "1489404"},
        "live": True,
        "status_code": 200,
        "requested_at": NOW,
        "completed_at": NOW,
        "headers": {},
        "payload": {"response": []},
    }

    ledger.record_request(**kwargs)
    ledger.record_request(**kwargs)
    with Session(engine) as session:
        assert len(list(session.scalars(select(ProviderRequestLogModel)))) == 1

    with pytest.raises(ProviderLedgerError, match="PROVIDER_REQUEST_LEDGER_CONFLICT"):
        ledger.record_request(**{**kwargs, "status_code": 503})


def test_provider_timeout_count_since_counts_live_api_football_attempts(
    monkeypatch,
    tmp_path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ledger.db'}"
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                ProviderRequestLogModel(
                    provider="api_football",
                    endpoint="fixtures",
                    request_hash=f"{index:064x}",
                    live=live,
                    requested_at=requested_at,
                    completed_at=requested_at,
                    error=error,
                )
                for index, (live, requested_at, error) in enumerate(
                    (
                        (True, NOW, "PROVIDER_TIMEOUT"),
                        (True, NOW - timedelta(days=2), "PROVIDER_TIMEOUT"),
                        (False, NOW, "PROVIDER_TIMEOUT"),
                        (True, NOW, "PROVIDER_CONNECTION_ERROR"),
                    )
                )
            ]
        )
        session.commit()

    assert provider_timeout_count_since(NOW - timedelta(hours=24)) == 1
