from __future__ import annotations

import os
from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from w2.config import get_settings
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.future_refresh_models import (
    GateAProviderCallModel,
    GateARunReservationModel,
)
from w2.operations.gate_a import (
    GateAError,
    GateARunReservation,
    GateARuntimeAuthorization,
    authorization_signing_message,
    reserve_gate_a_run,
)

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
HEAD = "a" * 40
TREE = "b" * 40
TASK_KEY = "future-refresh:world_cup_2026:2026:20260801T120000Z"
SIGNING_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
PUBLIC_KEY = b64encode(
    SIGNING_KEY.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
).decode()
TRUSTED_KEYS = {"test-independent-key": PUBLIC_KEY}


def authorization_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "w2.gate-a-one-shot-authorization.v1",
        "action": "ONE_SHOT_FOREGROUND_CANARY",
        "review_status": "APPROVED",
        "one_shot": True,
        "persistence": "db",
        "authorization_id": "gate-a-test-1",
        "task_key": TASK_KEY,
        "competition_id": "world_cup_2026",
        "season": "2026",
        "exact_head": HEAD,
        "exact_tree": TREE,
        "allowed_endpoints": ["status", "fixtures", "odds", "lineups"],
        "provider_call_cap": 4,
        "issued_at": (NOW - timedelta(minutes=1)).isoformat(),
        "expires_at": (NOW + timedelta(minutes=30)).isoformat(),
        "author": "runtime-owner",
        "reviewer": "independent-reviewer",
        "approval_key_id": "test-independent-key",
    }
    payload.update(overrides)
    if "approval_signature" not in overrides:
        payload["approval_signature"] = b64encode(
            SIGNING_KEY.sign(authorization_signing_message(payload))
        ).decode()
    return payload


def runtime_authorization(**overrides: object) -> GateARuntimeAuthorization:
    return GateARuntimeAuthorization.from_mapping(
        authorization_payload(**overrides),
        trusted_public_keys=TRUSTED_KEYS,
    )


def test_authorization_is_independent_scoped_short_lived_and_db_only() -> None:
    authorization = runtime_authorization()
    authorization.validate_scope(
        competition_id="world_cup_2026",
        season="2026",
        persistence="db",
        task_key=TASK_KEY,
        exact_head=HEAD,
        exact_tree=TREE,
        policy_season="2026",
        now=NOW,
    )

    failures = (
        ({"author": "same", "reviewer": "same"}, "GATE_A_INDEPENDENT_REVIEW_REQUIRED"),
        ({"one_shot": False}, "GATE_A_AUTHORIZATION_INVALID"),
        ({"persistence": "file"}, "GATE_A_AUTHORIZATION_INVALID"),
        ({"provider_call_cap": 11}, "GATE_A_PROVIDER_CALL_CAP_INVALID"),
        ({"allowed_endpoints": ["injuries"]}, "GATE_A_ENDPOINT_SCOPE_INVALID"),
    )
    for overrides, code in failures:
        with pytest.raises(GateAError, match=code):
            runtime_authorization(**overrides)
    with pytest.raises(GateAError, match="GATE_A_APPROVAL_SIGNATURE_INVALID"):
        runtime_authorization(approval_signature=b64encode(b"not-a-signature").decode())


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("competition_id", "other", "GATE_A_COMPETITION_SCOPE_MISMATCH"),
        ("season", "2027", "GATE_A_SEASON_SCOPE_MISMATCH"),
        ("persistence", "file", "GATE_A_DB_PERSISTENCE_REQUIRED"),
        ("task_key", "other", "GATE_A_TASK_KEY_SCOPE_MISMATCH"),
        ("exact_head", "b" * 40, "GATE_A_EXACT_HEAD_MISMATCH"),
        ("exact_tree", "c" * 40, "GATE_A_EXACT_TREE_MISMATCH"),
        ("policy_season", "2027", "GATE_A_POLICY_SEASON_MISMATCH"),
        ("now", NOW + timedelta(hours=1), "GATE_A_AUTHORIZATION_EXPIRED"),
    ],
)
def test_authorization_scope_mismatch_fails_closed(field: str, value: object, code: str) -> None:
    authorization = runtime_authorization()
    scope: dict[str, object] = {
        "competition_id": "world_cup_2026",
        "season": "2026",
        "persistence": "db",
        "task_key": TASK_KEY,
        "exact_head": HEAD,
        "exact_tree": TREE,
        "policy_season": "2026",
        "now": NOW,
    }
    scope[field] = value
    with pytest.raises(GateAError, match=code):
        authorization.validate_scope(**scope)  # type: ignore[arg-type]


def test_db_reservation_is_one_shot_fenced_and_atomically_capped(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'gate-a.db'}"
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    authorization = runtime_authorization(provider_call_cap=2)

    reservation = reserve_gate_a_run(authorization, owner="foreground", now=NOW)
    assert reservation.reserve_provider_call("status") == 1
    reservation.record_provider_outcome(1, state="RESPONSE_RECEIVED")
    assert reservation.reserve_provider_call("fixtures") == 2
    reservation.record_provider_outcome(
        2,
        state="DELIVERY_UNCERTAIN",
        error_code="TimeoutError",
    )
    with pytest.raises(GateAError, match="GATE_A_PROVIDER_CALL_RESERVATION_REJECTED"):
        reservation.reserve_provider_call("odds")
    with pytest.raises(GateAError, match="GATE_A_AUTHORIZATION_ALREADY_CONSUMED"):
        reserve_gate_a_run(authorization, owner="second", now=NOW)
    with pytest.raises(GateAError, match="GATE_A_TASK_ALREADY_RESERVED"):
        reserve_gate_a_run(
            runtime_authorization(authorization_id="gate-a-test-2"),
            owner="competing-owner",
            now=NOW,
        )

    stale = GateARunReservation(
        authorization_id=reservation.authorization_id,
        task_key=reservation.task_key,
        owner=reservation.owner,
        lease_epoch=reservation.lease_epoch + 1,
        provider_call_cap=2,
    )
    with pytest.raises(GateAError, match="GATE_A_LEASE_EPOCH_REJECTED"):
        stale.finalize("FAILED")
    reservation.finalize("COMPLETED")
    with Session(engine) as session:
        row = session.scalar(select(GateARunReservationModel))
        calls = list(
            session.scalars(
                select(GateAProviderCallModel).order_by(GateAProviderCallModel.call_ordinal)
            )
        )
    assert row is not None
    assert (row.status, row.provider_calls_used, row.last_endpoint) == (
        "COMPLETED",
        2,
        "fixtures",
    )
    assert [(call.endpoint, call.state, call.error_code) for call in calls] == [
        ("status", "RESPONSE_RECEIVED", None),
        ("fixtures", "DELIVERY_UNCERTAIN", "TimeoutError"),
    ]
    get_settings.cache_clear()


def test_postgres_distinct_authorizations_have_one_task_key_lease_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = os.environ.get("W2_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("W2_TEST_POSTGRES_URL is required for PostgreSQL task-key fencing")
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.execute(delete(GateAProviderCallModel))
        session.execute(delete(GateARunReservationModel))
        session.commit()
    barrier = Barrier(2)

    def reserve(authorization_id: str) -> str:
        barrier.wait()
        try:
            reservation = reserve_gate_a_run(
                runtime_authorization(authorization_id=authorization_id),
                owner=authorization_id,
                now=NOW,
            )
        except GateAError as exc:
            return str(exc)
        return f"WINNER:{reservation.authorization_id}"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, ("authorization-a", "authorization-b")))

    assert sum(result.startswith("WINNER:") for result in results) == 1
    assert results.count("GATE_A_TASK_ALREADY_RESERVED") == 1
    get_settings.cache_clear()
