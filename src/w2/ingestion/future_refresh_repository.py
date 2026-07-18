from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, Float, case, cast, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.config import Settings
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.future_refresh_models import (
    FutureMarketObservationModel,
    FutureRefreshCheckpointAuditModel,
    FutureRefreshCheckpointPlanModel,
    FutureRefreshRunAuditModel,
    FutureRefreshTaskAuditModel,
    RawPayloadModel,
    TeamXgMatchModel,
    TeamXgRollingSnapshotModel,
)
from w2.infrastructure.persistence.ingestion_models import (
    ProviderRequestLogModel,
    QuotaUsageModel,
)
from w2.infrastructure.persistence.models import (
    LineupSourceSnapshotModel,
    PlayerIdentityMappingModel,
    PlayerValuationObservationModel,
    StructuredLineupPlayerModel,
    StructuredLineupSnapshotModel,
    TransfermarktPlayerReferenceModel,
)
from w2.lineups.intelligence import (
    PlayerIdentityCandidate,
    normalize_player_name,
    resolve_player_identity,
)


class FutureRefreshPersistenceError(RuntimeError):
    pass


SCOPED_OBSERVATION_ROWS_PER_MARKET = 128


def parse_db_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value:
        raise FutureRefreshPersistenceError("INVALID_DATETIME")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
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

    def save_lineup_snapshots(
        self,
        *,
        fixture_id: str,
        captured_at: datetime,
        raw_sha256: str,
        payload: dict[str, Any],
    ) -> int:
        response = payload.get("response")
        if not isinstance(response, list):
            raise FutureRefreshPersistenceError("LINEUP_RESPONSE_INVALID")
        snapshots: list[tuple[StructuredLineupSnapshotModel, list[dict[str, Any]]]] = []
        for team_row in response:
            if not isinstance(team_row, dict):
                continue
            team = team_row.get("team")
            team_id = str(team.get("id") or "") if isinstance(team, dict) else ""
            team_name = str(team.get("name") or "") if isinstance(team, dict) else ""
            if not team_id:
                continue
            starters = self._lineup_players(team_row.get("startXI"), starter=True)
            substitutes = self._lineup_players(team_row.get("substitutes"), starter=False)
            snapshots.append(
                (
                    StructuredLineupSnapshotModel(
                        fixture_id=fixture_id,
                        team_external_id=team_id,
                        team_name=team_name or team_id,
                        formation=str(team_row.get("formation") or "") or None,
                        captured_at=captured_at,
                        confirmed=len(starters) == 11,
                        authoritative_status="COMPLETE" if len(starters) == 11 else "INCOMPLETE",
                        raw_sha256=raw_sha256,
                        schema_version="w2.structured_lineup.v1",
                    ),
                    [*starters, *substitutes],
                )
            )
        if len(snapshots) < 2:
            raise FutureRefreshPersistenceError("LINEUP_TEAMS_INCOMPLETE")
        with Session(self.engine) as session:
            try:
                for snapshot, players in snapshots:
                    session.add(snapshot)
                    session.flush()
                    for player in players:
                        session.add(
                            StructuredLineupPlayerModel(
                                lineup_snapshot_id=snapshot.id,
                                mapping_status="MISSING",
                                **player,
                            )
                        )
                session.commit()
                materialized = len(snapshots)
            except IntegrityError:
                session.rollback()
                return 0
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("LINEUP_MATERIALIZATION_FAILED") from exc
        self.materialize_player_identity_mappings(fixture_id=fixture_id, as_of=captured_at)
        return materialized

    def materialize_player_identity_mappings(
        self,
        *,
        fixture_id: str,
        as_of: datetime,
    ) -> int:
        with Session(self.engine) as session:
            snapshots = session.scalars(
                select(StructuredLineupSnapshotModel)
                .where(
                    StructuredLineupSnapshotModel.fixture_id == fixture_id,
                    StructuredLineupSnapshotModel.captured_at <= as_of,
                )
                .order_by(StructuredLineupSnapshotModel.captured_at.desc())
            ).all()
            latest: dict[str, StructuredLineupSnapshotModel] = {}
            for snapshot in snapshots:
                latest.setdefault(snapshot.team_external_id, snapshot)
            pending: list[PlayerIdentityMappingModel] = []
            for snapshot in latest.values():
                players = session.scalars(
                    select(StructuredLineupPlayerModel).where(
                        StructuredLineupPlayerModel.lineup_snapshot_id == snapshot.id,
                        StructuredLineupPlayerModel.starter.is_(True),
                    )
                ).all()
                for player in players:
                    normalized = normalize_player_name(player.player_name)
                    references = session.scalars(
                        select(TransfermarktPlayerReferenceModel)
                        .where(
                            TransfermarktPlayerReferenceModel.normalized_name == normalized,
                            TransfermarktPlayerReferenceModel.observed_at <= as_of,
                        )
                        .order_by(TransfermarktPlayerReferenceModel.observed_at.desc())
                    ).all()
                    newest_by_id: dict[str, TransfermarktPlayerReferenceModel] = {}
                    for reference in references:
                        newest_by_id.setdefault(reference.transfermarkt_player_id, reference)
                    team_name = normalize_player_name(snapshot.team_name)
                    team_confirmed = [
                        reference
                        for reference in newest_by_id.values()
                        if reference.current_club_name
                        and (
                            team_name in normalize_player_name(reference.current_club_name)
                            or normalize_player_name(reference.current_club_name) in team_name
                        )
                    ]
                    resolution = resolve_player_identity(
                        api_football_player_id=player.api_football_player_id,
                        player_name=player.player_name,
                        team_external_id=snapshot.team_external_id,
                        provider_position=player.provider_position,
                        candidates=[
                            PlayerIdentityCandidate(
                                transfermarkt_player_id=reference.transfermarkt_player_id,
                                player_name=reference.player_name,
                                team_external_id=snapshot.team_external_id,
                                position=reference.position,
                            )
                            for reference in team_confirmed
                        ],
                    )
                    pending.append(
                        PlayerIdentityMappingModel(
                            api_football_player_id=player.api_football_player_id,
                            transfermarkt_player_id=resolution.transfermarkt_player_id,
                            team_external_id=snapshot.team_external_id,
                            player_name=player.player_name,
                            normalized_name=resolution.normalized_name,
                            provider_position=player.provider_position,
                            transfermarkt_position=team_confirmed[0].position
                            if len(team_confirmed) == 1
                            else None,
                            mapping_status=resolution.status.value,
                            evidence={
                                "reason": resolution.reason,
                                "candidate_ids": sorted(
                                    reference.transfermarkt_player_id
                                    for reference in team_confirmed
                                ),
                                "team_name": snapshot.team_name,
                            },
                            identity_hash=resolution.identity_hash,
                            valid_from=snapshot.captured_at,
                        )
                    )
            appended = 0
            for mapping in pending:
                try:
                    with session.begin_nested():
                        session.add(mapping)
                        session.flush()
                    appended += 1
                except IntegrityError:
                    continue
            session.commit()
            return appended

    def lineup_gate_evidence(
        self,
        *,
        fixture_id: str,
        as_of: datetime,
    ) -> dict[str, Any]:
        with Session(self.engine) as session:
            snapshots = session.scalars(
                select(StructuredLineupSnapshotModel)
                .where(
                    StructuredLineupSnapshotModel.fixture_id == fixture_id,
                    StructuredLineupSnapshotModel.captured_at <= as_of,
                )
                .order_by(StructuredLineupSnapshotModel.captured_at.desc())
            ).all()
            latest_by_team: dict[str, StructuredLineupSnapshotModel] = {}
            for snapshot in snapshots:
                latest_by_team.setdefault(snapshot.team_external_id, snapshot)
            selected = list(latest_by_team.values())
            if len(selected) != 2:
                return {
                    "status": "INCOMPLETE",
                    "confirmed": False,
                    "team_count": len(selected),
                    "starter_counts": [],
                    "uniquely_mapped_starters": 0,
                    "valued_starters": 0,
                    "formation_count": sum(bool(row.formation) for row in selected),
                    "blockers": ["LINEUP_SNAPSHOT_INCOMPLETE"],
                }
            starter_counts: list[int] = []
            mappings: list[PlayerIdentityMappingModel] = []
            for snapshot in selected:
                players = session.scalars(
                    select(StructuredLineupPlayerModel).where(
                        StructuredLineupPlayerModel.lineup_snapshot_id == snapshot.id,
                        StructuredLineupPlayerModel.starter.is_(True),
                    )
                ).all()
                starter_counts.append(len(players))
                api_ids = [player.api_football_player_id for player in players]
                team_mappings = session.scalars(
                    select(PlayerIdentityMappingModel)
                    .where(
                        PlayerIdentityMappingModel.api_football_player_id.in_(api_ids),
                        PlayerIdentityMappingModel.team_external_id == snapshot.team_external_id,
                        PlayerIdentityMappingModel.mapping_status == "MATCHED",
                        PlayerIdentityMappingModel.valid_from <= as_of,
                        (PlayerIdentityMappingModel.valid_to.is_(None))
                        | (PlayerIdentityMappingModel.valid_to > as_of),
                    )
                    .order_by(PlayerIdentityMappingModel.valid_from.desc())
                ).all()
                newest_mapping: dict[str, PlayerIdentityMappingModel] = {}
                for mapping in team_mappings:
                    newest_mapping.setdefault(mapping.api_football_player_id, mapping)
                mappings.extend(newest_mapping.values())
            transfermarkt_ids = {
                str(mapping.transfermarkt_player_id)
                for mapping in mappings
                if mapping.transfermarkt_player_id
            }
            valued_ids = set(
                session.scalars(
                    select(PlayerValuationObservationModel.transfermarkt_player_id)
                    .where(
                        PlayerValuationObservationModel.transfermarkt_player_id.in_(
                            transfermarkt_ids
                        ),
                        PlayerValuationObservationModel.observed_at <= as_of,
                    )
                    .distinct()
                ).all()
            )
            return {
                "status": "COMPLETE"
                if starter_counts == [11, 11] and len(mappings) == 22 and len(valued_ids) == 22
                else "INCOMPLETE",
                "confirmed": all(snapshot.confirmed for snapshot in selected),
                "team_count": 2,
                "starter_counts": starter_counts,
                "uniquely_mapped_starters": len(mappings),
                "valued_starters": len(valued_ids),
                "formation_count": sum(bool(snapshot.formation) for snapshot in selected),
                "captured_at": max(snapshot.captured_at for snapshot in selected).isoformat(),
                "raw_sha256": sorted({snapshot.raw_sha256 for snapshot in selected}),
                "schema_version": "w2.lineup_gate_evidence.v1",
            }

    def import_transfermarkt_player_snapshot(
        self,
        *,
        source_url: str,
        source_sha256: str,
        observed_at: datetime,
        rows: list[dict[str, Any]],
    ) -> int:
        with Session(self.engine) as session:
            try:
                session.add(
                    LineupSourceSnapshotModel(
                        source="TRANSFERMARKT_DATASET",
                        source_revision=source_sha256,
                        schema_version="w2.transfermarkt_players.v1",
                        object_uri=source_url,
                        sha256=source_sha256,
                        observed_at=observed_at,
                        ingested_at=datetime.now(UTC),
                    )
                )
                for row in rows:
                    session.add(TransfermarktPlayerReferenceModel(**row))
                    value = row.get("market_value_eur")
                    if value is not None:
                        session.add(
                            PlayerValuationObservationModel(
                                transfermarkt_player_id=row["transfermarkt_player_id"],
                                observed_at=observed_at,
                                market_value_eur=value,
                                source="TRANSFERMARKT_DATASET",
                                source_sha256=source_sha256,
                                schema_version="w2.transfermarkt_player_value.v1",
                            )
                        )
                session.commit()
                return len(rows)
            except IntegrityError:
                session.rollback()
                source_exists = session.scalar(
                    select(func.count(LineupSourceSnapshotModel.id)).where(
                        LineupSourceSnapshotModel.sha256 == source_sha256
                    )
                )
                if source_exists:
                    return 0
                raise FutureRefreshPersistenceError("TRANSFERMARKT_IMPORT_CONFLICT") from None
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("TRANSFERMARKT_IMPORT_FAILED") from exc

    def structured_lineup_fixture_ids(self) -> list[str]:
        with Session(self.engine) as session:
            return list(
                session.scalars(select(StructuredLineupSnapshotModel.fixture_id).distinct()).all()
            )

    def stored_lineup_materialization_candidates(
        self,
        *,
        limit: int = 512,
    ) -> list[dict[str, Any]]:
        """Return bounded, saved lineup payloads for an explicit offline materializer.

        This is an administrative migration reader, not a public-request fallback.
        Fixture identity must come from the parameters saved with the original
        provider response; rows without that identity are excluded fail closed.
        """
        bounded_limit = max(0, min(int(limit), 4096))
        if bounded_limit == 0:
            return []
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == "lineups")
                    .order_by(RawPayloadModel.captured_at, RawPayloadModel.sha256)
                    .limit(bounded_limit)
                )
            )
        candidates: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row.payload)
            parameters = payload.get("parameters")
            fixture_id = (
                str(parameters.get("fixture") or "")
                if isinstance(parameters, dict)
                else ""
            )
            if not fixture_id:
                continue
            candidates.append(
                {
                    "fixture_id": fixture_id,
                    "captured_at": parse_db_datetime(row.captured_at),
                    "raw_sha256": row.sha256,
                    "payload": payload,
                }
            )
        return candidates

    def materialize_stored_lineup_payloads(self, *, limit: int = 512) -> dict[str, int]:
        """Idempotently materialize already-saved lineup payloads without a provider call."""
        candidates = self.stored_lineup_materialization_candidates(limit=limit)
        materialized_snapshots = 0
        skipped_incomplete = 0
        for candidate in candidates:
            try:
                materialized_snapshots += self.save_lineup_snapshots(**candidate)
            except FutureRefreshPersistenceError as exc:
                if str(exc) in {"LINEUP_RESPONSE_INVALID", "LINEUP_TEAMS_INCOMPLETE"}:
                    skipped_incomplete += 1
                    continue
                raise
        return {
            "candidate_payload_count": len(candidates),
            "materialized_snapshot_count": materialized_snapshots,
            "skipped_incomplete_count": skipped_incomplete,
            "provider_calls": 0,
        }

    @staticmethod
    def _lineup_players(value: Any, *, starter: bool) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        players: list[dict[str, Any]] = []
        for wrapper in value:
            player = wrapper.get("player") if isinstance(wrapper, dict) else None
            if not isinstance(player, dict) or player.get("id") is None:
                continue
            players.append(
                {
                    "api_football_player_id": str(player["id"]),
                    "player_name": str(player.get("name") or ""),
                    "starter": starter,
                    "shirt_number": int(player["number"])
                    if player.get("number") is not None
                    else None,
                    "provider_position": str(player.get("pos") or "") or None,
                    "grid": str(player.get("grid") or "") or None,
                    "captain": bool(player.get("captain", False)),
                }
            )
        return players

    def append_observations(self, observations: list[dict[str, Any]]) -> int:
        try:
            models = [self._observation_model(row) for row in observations]
            appended = 0
            with Session(self.engine) as session:
                with session.begin():
                    for model in models:
                        try:
                            with session.begin_nested():
                                session.add(model)
                                session.flush()
                            appended += 1
                        except IntegrityError:
                            continue
        except Exception as exc:
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
        return self._latest_observation_dicts(rows)

    def latest_market_observations_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> list[dict[str, Any]]:
        ids = [fixture_id for fixture_id in dict.fromkeys(fixture_ids) if fixture_id]
        if not ids or len(ids) > 64:
            return []
        partition = (
            FutureMarketObservationModel.fixture_id,
            FutureMarketObservationModel.canonical_market,
            FutureMarketObservationModel.bookmaker_id,
            FutureMarketObservationModel.selection,
            FutureMarketObservationModel.line,
        )
        ranked = (
            select(
                FutureMarketObservationModel.observation_id.label("observation_id"),
                func.row_number()
                .over(
                    partition_by=partition,
                    order_by=FutureMarketObservationModel.captured_at.desc(),
                )
                .label("rank"),
            )
            .where(FutureMarketObservationModel.fixture_id.in_(ids))
            .subquery()
        )
        side = case(
            (func.lower(FutureMarketObservationModel.selection).like("home%"), "HOME"),
            (func.lower(FutureMarketObservationModel.selection).like("away%"), "AWAY"),
            (func.lower(FutureMarketObservationModel.selection).like("over%"), "OVER"),
            (func.lower(FutureMarketObservationModel.selection).like("under%"), "UNDER"),
            else_="OTHER",
        )
        full_time_label = func.lower(func.trim(FutureMarketObservationModel.raw_market_label))
        relevant_latest = (
            select(
                FutureMarketObservationModel.observation_id.label("observation_id"),
                FutureMarketObservationModel.fixture_id.label("fixture_id"),
                FutureMarketObservationModel.canonical_market.label("canonical_market"),
                FutureMarketObservationModel.bookmaker_id.label("bookmaker_id"),
                side.label("side"),
                func.row_number()
                .over(
                    partition_by=(
                        FutureMarketObservationModel.fixture_id,
                        FutureMarketObservationModel.canonical_market,
                        FutureMarketObservationModel.bookmaker_id,
                        side,
                    ),
                    order_by=(
                        func.abs(cast(FutureMarketObservationModel.decimal_odds, Float) - 1.9),
                        func.abs(cast(FutureMarketObservationModel.line, Float)),
                        FutureMarketObservationModel.selection,
                    ),
                )
                .label("side_rank"),
            )
            .join(ranked, FutureMarketObservationModel.observation_id == ranked.c.observation_id)
            .where(
                ranked.c.rank == 1,
                FutureMarketObservationModel.suspended.is_(False),
                FutureMarketObservationModel.live.is_(False),
                side != "OTHER",
                (
                    (FutureMarketObservationModel.canonical_market == "ASIAN_HANDICAP")
                    & (
                        (FutureMarketObservationModel.raw_market_label.is_(None))
                        | (full_time_label.in_(("", "asian handicap", "handicap", "ah")))
                    )
                )
                | (
                    (FutureMarketObservationModel.canonical_market == "TOTALS")
                    & (
                        (FutureMarketObservationModel.raw_market_label.is_(None))
                        | (
                            full_time_label.in_(
                                ("", "goals over/under", "total goals", "over/under")
                            )
                        )
                    )
                ),
            )
            .subquery()
        )
        market_ranked = (
            select(
                relevant_latest.c.observation_id,
                func.row_number()
                .over(
                    partition_by=(
                        relevant_latest.c.fixture_id,
                        relevant_latest.c.canonical_market,
                    ),
                    order_by=(
                        relevant_latest.c.side_rank,
                        relevant_latest.c.bookmaker_id,
                        relevant_latest.c.side,
                    ),
                )
                .label("market_rank"),
            )
            .where(relevant_latest.c.side_rank <= 12)
            .subquery()
        )
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(FutureMarketObservationModel)
                    .join(
                        market_ranked,
                        FutureMarketObservationModel.observation_id
                        == market_ranked.c.observation_id,
                    )
                    .where(market_ranked.c.market_rank <= SCOPED_OBSERVATION_ROWS_PER_MARKET)
                    .order_by(
                        FutureMarketObservationModel.fixture_id,
                        FutureMarketObservationModel.canonical_market,
                        FutureMarketObservationModel.bookmaker_id,
                        FutureMarketObservationModel.selection,
                    )
                    .limit(len(ids) * SCOPED_OBSERVATION_ROWS_PER_MARKET * 2)
                )
            )
        return self._latest_observation_dicts(rows)

    def _latest_observation_dicts(
        self,
        rows: list[FutureMarketObservationModel],
    ) -> list[dict[str, Any]]:
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

    def fixture_payloads(self, *, provider_league_id: str | None = None) -> list[dict[str, Any]]:
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
                if provider_league_id is not None:
                    league_id = str(item.get("league", {}).get("id") or "")
                    if league_id != provider_league_id:
                        continue
                fixture_id = str(item.get("fixture", {}).get("id"))
                if fixture_id and fixture_id != "None":
                    fixtures[fixture_id] = item
        return sorted(fixtures.values(), key=lambda item: item.get("fixture", {}).get("date", ""))

    def fixture_payload(self, fixture_id: str, *, payload_limit: int = 32) -> dict[str, Any] | None:
        """Find one fixture without scanning the complete raw-payload history."""
        bounded_limit = max(0, min(int(payload_limit), 128))
        if not fixture_id or bounded_limit == 0:
            return None
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == "fixtures")
                    .order_by(RawPayloadModel.captured_at.desc())
                    .limit(bounded_limit)
                )
            )
        for row in rows:
            response = row.payload.get("response")
            if not isinstance(response, list):
                continue
            for item in response[:256]:
                if not isinstance(item, dict):
                    continue
                if str(item.get("fixture", {}).get("id") or "") == fixture_id:
                    return item
        return None

    def fixture_payloads_bounded(
        self,
        *,
        payload_limit: int = 32,
        item_limit: int = 512,
    ) -> list[dict[str, Any]]:
        bounded_payloads = max(0, min(int(payload_limit), 128))
        bounded_items = max(0, min(int(item_limit), 1024))
        if bounded_payloads == 0 or bounded_items == 0:
            return []
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == "fixtures")
                    .order_by(RawPayloadModel.captured_at.desc())
                    .limit(bounded_payloads)
                )
            )
        fixtures: dict[str, dict[str, Any]] = {}
        for row in rows:
            response = row.payload.get("response")
            if not isinstance(response, list):
                continue
            for item in response[:bounded_items]:
                if not isinstance(item, dict):
                    continue
                fixture_id = str(item.get("fixture", {}).get("id") or "")
                if fixture_id and fixture_id not in fixtures:
                    fixtures[fixture_id] = item
                if len(fixtures) >= bounded_items:
                    return sorted(
                        fixtures.values(),
                        key=lambda value: value.get("fixture", {}).get("date", ""),
                    )
        return sorted(
            fixtures.values(),
            key=lambda value: value.get("fixture", {}).get("date", ""),
        )

    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == endpoint)
                    .order_by(RawPayloadModel.captured_at)
                )
            )
        return [
            {
                "sha256": row.sha256,
                "endpoint": row.endpoint,
                "captured_at": iso_z(row.captured_at),
                "payload": dict(row.payload),
            }
            for row in rows
        ]

    def raw_payloads_for_scope(
        self,
        endpoint: str,
        *,
        fixture_id: str | None = None,
        team_ids: list[str] | None = None,
        limit: int = 32,
    ) -> list[dict[str, Any]]:
        """Return a bounded set of raw payloads relevant to one public request."""
        bounded_limit = max(0, min(int(limit), 128))
        if bounded_limit == 0 or (fixture_id is None and not team_ids):
            return []
        wanted_teams = {str(team_id) for team_id in team_ids or [] if str(team_id)}
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == endpoint)
                    .order_by(RawPayloadModel.captured_at.desc())
                    .limit(bounded_limit)
                )
            )
        scoped: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row.payload)
            parameters = payload.get("parameters")
            parameters = parameters if isinstance(parameters, dict) else {}
            parameter_fixture = str(parameters.get("fixture") or "")
            parameter_team = str(parameters.get("team") or "")
            parameter_h2h = {
                value
                for value in str(parameters.get("h2h") or "").replace("-", "_").split("_")
                if value
            }
            fixture_match = fixture_id is not None and parameter_fixture == fixture_id
            team_match = bool(wanted_teams) and (
                parameter_team in wanted_teams or wanted_teams <= parameter_h2h
            )
            if not fixture_match and not team_match:
                continue
            scoped.append(
                {
                    "sha256": row.sha256,
                    "endpoint": row.endpoint,
                    "captured_at": iso_z(row.captured_at),
                    "payload": payload,
                }
            )
        return scoped

    def upsert_team_xg_matches(self, matches: list[dict[str, Any]]) -> int:
        upserted = 0
        with Session(self.engine) as session:
            for row in matches:
                model = TeamXgMatchModel(
                    id=str(row["id"]),
                    fixture_id=str(row["fixture_id"]),
                    team_id=str(row["team_id"]),
                    opponent_team_id=str(row["opponent_team_id"]),
                    kickoff_at=parse_db_datetime(row["kickoff_at"]),
                    captured_at=parse_db_datetime(row["captured_at"]),
                    xg_for=float(row["xg_for"]),
                    xg_against=float(row["xg_against"]),
                    goals_for=int(row["goals_for"]),
                    goals_against=int(row["goals_against"]),
                    raw_payload_sha256=str(row["raw_payload_sha256"]),
                    source_system=str(row["source_system"]),
                    candidate=False,
                    formal_recommendation=False,
                )
                session.merge(model)
                upserted += 1
            try:
                session.commit()
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("TEAM_XG_MATCH_WRITE_FAILED") from exc
        return upserted

    def team_xg_matches(self) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(TeamXgMatchModel).order_by(
                        TeamXgMatchModel.team_id,
                        TeamXgMatchModel.kickoff_at,
                    )
                )
            )
        return [self._team_xg_match_dict(row) for row in rows]

    def team_xg_matches_for_teams(
        self,
        team_ids: list[str],
        *,
        before: datetime,
        limit_per_team: int = 20,
    ) -> list[dict[str, Any]]:
        ids = [team_id for team_id in dict.fromkeys(team_ids) if team_id]
        bounded_limit = max(0, min(int(limit_per_team), 50))
        if not ids or bounded_limit == 0:
            return []
        ranked = (
            select(
                TeamXgMatchModel.id.label("id"),
                func.row_number()
                .over(
                    partition_by=TeamXgMatchModel.team_id,
                    order_by=TeamXgMatchModel.kickoff_at.desc(),
                )
                .label("rank"),
            )
            .where(
                TeamXgMatchModel.team_id.in_(ids),
                TeamXgMatchModel.kickoff_at < before,
            )
            .subquery()
        )
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(TeamXgMatchModel)
                    .join(ranked, TeamXgMatchModel.id == ranked.c.id)
                    .where(ranked.c.rank <= bounded_limit)
                    .order_by(TeamXgMatchModel.team_id, TeamXgMatchModel.kickoff_at)
                )
            )
        return [self._team_xg_match_dict(row) for row in rows]

    @staticmethod
    def _team_xg_match_dict(row: TeamXgMatchModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "fixture_id": row.fixture_id,
            "team_id": row.team_id,
            "opponent_team_id": row.opponent_team_id,
            "kickoff_at": iso_z(row.kickoff_at),
            "captured_at": iso_z(row.captured_at),
            "xg_for": row.xg_for,
            "xg_against": row.xg_against,
            "goals_for": row.goals_for,
            "goals_against": row.goals_against,
            "raw_payload_sha256": row.raw_payload_sha256,
            "source_system": row.source_system,
            "candidate": False,
            "formal_recommendation": False,
        }

    def upsert_team_xg_rolling_snapshots(self, snapshots: list[dict[str, Any]]) -> int:
        upserted = 0
        with Session(self.engine) as session:
            for row in snapshots:
                session.merge(
                    TeamXgRollingSnapshotModel(
                        snapshot_id=str(row["snapshot_id"]),
                        team_id=str(row["team_id"]),
                        as_of_fixture_id=str(row["as_of_fixture_id"]),
                        as_of_time=parse_db_datetime(row["as_of_time"]),
                        match_count=int(row["match_count"]),
                        rolling_xg_for=float(row["rolling_xg_for"]),
                        rolling_xg_against=float(row["rolling_xg_against"]),
                        rolling_goals_for=float(row["rolling_goals_for"]),
                        rolling_goals_against=float(row["rolling_goals_against"]),
                        regression_index=float(row["regression_index"]),
                        source_system=str(row["source_system"]),
                        candidate=False,
                        formal_recommendation=False,
                    )
                )
                upserted += 1
            try:
                session.commit()
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("TEAM_XG_SNAPSHOT_WRITE_FAILED") from exc
        return upserted

    def team_xg_rolling_snapshots(
        self,
        *,
        fixture_id: str | None = None,
        team_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            query = select(TeamXgRollingSnapshotModel)
            if fixture_id is not None:
                query = query.where(TeamXgRollingSnapshotModel.as_of_fixture_id == fixture_id)
            if team_id is not None:
                query = query.where(TeamXgRollingSnapshotModel.team_id == team_id)
            rows = list(
                session.scalars(
                    query.order_by(
                        TeamXgRollingSnapshotModel.team_id,
                        TeamXgRollingSnapshotModel.as_of_time,
                    )
                )
            )
        return [self._team_xg_rolling_snapshot_dict(row) for row in rows]

    def team_xg_rolling_snapshots_for_teams(
        self,
        team_ids: list[str],
        *,
        before: datetime,
    ) -> list[dict[str, Any]]:
        ids = [team_id for team_id in dict.fromkeys(team_ids) if team_id]
        if not ids or len(ids) > 2:
            return []
        ranked = (
            select(
                TeamXgRollingSnapshotModel.snapshot_id.label("snapshot_id"),
                func.row_number()
                .over(
                    partition_by=TeamXgRollingSnapshotModel.team_id,
                    order_by=TeamXgRollingSnapshotModel.as_of_time.desc(),
                )
                .label("rank"),
            )
            .where(
                TeamXgRollingSnapshotModel.team_id.in_(ids),
                TeamXgRollingSnapshotModel.as_of_time < before,
            )
            .subquery()
        )
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(TeamXgRollingSnapshotModel)
                    .join(
                        ranked,
                        TeamXgRollingSnapshotModel.snapshot_id == ranked.c.snapshot_id,
                    )
                    .where(ranked.c.rank == 1)
                    .order_by(TeamXgRollingSnapshotModel.team_id)
                    .limit(2)
                )
            )
        return [self._team_xg_rolling_snapshot_dict(row) for row in rows]

    @staticmethod
    def _team_xg_rolling_snapshot_dict(
        row: TeamXgRollingSnapshotModel,
    ) -> dict[str, Any]:
        return {
            "snapshot_id": row.snapshot_id,
            "team_id": row.team_id,
            "as_of_fixture_id": row.as_of_fixture_id,
            "as_of_time": iso_z(row.as_of_time),
            "match_count": row.match_count,
            "rolling_xg_for": row.rolling_xg_for,
            "rolling_xg_against": row.rolling_xg_against,
            "rolling_goals_for": row.rolling_goals_for,
            "rolling_goals_against": row.rolling_goals_against,
            "regression_index": row.regression_index,
            "source_system": row.source_system,
            "candidate": False,
            "formal_recommendation": False,
        }

    def market_snapshots(self) -> list[dict[str, Any]]:
        observations = self.latest_market_observations()
        return self._market_snapshots_from_observations(observations)

    def market_snapshots_for_fixture(self, fixture_id: str) -> list[dict[str, Any]]:
        observations = self.latest_market_observations_for_fixtures([fixture_id])
        return self._market_snapshots_from_observations(observations)

    def _market_snapshots_from_observations(
        self,
        observations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
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

    def task_key_exists(self, key: str) -> bool:
        with Session(self.engine) as session:
            row = session.scalar(
                select(FutureRefreshTaskAuditModel.task_id)
                .where(
                    FutureRefreshTaskAuditModel.key == key,
                    FutureRefreshTaskAuditModel.status == "COMPLETED",
                )
                .limit(1)
            )
        return row is not None

    def upsert_checkpoint_plans(self, plans: list[dict[str, Any]]) -> int:
        if not plans:
            return 0
        upserted = 0
        with Session(self.engine) as session:
            for row in plans:
                plan_id = str(row["id"])
                existing = session.get(FutureRefreshCheckpointPlanModel, plan_id)
                if existing is not None and existing.status == "COMPLETED":
                    continue
                session.merge(
                    FutureRefreshCheckpointPlanModel(
                        id=plan_id,
                        fixture_id=str(row["fixture_id"]),
                        checkpoint=str(row["checkpoint"]),
                        kickoff_utc=parse_db_datetime(row["kickoff_utc"]),
                        due_at=parse_db_datetime(row["due_at"]),
                        endpoints=list(row["endpoints"]),
                        source=str(row["source"]),
                        status=str(row.get("status") or "PENDING"),
                        executed_at=(
                            parse_db_datetime(row["executed_at"])
                            if row.get("executed_at")
                            else None
                        ),
                        last_audit_id=row.get("last_audit_id"),
                    )
                )
                upserted += 1
            try:
                session.commit()
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("CHECKPOINT_PLAN_WRITE_FAILED") from exc
        return upserted

    def due_checkpoint_plans(
        self,
        *,
        now: datetime,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        current = parse_db_datetime(now)
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(FutureRefreshCheckpointPlanModel)
                    .where(
                        FutureRefreshCheckpointPlanModel.status == "PENDING",
                        FutureRefreshCheckpointPlanModel.due_at <= current,
                    )
                    .order_by(
                        FutureRefreshCheckpointPlanModel.due_at,
                        FutureRefreshCheckpointPlanModel.kickoff_utc,
                        FutureRefreshCheckpointPlanModel.fixture_id,
                        FutureRefreshCheckpointPlanModel.checkpoint,
                    )
                    .limit(limit)
                )
            )
        return [self._checkpoint_plan_dict(row) for row in rows]

    def market_refresh_status_for_fixtures(
        self,
        fixture_ids: list[str],
        *,
        now: datetime | None = None,
    ) -> dict[str, str | None]:
        ids = [fixture_id for fixture_id in dict.fromkeys(fixture_ids) if fixture_id]
        if not ids or len(ids) > 64:
            return {"odds_last_confirmed_at": None, "next_refresh_tick": None}
        reference = parse_db_datetime(now or datetime.now(UTC))
        with Session(self.engine) as session:
            odds_last_confirmed_at = session.scalar(
                select(func.max(FutureMarketObservationModel.captured_at)).where(
                    FutureMarketObservationModel.fixture_id.in_(ids),
                    FutureMarketObservationModel.live.is_(False),
                )
            )
            next_refresh_tick = session.scalar(
                select(func.min(FutureRefreshCheckpointPlanModel.due_at)).where(
                    FutureRefreshCheckpointPlanModel.fixture_id.in_(ids),
                    FutureRefreshCheckpointPlanModel.status == "PENDING",
                    FutureRefreshCheckpointPlanModel.due_at >= reference,
                )
            )
        return {
            "odds_last_confirmed_at": (
                iso_z(odds_last_confirmed_at) if odds_last_confirmed_at is not None else None
            ),
            "next_refresh_tick": (
                iso_z(next_refresh_tick) if next_refresh_tick is not None else None
            ),
        }

    def next_market_refresh_by_fixture(
        self,
        fixture_ids: list[str],
        *,
        now: datetime | None = None,
    ) -> dict[str, str]:
        ids = [fixture_id for fixture_id in dict.fromkeys(fixture_ids) if fixture_id]
        if not ids or len(ids) > 64:
            return {}
        reference = parse_db_datetime(now or datetime.now(UTC))
        with Session(self.engine) as session:
            rows = session.execute(
                select(
                    FutureRefreshCheckpointPlanModel.fixture_id,
                    func.min(FutureRefreshCheckpointPlanModel.due_at),
                )
                .where(
                    FutureRefreshCheckpointPlanModel.fixture_id.in_(ids),
                    FutureRefreshCheckpointPlanModel.status == "PENDING",
                    FutureRefreshCheckpointPlanModel.due_at >= reference,
                )
                .group_by(FutureRefreshCheckpointPlanModel.fixture_id)
            ).all()
        return {str(fixture_id): iso_z(due_at) for fixture_id, due_at in rows}

    def write_checkpoint_audit(
        self,
        *,
        fixture_id: str,
        checkpoint: str,
        as_of: datetime,
        calls_used: int,
        status: str,
        details: dict[str, Any],
    ) -> int:
        with Session(self.engine) as session:
            try:
                audit = FutureRefreshCheckpointAuditModel(
                    fixture_id=str(fixture_id),
                    checkpoint=str(checkpoint),
                    as_of=parse_db_datetime(as_of),
                    calls_used=int(calls_used),
                    status=str(status),
                    details=dict(details),
                )
                session.add(audit)
                plan = session.get(
                    FutureRefreshCheckpointPlanModel,
                    f"{fixture_id}:{checkpoint}",
                )
                if plan is not None and status in {"COMPLETED", "BLOCKED", "PARTIAL_FAILED"}:
                    plan.status = status
                    plan.executed_at = parse_db_datetime(as_of)
                    session.flush()
                    plan.last_audit_id = audit.id
                session.commit()
                return int(audit.id)
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("CHECKPOINT_AUDIT_WRITE_FAILED") from exc

    def _checkpoint_plan_dict(self, row: FutureRefreshCheckpointPlanModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "fixture_id": row.fixture_id,
            "checkpoint": row.checkpoint,
            "kickoff_utc": iso_z(row.kickoff_utc),
            "due_at": iso_z(row.due_at),
            "endpoints": list(row.endpoints),
            "source": row.source,
            "status": row.status,
            "executed_at": iso_z(row.executed_at) if row.executed_at is not None else None,
            "last_audit_id": row.last_audit_id,
        }

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

    def request_count_since(self, since: datetime, *, include_quota_usage: bool = True) -> int:
        since_utc = parse_db_datetime(since)
        day_start = since_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        try:
            with Session(self.engine) as session:
                future_refresh_requests = session.scalar(
                    select(
                        func.coalesce(func.sum(FutureRefreshRunAuditModel.request_count), 0)
                    ).where(FutureRefreshRunAuditModel.generated_at >= since_utc)
                )
                provider_request_logs = session.scalar(
                    select(func.count())
                    .select_from(ProviderRequestLogModel)
                    .where(
                        ProviderRequestLogModel.provider == "api_football",
                        ProviderRequestLogModel.requested_at >= since_utc,
                    )
                )
                quota_usage = (
                    session.scalar(
                        select(func.coalesce(func.max(QuotaUsageModel.used), 0)).where(
                            QuotaUsageModel.provider == "api_football",
                            QuotaUsageModel.window_start >= day_start,
                            QuotaUsageModel.window_start < day_end,
                        )
                    )
                    if include_quota_usage
                    else 0
                )
        except Exception as exc:
            raise FutureRefreshPersistenceError("REQUEST_COUNT_READ_FAILED") from exc
        return max(
            int(future_refresh_requests or 0),
            int(provider_request_logs or 0),
            int(quota_usage or 0),
        )

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
