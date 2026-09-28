"""F1R-B: the database sink for forward AH factor observations.

Same contract as the accepted JSONL ledger, different medium. The rules that
matter are the ones the file ledger already proved and this one has to keep:

* **All four or none.** The whole batch is validated, conflict-checked and
  staged before anything is committed; the transaction is the commit point, so
  a refusal or a failure part way through adds zero rows.
* **Append-only.** A stored row is never updated or deleted. A correction is a
  new observation that points at the one it supersedes.
* **Idempotent, not lenient.** Re-appending an identical observation is a
  no-op. Re-appending the same observation_id with different business fields is
  a conflict, and conflicts refuse the batch.

Timestamps are stored as aware UTC instants and numbers as the canonical
decimal text the identity was hashed over, so a readback reproduces the exact
payload the hash was computed from.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence import (
    ForwardAhFactorObservationModel,
    TeamXgRollingSnapshotModel,
)
from w2.infrastructure.persistence.factor_model_models import CanonicalTeamMatchHistoryModel

_HERE = Path(__file__).resolve().parent


def _load(module_name: str, filename: str) -> Any:
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, _HERE / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


recorder = _load("w2_f1r_a0_offline_factor_recorder", "f1r_a0_offline_factor_recorder.py")
contract = recorder.contract

_TIMESTAMPS = ("evidence_time_utc", "evaluated_at_utc", "created_at_utc")


class StoreError(recorder.BatchError):
    """A batch-level refusal from the store. Nothing is written when raised."""


def batch_key(payload: dict[str, Any]) -> str:
    return "|".join((
        payload["evaluation_id"], payload["attempt_id"],
        payload["fixture_id"], payload["evaluated_at_utc"],
    ))


def _to_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = {
        name: payload[name] for name in (
            "observation_id", "schema_version", "record_kind", "evaluation_id",
            "attempt_id", "fixture_id", "market", "factor_id", "factor_version",
            "factor_status", "participated", "applied_weight", "signed_score",
            "factor_inputs", "source_capture_id", "source_capture_sha256",
            "source_version", "factor_input_hash", "factor_verdict_hash",
            "supersedes_observation_id", "revision_reason",
        )
    }
    row["batch_key"] = batch_key(payload)
    for name in _TIMESTAMPS:
        row[name] = contract.parse_aware_utc(payload[name], field_name=name)
    return row


def _from_row(model: ForwardAhFactorObservationModel) -> dict[str, Any]:
    payload: dict[str, Any] = {
        name: getattr(model, name) for name in (
            "observation_id", "schema_version", "record_kind", "evaluation_id",
            "attempt_id", "fixture_id", "market", "factor_id", "factor_version",
            "factor_status", "participated", "applied_weight", "signed_score",
            "factor_inputs", "source_capture_id", "source_capture_sha256",
            "source_version", "factor_input_hash", "factor_verdict_hash",
            "supersedes_observation_id", "revision_reason",
        )
    }
    for name in _TIMESTAMPS:
        value = getattr(model, name)
        # SQLite hands back naive datetimes; the column is declared timezone
        # aware and every write was UTC, so re-attaching UTC restores the exact
        # instant rather than guessing one.
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        payload[name] = value.astimezone(UTC).isoformat()
    return payload


class ForwardFactorObservationStore:
    """Append-only store over `forward_ah_factor_observations`."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def by_id(self) -> dict[str, dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(ForwardAhFactorObservationModel).order_by(
                    ForwardAhFactorObservationModel.observation_id
                )
            )
            return {model.observation_id: _from_row(model) for model in rows}

    def append_batch(self, batch: list[Any]) -> dict[str, Any]:
        """All four or none. The transaction is the commit point."""
        sealed = [contract.validate(record) for record in batch]
        recorder._batch_coherence(sealed)

        existing = self.by_id()
        to_write: list[dict[str, Any]] = []
        staged_ids: set[str] = set()
        idempotent = 0
        for record in sealed:
            payload = contract.as_dict(record)
            observation_id = record.observation_id or ""
            stored = existing.get(observation_id)
            if stored is not None:
                differing = sorted(
                    name for name in contract.BUSINESS_FIELDS
                    if stored.get(name) != payload.get(name))
                if differing:
                    raise StoreError(
                        "OBSERVATION_ID_BUSINESS_CONFLICT", ",".join(differing))
                idempotent += 1
                continue
            if record.supersedes_observation_id is not None:
                target = record.supersedes_observation_id
                if target not in existing and target not in staged_ids:
                    raise StoreError("SUPERSEDES_TARGET_NOT_FOUND", target)
                if record.revision_reason is None:
                    raise StoreError("REVISION_REASON_MISSING", target)
                self._assert_no_cycle(observation_id, target, existing)
            staged_ids.add(observation_id)
            to_write.append(payload)

        if to_write:
            with Session(self.engine) as session:
                with session.begin():           # <- commit point
                    self._assert_source_capture_ids_self_consistent(session, to_write)
                    for payload in to_write:
                        session.add(ForwardAhFactorObservationModel(**_to_row(payload)))
        return {
            "observation_ids": [record.observation_id for record in sealed],
            "appended": len(to_write),
            "idempotent_no_ops": idempotent,
            "batch_size": len(sealed),
        }

    @staticmethod
    def _assert_source_capture_ids_self_consistent(
        session: Session,
        payloads: list[dict[str, Any]],
    ) -> None:
        """Cross-table reference check (task 9 #1, option ① + 整改 item 4).

        ``source_capture_sha256`` stays a contract-level ``require_hex64`` check
        (its target ``raw_payload_sha256`` is non-unique, so no DB FK is
        possible). The capture the observation cites is verified in two layers:

        * *self-consistency*: ``source_capture_id`` is a content address of the
          consumed source set, so it must re-derive from
          ``factor_inputs.source_record_ids``.
        * *existence*: every cited ``source_record_id`` must resolve to a real
          source row (canonical match history or rolling xG snapshot). A forged
          id, a dropped record, a reordered/edited set, or a dangling record id
          all refuse the batch.
        """
        all_record_ids: set[str] = set()
        for payload in payloads:
            scid = str(payload["source_capture_id"])
            for prefix in ("w2.consumed_source_set.v1", "w2.synthetic_source_set.v1"):
                if scid.startswith(prefix + ":"):
                    digest = scid[len(prefix) + 1:]
                    contract.require_hex64(digest, field_name="source_capture_id.digest")
                    record_ids_text = (payload["factor_inputs"] or {}).get(
                        "source_record_ids"
                    )
                    if not record_ids_text:
                        raise StoreError("SOURCE_RECORD_IDS_MISSING", payload["factor_id"])
                    record_ids = [
                        rid for rid in str(record_ids_text).split(",") if rid
                    ]
                    expected = contract.canonical_sha256(
                        {
                            "contract": "w2.f1r_b_source_capture.v1",
                            "factor_id": payload["factor_id"],
                            "record_ids": sorted(record_ids),
                        },
                        domain=contract.HASH_DOMAIN,
                    )
                    if digest != expected:
                        raise StoreError("SOURCE_CAPTURE_ID_MISMATCH", payload["factor_id"])
                    all_record_ids.update(record_ids)
                    break
            else:
                raise StoreError("SOURCE_CAPTURE_ID_FORMAT_INVALID", scid)

        if all_record_ids:
            _assert_source_records_exist(session, all_record_ids)

    @staticmethod
    def _assert_no_cycle(
        observation_id: str, target: str, existing: dict[str, dict[str, Any]]
    ) -> None:
        seen = {observation_id}
        cursor: str | None = target
        while cursor is not None:
            if cursor in seen:
                raise StoreError("SUPERSEDES_CYCLE", cursor)
            seen.add(cursor)
            stored = existing.get(cursor)
            cursor = stored.get("supersedes_observation_id") if stored else None


def _assert_source_records_exist(session: Session, record_ids: set[str]) -> None:
    """Every cited source record must resolve to a real, complete source row.

    The consumed source set spans the canonical match history (F6) and the
    rolling xG snapshot (F9). Beyond id existence, each row must carry its
    capture hash and its content fields, so a record that exists but was
    truncated or stripped of provenance is refused too (整改 item 6).
    """
    if not record_ids:
        return
    history_rows = list(
        session.scalars(
            select(CanonicalTeamMatchHistoryModel).where(
                CanonicalTeamMatchHistoryModel.history_id.in_(record_ids)
            )
        )
    )
    snapshot_rows = list(
        session.scalars(
            select(TeamXgRollingSnapshotModel).where(
                TeamXgRollingSnapshotModel.snapshot_id.in_(record_ids)
            )
        )
    )
    found = {row.history_id for row in history_rows} | {
        row.snapshot_id for row in snapshot_rows
    }
    missing = sorted(record_ids - found)
    if missing:
        raise StoreError("SOURCE_RECORD_NOT_FOUND", ",".join(missing))
    for row in history_rows:
        if not row.history_hash or not row.source_raw_hash:
            raise StoreError("SOURCE_RECORD_PROVENANCE_INCOMPLETE", row.history_id)
        if row.goals_for is None or row.goals_against is None or not row.team_side:
            raise StoreError("SOURCE_RECORD_CONTENT_INCOMPLETE", row.history_id)
    for row in snapshot_rows:
        if row.rolling_xg_for is None or row.rolling_xg_against is None:
            raise StoreError("SOURCE_RECORD_CONTENT_INCOMPLETE", row.snapshot_id)


def utc_now() -> datetime:
    return datetime.now(UTC)
