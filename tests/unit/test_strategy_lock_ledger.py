from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.recommendation_lock_models import (
    Gate5RecommendationLockEventModel,
)
from w2.strategy.lock_ledger import (
    LockEventType,
    LockLedgerError,
    RecommendationLockLedger,
    RecommendationLockPayload,
    lock_id_for,
)

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


def ledger(tmp_path: Path) -> RecommendationLockLedger:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'locks.db'}")
    Base.metadata.create_all(engine)
    return RecommendationLockLedger(engine=engine)


def payload(
    *,
    market: str = "TOTALS",
    selection: str = "UNDER",
    probability: str = "0.5400",
) -> RecommendationLockPayload:
    return RecommendationLockPayload(
        fixture_id="1489404",
        market=market,
        selection=selection,
        line="2.5",
        probability=Decimal(probability),
        source="unit-test",
    )


def test_lock_after_direction_or_probability_change_is_rejected(tmp_path: Path) -> None:
    store = ledger(tmp_path)
    first = store.create_lock(
        payload(),
        actor="tester",
        reason="initial shadow lock",
        event_time=NOW,
    )

    same = store.create_lock(
        payload(),
        actor="tester",
        reason="idempotent retry",
        event_time=NOW + timedelta(seconds=1),
    )
    assert same.event_id == first.event_id

    with pytest.raises(LockLedgerError, match="LOCK_IMMUTABLE"):
        store.create_lock(
            payload(selection="OVER"),
            actor="tester",
            reason="direction changed",
            event_time=NOW + timedelta(seconds=2),
        )
    with pytest.raises(LockLedgerError, match="LOCK_IMMUTABLE"):
        store.create_lock(
            payload(probability="0.6100"),
            actor="tester",
            reason="probability changed",
            event_time=NOW + timedelta(seconds=3),
        )

    assert len(store.events(first.lock_id)) == 1


def test_only_append_version_or_revoke_after_lock(tmp_path: Path) -> None:
    store = ledger(tmp_path)
    first = store.create_lock(
        payload(),
        actor="tester",
        reason="initial shadow lock",
        event_time=NOW,
    )
    version = store.append_version(
        first.lock_id,
        payload(selection="OVER", probability="0.5800"),
        actor="tester",
        reason="new evidence version",
        event_time=NOW + timedelta(minutes=1),
    )
    revoked = store.revoke(
        first.lock_id,
        actor="tester",
        reason="market suspended",
        event_time=NOW + timedelta(minutes=2),
    )

    events = store.events(first.lock_id)
    assert [event.event_type for event in events] == [
        LockEventType.LOCK_CREATED,
        LockEventType.VERSION_APPENDED,
        LockEventType.REVOKED,
    ]
    assert version.version == 2
    assert version.prior_event_id == first.event_id
    assert revoked.version == 3
    assert revoked.prior_event_id == version.event_id
    assert all(event.candidate is False for event in events)
    assert all(event.formal_recommendation is False for event in events)


def test_lock_ledger_is_db_backed_append_only(tmp_path: Path) -> None:
    store = ledger(tmp_path)
    first = store.create_lock(
        payload(),
        actor="tester",
        reason="initial shadow lock",
        event_time=NOW,
    )

    with Session(store.engine) as session:
        assert (
            session.scalar(select(func.count()).select_from(Gate5RecommendationLockEventModel))
            == 1
        )
        row = session.scalar(
            select(Gate5RecommendationLockEventModel).where(
                Gate5RecommendationLockEventModel.lock_id == lock_id_for(payload())
            )
        )
        assert row is not None
        assert row.event_id == first.event_id
        assert row.candidate is False
        assert row.formal_recommendation is False
