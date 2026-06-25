from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.config import Settings
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.team_value_models import (
    TeamValueMappingModel,
    TeamValueObservationModel,
    TeamValueSourceSnapshotModel,
)

SOURCE_SYSTEM = "transfermarkt_dataset"
SCHEMA_VERSION = "TRANSFERMARKT_DATASETS_TEAM_VALUE_V1"
DEFAULT_PLAYERS_URL = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/players.csv.gz"
DEFAULT_PLAYER_VALUATIONS_URL = (
    "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/player_valuations.csv.gz"
)
DEFAULT_USER_AGENT = "W2FootballIntelligenceEngine/transfermarkt-dataset-sync"
DEFAULT_TERMS_SUMMARY = (
    "Dataset repository is CC0-1.0 and refreshed weekly; source data originates from "
    "Transfermarkt, whose terms may constrain automated extraction. W2 consumes only the "
    "public dcaribou dataset artifact and records this provenance for user/legal review."
)


class TeamValueSyncError(RuntimeError):
    pass


@dataclass(frozen=True, kw_only=True)
class SourceFile:
    raw_path: str
    source_url: str
    content: bytes
    source_revision: str | None = None

    @property
    def sha256_checksum(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True, kw_only=True)
class TeamValueObservation:
    transfermarkt_club_id: str
    transfermarkt_club_name: str
    season: str | None
    valid_from: datetime
    value_eur: Decimal
    raw_path: str
    payload: dict[str, Any]

    @property
    def source_row_sha256(self) -> str:
        payload = {
            "transfermarkt_club_id": self.transfermarkt_club_id,
            "transfermarkt_club_name": self.transfermarkt_club_name,
            "season": self.season,
            "valid_from": iso(self.valid_from),
            "value_eur": str(self.value_eur),
            "raw_path": self.raw_path,
        }
        return sha256_json(payload)


@dataclass(frozen=True, kw_only=True)
class TeamValueMapping:
    transfermarkt_club_id: str
    transfermarkt_club_name: str
    w2_team_id: str
    confidence: Decimal
    mapping_source: str
    valid_from: datetime
    valid_to: datetime | None = None
    notes: str | None = None


@dataclass(frozen=True, kw_only=True)
class TeamValueSnapshot:
    w2_team_id: str
    transfermarkt_club_id: str
    transfermarkt_club_name: str
    value_eur: Decimal
    valid_from: datetime
    source_snapshot_id: str


@dataclass(frozen=True, kw_only=True)
class TeamValueSignalLookup:
    home: TeamValueSnapshot | None
    away: TeamValueSnapshot | None
    status: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class TeamValueSyncResult:
    status: str
    snapshots: int
    observations_seen: int
    observations_inserted: int
    mappings_seen: int
    mappings_inserted: int
    coverage: dict[str, int]
    source_checksums: dict[str, str]
    candidate: bool = False
    formal_recommendation: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "snapshots": self.snapshots,
            "observations_seen": self.observations_seen,
            "observations_inserted": self.observations_inserted,
            "mappings_seen": self.mappings_seen,
            "mappings_inserted": self.mappings_inserted,
            "coverage": self.coverage,
            "source_checksums": self.source_checksums,
            "candidate": False,
            "formal_recommendation": False,
        }


def parse_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def db_datetime(engine: Engine, value: datetime) -> datetime:
    utc_value = parse_utc(value)
    if engine.dialect.name == "sqlite":
        return utc_value.replace(tzinfo=None)
    return utc_value


def iso(value: datetime) -> str:
    return parse_utc(value).isoformat().replace("+00:00", "Z")


def sha256_json(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def open_source_file(path_or_url: str, *, user_agent: str = DEFAULT_USER_AGENT) -> SourceFile:
    if path_or_url.startswith(("http://", "https://")):
        request = urllib.request.Request(  # noqa: S310
            path_or_url,
            headers={"User-Agent": user_agent},
        )
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            return SourceFile(
                raw_path=path_or_url.rsplit("/", 1)[-1],
                source_url=path_or_url,
                source_revision=response.headers.get("ETag"),
                content=response.read(),
            )
    path = Path(path_or_url.removeprefix("file://"))
    return SourceFile(raw_path=str(path), source_url=path.as_uri(), content=path.read_bytes())


def csv_rows(source: SourceFile) -> list[dict[str, str]]:
    content = source.content
    if source.raw_path.endswith(".gz") or content[:2] == b"\x1f\x8b":
        content = gzip.decompress(content)
    text = content.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def parse_decimal(value: str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def parse_date(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    date_value = value.split(" ", 1)[0]
    try:
        return datetime.fromisoformat(date_value).replace(tzinfo=UTC)
    except ValueError:
        return None


def observations_from_players(
    source: SourceFile,
    *,
    ingested_at: datetime,
) -> list[TeamValueObservation]:
    observations: list[TeamValueObservation] = []
    for row in csv_rows(source):
        club_id = row.get("current_club_id") or ""
        value = parse_decimal(row.get("market_value_in_eur"))
        if not club_id or value is None or value <= 0:
            continue
        observed_at = parse_date(row.get("last_season")) or parse_utc(ingested_at)
        season = row.get("last_season") or None
        observations.append(
            TeamValueObservation(
                transfermarkt_club_id=club_id,
                transfermarkt_club_name=row.get("current_club_name") or "Unknown",
                season=season,
                valid_from=observed_at,
                value_eur=value,
                raw_path=source.raw_path,
                payload={"source_table": "players", "row": row},
            )
        )
    return aggregate_player_observations(observations)


def observations_from_player_valuations(source: SourceFile) -> list[TeamValueObservation]:
    observations: list[TeamValueObservation] = []
    for row in csv_rows(source):
        club_id = row.get("current_club_id") or ""
        value = parse_decimal(row.get("market_value_in_eur"))
        observed_at = parse_date(row.get("date"))
        if not club_id or value is None or value <= 0 or observed_at is None:
            continue
        observations.append(
            TeamValueObservation(
                transfermarkt_club_id=club_id,
                transfermarkt_club_name=row.get("current_club_name") or "Unknown",
                season=None,
                valid_from=observed_at,
                value_eur=value,
                raw_path=source.raw_path,
                payload={"source_table": "player_valuations", "row": row},
            )
        )
    return aggregate_player_observations(observations)


def aggregate_player_observations(
    observations: Iterable[TeamValueObservation],
) -> list[TeamValueObservation]:
    grouped: dict[tuple[str, datetime, str | None], list[TeamValueObservation]] = {}
    for observation in observations:
        grouped.setdefault(
            (observation.transfermarkt_club_id, observation.valid_from, observation.season),
            [],
        ).append(observation)
    aggregated: list[TeamValueObservation] = []
    for (club_id, valid_from, season), items in grouped.items():
        value = sum((item.value_eur for item in items), Decimal("0"))
        club_name = next(
            (item.transfermarkt_club_name for item in items if item.transfermarkt_club_name),
            "Unknown",
        )
        raw_paths = sorted({item.raw_path for item in items})
        aggregated.append(
            TeamValueObservation(
                transfermarkt_club_id=club_id,
                transfermarkt_club_name=club_name,
                season=season,
                valid_from=valid_from,
                value_eur=value,
                raw_path=",".join(raw_paths),
                payload={
                    "aggregation": "sum_player_market_value_by_club_and_asof",
                    "player_rows": len(items),
                    "source_tables": sorted(
                        {str(item.payload.get("source_table")) for item in items}
                    ),
                },
            )
        )
    return sorted(aggregated, key=lambda item: (item.transfermarkt_club_id, item.valid_from))


class TeamValueRepository:
    def __init__(self, *, engine: Engine | None = None, settings: Settings | None = None) -> None:
        self.engine = engine or create_engine(settings)

    def record_source_snapshot(
        self,
        source: SourceFile,
        *,
        ingested_at: datetime,
        payload: dict[str, Any],
    ) -> str:
        snapshot_id = sha256_json(
            [SOURCE_SYSTEM, source.raw_path, source.sha256_checksum, source.source_revision]
        )
        with Session(self.engine) as session:
            row = TeamValueSourceSnapshotModel(
                id=snapshot_id,
                source_system=SOURCE_SYSTEM,
                source_url=source.source_url,
                source_revision=source.source_revision,
                schema_version=SCHEMA_VERSION,
                raw_path=source.raw_path,
                sha256_checksum=source.sha256_checksum,
                ingested_at=db_datetime(self.engine, ingested_at),
                license="CC0-1.0",
                terms_summary=DEFAULT_TERMS_SUMMARY,
                payload=payload,
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
        return snapshot_id

    def upsert_mappings(
        self,
        mappings: Iterable[TeamValueMapping],
        *,
        ingested_at: datetime,
    ) -> int:
        inserted = 0
        with Session(self.engine) as session:
            for mapping in mappings:
                row_id = sha256_json(
                    [
                        SOURCE_SYSTEM,
                        mapping.transfermarkt_club_id,
                        mapping.w2_team_id,
                        iso(mapping.valid_from),
                    ]
                )
                session.add(
                    TeamValueMappingModel(
                        id=row_id,
                        source_system=SOURCE_SYSTEM,
                        transfermarkt_club_id=mapping.transfermarkt_club_id,
                        transfermarkt_club_name=mapping.transfermarkt_club_name,
                        w2_team_id=mapping.w2_team_id,
                        confidence=mapping.confidence,
                        mapping_source=mapping.mapping_source,
                        valid_from=db_datetime(self.engine, mapping.valid_from),
                        valid_to=(
                            db_datetime(self.engine, mapping.valid_to)
                            if mapping.valid_to is not None
                            else None
                        ),
                        ingested_at=db_datetime(self.engine, ingested_at),
                        notes=mapping.notes,
                    )
                )
                try:
                    session.commit()
                    inserted += 1
                except IntegrityError:
                    session.rollback()
        return inserted

    def upsert_observations(
        self,
        observations: Iterable[TeamValueObservation],
        *,
        source_snapshot_id: str,
        ingested_at: datetime,
    ) -> int:
        inserted = 0
        with Session(self.engine) as session:
            for observation in observations:
                row_sha = observation.source_row_sha256
                row_id = sha256_json([SOURCE_SYSTEM, source_snapshot_id, row_sha])
                session.add(
                    TeamValueObservationModel(
                        id=row_id,
                        source_system=SOURCE_SYSTEM,
                        source_snapshot_id=source_snapshot_id,
                        transfermarkt_club_id=observation.transfermarkt_club_id,
                        transfermarkt_club_name=observation.transfermarkt_club_name,
                        season=observation.season,
                        valid_from=db_datetime(self.engine, observation.valid_from),
                        valid_to=None,
                        value_eur=observation.value_eur,
                        currency="EUR",
                        raw_path=observation.raw_path,
                        source_row_sha256=row_sha,
                        schema_version=SCHEMA_VERSION,
                        ingested_at=db_datetime(self.engine, ingested_at),
                        payload=observation.payload,
                    )
                )
                try:
                    session.commit()
                    inserted += 1
                except IntegrityError:
                    session.rollback()
        return inserted

    def lookup_team_value(self, *, w2_team_id: str, as_of: datetime) -> TeamValueSnapshot | None:
        as_of_db = db_datetime(self.engine, as_of)
        with Session(self.engine) as session:
            mapping = session.scalar(
                select(TeamValueMappingModel)
                .where(
                    TeamValueMappingModel.source_system == SOURCE_SYSTEM,
                    TeamValueMappingModel.w2_team_id == w2_team_id,
                    TeamValueMappingModel.valid_from <= as_of_db,
                    (
                        TeamValueMappingModel.valid_to.is_(None)
                        | (TeamValueMappingModel.valid_to > as_of_db)
                    ),
                )
                .order_by(
                    TeamValueMappingModel.confidence.desc(),
                    TeamValueMappingModel.valid_from.desc(),
                )
                .limit(1)
            )
            if mapping is None:
                return None
            row = session.scalar(
                select(TeamValueObservationModel)
                .where(
                    TeamValueObservationModel.source_system == SOURCE_SYSTEM,
                    TeamValueObservationModel.transfermarkt_club_id
                    == mapping.transfermarkt_club_id,
                    TeamValueObservationModel.valid_from <= as_of_db,
                    (
                        TeamValueObservationModel.valid_to.is_(None)
                        | (TeamValueObservationModel.valid_to > as_of_db)
                    ),
                )
                .order_by(
                    TeamValueObservationModel.valid_from.desc(),
                    TeamValueObservationModel.ingested_at.desc(),
                )
                .limit(1)
            )
            if row is None:
                return None
            return TeamValueSnapshot(
                w2_team_id=w2_team_id,
                transfermarkt_club_id=row.transfermarkt_club_id,
                transfermarkt_club_name=row.transfermarkt_club_name,
                value_eur=Decimal(row.value_eur),
                valid_from=parse_utc(row.valid_from),
                source_snapshot_id=row.source_snapshot_id,
            )

    def coverage(self) -> dict[str, int]:
        with Session(self.engine) as session:
            teams = (
                session.scalar(
                    select(func.count(func.distinct(TeamValueMappingModel.w2_team_id)))
                )
                or 0
            )
            clubs = session.scalar(
                select(func.count(func.distinct(TeamValueObservationModel.transfermarkt_club_id)))
            ) or 0
            seasons = (
                session.scalar(
                    select(func.count(func.distinct(TeamValueObservationModel.season)))
                )
                or 0
            )
            observations = (
                session.scalar(select(func.count()).select_from(TeamValueObservationModel)) or 0
            )
        return {
            "mapped_w2_teams": int(teams),
            "transfermarkt_clubs": int(clubs),
            "seasons": int(seasons),
            "observations": int(observations),
        }


def load_mappings_from_csv(path: str | None, *, valid_from: datetime) -> list[TeamValueMapping]:
    if not path:
        return []
    source = open_source_file(path)
    mappings: list[TeamValueMapping] = []
    for row in csv_rows(source):
        confidence = parse_decimal(row.get("confidence")) or Decimal("0")
        if not row.get("transfermarkt_club_id") or not row.get("w2_team_id"):
            continue
        row_valid_from = parse_date(row.get("valid_from")) or valid_from
        mappings.append(
            TeamValueMapping(
                transfermarkt_club_id=str(row["transfermarkt_club_id"]),
                transfermarkt_club_name=row.get("transfermarkt_club_name") or "Unknown",
                w2_team_id=str(row["w2_team_id"]),
                confidence=confidence,
                mapping_source=row.get("mapping_source") or "manual",
                valid_from=row_valid_from,
                notes=row.get("notes") or None,
            )
        )
    return mappings


def sync_transfermarkt_team_values(
    *,
    players_url: str = DEFAULT_PLAYERS_URL,
    player_valuations_url: str = DEFAULT_PLAYER_VALUATIONS_URL,
    mapping_csv: str | None = None,
    engine: Engine | None = None,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> TeamValueSyncResult:
    ingested_at = parse_utc(now or datetime.now(UTC))
    repository = TeamValueRepository(engine=engine, settings=settings)
    sources = [open_source_file(players_url), open_source_file(player_valuations_url)]
    observations_seen = 0
    observations_inserted = 0
    snapshots = 0
    checksums: dict[str, str] = {}
    for source in sources:
        snapshot_id = repository.record_source_snapshot(
            source,
            ingested_at=ingested_at,
            payload={
                "upstream": "dcaribou/transfermarkt-datasets",
                "refresh_cadence": "weekly per upstream README",
                "raw_path": source.raw_path,
            },
        )
        snapshots += 1
        checksums[source.raw_path] = source.sha256_checksum
        if "player_valuations" in source.raw_path:
            observations = observations_from_player_valuations(source)
        elif "players" in source.raw_path:
            observations = observations_from_players(source, ingested_at=ingested_at)
        else:
            observations = []
        observations_seen += len(observations)
        observations_inserted += repository.upsert_observations(
            observations,
            source_snapshot_id=snapshot_id,
            ingested_at=ingested_at,
        )
    mappings = load_mappings_from_csv(
        mapping_csv,
        valid_from=datetime(1970, 1, 1, tzinfo=UTC),
    )
    mappings_inserted = repository.upsert_mappings(mappings, ingested_at=ingested_at)
    return TeamValueSyncResult(
        status="OK",
        snapshots=snapshots,
        observations_seen=observations_seen,
        observations_inserted=observations_inserted,
        mappings_seen=len(mappings),
        mappings_inserted=mappings_inserted,
        coverage=repository.coverage(),
        source_checksums=checksums,
    )


def transfermarkt_sync_enabled() -> bool:
    return os.environ.get("W2_TRANSFERMARKT_TEAM_VALUE_SYNC_ENABLED", "true").lower() == "true"


def transfermarkt_sync_interval_seconds() -> int:
    return int(os.environ.get("W2_TRANSFERMARKT_TEAM_VALUE_SYNC_INTERVAL_SECONDS", "604800"))


def build_team_value_lookup(
    *,
    home_team_id: str,
    away_team_id: str,
    as_of: datetime,
    repository: TeamValueRepository,
) -> TeamValueSignalLookup:
    home = repository.lookup_team_value(w2_team_id=home_team_id, as_of=as_of)
    away = repository.lookup_team_value(w2_team_id=away_team_id, as_of=as_of)
    if home is None or away is None:
        return TeamValueSignalLookup(
            home=home,
            away=away,
            status="VALUE_DATA_UNAVAILABLE",
            reason=(
                "VALUE_DATA_UNAVAILABLE: Transfermarkt mapping/value missing "
                "for one or both teams"
            ),
        )
    return TeamValueSignalLookup(
        home=home,
        away=away,
        status="READY",
        reason=(
            "球队身价来自 transfermarkt-datasets as-of 快照，低权重处理，"
            "通常已被赔率部分消化"
        ),
    )
