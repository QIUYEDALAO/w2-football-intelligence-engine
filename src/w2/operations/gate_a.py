from __future__ import annotations

import hashlib
import json
import re
from base64 import b64decode
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.future_refresh_models import (
    GateAProviderCallModel,
    GateARunReservationModel,
)

GATE_A_AUTHORIZATION_SCHEMA = "w2.gate-a-one-shot-authorization.v3"
GATE_A_ACTION = "ONE_SHOT_FOREGROUND_CANARY"
GATE_A_CANARY_ENDPOINTS = frozenset({"status", "fixtures", "odds", "lineups"})
GATE_A_CANARY_PROVIDER_CALL_CAP = 5
GATE_A_TRUST_STORE_SCHEMA = "w2.gate-a-authorization-trust.v1"
DEFAULT_TRUST_STORE = (
    Path(__file__).resolve().parents[3] / "config/policies/gate_a_authorization_trust.v1.json"
)


class GateAError(RuntimeError):
    pass


@dataclass(frozen=True, kw_only=True)
class GateARuntimeAuthorization:
    authorization_id: str
    task_key: str
    fixture_id: str
    competition_id: str
    season: str
    persistence: str
    exact_head: str
    exact_tree: str
    execution_mode: str
    runtime_artifact_digest: str | None
    complete_checkout_manifest_sha256: str | None
    allowed_endpoints: frozenset[str]
    provider_call_cap: int
    issued_at: datetime
    expires_at: datetime
    author: str
    reviewer: str
    approval_key_id: str
    approval_public_key_sha256: str
    approval_custody_status: str

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        trust_store_path: Path = DEFAULT_TRUST_STORE,
    ) -> GateARuntimeAuthorization:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GateAError("GATE_A_AUTHORIZATION_UNREADABLE") from exc
        if not isinstance(payload, dict):
            raise GateAError("GATE_A_AUTHORIZATION_INVALID")
        return cls.from_mapping(payload, trusted_public_keys=_load_trusted_keys(trust_store_path))

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        trusted_public_keys: Mapping[str, TrustedApprovalKey] | None = None,
    ) -> GateARuntimeAuthorization:
        required = {
            "authorization_id",
            "task_key",
            "fixture_id",
            "competition_id",
            "season",
            "exact_head",
            "exact_tree",
            "execution_mode",
            "allowed_endpoints",
            "provider_call_cap",
            "issued_at",
            "expires_at",
            "author",
            "reviewer",
            "approval_key_id",
            "approval_public_key_sha256",
            "approval_custody_status",
            "approval_signature",
        }
        if (
            payload.get("schema_version") != GATE_A_AUTHORIZATION_SCHEMA
            or payload.get("action") != GATE_A_ACTION
            or payload.get("review_status") != "APPROVED"
            or payload.get("one_shot") is not True
            or payload.get("persistence") != "db"
            or not required.issubset(payload)
        ):
            raise GateAError("GATE_A_AUTHORIZATION_INVALID")
        author = str(payload["author"]).strip()
        reviewer = str(payload["reviewer"]).strip()
        if not author or not reviewer or author == reviewer:
            raise GateAError("GATE_A_INDEPENDENT_REVIEW_REQUIRED")
        authorization_id = str(payload["authorization_id"]).strip()
        task_key = str(payload["task_key"]).strip()
        fixture_id = str(payload["fixture_id"]).strip()
        exact_head = str(payload["exact_head"]).strip()
        exact_tree = str(payload["exact_tree"]).strip()
        execution_mode = str(payload["execution_mode"]).strip()
        runtime_artifact_digest = _optional_str(payload.get("runtime_artifact_digest"))
        checkout_manifest = _optional_str(payload.get("complete_checkout_manifest_sha256"))
        raw_endpoints = payload["allowed_endpoints"]
        if (
            not authorization_id
            or len(authorization_id) > 128
            or not task_key
            or len(task_key) > 255
            or not fixture_id
            or len(fixture_id) > 128
            or re.fullmatch(r"[0-9a-f]{40}", exact_head) is None
            or re.fullmatch(r"[0-9a-f]{40}", exact_tree) is None
            or not isinstance(raw_endpoints, list)
        ):
            raise GateAError("GATE_A_AUTHORIZATION_INVALID")
        if execution_mode == "IMMUTABLE_IMAGE":
            if (
                runtime_artifact_digest is None
                or re.fullmatch(r"sha256:[0-9a-f]{64}", runtime_artifact_digest) is None
                or checkout_manifest is not None
            ):
                raise GateAError("GATE_A_RUNTIME_ARTIFACT_IDENTITY_INVALID")
        elif execution_mode == "COMPLETE_CLEAN_CHECKOUT":
            if (
                checkout_manifest is None
                or re.fullmatch(r"[0-9a-f]{64}", checkout_manifest) is None
                or runtime_artifact_digest is not None
            ):
                raise GateAError("GATE_A_RUNTIME_ARTIFACT_IDENTITY_INVALID")
        else:
            raise GateAError("GATE_A_EXECUTION_MODE_INVALID")
        endpoints = frozenset(str(value) for value in raw_endpoints)
        if endpoints != GATE_A_CANARY_ENDPOINTS or len(raw_endpoints) != len(endpoints):
            raise GateAError("GATE_A_ENDPOINT_SCOPE_INVALID")
        try:
            cap = int(payload["provider_call_cap"])
        except (TypeError, ValueError) as exc:
            raise GateAError("GATE_A_PROVIDER_CALL_CAP_INVALID") from exc
        if cap != GATE_A_CANARY_PROVIDER_CALL_CAP:
            raise GateAError("GATE_A_PROVIDER_CALL_CAP_INVALID")
        issued_at = _aware_utc(payload["issued_at"])
        expires_at = _aware_utc(payload["expires_at"])
        if expires_at <= issued_at or expires_at - issued_at > timedelta(hours=1):
            raise GateAError("GATE_A_AUTHORIZATION_WINDOW_INVALID")
        approval_key_id = str(payload["approval_key_id"]).strip()
        _verify_approval_signature(
            payload,
            key_id=approval_key_id,
            trusted_public_keys=(
                trusted_public_keys
                if trusted_public_keys is not None
                else _load_trusted_keys(DEFAULT_TRUST_STORE)
            ),
        )
        return cls(
            authorization_id=authorization_id,
            task_key=task_key,
            fixture_id=fixture_id,
            competition_id=str(payload["competition_id"]),
            season=str(payload["season"]),
            persistence="db",
            exact_head=exact_head,
            exact_tree=exact_tree,
            execution_mode=execution_mode,
            runtime_artifact_digest=runtime_artifact_digest,
            complete_checkout_manifest_sha256=checkout_manifest,
            allowed_endpoints=endpoints,
            provider_call_cap=cap,
            issued_at=issued_at,
            expires_at=expires_at,
            author=author,
            reviewer=reviewer,
            approval_key_id=approval_key_id,
            approval_public_key_sha256=str(payload["approval_public_key_sha256"]),
            approval_custody_status=str(payload["approval_custody_status"]),
        )

    def validate_scope(
        self,
        *,
        competition_id: str,
        season: str,
        persistence: str,
        task_key: str,
        fixture_id: str,
        exact_head: str,
        exact_tree: str,
        execution_mode: str,
        runtime_artifact_digest: str | None,
        complete_checkout_manifest_sha256: str | None,
        policy_season: str,
        now: datetime,
    ) -> None:
        current = _aware_utc(now)
        if current < self.issued_at or current > self.expires_at:
            raise GateAError("GATE_A_AUTHORIZATION_EXPIRED")
        if competition_id != self.competition_id:
            raise GateAError("GATE_A_COMPETITION_SCOPE_MISMATCH")
        if season != self.season:
            raise GateAError("GATE_A_SEASON_SCOPE_MISMATCH")
        if policy_season != season or policy_season != self.season:
            raise GateAError("GATE_A_POLICY_SEASON_MISMATCH")
        if persistence != "db":
            raise GateAError("GATE_A_DB_PERSISTENCE_REQUIRED")
        if task_key != self.task_key:
            raise GateAError("GATE_A_TASK_KEY_SCOPE_MISMATCH")
        if fixture_id != self.fixture_id:
            raise GateAError("GATE_A_FIXTURE_SCOPE_MISMATCH")
        if exact_head != self.exact_head:
            raise GateAError("GATE_A_EXACT_HEAD_MISMATCH")
        if exact_tree != self.exact_tree:
            raise GateAError("GATE_A_EXACT_TREE_MISMATCH")
        if execution_mode != self.execution_mode:
            raise GateAError("GATE_A_EXECUTION_MODE_MISMATCH")
        if runtime_artifact_digest != self.runtime_artifact_digest:
            raise GateAError("GATE_A_RUNTIME_ARTIFACT_DIGEST_MISMATCH")
        if complete_checkout_manifest_sha256 != self.complete_checkout_manifest_sha256:
            raise GateAError("GATE_A_CHECKOUT_MANIFEST_MISMATCH")


@dataclass(frozen=True, kw_only=True)
class GateARunReservation:
    authorization_id: str
    task_key: str
    owner: str
    lease_epoch: int
    provider_call_cap: int

    def reserve_provider_call(self, endpoint: str) -> int:
        engine = create_engine()
        with Session(engine) as session:
            result = session.execute(
                update(GateARunReservationModel)
                .where(
                    GateARunReservationModel.lease_epoch == self.lease_epoch,
                    GateARunReservationModel.authorization_id == self.authorization_id,
                    GateARunReservationModel.owner == self.owner,
                    GateARunReservationModel.status == "RESERVED",
                    GateARunReservationModel.provider_calls_used
                    < GateARunReservationModel.provider_call_cap,
                )
                .values(
                    provider_calls_used=GateARunReservationModel.provider_calls_used + 1,
                    last_endpoint=endpoint,
                )
            )
            if getattr(result, "rowcount", 0) != 1:
                session.rollback()
                raise GateAError("GATE_A_PROVIDER_CALL_RESERVATION_REJECTED")
            row = session.get(GateARunReservationModel, self.lease_epoch)
            assert row is not None
            ordinal = row.provider_calls_used
            session.add(
                GateAProviderCallModel(
                    lease_epoch=self.lease_epoch,
                    call_ordinal=ordinal,
                    endpoint=endpoint,
                    state="RESERVED_BEFORE_DISPATCH",
                    reserved_at=datetime.now(UTC),
                )
            )
            session.commit()
        return ordinal

    def record_provider_outcome(
        self,
        ordinal: int,
        *,
        state: str,
        error_code: str | None = None,
    ) -> None:
        if state not in {"RESPONSE_RECEIVED", "DELIVERY_UNCERTAIN"}:
            raise GateAError("GATE_A_PROVIDER_OUTCOME_INVALID")
        engine = create_engine()
        with Session(engine) as session:
            result = session.execute(
                update(GateAProviderCallModel)
                .where(
                    GateAProviderCallModel.lease_epoch == self.lease_epoch,
                    GateAProviderCallModel.call_ordinal == ordinal,
                    GateAProviderCallModel.state == "RESERVED_BEFORE_DISPATCH",
                )
                .values(
                    state=state,
                    finished_at=datetime.now(UTC),
                    error_code=error_code,
                )
            )
            if getattr(result, "rowcount", 0) != 1:
                session.rollback()
                raise GateAError("GATE_A_PROVIDER_OUTCOME_WRITE_FAILED")
            session.commit()

    def finalize(self, status: str) -> None:
        engine = create_engine()
        with Session(engine) as session:
            result = session.execute(
                update(GateARunReservationModel)
                .where(
                    GateARunReservationModel.lease_epoch == self.lease_epoch,
                    GateARunReservationModel.authorization_id == self.authorization_id,
                    GateARunReservationModel.owner == self.owner,
                    GateARunReservationModel.status == "RESERVED",
                )
                .values(status=status, finished_at=datetime.now(UTC))
            )
            if getattr(result, "rowcount", 0) != 1:
                session.rollback()
                raise GateAError("GATE_A_LEASE_EPOCH_REJECTED")
            session.commit()


def reserve_gate_a_run(
    authorization: GateARuntimeAuthorization,
    *,
    owner: str,
    now: datetime,
) -> GateARunReservation:
    engine = create_engine()
    from w2.operations.gate_a_evidence_producer import (  # noqa: PLC0415
        capture_gate_a_evidence_baseline,
    )

    evidence_baseline = capture_gate_a_evidence_baseline(engine, authorization)
    with Session(engine) as session:
        row = GateARunReservationModel(
            authorization_id=authorization.authorization_id,
            task_key=authorization.task_key,
            fixture_id=authorization.fixture_id,
            competition_id=authorization.competition_id,
            season=authorization.season,
            exact_head=authorization.exact_head,
            exact_tree=authorization.exact_tree,
            execution_mode=authorization.execution_mode,
            runtime_artifact_digest=authorization.runtime_artifact_digest,
            complete_checkout_manifest_sha256=authorization.complete_checkout_manifest_sha256,
            evidence_baseline=evidence_baseline,
            owner=owner,
            reserved_at=_aware_utc(now),
            status="RESERVED",
            provider_call_cap=authorization.provider_call_cap,
            provider_calls_used=0,
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = session.scalar(
                select(GateARunReservationModel.lease_epoch).where(
                    GateARunReservationModel.authorization_id == authorization.authorization_id
                )
            )
            active_task = session.scalar(
                select(GateARunReservationModel.lease_epoch).where(
                    GateARunReservationModel.task_key == authorization.task_key,
                    GateARunReservationModel.status == "RESERVED",
                )
            )
            code = (
                "GATE_A_AUTHORIZATION_ALREADY_CONSUMED"
                if existing is not None
                else (
                    "GATE_A_TASK_ALREADY_RESERVED"
                    if active_task is not None
                    else "GATE_A_RESERVATION_WRITE_FAILED"
                )
            )
            raise GateAError(code) from None
        session.refresh(row)
        lease_epoch = row.lease_epoch
    return GateARunReservation(
        authorization_id=authorization.authorization_id,
        task_key=authorization.task_key,
        owner=owner,
        lease_epoch=lease_epoch,
        provider_call_cap=authorization.provider_call_cap,
    )


@dataclass(frozen=True)
class TrustedApprovalKey:
    public_key_base64: str
    public_key_sha256: str
    custody_status: str
    authorization_enabled: bool


def _load_trusted_keys(path: Path) -> dict[str, TrustedApprovalKey]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateAError("GATE_A_TRUST_STORE_UNAVAILABLE") from exc
    keys = payload.get("trusted_ed25519_keys") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != GATE_A_TRUST_STORE_SCHEMA
        or not isinstance(keys, dict)
    ):
        raise GateAError("GATE_A_TRUST_STORE_INVALID")
    resolved: dict[str, TrustedApprovalKey] = {}
    for key_id, value in keys.items():
        if not key_id or not isinstance(value, Mapping):
            raise GateAError("GATE_A_TRUST_STORE_INVALID")
        encoded = str(value.get("public_key_base64") or "")
        fingerprint = str(value.get("public_key_sha256") or "")
        custody = str(value.get("custody_status") or "")
        enabled = value.get("authorization_enabled") is True
        try:
            raw_key = b64decode(encoded, validate=True)
        except ValueError as exc:
            raise GateAError("GATE_A_TRUST_STORE_INVALID") from exc
        if len(raw_key) != 32 or fingerprint != hashlib.sha256(raw_key).hexdigest() or not custody:
            raise GateAError("GATE_A_TRUST_STORE_INVALID")
        resolved[str(key_id)] = TrustedApprovalKey(
            public_key_base64=encoded,
            public_key_sha256=fingerprint,
            custody_status=custody,
            authorization_enabled=enabled,
        )
    if not resolved:
        raise GateAError("GATE_A_TRUST_STORE_INVALID")
    return resolved


def _verify_approval_signature(
    payload: Mapping[str, Any],
    *,
    key_id: str,
    trusted_public_keys: Mapping[str, TrustedApprovalKey],
) -> None:
    configured = trusted_public_keys.get(key_id)
    if not key_id or configured is None:
        raise GateAError("GATE_A_APPROVAL_KEY_UNTRUSTED")
    if not configured.authorization_enabled:
        raise GateAError("GATE_A_APPROVAL_KEY_NOT_AUTHORIZATION_ENABLED")
    if configured.custody_status != "INDEPENDENT_SIGNER_CONFIRMED":
        raise GateAError("GATE_A_APPROVAL_KEY_CUSTODY_UNCONFIRMED")
    if (
        payload.get("approval_public_key_sha256") != configured.public_key_sha256
        or payload.get("approval_custody_status") != configured.custody_status
    ):
        raise GateAError("GATE_A_APPROVAL_KEY_METADATA_MISMATCH")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            b64decode(configured.public_key_base64, validate=True)
        )
        signature = b64decode(str(payload["approval_signature"]), validate=True)
        public_key.verify(signature, authorization_signing_message(payload))
    except (InvalidSignature, TypeError, ValueError) as exc:
        raise GateAError("GATE_A_APPROVAL_SIGNATURE_INVALID") from exc


def authorization_signing_message(payload: Mapping[str, Any]) -> bytes:
    endpoints = payload.get("allowed_endpoints")
    if not isinstance(endpoints, list) or not all(isinstance(item, str) for item in endpoints):
        raise GateAError("GATE_A_AUTHORIZATION_INVALID")
    values = (
        payload.get("schema_version"),
        payload.get("action"),
        payload.get("review_status"),
        "true" if payload.get("one_shot") is True else "false",
        payload.get("authorization_id"),
        payload.get("task_key"),
        payload.get("fixture_id"),
        payload.get("competition_id"),
        payload.get("season"),
        payload.get("persistence"),
        payload.get("exact_head"),
        payload.get("exact_tree"),
        payload.get("execution_mode"),
        payload.get("runtime_artifact_digest"),
        payload.get("complete_checkout_manifest_sha256"),
        ",".join(sorted(endpoints)),
        payload.get("provider_call_cap"),
        payload.get("issued_at"),
        payload.get("expires_at"),
        payload.get("author"),
        payload.get("reviewer"),
        payload.get("approval_key_id"),
        payload.get("approval_public_key_sha256"),
        payload.get("approval_custody_status"),
    )
    message = bytearray(b"W2_GATE_A_AUTHORIZATION_V3")
    for value in values:
        encoded = str(value).encode("utf-8")
        message.extend(len(encoded).to_bytes(4, "big"))
        message.extend(encoded)
    return bytes(message)


def _aware_utc(value: Any) -> datetime:
    try:
        parsed = (
            value
            if isinstance(value, datetime)
            else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        )
    except (TypeError, ValueError) as exc:
        raise GateAError("GATE_A_AUTHORIZATION_TIME_INVALID") from exc
    if parsed.tzinfo is None:
        raise GateAError("GATE_A_AUTHORIZATION_TIME_INVALID")
    return parsed.astimezone(UTC)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
