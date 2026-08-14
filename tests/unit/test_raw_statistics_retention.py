from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import HashDomain
from w2.infrastructure.persistence.future_refresh_models import (
    RawPayloadModel,
    RawStatisticsRetentionModel,
)
from w2.ingestion.future_refresh import sha256_payload
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository


def test_statistics_raw_is_manifested_and_append_only(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'retention.db'}")
    RawPayloadModel.__table__.create(engine)
    RawStatisticsRetentionModel.__table__.create(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    payload = {"parameters": {"fixture": "1"}, "response": []}
    digest = sha256_payload(payload, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)

    repository.save_raw_payload(
        sha256=digest,
        endpoint="statistics",
        captured_at=datetime(2026, 8, 14, tzinfo=UTC),
        payload=payload,
    )

    with Session(engine) as session:
        assert session.scalar(select(RawStatisticsRetentionModel.raw_payload_sha256)) == digest
        row = session.get(RawPayloadModel, digest)
        assert row is not None
        row.payload = {"parameters": {"fixture": "1"}, "response": ["mutated"]}
        with pytest.raises(ValueError, match="permanently retained"):
            session.commit()
        session.rollback()
        row = session.get(RawPayloadModel, digest)
        assert row is not None
        session.delete(row)
        with pytest.raises(ValueError, match="permanently retained"):
            session.commit()


def test_non_statistics_raw_does_not_create_statistics_manifest(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'retention.db'}")
    RawPayloadModel.__table__.create(engine)
    RawStatisticsRetentionModel.__table__.create(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    payload = {"response": []}
    digest = sha256_payload(payload, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)

    repository.save_raw_payload(
        sha256=digest,
        endpoint="fixtures",
        captured_at=datetime(2026, 8, 14, tzinfo=UTC),
        payload=payload,
    )

    with Session(engine) as session:
        assert session.scalar(select(RawStatisticsRetentionModel.raw_payload_sha256)) is None
