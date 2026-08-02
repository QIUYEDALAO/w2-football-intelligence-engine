from __future__ import annotations

import hashlib
import json
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
    GATE_A_OWNER_APPROVAL_MODE,
    GATE_A_SELECTION_POLICY_VERSION,
    GATE_A_SELECTION_RULE,
    GateAError,
    GateARunReservation,
    GateARuntimeAuthorization,
    TrustedApprovalKey,
    authorization_signing_message,
    reserve_gate_a_run,
    select_fixture_from_authorization,
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
PUBLIC_KEY_SHA256 = hashlib.sha256(
    SIGNING_KEY.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
).hexdigest()
TRUSTED_KEYS = {
    "test-independent-key": TrustedApprovalKey(
        public_key_base64=PUBLIC_KEY,
        public_key_sha256=PUBLIC_KEY_SHA256,
        custody_status="INDEPENDENT_SIGNER_CONFIRMED",
        authorization_enabled=True,
    )
}


def authorization_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "w2.gate-a-one-shot-authorization.v4",
        "action": "ONE_SHOT_FOREGROUND_CANARY",
        "review_status": "APPROVED",
        "one_shot": True,
        "persistence": "db",
        "authorization_id": "gate-a-test-1",
        "task_key": TASK_KEY,
        "fixture_id": "12345",
        "competition_id": "world_cup_2026",
        "season": "2026",
        "provider_league_id": "1",
        "competition_policy_config_hash": "d" * 64,
        "fixture_scope_mode": "EXACT_FIXTURE_ID",
        "kickoff_window_start_utc": None,
        "kickoff_window_end_utc": None,
        "selection_policy_version": GATE_A_SELECTION_POLICY_VERSION,
        "selection_rule": GATE_A_SELECTION_RULE,
        "exact_head": HEAD,
        "exact_tree": TREE,
        "execution_mode": "COMPLETE_CLEAN_CHECKOUT",
        "runtime_artifact_digest": None,
        "complete_checkout_manifest_sha256": "c" * 64,
        "allowed_endpoints": ["status", "fixtures", "odds", "lineups"],
        "provider_call_cap": 5,
        "issued_at": (NOW - timedelta(minutes=1)).isoformat(),
        "expires_at": (NOW + timedelta(minutes=30)).isoformat(),
        "author": "runtime-owner",
        "reviewer": "independent-reviewer",
        "approval_mode": "INDEPENDENT_ED25519",
        "approval_key_id": "test-independent-key",
        "approval_public_key_sha256": PUBLIC_KEY_SHA256,
        "approval_custody_status": "INDEPENDENT_SIGNER_CONFIRMED",
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


def unsigned_authorization_payload(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "approval_mode": GATE_A_OWNER_APPROVAL_MODE,
        "owner_decision_issue": 454,
        "owner_decision_comment_id": 5155919529,
    }
    values.update(overrides)
    payload = authorization_payload(**values)
    for field in (
        "approval_key_id",
        "approval_public_key_sha256",
        "approval_custody_status",
        "approval_signature",
    ):
        if field not in overrides:
            payload.pop(field, None)
    return payload


def window_authorization(**overrides: object) -> GateARuntimeAuthorization:
    values: dict[str, object] = {
        "fixture_id": None,
        "fixture_scope_mode": "SIGNED_KICKOFF_WINDOW",
        "kickoff_window_start_utc": (NOW + timedelta(minutes=20)).isoformat(),
        "kickoff_window_end_utc": (NOW + timedelta(minutes=80)).isoformat(),
    }
    values.update(overrides)
    return runtime_authorization(**values)


def fixture_payload(
    fixture_id: int,
    *,
    kickoff: datetime,
    league: int = 1,
    season: int = 2026,
    status: str = "NS",
) -> dict[str, object]:
    return {
        "fixture": {
            "id": fixture_id,
            "date": kickoff.isoformat(),
            "status": {"short": status},
        },
        "league": {"id": league, "season": season},
        "teams": {"home": {"id": 10}, "away": {"id": 20}},
    }


def test_authorization_is_independent_scoped_short_lived_and_db_only() -> None:
    authorization = runtime_authorization()
    authorization.validate_scope(
        competition_id="world_cup_2026",
        season="2026",
        persistence="db",
        task_key=TASK_KEY,
        fixture_id="12345",
        exact_head=HEAD,
        exact_tree=TREE,
        execution_mode="COMPLETE_CLEAN_CHECKOUT",
        runtime_artifact_digest=None,
        complete_checkout_manifest_sha256="c" * 64,
        policy_season="2026",
        policy_provider_league_id="1",
        policy_config_hash="d" * 64,
        now=NOW,
    )

    failures = (
        ({"author": "same", "reviewer": "same"}, "GATE_A_INDEPENDENT_REVIEW_REQUIRED"),
        ({"one_shot": False}, "GATE_A_AUTHORIZATION_INVALID"),
        ({"persistence": "file"}, "GATE_A_AUTHORIZATION_INVALID"),
        ({"provider_call_cap": 4}, "GATE_A_PROVIDER_CALL_CAP_INVALID"),
        ({"allowed_endpoints": ["injuries"]}, "GATE_A_ENDPOINT_SCOPE_INVALID"),
    )
    for overrides, code in failures:
        with pytest.raises(GateAError, match=code):
            runtime_authorization(**overrides)
    with pytest.raises(GateAError, match="GATE_A_APPROVAL_SIGNATURE_INVALID"):
        runtime_authorization(approval_signature=b64encode(b"not-a-signature").decode())


def test_owner_approved_unsigned_authorization_needs_no_trust_store(tmp_path) -> None:
    path = tmp_path / "owner-authorization.json"
    path.write_text(json.dumps(unsigned_authorization_payload()), encoding="utf-8")

    authorization = GateARuntimeAuthorization.load(
        path,
        trust_store_path=tmp_path / "missing-trust-store.json",
    )

    assert authorization.approval_mode == GATE_A_OWNER_APPROVAL_MODE
    assert authorization.owner_decision_issue == 454
    assert authorization.owner_decision_comment_id == 5155919529
    assert authorization.approval_key_id is None


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"owner_decision_comment_id": 1}, "GATE_A_OWNER_DECISION_RECEIPT_INVALID"),
        ({"approval_signature": "not-used"}, "GATE_A_UNSIGNED_APPROVAL_CRYPTOGRAPHIC"),
    ],
)
def test_owner_approved_unsigned_authorization_rejects_wrong_receipt_or_signature(
    overrides: dict[str, object],
    error: str,
) -> None:
    payload = unsigned_authorization_payload(**overrides)
    with pytest.raises(GateAError, match=error):
        GateARuntimeAuthorization.from_mapping(payload)


def test_authorization_requires_independent_key_custody_and_supports_image_digest() -> None:
    pending = TrustedApprovalKey(
        public_key_base64=PUBLIC_KEY,
        public_key_sha256=PUBLIC_KEY_SHA256,
        custody_status="PENDING_INDEPENDENT_CUSTODY",
        authorization_enabled=True,
    )
    payload = authorization_payload(approval_custody_status="PENDING_INDEPENDENT_CUSTODY")
    with pytest.raises(GateAError, match="GATE_A_APPROVAL_KEY_CUSTODY_UNCONFIRMED"):
        GateARuntimeAuthorization.from_mapping(
            payload,
            trusted_public_keys={"test-independent-key": pending},
        )

    disabled = TrustedApprovalKey(
        public_key_base64=PUBLIC_KEY,
        public_key_sha256=PUBLIC_KEY_SHA256,
        custody_status="INDEPENDENT_SIGNER_CONFIRMED",
        authorization_enabled=False,
    )
    with pytest.raises(GateAError, match="GATE_A_APPROVAL_KEY_NOT_AUTHORIZATION_ENABLED"):
        GateARuntimeAuthorization.from_mapping(
            authorization_payload(),
            trusted_public_keys={"test-independent-key": disabled},
        )

    image = runtime_authorization(
        execution_mode="IMMUTABLE_IMAGE",
        complete_checkout_manifest_sha256=None,
        runtime_artifact_digest="sha256:" + "e" * 64,
    )
    assert image.runtime_artifact_digest == "sha256:" + "e" * 64


def test_window_authorization_and_selection_are_order_independent() -> None:
    authorization = window_authorization()
    later_low_id = fixture_payload(100, kickoff=NOW + timedelta(minutes=60))
    earlier_high_id = fixture_payload(200, kickoff=NOW + timedelta(minutes=40))
    same_earlier_low_id = fixture_payload(150, kickoff=NOW + timedelta(minutes=40))
    first = select_fixture_from_authorization(
        {"response": [later_low_id, earlier_high_id, same_earlier_low_id]},
        authorization,
    )
    second = select_fixture_from_authorization(
        {"response": [same_earlier_low_id, earlier_high_id, later_low_id]},
        authorization,
    )
    assert first.selected_fixture_id == second.selected_fixture_id == "150"
    assert first.candidate_set_sha256 == second.candidate_set_sha256
    assert first.eligible_candidate_count == 3


@pytest.mark.parametrize(
    "candidate",
    [
        fixture_payload(100, kickoff=NOW + timedelta(minutes=40), league=2),
        fixture_payload(100, kickoff=NOW + timedelta(minutes=40), season=2027),
        fixture_payload(100, kickoff=NOW + timedelta(minutes=90)),
    ],
)
def test_window_selection_rejects_out_of_scope_candidates(candidate: dict[str, object]) -> None:
    with pytest.raises(GateAError, match="GATE_A_NO_ELIGIBLE_FIXTURE_IN_SIGNED_WINDOW"):
        select_fixture_from_authorization({"response": [candidate]}, window_authorization())


def test_window_selection_rejects_conflicting_duplicate_fixture() -> None:
    first = fixture_payload(100, kickoff=NOW + timedelta(minutes=40))
    conflicting = fixture_payload(100, kickoff=NOW + timedelta(minutes=50))
    with pytest.raises(GateAError, match="GATE_A_FIXTURE_CANDIDATE_CONFLICT"):
        select_fixture_from_authorization(
            {"response": [first, conflicting]},
            window_authorization(),
        )


def test_window_selection_deduplicates_identical_fixture_payload() -> None:
    candidate = fixture_payload(100, kickoff=NOW + timedelta(minutes=40))
    selection = select_fixture_from_authorization(
        {"response": [candidate, candidate]},
        window_authorization(),
    )
    assert selection.eligible_candidate_count == 1


def test_window_authorization_rejects_overlong_window() -> None:
    with pytest.raises(GateAError, match="GATE_A_KICKOFF_WINDOW_INVALID"):
        window_authorization(kickoff_window_end_utc=(NOW + timedelta(minutes=141)).isoformat())


def test_window_authorization_requires_explicit_utc_offsets() -> None:
    with pytest.raises(GateAError, match="GATE_A_KICKOFF_WINDOW_INVALID"):
        window_authorization(
            kickoff_window_start_utc="2026-08-01T20:20:00+08:00",
            kickoff_window_end_utc="2026-08-01T21:20:00+08:00",
        )


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("competition_id", "other", "GATE_A_COMPETITION_SCOPE_MISMATCH"),
        ("season", "2027", "GATE_A_SEASON_SCOPE_MISMATCH"),
        ("persistence", "file", "GATE_A_DB_PERSISTENCE_REQUIRED"),
        ("task_key", "other", "GATE_A_TASK_KEY_SCOPE_MISMATCH"),
        ("fixture_id", "other", "GATE_A_FIXTURE_SCOPE_MISMATCH"),
        ("exact_head", "b" * 40, "GATE_A_EXACT_HEAD_MISMATCH"),
        ("exact_tree", "c" * 40, "GATE_A_EXACT_TREE_MISMATCH"),
        ("execution_mode", "IMMUTABLE_IMAGE", "GATE_A_EXECUTION_MODE_MISMATCH"),
        (
            "complete_checkout_manifest_sha256",
            "d" * 64,
            "GATE_A_CHECKOUT_MANIFEST_MISMATCH",
        ),
        ("policy_season", "2027", "GATE_A_POLICY_SEASON_MISMATCH"),
        (
            "policy_provider_league_id",
            "2",
            "GATE_A_POLICY_PROVIDER_LEAGUE_MISMATCH",
        ),
        ("policy_config_hash", "e" * 64, "GATE_A_POLICY_CONFIG_HASH_MISMATCH"),
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
        "fixture_id": "12345",
        "exact_head": HEAD,
        "exact_tree": TREE,
        "execution_mode": "COMPLETE_CLEAN_CHECKOUT",
        "runtime_artifact_digest": None,
        "complete_checkout_manifest_sha256": "c" * 64,
        "policy_season": "2026",
        "policy_provider_league_id": "1",
        "policy_config_hash": "d" * 64,
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
    authorization = runtime_authorization()

    reservation = reserve_gate_a_run(authorization, owner="foreground", now=NOW)
    assert reservation.reserve_provider_call("status") == 1
    reservation.record_provider_outcome(1, state="RESPONSE_RECEIVED")
    assert reservation.reserve_provider_call("fixtures") == 2
    reservation.record_provider_outcome(
        2,
        state="DELIVERY_UNCERTAIN",
        error_code="TimeoutError",
    )
    reservation.bind_selected_fixture(
        fixture_id="12345",
        candidate_set_sha256="e" * 64,
        discovery_capture_id="capture-fixtures",
        eligible_candidate_count=1,
        selected_at=NOW,
    )
    for endpoint in ("odds", "lineups", "odds"):
        ordinal = reservation.reserve_provider_call(endpoint, fixture_id="12345")
        reservation.record_provider_outcome(ordinal, state="RESPONSE_RECEIVED")
    with pytest.raises(GateAError, match="GATE_A_PROVIDER_CALL_RESERVATION_REJECTED"):
        reservation.reserve_provider_call("odds", fixture_id="12345")
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
        provider_call_cap=5,
        fixture_scope_mode="EXACT_FIXTURE_ID",
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
        5,
        "odds",
    )
    assert [(call.endpoint, call.state, call.error_code) for call in calls] == [
        ("status", "RESPONSE_RECEIVED", None),
        ("fixtures", "DELIVERY_UNCERTAIN", "TimeoutError"),
        ("odds", "RESPONSE_RECEIVED", None),
        ("lineups", "RESPONSE_RECEIVED", None),
        ("odds", "RESPONSE_RECEIVED", None),
    ]
    get_settings.cache_clear()


def test_window_reservation_blocks_fixture_calls_until_one_atomic_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'window-binding.db'}"
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    get_settings.cache_clear()
    Base.metadata.create_all(create_engine(database_url))
    reservation = reserve_gate_a_run(window_authorization(), owner="foreground", now=NOW)
    status = reservation.reserve_provider_call("status")
    reservation.record_provider_outcome(status, state="RESPONSE_RECEIVED")
    fixtures = reservation.reserve_provider_call("fixtures")
    reservation.record_provider_outcome(fixtures, state="RESPONSE_RECEIVED")
    with pytest.raises(GateAError, match="GATE_A_PROVIDER_CALL_RESERVATION_REJECTED"):
        reservation.reserve_provider_call("odds", fixture_id="100")
    reservation.bind_selected_fixture(
        fixture_id="100",
        candidate_set_sha256="e" * 64,
        discovery_capture_id="capture-fixtures",
        eligible_candidate_count=2,
        selected_at=NOW,
    )
    with pytest.raises(GateAError, match="GATE_A_FIXTURE_BINDING_FAILED"):
        reservation.bind_selected_fixture(
            fixture_id="101",
            candidate_set_sha256="f" * 64,
            discovery_capture_id="capture-other",
            eligible_candidate_count=1,
            selected_at=NOW,
        )
    with pytest.raises(GateAError, match="GATE_A_PROVIDER_CALL_RESERVATION_REJECTED"):
        reservation.reserve_provider_call("odds", fixture_id="101")
    assert reservation.reserve_provider_call("odds", fixture_id="100") == 3
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


def test_postgres_runtime_fixture_binding_has_one_atomic_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = os.environ.get("W2_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("W2_TEST_POSTGRES_URL is required for fixture binding fencing")
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.execute(delete(GateAProviderCallModel))
        session.execute(delete(GateARunReservationModel))
        session.commit()
    reservation = reserve_gate_a_run(window_authorization(), owner="foreground", now=NOW)
    for endpoint in ("status", "fixtures"):
        ordinal = reservation.reserve_provider_call(endpoint)
        reservation.record_provider_outcome(ordinal, state="RESPONSE_RECEIVED")
    barrier = Barrier(2)

    def bind(fixture_id: str) -> str:
        barrier.wait()
        try:
            reservation.bind_selected_fixture(
                fixture_id=fixture_id,
                candidate_set_sha256=("e" if fixture_id == "100" else "f") * 64,
                discovery_capture_id="capture-fixtures",
                eligible_candidate_count=2,
                selected_at=NOW,
            )
        except GateAError as exc:
            return str(exc)
        return f"WINNER:{fixture_id}"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(bind, ("100", "101")))

    assert sum(result.startswith("WINNER:") for result in results) == 1
    assert results.count("GATE_A_FIXTURE_BINDING_FAILED") == 1
    with Session(engine) as session:
        stored = session.get(GateARunReservationModel, reservation.lease_epoch)
    assert stored is not None
    assert f"WINNER:{stored.selected_fixture_id}" in results
    get_settings.cache_clear()
