from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import (
    HashDomain,
    SerializerVersion,
    canonical_sha256,
)
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayEndpointCaptureModel,
    MatchdayFixtureIdentityModel,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.infrastructure.persistence.outcome_ledger_models import OutcomeLedgerModel

IMPORT_CONFIRMATION_PHRASE = "EVAL_01A_IMPORT_RUNTIME_LEDGER"  # noqa: S105
TERMINAL_STATUSES = {"FT", "AET", "PEN"}
RUNTIME_LEDGER_SOURCE = "db:forward_outcome_ledger"
CURRENT_FORWARD_RECORD_TYPES = frozenset({"capture", "outcome", "supersession"})


class OutcomeLedgerError(ValueError):
    pass


class FixtureIdentityConflict(ValueError):
    pass


class ExactFixtureResolver:
    """Resolve only canonical IDs and the exact API-Football numeric namespace."""

    def __init__(self, rows: Iterable[MatchdayFixtureIdentityModel]) -> None:
        aliases: dict[str, set[str]] = {}
        for row in rows:
            canonical = str(row.fixture_id)
            provider = str(row.provider_fixture_id)
            aliases.setdefault(canonical, set()).add(canonical)
            aliases.setdefault(provider, set()).add(canonical)
            aliases.setdefault(f"api_football:{provider}", set()).add(canonical)
        self._aliases = aliases

    def candidates(self, value: str) -> frozenset[str]:
        text = str(value).strip()
        if not text:
            return frozenset()
        bare = text.removeprefix("api_football:")
        return frozenset(
            self._aliases.get(text, set()) | self._aliases.get(bare, set())
        )

    def resolve(self, value: str) -> str | None:
        return _resolve_exact_fixture_id(value, self.candidates(value))


def _resolve_exact_fixture_id(
    value: str,
    candidates: Iterable[str],
) -> str | None:
    text = str(value).strip()
    canonical = frozenset(candidates)
    if len(canonical) > 1:
        raise FixtureIdentityConflict("FIXTURE_IDENTITY_CONFLICT")
    if canonical:
        return next(iter(canonical))
    bare = text.removeprefix("api_football:")
    if bare.isdigit() and text in {bare, f"api_football:{bare}"}:
        return f"api_football:{bare}"
    return None


@dataclass(frozen=True, kw_only=True)
class ImportRecord:
    payload: dict[str, Any]
    record_type: str
    source_artifact: str
    source_line_number: int | None


def payload_sha256(payload: Mapping[str, Any]) -> str:
    return canonical_sha256(
        payload,
        domain=HashDomain.OUTCOME_LEDGER_PAYLOAD,
        version=SerializerVersion.LEGACY_V1,
    )


def _runtime_capture_sha256(
    payload: Mapping[str, Any],
    *,
    record_type: str,
    source_artifact: str,
) -> str | None:
    if record_type != "capture" or source_artifact != RUNTIME_LEDGER_SOURCE:
        return None
    business_payload = dict(payload)
    business_payload.pop("captured_at", None)
    # A future-window replay may project the same immutable capture under a
    # different selected football-day label. The capture identity itself is
    # unchanged, so this request-scoped label must not break idempotency.
    business_payload.pop("football_day", None)
    return payload_sha256(business_payload)


def business_key(payload: Mapping[str, Any], record_type: str | None = None) -> str:
    kind = str(record_type or payload.get("record_type") or "").lower()
    fixture_id = str(payload.get("fixture_id") or "")
    if kind == "capture":
        identity: Any = payload.get("capture_identity_hash") or (
            fixture_id,
            payload.get("card_hash"),
            payload.get("captured_at"),
            payload.get("recommendation_scope"),
            payload.get("shadow_pick"),
        )
    elif kind == "outcome":
        identity = (
            payload.get("capture_identity_hash")
            or payload.get("source_capture_hash")
            or payload.get("card_hash"),
            fixture_id,
            payload.get("settled_side"),
            payload.get("market"),
            payload.get("selection"),
            payload.get("settled_at"),
        )
    elif kind == "supersession":
        identity = payload.get("supersession_hash") or (
            fixture_id,
            payload.get("target_capture_identity_hash"),
            payload.get("reason_code"),
        )
    elif kind == "formal_snapshot":
        identity = payload.get("snapshot_id")
    elif kind == "formal_settlement":
        identity = payload.get("settlement_id") or (
            payload.get("snapshot_id"),
            payload.get("prediction_hash"),
        )
    elif kind == "legacy_recovery":
        capture_hash = payload.get("capture_hash")
        identity = (fixture_id, capture_hash) if fixture_id and capture_hash else None
    else:
        identity = payload
    if not kind or not identity:
        raise OutcomeLedgerError("OUTCOME_LEDGER_IDENTITY_INCOMPLETE")
    return canonical_sha256(
        {"record_type": kind, "identity": identity},
        domain=HashDomain.OUTCOME_LEDGER_BUSINESS_KEY,
        version=SerializerVersion.LEGACY_V1,
    )


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _record_time(payload: Mapping[str, Any]) -> tuple[datetime, datetime | None, datetime | None]:
    captured = _parse_time(payload.get("captured_at"))
    settled = _parse_time(payload.get("settled_at") or payload.get("evaluated_at"))
    superseded = _parse_time(payload.get("superseded_at"))
    occurred = captured or settled or superseded
    if occurred is None:
        raise OutcomeLedgerError("OUTCOME_LEDGER_TIME_MISSING")
    return occurred, captured, settled


class OutcomeLedgerRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine()

    def append(
        self,
        records: Sequence[Mapping[str, Any]],
        *,
        dry_run: bool,
        write_db: bool,
        source_artifact: str = RUNTIME_LEDGER_SOURCE,
        imported_at: datetime | None = None,
    ) -> dict[str, Any]:
        imports = [
            ImportRecord(
                payload=dict(record),
                record_type=str(record.get("record_type") or ""),
                source_artifact=source_artifact,
                source_line_number=None,
            )
            for record in records
        ]
        return self._append_imports(
            imports,
            dry_run=dry_run,
            write_db=write_db,
            imported_at=imported_at,
        )

    def _append_imports(
        self,
        records: Sequence[ImportRecord],
        *,
        dry_run: bool,
        write_db: bool,
        imported_at: datetime | None = None,
        session: Session | None = None,
    ) -> dict[str, Any]:
        if dry_run and write_db:
            raise OutcomeLedgerError("write_db requires dry_run=false")
        own_session = session is None
        active = session or Session(self.engine)
        now = (imported_at or datetime.now(UTC)).astimezone(UTC)
        written = 0
        already_imported = 0
        pending: dict[str, tuple[str, str | None]] = {}
        try:
            for item in records:
                payload = dict(item.payload)
                key = business_key(payload, item.record_type)
                digest = payload_sha256(payload)
                runtime_digest = _runtime_capture_sha256(
                    payload,
                    record_type=item.record_type,
                    source_artifact=item.source_artifact,
                )
                if key in pending:
                    pending_digest, pending_runtime_digest = pending[key]
                    if pending_digest != digest and (
                        runtime_digest is None
                        or runtime_digest != pending_runtime_digest
                    ):
                        raise OutcomeLedgerError("LEDGER_IMPORT_IDENTITY_CONFLICT")
                    already_imported += 1
                    continue
                existing = active.get(OutcomeLedgerModel, key)
                if existing is not None:
                    existing_runtime_digest = _runtime_capture_sha256(
                        existing.payload,
                        record_type=existing.record_type,
                        source_artifact=existing.source_artifact,
                    )
                    if existing.payload_sha256 != digest and (
                        runtime_digest is None
                        or runtime_digest != existing_runtime_digest
                    ):
                        raise OutcomeLedgerError("LEDGER_IMPORT_IDENTITY_CONFLICT")
                    already_imported += 1
                    continue
                if not write_db:
                    pending[key] = (digest, runtime_digest)
                    written += 1
                    continue
                occurred, captured, settled = _record_time(payload)
                fixture_id = str(payload.get("fixture_id") or "")
                if not fixture_id:
                    raise OutcomeLedgerError("OUTCOME_LEDGER_FIXTURE_ID_MISSING")
                active.add(
                    OutcomeLedgerModel(
                        business_key=key,
                        record_type=item.record_type,
                        fixture_id=fixture_id,
                        occurred_at=occurred,
                        captured_at=captured,
                        settled_at=settled,
                        schema_version=str(payload.get("schema_version") or "UNKNOWN"),
                        recommendation_scope=_optional(payload.get("recommendation_scope")),
                        capture_identity_hash=_optional(payload.get("capture_identity_hash")),
                        decision_hash=_optional(payload.get("decision_hash")),
                        payload=payload,
                        payload_sha256=digest,
                        source_artifact=item.source_artifact,
                        source_line_number=item.source_line_number,
                        imported_at=now,
                    )
                )
                pending[key] = (digest, runtime_digest)
                written += 1
            if own_session:
                active.commit() if write_db else active.rollback()
            elif write_db:
                active.flush()
        except Exception:
            if own_session:
                active.rollback()
            raise
        finally:
            if own_session:
                active.close()
        return {
            "status": "PASS",
            "record_count": len(records),
            "written": written if write_db else 0,
            "would_write": written if not write_db else 0,
            "already_imported": already_imported,
            "db_writes": written if write_db else 0,
            "provider_calls": 0,
        }

    def records(
        self,
        record_types: Iterable[str] | None = None,
        *,
        fixture_ids: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            statement = select(OutcomeLedgerModel)
            if record_types is not None:
                selected_types = tuple(
                    sorted({str(item) for item in record_types if str(item)})
                )
                if not selected_types:
                    return []
                statement = statement.where(
                    OutcomeLedgerModel.record_type.in_(selected_types)
                )
            if fixture_ids is not None:
                selected_fixture_ids = tuple(
                    sorted({str(item) for item in fixture_ids if str(item)})
                )
                if not selected_fixture_ids:
                    return []
                statement = statement.where(
                    OutcomeLedgerModel.fixture_id.in_(selected_fixture_ids)
                )
            rows = list(
                session.scalars(
                    statement.order_by(
                        OutcomeLedgerModel.occurred_at,
                        OutcomeLedgerModel.business_key,
                    )
                )
            )
        return [dict(row.payload) for row in rows]

    def legacy_recoveries(self) -> dict[str, dict[str, Any]]:
        recoveries: dict[str, dict[str, Any]] = {}
        for payload in self.records({"legacy_recovery"}):
            fixture_id = str(payload.get("fixture_id") or "")
            if not fixture_id or fixture_id in recoveries:
                raise OutcomeLedgerError("LEGACY_RECOVERY_IDENTITY_CONFLICT")
            recoveries[fixture_id] = payload
        return recoveries

    def result_payloads(self) -> dict[str, dict[str, Any]]:
        return self.result_payloads_for_fixtures()

    def result_payloads_for_fixtures(
        self,
        fixture_ids: Iterable[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        with Session(self.engine) as session:
            statement = select(ResultModel)
            if fixture_ids is not None:
                selected = tuple(sorted({str(item) for item in fixture_ids if str(item)}))
                if not selected:
                    return {}
                statement = statement.where(ResultModel.fixture_id.in_(selected))
            rows = list(session.scalars(statement.order_by(ResultModel.fixture_id)))
        return {
            row.fixture_id: {
                "fixture_id": row.fixture_id,
                "status": row.result_status,
                "home_goals": row.home_goals,
                "away_goals": row.away_goals,
                "confirmed_at": _iso(row.confirmed_at),
                "result_hash": row.result_hash,
            }
            for row in rows
        }

    def canonical_aggregate_sha256(
        self,
        business_keys: Sequence[str] | None = None,
    ) -> str:
        with Session(self.engine) as session:
            statement = select(
                OutcomeLedgerModel.business_key,
                OutcomeLedgerModel.payload_sha256,
            )
            if business_keys is not None:
                statement = statement.where(
                    OutcomeLedgerModel.business_key.in_(tuple(business_keys))
                )
            rows = list(
                session.execute(statement.order_by(OutcomeLedgerModel.business_key))
            )
        return hashlib.sha256(
            "".join(f"{key}:{digest}\n" for key, digest in rows).encode()
        ).hexdigest()

    def materialize_results(
        self,
        *,
        fixture_ids: Sequence[str] | None = None,
        dry_run: bool,
        write_db: bool,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if dry_run and write_db:
            raise OutcomeLedgerError("write_db requires dry_run=false")
        with Session(self.engine) as session:
            identities = list(
                session.scalars(
                    select(MatchdayFixtureIdentityModel).order_by(
                        MatchdayFixtureIdentityModel.fixture_id
                    )
                )
            )
            selected, unresolved = _select_identities(identities, fixture_ids)
            raw_rows = list(
                session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == "fixtures")
                    .order_by(RawPayloadModel.captured_at, RawPayloadModel.sha256)
                )
            )
            captures = {
                row.raw_payload_sha256: row.capture_id
                for row in session.scalars(
                    select(MatchdayEndpointCaptureModel).where(
                        MatchdayEndpointCaptureModel.endpoint == "fixtures"
                    )
                )
            }
            by_provider_id = _fixture_payload_candidates(raw_rows)
            counts = {
                "inspected_fixture_count": len(selected),
                "materialized_result_count": 0,
                "already_materialized_count": 0,
                "result_source_missing_count": len(unresolved),
                "result_source_conflict_count": 0,
                "result_not_finished_count": 0,
            }
            blockers = [
                f"{fixture_id}:RESULT_SOURCE_MISSING"
                for fixture_id in unresolved
            ]
            staged: list[ResultModel] = []
            confirmed_fixture_ids: list[str] = []
            for identity in selected:
                candidates = list(by_provider_id.get(identity.provider_fixture_id, ()))
                candidates.append(
                    (
                        identity.captured_at,
                        identity.raw_payload_sha256,
                        identity.payload,
                    )
                )
                outcome = _authoritative_result(identity.fixture_id, candidates)
                if outcome["status"] == "RESULT_NOT_FINISHED":
                    counts["result_not_finished_count"] += 1
                    continue
                if outcome["status"] == "RESULT_SOURCE_MISSING":
                    counts["result_source_missing_count"] += 1
                    blockers.append(f"{identity.fixture_id}:RESULT_SOURCE_MISSING")
                    continue
                if outcome["status"] == "RESULT_SOURCE_CONFLICT":
                    counts["result_source_conflict_count"] += 1
                    blockers.append(f"{identity.fixture_id}:RESULT_SOURCE_CONFLICT")
                    continue
                existing = session.scalar(
                    select(ResultModel).where(ResultModel.fixture_id == identity.fixture_id)
                )
                if existing is not None:
                    if (
                        existing.home_goals != outcome["home_goals"]
                        or existing.away_goals != outcome["away_goals"]
                    ):
                        counts["result_source_conflict_count"] += 1
                        blockers.append(f"{identity.fixture_id}:RESULT_SOURCE_CONFLICT")
                    else:
                        counts["already_materialized_count"] += 1
                        confirmed_fixture_ids.append(identity.fixture_id)
                    continue
                staged.append(
                    ResultModel(
                        fixture_id=identity.fixture_id,
                        home_goals=outcome["home_goals"],
                        away_goals=outcome["away_goals"],
                        result_status=outcome["result_status"],
                        confirmed_at=outcome["captured_at"],
                        source_payload_sha256=outcome["source_payload_sha256"],
                        source_capture_id=captures.get(outcome["source_payload_sha256"]),
                        result_hash=_result_hash(
                            identity.fixture_id,
                            outcome["home_goals"],
                            outcome["away_goals"],
                        ),
                    )
                )
                confirmed_fixture_ids.append(identity.fixture_id)
            if counts["result_source_conflict_count"]:
                session.rollback()
                staged = []
            elif write_db:
                session.add_all(staged)
                session.commit()
                counts["materialized_result_count"] = len(staged)
            else:
                session.rollback()
            return {
                "status": "BLOCKED" if blockers else "PASS",
                **counts,
                "provider_calls": 0,
                "db_writes": counts["materialized_result_count"],
                "blockers": blockers,
                "confirmed_fixture_ids": (
                    sorted(set(confirmed_fixture_ids))
                    if not counts["result_source_conflict_count"]
                    else []
                ),
                "evaluated_at": _iso(now or datetime.now(UTC)),
            }


def load_runtime_import_records(source_root: Path) -> list[ImportRecord]:
    records: list[ImportRecord] = []
    ledger_root = source_root / "forward_outcome_ledger"
    for path in sorted(ledger_root.glob("*.jsonl")):
        relative = str(path.relative_to(source_root))
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise OutcomeLedgerError("LEDGER_IMPORT_MALFORMED_RECORD") from exc
        for line_number, line in enumerate(lines, 1):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise OutcomeLedgerError("LEDGER_IMPORT_MALFORMED_RECORD") from exc
            if not isinstance(payload, dict):
                raise OutcomeLedgerError("LEDGER_IMPORT_MALFORMED_RECORD")
            record_type = payload.get("record_type")
            if (
                not record_type
                and payload.get("fixture_id")
                and payload.get("captured_at")
            ):
                record_type = "capture"
            if not record_type:
                raise OutcomeLedgerError("LEDGER_IMPORT_MALFORMED_RECORD")
            records.append(
                ImportRecord(
                    payload=payload,
                    record_type=str(record_type),
                    source_artifact=relative,
                    source_line_number=line_number,
                )
            )
    for dirname, record_type in (
        ("formal_recommendation_snapshots", "formal_snapshot"),
        ("formal_recommendation_settlements", "formal_settlement"),
    ):
        for path in sorted((source_root / dirname).glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise OutcomeLedgerError("LEDGER_IMPORT_MALFORMED_RECORD") from exc
            if not isinstance(payload, dict):
                raise OutcomeLedgerError("LEDGER_IMPORT_MALFORMED_RECORD")
            records.append(
                ImportRecord(
                    payload=payload,
                    record_type=record_type,
                    source_artifact=str(path.relative_to(source_root)),
                    source_line_number=1,
                )
            )
    return records


def load_legacy_recovery_import_records(path: Path) -> list[ImportRecord]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OutcomeLedgerError("LEDGER_IMPORT_MALFORMED_RECORD") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version")
        != "w2.forward_ledger_legacy_recovery.v1"
        or manifest.get("authority_status") != "MIGRATION_INPUT_ONLY"
        or not isinstance(manifest.get("entries"), list)
    ):
        raise OutcomeLedgerError("LEDGER_IMPORT_MALFORMED_RECORD")
    shared = {
        "record_type": "legacy_recovery",
        "schema_version": manifest.get("schema_version"),
        "environment": manifest.get("environment"),
        "policy": manifest.get("policy"),
        "authority_status": manifest.get("authority_status"),
        "reviewed_at": manifest.get("reviewed_at_utc"),
    }
    records: list[ImportRecord] = []
    for index, entry in enumerate(manifest["entries"], 1):
        if not isinstance(entry, dict):
            raise OutcomeLedgerError("LEDGER_IMPORT_MALFORMED_RECORD")
        payload = {**shared, **entry}
        if any(
            payload.get(key) in {None, ""}
            for key in (
                "schema_version",
                "reviewed_at",
                "fixture_id",
                "captured_at",
                "capture_hash",
                "kickoff_utc",
                "competition",
                "home_team_name",
                "away_team_name",
                "market",
                "selection",
                "line",
                "entry_price",
                "settlement_outcome",
            )
        ) or not isinstance(payload.get("final_score"), Mapping):
            raise OutcomeLedgerError("LEDGER_IMPORT_MALFORMED_RECORD")
        records.append(
            ImportRecord(
                payload=payload,
                record_type="legacy_recovery",
                source_artifact=str(path),
                source_line_number=index,
            )
        )
    return records


def canonical_import_sha256(records: Sequence[ImportRecord]) -> str:
    rows = sorted(
        (business_key(item.payload, item.record_type), payload_sha256(item.payload))
        for item in records
    )
    return hashlib.sha256("".join(f"{key}:{digest}\n" for key, digest in rows).encode()).hexdigest()


def import_runtime_ledger(
    repository: OutcomeLedgerRepository,
    source_root: Path,
    *,
    dry_run: bool,
    write_db: bool,
    confirm_write: str | None,
    legacy_recovery_manifest: Path | None = None,
) -> dict[str, Any]:
    if write_db and confirm_write != IMPORT_CONFIRMATION_PHRASE:
        raise OutcomeLedgerError("LEDGER_IMPORT_WRITE_REQUIRES_CONFIRMATION")
    records = load_runtime_import_records(source_root)
    recovery_records = (
        load_legacy_recovery_import_records(legacy_recovery_manifest)
        if legacy_recovery_manifest is not None
        else []
    )
    records.extend(recovery_records)
    source_files = {item.source_artifact for item in records}
    source_hash = canonical_import_sha256(records)
    business_keys = [business_key(item.payload, item.record_type) for item in records]
    recovery_keys = [
        business_key(item.payload, item.record_type) for item in recovery_records
    ]
    recovery_source_hash = canonical_import_sha256(recovery_records)
    with Session(repository.engine) as session:
        try:
            result_count = _materialize_imported_results(session, records, write_db=write_db)
            outcome = repository._append_imports(
                records,
                dry_run=dry_run,
                write_db=write_db,
                session=session,
            )
            session.commit() if write_db else session.rollback()
        except Exception:
            session.rollback()
            raise
    db_count = 0
    db_hash = source_hash
    total_db_count = 0
    total_db_hash = source_hash
    recovery_db_count = 0
    recovery_db_hash = recovery_source_hash
    if write_db:
        with Session(repository.engine) as session:
            db_count = int(
                session.query(OutcomeLedgerModel)
                .filter(
                    OutcomeLedgerModel.business_key.in_(business_keys)
                )
                .count()
            )
            total_db_count = int(session.query(OutcomeLedgerModel).count())
            recovery_db_count = int(
                session.query(OutcomeLedgerModel)
                .filter(OutcomeLedgerModel.business_key.in_(recovery_keys))
                .count()
            )
        db_hash = repository.canonical_aggregate_sha256(business_keys)
        total_db_hash = repository.canonical_aggregate_sha256()
        recovery_db_hash = repository.canonical_aggregate_sha256(recovery_keys)
    reconciliation = (
        len(records) == db_count and source_hash == db_hash
        if write_db
        else True
    )
    return {
        "status": "PASS" if reconciliation else "BLOCKED",
        "source_file_count": len(source_files),
        "source_record_count": len(records),
        "source_canonical_sha256": source_hash,
        "importable_record_count": (
            outcome["written"] if write_db else outcome["would_write"]
        ),
        "already_imported_count": outcome["already_imported"],
        "db_record_count": db_count,
        "db_canonical_sha256": db_hash,
        "total_db_record_count": total_db_count,
        "total_db_canonical_sha256": total_db_hash,
        "legacy_recovery_source_count": len(recovery_records),
        "legacy_recovery_db_count": recovery_db_count,
        "legacy_recovery_source_sha256": recovery_source_hash,
        "legacy_recovery_db_sha256": recovery_db_hash,
        "legacy_recovery_hash_parity": (
            "NOT_APPLICABLE"
            if not recovery_records
            else "PASS"
            if write_db
            and len(recovery_records) == recovery_db_count
            and recovery_source_hash == recovery_db_hash
            else "NOT_RUN"
        ),
        "result_fixture_count": result_count,
        "result_conflict_count": 0,
        "malformed_count": 0,
        "reconciliation_status": "PASS" if reconciliation else "FAIL",
        "provider_calls": 0,
        "db_writes": outcome["db_writes"] + (result_count if write_db else 0),
    }


def _materialize_imported_results(
    session: Session,
    records: Sequence[ImportRecord],
    *,
    write_db: bool,
) -> int:
    candidates: dict[str, set[tuple[int, int, str, str]]] = {}
    for item in records:
        result = _result_from_record(item)
        if result is None:
            continue
        fixture_id = _resolve_fixture_id(session, result["fixture_id"])
        if fixture_id is None:
            raise OutcomeLedgerError("RESULT_SOURCE_MISSING")
        candidates.setdefault(fixture_id, set()).add(
            (
                result["home_goals"],
                result["away_goals"],
                result["status"],
                payload_sha256(item.payload),
            )
        )
    staged = 0
    for fixture_id, values in candidates.items():
        scores = {(home, away) for home, away, _, _ in values}
        if len(scores) != 1:
            raise OutcomeLedgerError("RESULT_SOURCE_CONFLICT")
        home, away = next(iter(scores))
        status, source_hash = sorted((status, digest) for _, _, status, digest in values)[0]
        existing = session.scalar(select(ResultModel).where(ResultModel.fixture_id == fixture_id))
        if existing is not None:
            if (existing.home_goals, existing.away_goals) != (home, away):
                raise OutcomeLedgerError("RESULT_SOURCE_CONFLICT")
            continue
        staged += 1
        if write_db:
            session.add(
                ResultModel(
                    fixture_id=fixture_id,
                    home_goals=home,
                    away_goals=away,
                    result_status=status,
                    confirmed_at=datetime.now(UTC),
                    source_payload_sha256=source_hash,
                    source_capture_id=None,
                    result_hash=_result_hash(fixture_id, home, away),
                )
            )
    return staged


def _result_from_record(item: ImportRecord) -> dict[str, Any] | None:
    if item.record_type not in {"outcome", "formal_settlement"}:
        return None
    score = item.payload.get("final_score")
    if not isinstance(score, Mapping):
        return None
    home = _integer(score.get("home", score.get("home_goals")))
    away = _integer(score.get("away", score.get("away_goals")))
    status = str(score.get("status") or "").upper()
    fixture_id = str(item.payload.get("fixture_id") or "")
    if status not in TERMINAL_STATUSES or home is None or away is None or not fixture_id:
        return None
    return {"fixture_id": fixture_id, "home_goals": home, "away_goals": away, "status": status}


def _resolve_fixture_id(session: Session, value: str) -> str | None:
    bare = value.removeprefix("api_football:")
    rows = session.scalars(
        select(MatchdayFixtureIdentityModel).where(
            or_(
                MatchdayFixtureIdentityModel.fixture_id == value,
                MatchdayFixtureIdentityModel.provider_fixture_id == bare,
            )
        )
    )
    try:
        return _resolve_exact_fixture_id(value, (row.fixture_id for row in rows))
    except FixtureIdentityConflict:
        raise OutcomeLedgerError("RESULT_SOURCE_CONFLICT") from None


def _select_identities(
    rows: Sequence[MatchdayFixtureIdentityModel],
    fixture_ids: Sequence[str] | None,
) -> tuple[list[MatchdayFixtureIdentityModel], list[str]]:
    if fixture_ids is None:
        return list(rows), []
    requested = {str(value) for value in fixture_ids}
    selected = [
        row
        for row in rows
        if row.fixture_id in requested
        or row.provider_fixture_id in requested
        or f"api_football:{row.provider_fixture_id}" in requested
    ]
    resolved = {
        requested_id
        for row in selected
        for requested_id in requested
        if requested_id
        in {
            row.fixture_id,
            row.provider_fixture_id,
            f"api_football:{row.provider_fixture_id}",
        }
    }
    return selected, sorted(requested - resolved)


def _fixture_payload_candidates(
    rows: Sequence[RawPayloadModel],
) -> dict[str, list[tuple[datetime, str, Mapping[str, Any]]]]:
    grouped: dict[str, list[tuple[datetime, str, Mapping[str, Any]]]] = {}
    for row in rows:
        response = row.payload.get("response")
        if not isinstance(response, list):
            continue
        for item in response:
            if not isinstance(item, Mapping):
                continue
            fixture = item.get("fixture")
            provider_id = (
                str(fixture.get("id") or "") if isinstance(fixture, Mapping) else ""
            )
            if provider_id:
                grouped.setdefault(provider_id, []).append(
                    (row.captured_at, row.sha256, item)
                )
    return grouped


def _authoritative_result(
    fixture_id: str,
    candidates: Sequence[tuple[datetime, str, Mapping[str, Any]]],
) -> dict[str, Any]:
    terminal: list[tuple[datetime, str, str, int, int]] = []
    invalid_terminal = False
    for captured_at, source_hash, item in candidates:
        fixture = item.get("fixture")
        fixture = fixture if isinstance(fixture, Mapping) else {}
        status_value = fixture.get("status")
        status_value = status_value if isinstance(status_value, Mapping) else {}
        status = str(status_value.get("short") or "").upper()
        if status not in TERMINAL_STATUSES:
            continue
        score_value = item.get("score")
        score = score_value if isinstance(score_value, Mapping) else {}
        fulltime_value = score.get("fulltime")
        fulltime = fulltime_value if isinstance(fulltime_value, Mapping) else {}
        home = _integer(fulltime.get("home"))
        away = _integer(fulltime.get("away"))
        if home is None or away is None:
            invalid_terminal = True
            continue
        terminal.append((captured_at, source_hash, status, home, away))
    if invalid_terminal:
        return {"status": "RESULT_SOURCE_MISSING"}
    if not terminal:
        return {"status": "RESULT_NOT_FINISHED"}
    scores = {(home, away) for _, _, _, home, away in terminal}
    if len(scores) != 1:
        return {"status": "RESULT_SOURCE_CONFLICT"}
    captured_at, source_hash, status, home, away = sorted(
        terminal, key=lambda item: (item[0], item[1], item[2])
    )[0]
    return {
        "status": "PASS",
        "fixture_id": fixture_id,
        "result_status": status,
        "home_goals": home,
        "away_goals": away,
        "captured_at": captured_at,
        "source_payload_sha256": source_hash,
    }


def _result_hash(fixture_id: str, home_goals: int, away_goals: int) -> str:
    return payload_sha256(
        {
            "schema_version": "w2.result.v2",
            "fixture_id": fixture_id,
            "home_goals": home_goals,
            "away_goals": away_goals,
        }
    )


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _optional(value: Any) -> str | None:
    text = str(value or "")
    return text or None


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
