from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.historical.formal_ah import parse_utc, stable_hash
from w2.infrastructure.persistence.models import (
    CanonicalHistoricalAhFactModel,
    HistoricalMarketSourceSnapshotModel,
    PlayerClubMembershipObservationModel,
    TeamIdentityCrosswalkModel,
    TeamValueAsOfArtifactModel,
)


@dataclass(frozen=True, kw_only=True)
class FahWriteSummary:
    attempted: int = 0
    inserted: int = 0
    skipped_identical: int = 0
    conflicts: int = 0
    rejected: int = 0
    committed: bool = False
    rolled_back: bool = False
    db_writes: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class FahDataFoundationRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @classmethod
    def from_url(cls, database_url: str) -> FahDataFoundationRepository:
        return cls(create_engine(database_url, pool_pre_ping=True))

    def write_team_crosswalks(
        self,
        rows: Iterable[Mapping[str, Any]],
    ) -> FahWriteSummary:
        return self._write(
            rows,
            model=TeamIdentityCrosswalkModel,
            hash_key="crosswalk_hash",
            factory=_team_crosswalk_model,
        )

    def write_team_value_artifacts(
        self,
        rows: Iterable[Mapping[str, Any]],
    ) -> FahWriteSummary:
        return self._write(
            rows,
            model=TeamValueAsOfArtifactModel,
            hash_key="artifact_hash",
            factory=_team_value_model,
        )

    def write_canonical_ah_facts(
        self,
        rows: Iterable[Mapping[str, Any]],
    ) -> FahWriteSummary:
        return self._write(
            rows,
            model=CanonicalHistoricalAhFactModel,
            hash_key="fact_hash",
            factory=_canonical_ah_model,
        )

    def write_source_snapshots(
        self,
        rows: Iterable[Mapping[str, Any]],
    ) -> FahWriteSummary:
        return self._write(
            rows,
            model=HistoricalMarketSourceSnapshotModel,
            hash_key="snapshot_hash",
            factory=_source_snapshot_model,
            identity_fields=("source_id", "sha256"),
        )

    def write_player_memberships(
        self,
        rows: Iterable[Mapping[str, Any]],
    ) -> FahWriteSummary:
        return self._write(
            rows,
            model=PlayerClubMembershipObservationModel,
            hash_key="membership_hash",
            factory=_player_membership_model,
        )

    def _write(
        self,
        rows: Iterable[Mapping[str, Any]],
        *,
        model: type[Any],
        hash_key: str,
        factory: Any,
        identity_fields: tuple[str, ...] = (),
    ) -> FahWriteSummary:
        attempted = inserted = skipped = conflicts = rejected = 0
        with Session(self.engine) as session:
            try:
                for row in rows:
                    attempted += 1
                    row_hash = str(row.get(hash_key) or "")
                    if not row_hash and identity_fields:
                        row_hash = stable_hash({field: row.get(field) for field in identity_fields})
                    if not row_hash:
                        rejected += 1
                        continue
                    existing = _existing(session, model, hash_key, row_hash, identity_fields, row)
                    payload_hash = stable_hash(dict(row))
                    if existing is not None:
                        if stable_hash(_stored_payload(existing)) == payload_hash:
                            skipped += 1
                            continue
                        conflicts += 1
                        raise ValueError(f"FAH_CONFLICT:{model.__tablename__}:{row_hash}")
                    session.add(factory(row))
                    inserted += 1
                session.commit()
            except Exception:
                session.rollback()
                return FahWriteSummary(
                    attempted=attempted,
                    inserted=0,
                    skipped_identical=skipped,
                    conflicts=conflicts,
                    rejected=rejected,
                    committed=False,
                    rolled_back=True,
                    db_writes=False,
                )
        return FahWriteSummary(
            attempted=attempted,
            inserted=inserted,
            skipped_identical=skipped,
            conflicts=conflicts,
            rejected=rejected,
            committed=True,
            rolled_back=False,
            db_writes=inserted > 0,
        )


def _existing(
    session: Session,
    model: type[Any],
    hash_key: str,
    row_hash: str,
    identity_fields: tuple[str, ...],
    row: Mapping[str, Any],
) -> Any | None:
    if hasattr(model, hash_key):
        return session.scalars(select(model).where(getattr(model, hash_key) == row_hash)).first()
    clauses = [getattr(model, field) == str(row.get(field) or "") for field in identity_fields]
    if clauses:
        return session.scalars(select(model).where(*clauses)).first()
    return None


def _stored_payload(model: Any) -> dict[str, Any]:
    payload = getattr(model, "payload", None)
    if isinstance(payload, dict):
        return payload
    audit_payload = getattr(model, "audit_payload", None)
    if isinstance(audit_payload, dict):
        return audit_payload
    return {}


def _team_crosswalk_model(row: Mapping[str, Any]) -> TeamIdentityCrosswalkModel:
    return TeamIdentityCrosswalkModel(
        api_football_team_id=str(row.get("api_football_team_id") or ""),
        transfermarkt_club_id=str(row.get("transfermarkt_club_id") or ""),
        competition_id=str(row.get("competition_id") or ""),
        valid_from=_required_time(row.get("valid_from")),
        valid_to=parse_utc(row.get("valid_to")),
        review_status=str(row.get("review_status") or ""),
        crosswalk_hash=str(row.get("crosswalk_hash") or ""),
        payload=dict(row),
    )


def _team_value_model(row: Mapping[str, Any]) -> TeamValueAsOfArtifactModel:
    return TeamValueAsOfArtifactModel(
        team_external_id=str(row.get("team_external_id") or ""),
        transfermarkt_club_id=str(row.get("transfermarkt_club_id") or ""),
        competition_id=str(row.get("competition_id") or ""),
        as_of=_required_time(row.get("as_of")),
        status=str(row.get("status") or ""),
        artifact_hash=str(row.get("artifact_hash") or ""),
        payload=dict(row),
    )


def _canonical_ah_model(row: Mapping[str, Any]) -> CanonicalHistoricalAhFactModel:
    return CanonicalHistoricalAhFactModel(
        fact_id=str(row.get("fact_id") or ""),
        fact_hash=str(row.get("fact_hash") or ""),
        source_snapshot_id=str(row.get("source_snapshot_id") or ""),
        provider_fixture_id=str(row.get("provider_fixture_id") or ""),
        competition_id=str(row.get("competition_id") or ""),
        season=str(row.get("season") or ""),
        kickoff_utc=_required_time(row.get("kickoff_utc")),
        home_team_provider_id=str(row.get("home_team_provider_id") or ""),
        away_team_provider_id=str(row.get("away_team_provider_id") or ""),
        bookmaker_id=str(row.get("bookmaker_id") or ""),
        quote_captured_at=_required_time(row.get("quote_captured_at")),
        quote_identity_hash=str(row.get("quote_identity_hash") or ""),
        result_identity_hash=str(row.get("result_identity_hash") or ""),
        home_settlement=str(row.get("home_settlement") or ""),
        away_settlement=str(row.get("away_settlement") or ""),
        payload=dict(row),
    )


def _source_snapshot_model(row: Mapping[str, Any]) -> HistoricalMarketSourceSnapshotModel:
    return HistoricalMarketSourceSnapshotModel(
        source_id=str(row.get("source_id") or ""),
        provider=str(row.get("provider") or ""),
        schema_version=str(row.get("schema_version") or ""),
        object_uri=str(row.get("object_uri") or row.get("local_path_or_object_uri") or ""),
        sha256=str(row.get("sha256") or row.get("source_sha256") or ""),
        license_status=str(row.get("license_status") or row.get("source_license_status") or ""),
        observed_at=parse_utc(row.get("observed_at")),
        ingested_at=parse_utc(row.get("ingested_at")) or datetime.now(tz=UTC),
        row_count=int(row.get("row_count") or 0),
        audit_payload=dict(row),
    )


def _player_membership_model(row: Mapping[str, Any]) -> PlayerClubMembershipObservationModel:
    return PlayerClubMembershipObservationModel(
        transfermarkt_player_id=str(row.get("transfermarkt_player_id") or ""),
        transfermarkt_club_id=str(
            row.get("transfermarkt_club_id") or row.get("club_id") or ""
        ),
        observed_at=_required_time(row.get("observed_at") or row.get("snapshot_date")),
        source_sha256=str(row.get("source_sha256") or row.get("_source_sha256") or ""),
        payload=dict(row),
    )


def _required_time(value: object) -> datetime:
    parsed = parse_utc(value)
    if parsed is None:
        raise ValueError("FAH_TIMESTAMP_REQUIRED")
    return parsed
