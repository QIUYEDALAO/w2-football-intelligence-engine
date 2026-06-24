from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.config import Settings
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.future_refresh_models import (
    FutureMarketObservationModel,
    FutureRefreshRunAuditModel,
    FutureRefreshTaskAuditModel,
    RawPayloadModel,
)


class FutureRefreshPersistenceError(RuntimeError):
    pass


def parse_db_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value:
        raise FutureRefreshPersistenceError("INVALID_DATETIME")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class DatabaseRawPayloadObjectStore:
    def __init__(self, session: Session) -> None:
        self.session = session

    def put(
        self,
        *,
        sha256: str,
        endpoint: str,
        captured_at: datetime,
        payload: dict[str, Any],
    ) -> str:
        storage_uri = f"db://raw_payload/{sha256}"
        self.session.add(
            RawPayloadModel(
                sha256=sha256,
                endpoint=endpoint,
                captured_at=captured_at,
                storage_uri=storage_uri,
                payload=payload,
            )
        )
        return storage_uri

    def get(self, sha256: str) -> dict[str, Any] | None:
        row = self.session.get(RawPayloadModel, sha256)
        return dict(row.payload) if row is not None else None


class FutureRefreshDbRepository:
    def __init__(self, *, engine: Engine | None = None, settings: Settings | None = None) -> None:
        self.engine = engine or create_engine(settings)

    def save_raw_payload(
        self,
        *,
        sha256: str,
        endpoint: str,
        captured_at: datetime,
        payload: dict[str, Any],
    ) -> str:
        with Session(self.engine) as session:
            store = DatabaseRawPayloadObjectStore(session)
            try:
                storage_uri = store.put(
                    sha256=sha256,
                    endpoint=endpoint,
                    captured_at=captured_at,
                    payload=payload,
                )
                session.commit()
                return storage_uri
            except IntegrityError:
                session.rollback()
                existing = session.get(RawPayloadModel, sha256)
                if existing is None:
                    raise FutureRefreshPersistenceError("RAW_PAYLOAD_CONFLICT") from None
                return existing.storage_uri
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("RAW_PAYLOAD_WRITE_FAILED") from exc

    def append_observations(self, observations: list[dict[str, Any]]) -> int:
        appended = 0
        with Session(self.engine) as session:
            for row in observations:
                session.add(self._observation_model(row))
                try:
                    session.commit()
                    appended += 1
                except IntegrityError:
                    session.rollback()
                except Exception as exc:
                    session.rollback()
                    raise FutureRefreshPersistenceError("OBSERVATION_WRITE_FAILED") from exc
        return appended

    def latest_market_observations(self) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(FutureMarketObservationModel).order_by(
                        FutureMarketObservationModel.fixture_id,
                        FutureMarketObservationModel.captured_at,
                        FutureMarketObservationModel.canonical_market,
                        FutureMarketObservationModel.bookmaker_id,
                        FutureMarketObservationModel.selection,
                    )
                )
            )
        latest: dict[tuple[str, str, str, str, str | None], dict[str, Any]] = {}
        for model in rows:
            row = self._observation_dict(model)
            key = (
                row["fixture_id"],
                row["canonical_market"],
                row["bookmaker_id"],
                row["selection"],
                row["line"],
            )
            current = latest.get(key)
            if current is None or str(row["captured_at"]) > str(current["captured_at"]):
                latest[key] = row
        return sorted(
            latest.values(),
            key=lambda item: (
                str(item["fixture_id"]),
                str(item["captured_at"]),
                str(item["canonical_market"]),
                str(item["bookmaker_id"]),
                str(item["selection"]),
            ),
        )

    def fixture_payloads(self) -> list[dict[str, Any]]:
        fixtures: dict[str, dict[str, Any]] = {}
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == "fixtures")
                    .order_by(RawPayloadModel.captured_at)
                )
            )
        for row in rows:
            response = row.payload.get("response")
            if not isinstance(response, list):
                continue
            for item in response:
                if not isinstance(item, dict):
                    continue
                fixture_id = str(item.get("fixture", {}).get("id"))
                if fixture_id and fixture_id != "None":
                    fixtures[fixture_id] = item
        return sorted(fixtures.values(), key=lambda item: item.get("fixture", {}).get("date", ""))

    def market_snapshots(self) -> list[dict[str, Any]]:
        observations = self.latest_market_observations()
        by_fixture: dict[str, list[dict[str, Any]]] = {}
        for row in observations:
            by_fixture.setdefault(str(row["fixture_id"]), []).append(row)
        snapshots: list[dict[str, Any]] = []
        for fixture_id, rows in sorted(by_fixture.items()):
            captured_at = max(str(row["captured_at"]) for row in rows)
            bookmakers = {str(row["bookmaker_id"]) for row in rows if row.get("bookmaker_id")}
            markets = {str(row["canonical_market"]) for row in rows}
            snapshots.append(
                {
                    "fixture_id": fixture_id,
                    "captured_at": captured_at,
                    "captured_at_utc": captured_at,
                    "snapshot_semantics": "CAPTURED_AT",
                    "bookmaker_count": len(bookmakers),
                    "quality": "READY" if rows else "MARKET_NOT_COMPARABLE",
                    "source": "future_refresh_db",
                    "market_coverage": {market: True for market in sorted(markets)},
                    "candidate": False,
                    "formal_recommendation": False,
                }
            )
        return snapshots

    def provider_status(self) -> dict[str, Any]:
        with Session(self.engine) as session:
            row = session.scalar(
                select(FutureRefreshRunAuditModel).order_by(
                    desc(FutureRefreshRunAuditModel.generated_at)
                )
            )
        if row is None:
            return {}
        last_success = next(
            (
                item
                for item in reversed(row.requests)
                if isinstance(item, dict) and item.get("status_code") == 200
            ),
            {},
        )
        return {
            "provider": "api_football",
            "status": "READY" if not row.blockers else "DEGRADED",
            "remaining_quota": row.remaining_quota,
            "credential_status": "PRESENT",
            "last_request_status": (
                row.requests[-1].get("status_code")
                if row.requests and isinstance(row.requests[-1], dict)
                else None
            ),
            "last_successful_refresh_at": last_success.get("captured_at_utc"),
            "blockers": row.blockers,
        }

    def write_task_audit(self, audit: dict[str, Any]) -> None:
        with Session(self.engine) as session:
            try:
                session.merge(
                    FutureRefreshTaskAuditModel(
                        task_id=str(audit["task_id"]),
                        key=str(audit["key"]),
                        owner=str(audit["owner"]),
                        queued_at=parse_db_datetime(audit["queued_at"]),
                        started_at=parse_db_datetime(audit["started_at"]),
                        finished_at=parse_db_datetime(audit["finished_at"]),
                        status=str(audit["status"]),
                        result=dict(audit["result"]),
                    )
                )
                session.commit()
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("TASK_AUDIT_WRITE_FAILED") from exc

    def write_run_audit(self, payload: dict[str, Any]) -> None:
        with Session(self.engine) as session:
            try:
                session.add(
                    FutureRefreshRunAuditModel(
                        generated_at=parse_db_datetime(payload["generated_at_utc"]),
                        competition_id=str(payload["competition_id"]),
                        request_count=int(payload["request_count"]),
                        remaining_quota=payload["remaining_quota"],
                        fixture_count=int(payload["fixture_count"]),
                        mapping_count=int(payload["mapping_count"]),
                        market_snapshot_count=int(payload["market_snapshot_count"]),
                        ledger_appended_count=int(payload["ledger_appended_count"]),
                        selected_market_fixture_ids=list(payload["selected_market_fixture_ids"]),
                        blockers=list(payload["blockers"]),
                        requests=list(payload["requests"]),
                        candidate=False,
                        formal_recommendation=False,
                    )
                )
                session.commit()
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("RUN_AUDIT_WRITE_FAILED") from exc

    def _observation_model(self, row: dict[str, Any]) -> FutureMarketObservationModel:
        return FutureMarketObservationModel(
            observation_id=str(row["observation_id"]),
            fixture_id=str(row["fixture_id"]),
            provider=str(row["provider"]),
            bookmaker_id=str(row["bookmaker_id"]),
            bookmaker_name=str(row["bookmaker_name"]),
            provider_bet_id=str(row["provider_bet_id"]),
            raw_market_label=str(row["raw_market_label"]),
            canonical_market=str(row["canonical_market"]),
            selection=str(row["selection"]),
            line=None if row.get("line") is None else str(row["line"]),
            decimal_odds=str(row["decimal_odds"]),
            suspended=bool(row["suspended"]),
            live=bool(row["live"]),
            provider_last_update=str(row["provider_last_update"]),
            captured_at=parse_db_datetime(row["captured_at"]),
            ingested_at=parse_db_datetime(row["ingested_at"]),
            raw_payload_sha256=str(row["raw_payload_sha256"]),
            source_revision=str(row["source_revision"]),
            candidate=False,
            formal_recommendation=False,
        )

    def _observation_dict(self, model: FutureMarketObservationModel) -> dict[str, Any]:
        return {
            "observation_id": model.observation_id,
            "fixture_id": model.fixture_id,
            "provider": model.provider,
            "bookmaker_id": model.bookmaker_id,
            "bookmaker_name": model.bookmaker_name,
            "provider_bet_id": model.provider_bet_id,
            "raw_market_label": model.raw_market_label,
            "canonical_market": model.canonical_market,
            "selection": model.selection,
            "line": model.line,
            "decimal_odds": model.decimal_odds,
            "suspended": model.suspended,
            "live": model.live,
            "provider_last_update": model.provider_last_update,
            "captured_at": iso_z(model.captured_at),
            "ingested_at": iso_z(model.ingested_at),
            "raw_payload_sha256": model.raw_payload_sha256,
            "source_revision": model.source_revision,
            "candidate": False,
            "formal_recommendation": False,
        }
