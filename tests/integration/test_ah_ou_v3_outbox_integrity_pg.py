"""Independent A05/A06 read-defense attacks on an isolated PostgreSQL DB.

Production producer/capture/frozen/forward and natural FT worker are reused.
Only the external sender is replaced with an in-memory recorder: real sends=0.
The ledger attack bypasses immutability only inside this audit DB; it tests
reading already-invalid data, not permissions granted to production writers.
"""

import json
from copy import deepcopy
from datetime import UTC, datetime, time, timedelta

import pytest
from apps.api.main import app
from apps.worker.celery_app import result_materialize
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from tests.integration.test_ah_ou_v11_postmatch_pg import _ft_capture

from w2.dashboard.date_window import FOOTBALL_DAY_TZ, football_day_for_kickoff
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import AhOuDecisionLedgerModel
from w2.infrastructure.persistence.dynamic_prematch_models import CandidateNotificationOutboxModel
from w2.prematch.analysis_calculator import ReadModelService
from w2.prematch.candidate_notifications import (
    V3_DAILY_SETTLEMENT,
    V3_RECOMMENDATION_CONFIRMED,
    deliver_pending_notifications,
    enqueue_v3_daily_settlement_in_session,
    render_bark_message,
)

pytest_plugins = ["tests.integration.test_ah_ou_v9_system_pg"]


def emit(label, **fields):
    print(json.dumps({"scenario": label, **fields}, default=str, ensure_ascii=False))


def configure_sender(monkeypatch):
    monkeypatch.setenv("W2_BARK_ENDPOINT", "https://bark.example.test")
    monkeypatch.setenv("W2_BARK_DEVICE_KEY", "test-key")


def deliver(repo, at):
    sent = []
    result = deliver_pending_notifications(
        now=at, engine=repo.engine, sender=lambda payload: sent.append(deepcopy(payload))
    )
    with Session(repo.engine) as session:
        stored = [
            {
                "id": row.notification_event_id,
                "status": row.delivery_status,
                "last_error": row.last_error,
            }
            for row in session.scalars(select(CandidateNotificationOutboxModel))
        ]
    return result, sent, stored


def mutate_ledger(repo, decision_id, field, value):
    with Session(repo.engine) as session, session.begin():
        session.execute(text("SET LOCAL session_replication_role = replica"))
        session.execute(
            update(AhOuDecisionLedgerModel)
            .where(AhOuDecisionLedgerModel.decision_id == decision_id)
            .values(**{field: value})
        )


def reset_pending(repo, event_type):
    with Session(repo.engine) as session, session.begin():
        session.execute(
            update(CandidateNotificationOutboxModel)
            .where(CandidateNotificationOutboxModel.event_type == event_type)
            .values(delivery_status="PENDING", last_error=None)
        )


def current_http(day):
    response = TestClient(app, raise_server_exceptions=False).get(
        "/v1/dashboard/intelligence-workspace/list", params={"date": day.isoformat()}
    )
    return response.status_code, response.text


@pytest.mark.parametrize(
    "field,bad",
    [
        ("source_capture_sha256", "f" * 64),
        ("decision_contract", None),
    ],
)
def test_recommendation_sender_rejects_invalid_frozen_authority(chain, monkeypatch, field, bad):
    configure_sender(monkeypatch)
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=datetime.fromisoformat(future["fixture"]["date"])
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    day = football_day_for_kickoff(datetime.fromisoformat(future["fixture"]["date"]))
    with Session(repo.engine) as session:
        ah = session.scalar(
            select(AhOuDecisionLedgerModel).where(
                AhOuDecisionLedgerModel.market == "ASIAN_HANDICAP"
            )
        )
        decision_id, original = ah.decision_id, getattr(ah, field)
    assert original != bad

    # Same PG mutation/read/send path, identical business value first.
    mutate_ledger(repo, decision_id, field, original)
    code, body = current_http(day)
    assert code == 200, body
    result, sent, stored = deliver(repo, datetime.now(UTC))
    emit(
        f"recommendation_{field}_noop",
        db=repo.engine.url.database,
        http=code,
        delivery=result,
        sent_ids=[row["decision_id"] for row in sent],
        stored=stored,
    )
    assert result["delivered"] == len(sent) == 2
    assert {row["market"] for row in sent} == {"ASIAN_HANDICAP", "TOTALS"}

    reset_pending(repo, V3_RECOMMENDATION_CONFIRMED)
    mutate_ledger(repo, decision_id, field, bad)
    code, body = current_http(day)
    result, sent, stored = deliver(repo, datetime.now(UTC))
    emit(
        f"recommendation_{field}_attack",
        db=repo.engine.url.database,
        mutated_decision_id=decision_id,
        old=original,
        new=bad,
        http=code,
        response=body[:1000],
        delivery=result,
        sent_ids=[row["decision_id"] for row in sent],
        stored=stored,
    )
    assert decision_id not in {row["decision_id"] for row in sent}, (
        "A05/A06 invalid v3 authority reached the current notification sender"
    )


@pytest.mark.parametrize(
    "field",
    [
        "selected",
        "settled",
        "pending",
        "blocked",
        "void",
        "net_units",
        "items",
        "event_type",
        "schema_version",
        "dashboard_url",
        "created_at",
    ],
)
def test_daily_sender_reconciles_all_business_counts(chain, monkeypatch, field):
    configure_sender(monkeypatch)
    repo, future, _, _ = chain
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=datetime.fromisoformat(future["fixture"]["date"])
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    _ft_capture(repo, future)
    settled = result_materialize.run(fixture_ids=["api_football:1489404"])
    assert settled["status"] == "PASS", settled
    day = football_day_for_kickoff(datetime.fromisoformat(future["fixture"]["date"]))
    at = datetime.combine(day + timedelta(days=1), time(12), tzinfo=FOOTBALL_DAY_TZ).astimezone(UTC)
    with Session(repo.engine) as session, session.begin():
        session.execute(
            update(CandidateNotificationOutboxModel).values(delivery_status="DELIVERED")
        )
        event_id = enqueue_v3_daily_settlement_in_session(session, now=at)
        row = session.get(CandidateNotificationOutboxModel, event_id)
        original = deepcopy(row.payload)
    assert original["selected"] == original["settled"] == 2
    assert original["net_units"] == "1.15"

    # Real ordinary UPDATE, same exact payload, then natural sender control.
    with Session(repo.engine) as session, session.begin():
        session.execute(
            update(CandidateNotificationOutboxModel)
            .where(CandidateNotificationOutboxModel.notification_event_id == event_id)
            .values(payload=deepcopy(original))
        )
    result, sent, stored = deliver(repo, at)
    emit(
        f"daily_{field}_noop",
        db=repo.engine.url.database,
        delivery=result,
        payload=sent,
        stored=stored,
    )
    assert result["delivered"] == len(sent) == 1
    assert sent[0][field] == original[field]

    reset_pending(repo, V3_DAILY_SETTLEMENT)
    bad = {
        "net_units": "999",
        "items": original["items"] + [original["items"][0]],
        "event_type": "OTHER",
        "schema_version": "other.v1",
        "dashboard_url": "/wrong",
        "created_at": "2000-01-01T00:00:00+00:00",
    }.get(field, 999)
    changed = {**original, field: bad}
    # The ordinary write fence rejects the same attack before the read defense.
    with pytest.raises(DBAPIError, match="V3_OUTBOX_BUSINESS_IMMUTABLE"):
        with Session(repo.engine) as session, session.begin():
            session.execute(
                update(CandidateNotificationOutboxModel)
                .where(CandidateNotificationOutboxModel.notification_event_id == event_id)
                .values(payload=changed)
            )
    with Session(repo.engine) as session, session.begin():
        # Preserve the registered read-defense attack beneath the new immutable trigger.
        session.execute(text("SET LOCAL session_replication_role = replica"))
        session.execute(
            update(CandidateNotificationOutboxModel)
            .where(CandidateNotificationOutboxModel.notification_event_id == event_id)
            .values(payload=changed)
        )
    result, sent, stored = deliver(repo, at)
    emit(
        f"daily_{field}_attack",
        db=repo.engine.url.database,
        changed_field=field,
        old=original[field],
        new=999,
        delivery=result,
        stored=stored,
        rendered=[render_bark_message(row) for row in sent],
    )
    assert not sent, f"A06 daily {field} disagrees with trusted decisions"
    error = next(row["last_error"] for row in stored if row["id"] == event_id)
    expected = (
        "V3_DAILY_SCHEMA_INVALID"
        if field == "schema_version"
        else f"V3_DAILY_CONTENT_CONFLICT:{field}"
    )
    assert expected in error
    with pytest.raises(ValueError, match=expected):
        with Session(repo.engine) as session:
            enqueue_v3_daily_settlement_in_session(session, now=at)


def test_daily_real_database_four_steps(chain):
    repo, future, _, _ = chain
    ReadModelService().public_analysis_card_bounded("1489404", use_frozen_canary=False)
    _ft_capture(repo, future)
    assert result_materialize.run(fixture_ids=["api_football:1489404"])["status"] == "PASS"
    day = football_day_for_kickoff(datetime.fromisoformat(future["fixture"]["date"]))
    at = datetime.combine(day + timedelta(days=1), time(12), tzinfo=FOOTBALL_DAY_TZ).astimezone(UTC)
    with Session(repo.engine) as session, session.begin():
        event_id = enqueue_v3_daily_settlement_in_session(session, now=at)
        assert event_id is not None
        assert enqueue_v3_daily_settlement_in_session(session, now=at) is None
    with Session(repo.engine) as session, session.begin():
        row = session.get(CandidateNotificationOutboxModel, event_id)
        original = deepcopy(row.payload)
        assert (
            enqueue_v3_daily_settlement_in_session(session, now=at + timedelta(seconds=1)) is None
        )
        assert row.payload == original
    with pytest.raises(DBAPIError, match="V3_OUTBOX_BUSINESS_IMMUTABLE"):
        with Session(repo.engine) as session, session.begin():
            session.execute(
                update(CandidateNotificationOutboxModel)
                .where(CandidateNotificationOutboxModel.notification_event_id == event_id)
                .values(payload={**original, "selected": 99})
            )
    with Session(repo.engine) as session:
        assert session.get(CandidateNotificationOutboxModel, event_id).payload == original
        print({"four_steps": "PASS", "event_id": event_id, "payload": original})
