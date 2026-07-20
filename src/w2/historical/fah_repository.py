from __future__ import annotations

import json
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
    PlayerIdentityCrosswalkModel,
    RegisteredRosterSnapshotModel,
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
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class FahDataFoundationRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @classmethod
    def from_url(cls, database_url: str) -> FahDataFoundationRepository:
        return cls(create_engine(database_url, pool_pre_ping=True))

    def import_team_crosswalks(
        self,
        rows: Iterable[Mapping[str, Any]],
    ) -> FahWriteSummary:
        return self._write(
            rows,
            model=TeamIdentityCrosswalkModel,
            hash_key="crosswalk_hash",
            natural_key=_team_crosswalk_identity,
            factory=_team_crosswalk_model,
            identity_fields=("api_football_team_id", "competition_id", "valid_from"),
        )

    write_team_crosswalks = import_team_crosswalks

    def import_player_crosswalks(
        self,
        rows: Iterable[Mapping[str, Any]],
    ) -> FahWriteSummary:
        return self._write(
            rows,
            model=PlayerIdentityCrosswalkModel,
            hash_key="crosswalk_hash",
            natural_key=_player_crosswalk_identity,
            factory=_player_crosswalk_model,
            identity_fields=("api_football_player_id", "competition_id", "valid_from"),
        )

    def import_registered_roster_snapshots(
        self,
        rows: Iterable[Mapping[str, Any]],
    ) -> FahWriteSummary:
        return self._write(
            rows,
            model=RegisteredRosterSnapshotModel,
            hash_key="membership_hash",
            natural_key=_registered_roster_identity,
            factory=_registered_roster_model,
        )

    def import_team_value_artifacts(
        self,
        rows: Iterable[Mapping[str, Any]],
    ) -> FahWriteSummary:
        return self._write(
            rows,
            model=TeamValueAsOfArtifactModel,
            hash_key="artifact_hash",
            natural_key=_team_value_identity,
            factory=_team_value_model,
        )

    write_team_value_artifacts = import_team_value_artifacts

    def import_canonical_ah_facts(
        self,
        rows: Iterable[Mapping[str, Any]],
    ) -> FahWriteSummary:
        return self._write(
            rows,
            model=CanonicalHistoricalAhFactModel,
            hash_key="fact_hash",
            natural_key=_canonical_ah_identity,
            factory=_canonical_ah_model,
        )

    write_canonical_ah_facts = import_canonical_ah_facts

    def import_source_snapshots(
        self,
        rows: Iterable[Mapping[str, Any]],
    ) -> FahWriteSummary:
        return self._write(
            rows,
            model=HistoricalMarketSourceSnapshotModel,
            hash_key="snapshot_hash",
            natural_key=_source_snapshot_identity,
            factory=_source_snapshot_model,
            identity_fields=("source_id", "sha256"),
        )

    write_source_snapshots = import_source_snapshots

    def import_player_memberships(
        self,
        rows: Iterable[Mapping[str, Any]],
    ) -> FahWriteSummary:
        return self._write(
            rows,
            model=PlayerClubMembershipObservationModel,
            hash_key="membership_hash",
            natural_key=_player_membership_identity,
            factory=_player_membership_model,
        )

    write_player_memberships = import_player_memberships

    def historical_ah_facts_for_teams(
        self,
        *,
        team_ids: Iterable[str],
        competition_id: str,
        as_of: datetime,
    ) -> list[dict[str, Any]]:
        teams = {str(item) for item in team_ids}
        with Session(self.engine) as session:
            rows = session.scalars(
                select(CanonicalHistoricalAhFactModel).where(
                    CanonicalHistoricalAhFactModel.competition_id == competition_id,
                    CanonicalHistoricalAhFactModel.kickoff_utc < as_of,
                )
            ).all()
        return [
            dict(row.payload)
            for row in rows
            if row.home_team_provider_id in teams or row.away_team_provider_id in teams
        ]

    def team_crosswalk_at(
        self,
        *,
        api_football_team_id: str,
        competition_id: str,
        as_of: datetime,
    ) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(TeamIdentityCrosswalkModel).where(
                    TeamIdentityCrosswalkModel.api_football_team_id == api_football_team_id,
                    TeamIdentityCrosswalkModel.competition_id == competition_id,
                    TeamIdentityCrosswalkModel.review_status == "APPROVED",
                    TeamIdentityCrosswalkModel.valid_from <= as_of,
                )
            ).all()
        valid = [row for row in rows if row.valid_to is None or as_of < row.valid_to]
        return dict(valid[-1].payload) if len(valid) == 1 else None

    def player_crosswalks_for_roster(
        self,
        *,
        api_football_team_id: str,
        competition_id: str,
        as_of: datetime,
    ) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(PlayerIdentityCrosswalkModel).where(
                    PlayerIdentityCrosswalkModel.api_football_team_id == api_football_team_id,
                    PlayerIdentityCrosswalkModel.competition_id == competition_id,
                    PlayerIdentityCrosswalkModel.review_status == "APPROVED",
                    PlayerIdentityCrosswalkModel.valid_from <= as_of,
                )
            ).all()
        return [dict(row.payload) for row in rows if row.valid_to is None or as_of < row.valid_to]

    def registered_roster_at(
        self,
        *,
        transfermarkt_club_id: str,
        as_of: datetime,
    ) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(RegisteredRosterSnapshotModel).where(
                    RegisteredRosterSnapshotModel.transfermarkt_club_id == transfermarkt_club_id,
                    RegisteredRosterSnapshotModel.snapshot_date <= as_of,
                    RegisteredRosterSnapshotModel.snapshot_status == "COMPLETE",
                )
            ).all()
        if not rows:
            return []
        latest = max(row.snapshot_date for row in rows)
        return [dict(row.payload) for row in rows if row.snapshot_date == latest]

    def team_value_artifact_at(
        self,
        *,
        team_external_id: str,
        competition_id: str,
        as_of: datetime,
    ) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(TeamValueAsOfArtifactModel).where(
                    TeamValueAsOfArtifactModel.team_external_id == team_external_id,
                    TeamValueAsOfArtifactModel.competition_id == competition_id,
                    TeamValueAsOfArtifactModel.as_of <= as_of,
                )
            ).all()
        if not rows:
            return None
        return dict(max(rows, key=lambda row: row.as_of).payload)

    def _write(
        self,
        rows: Iterable[Mapping[str, Any]],
        *,
        model: type[Any],
        hash_key: str,
        natural_key: Any,
        factory: Any,
        identity_fields: tuple[str, ...] = (),
    ) -> FahWriteSummary:
        attempted = inserted = skipped = conflicts = rejected = 0
        with Session(self.engine) as session:
            try:
                for row in rows:
                    attempted += 1
                    row_hash = str(row.get(hash_key) or "")
                    row_identity = natural_key(row)
                    if not row_hash:
                        row_hash = row_identity
                    if not row_hash and identity_fields:
                        row_hash = stable_hash({field: row.get(field) for field in identity_fields})
                    if not row_hash:
                        rejected += 1
                        continue
                    existing = _existing(
                        session,
                        model,
                        hash_key,
                        row_hash,
                        identity_fields,
                        row,
                        row_identity,
                    )
                    payload_hash = stable_hash(dict(row))
                    if existing is not None:
                        stored_hash = _stored_hash(existing, hash_key)
                        hash_matches = stored_hash == row_hash or not hasattr(model, hash_key)
                        if hash_matches and stable_hash(_stored_payload(existing)) == payload_hash:
                            skipped += 1
                            continue
                        conflicts += 1
                        raise ValueError(f"FAH_CONFLICT:{model.__tablename__}:{row_identity}")
                    model_instance = (
                        factory(row, session)
                        if factory is _canonical_ah_model
                        else factory(row)
                    )
                    session.add(model_instance)
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
                    error="FAH_WRITE_ROLLED_BACK",
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
    row_identity: str,
) -> Any | None:
    for field in ("natural_identity", "canonical_key", "membership_hash", "crosswalk_hash"):
        if hasattr(model, field) and row_identity:
            found = session.scalars(
                select(model).where(getattr(model, field) == row_identity)
            ).first()
            if found is not None:
                return found
    if hasattr(model, hash_key):
        found = session.scalars(select(model).where(getattr(model, hash_key) == row_hash)).first()
        if found is not None:
            return found
    clauses = [
        getattr(model, field) == _identity_value(field, row.get(field))
        for field in identity_fields
    ]
    if clauses:
        return session.scalars(select(model).where(*clauses)).first()
    return None


def _stored_hash(model: Any, hash_key: str) -> str:
    value = getattr(model, hash_key, "")
    return str(value or "")


def _identity_value(field: str, value: object) -> object:
    if field.endswith("_at") or field in {"valid_from", "valid_to", "as_of", "observed_at"}:
        return parse_utc(value)
    return str(value or "")


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
        source_sha256=str(row.get("source_sha256") or ""),
        reviewed_by=str(row.get("reviewed_by") or "") or None,
        reviewed_at=parse_utc(row.get("reviewed_at")),
        crosswalk_hash=str(row.get("crosswalk_hash") or ""),
        payload=dict(row),
    )


def _player_crosswalk_model(row: Mapping[str, Any]) -> PlayerIdentityCrosswalkModel:
    return PlayerIdentityCrosswalkModel(
        api_football_player_id=str(row.get("api_football_player_id") or ""),
        transfermarkt_player_id=str(row.get("transfermarkt_player_id") or ""),
        api_football_team_id=str(row.get("api_football_team_id") or ""),
        transfermarkt_club_id=str(row.get("transfermarkt_club_id") or ""),
        competition_id=str(row.get("competition_id") or ""),
        valid_from=_required_time(row.get("valid_from")),
        valid_to=parse_utc(row.get("valid_to")),
        source_sha256=str(row.get("source_sha256") or ""),
        reviewed_by=str(row.get("reviewed_by") or "") or None,
        reviewed_at=parse_utc(row.get("reviewed_at")),
        review_status=str(row.get("review_status") or ""),
        crosswalk_hash=str(row.get("crosswalk_hash") or ""),
        payload=dict(row),
    )


def _registered_roster_model(row: Mapping[str, Any]) -> RegisteredRosterSnapshotModel:
    snapshot_date = _required_time(row.get("snapshot_date") or row.get("observed_at"))
    payload = dict(row)
    roster_snapshot_id = str(row.get("roster_snapshot_id") or "")
    if not roster_snapshot_id:
        raise ValueError("ROSTER_SNAPSHOT_ID_REQUIRED")
    membership_hash = str(
        row.get("membership_hash") or stable_hash(_registered_roster_identity_payload(row))
    )
    payload.setdefault("membership_hash", membership_hash)
    payload.setdefault("roster_snapshot_id", roster_snapshot_id)
    return RegisteredRosterSnapshotModel(
        roster_snapshot_id=roster_snapshot_id,
        transfermarkt_club_id=str(row.get("transfermarkt_club_id") or row.get("club_id") or ""),
        transfermarkt_player_id=str(
            row.get("transfermarkt_player_id") or row.get("player_id") or ""
        ),
        snapshot_date=snapshot_date,
        valid_from=parse_utc(row.get("valid_from")) or snapshot_date,
        valid_to=parse_utc(row.get("valid_to")),
        source_sha256=str(row.get("source_sha256") or row.get("_source_sha256") or ""),
        snapshot_status=str(row.get("snapshot_status") or row.get("status") or "COMPLETE"),
        membership_hash=membership_hash,
        payload=payload,
    )


def _team_value_model(row: Mapping[str, Any]) -> TeamValueAsOfArtifactModel:
    natural_identity = _team_value_identity(row)
    return TeamValueAsOfArtifactModel(
        natural_identity=natural_identity,
        team_external_id=str(row.get("team_external_id") or ""),
        transfermarkt_club_id=str(row.get("transfermarkt_club_id") or ""),
        competition_id=str(row.get("competition_id") or ""),
        as_of=_required_time(row.get("as_of")),
        status=str(row.get("status") or ""),
        artifact_hash=str(row.get("artifact_hash") or ""),
        payload=dict(row),
    )


def _canonical_ah_model(
    row: Mapping[str, Any],
    session: Session | None = None,
) -> CanonicalHistoricalAhFactModel:
    source_snapshot_db_id = str(row.get("source_snapshot_db_id") or "")
    if not source_snapshot_db_id and session is not None:
        snapshot_id = str(row.get("source_snapshot_id") or "")
        source_sha = str(row.get("source_sha256") or "")
        if snapshot_id or source_sha:
            found = session.scalars(
                select(HistoricalMarketSourceSnapshotModel).where(
                    HistoricalMarketSourceSnapshotModel.source_id == snapshot_id
                )
            ).first()
            if found is None and source_sha:
                found = session.scalars(
                    select(HistoricalMarketSourceSnapshotModel).where(
                        HistoricalMarketSourceSnapshotModel.sha256 == source_sha
                    )
                ).first()
            if found is not None:
                source_snapshot_db_id = found.id
    if not source_snapshot_db_id:
        raise ValueError("SOURCE_SNAPSHOT_FK_REQUIRED")
    return CanonicalHistoricalAhFactModel(
        canonical_key=str(row.get("canonical_key") or _canonical_ah_identity(row)),
        fact_id=str(row.get("fact_id") or ""),
        fact_hash=str(row.get("fact_hash") or ""),
        source_snapshot_id=str(row.get("source_snapshot_id") or ""),
        source_snapshot_db_id=source_snapshot_db_id,
        source_registry_version=str(row.get("source_registry_version") or ""),
        source_schema_version=str(row.get("source_schema_version") or ""),
        bookmaker_policy=str(row.get("bookmaker_policy") or ""),
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
    payload = dict(row)
    policy = row.get("canonical_bookmaker_policy")
    policy_text = (
        json.dumps(policy, sort_keys=True)
        if isinstance(policy, Mapping)
        else str(policy or "")
    )
    source_sha = str(row.get("sha256") or row.get("source_sha256") or "")
    snapshot_hash = str(row.get("snapshot_hash") or stable_hash({
        "source_id": row.get("source_id"),
        "provider": row.get("provider"),
        "schema_version": row.get("schema_version"),
        "sha256": source_sha,
        "canonical_bookmaker_policy": policy if isinstance(policy, Mapping) else policy_text,
    }))
    payload.setdefault("snapshot_hash", snapshot_hash)
    return HistoricalMarketSourceSnapshotModel(
        source_id=str(row.get("source_id") or ""),
        provider=str(row.get("provider") or ""),
        registry_schema_version=str(
            row.get("registry_schema_version") or row.get("_registry_schema_version") or ""
        ),
        schema_version=str(row.get("schema_version") or ""),
        snapshot_semantics=str(row.get("snapshot_semantics") or ""),
        canonical_bookmaker_policy=policy_text,
        object_uri=str(row.get("object_uri") or row.get("local_path_or_object_uri") or ""),
        sha256=source_sha,
        snapshot_hash=snapshot_hash,
        license_status=str(row.get("license_status") or row.get("source_license_status") or ""),
        observed_at=parse_utc(row.get("observed_at")),
        ingested_at=parse_utc(row.get("ingested_at")) or datetime.now(tz=UTC),
        row_count=int(row.get("row_count") or 0),
        audit_payload=payload,
    )


def _player_membership_model(row: Mapping[str, Any]) -> PlayerClubMembershipObservationModel:
    membership_hash = str(
        row.get("membership_hash") or stable_hash(_player_membership_identity_payload(row))
    )
    return PlayerClubMembershipObservationModel(
        transfermarkt_player_id=str(row.get("transfermarkt_player_id") or ""),
        transfermarkt_club_id=str(
            row.get("transfermarkt_club_id") or row.get("club_id") or ""
        ),
        observed_at=_required_time(row.get("observed_at") or row.get("snapshot_date")),
        source_sha256=str(row.get("source_sha256") or row.get("_source_sha256") or ""),
        membership_hash=membership_hash,
        valid_from=parse_utc(row.get("valid_from")),
        valid_to=parse_utc(row.get("valid_to")),
        payload=dict(row),
    )


def _required_time(value: object) -> datetime:
    parsed = parse_utc(value)
    if parsed is None:
        raise ValueError("FAH_TIMESTAMP_REQUIRED")
    return parsed


def _source_snapshot_identity(row: Mapping[str, Any]) -> str:
    return stable_hash(
        {
            "source_id": row.get("source_id"),
            "sha256": row.get("sha256") or row.get("source_sha256"),
        }
    )


def _canonical_ah_identity(row: Mapping[str, Any]) -> str:
    return str(row.get("canonical_key") or row.get("fact_id") or "")


def _team_crosswalk_identity(row: Mapping[str, Any]) -> str:
    return stable_hash(
        {
            "api_football_team_id": row.get("api_football_team_id"),
            "competition_id": row.get("competition_id"),
            "valid_from": row.get("valid_from"),
        }
    )


def _player_crosswalk_identity(row: Mapping[str, Any]) -> str:
    return stable_hash(
        {
            "api_football_player_id": row.get("api_football_player_id"),
            "competition_id": row.get("competition_id"),
            "valid_from": row.get("valid_from"),
        }
    )


def _registered_roster_identity(row: Mapping[str, Any]) -> str:
    return str(row.get("membership_hash") or stable_hash(_registered_roster_identity_payload(row)))


def _registered_roster_identity_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "transfermarkt_club_id": row.get("transfermarkt_club_id") or row.get("club_id"),
        "transfermarkt_player_id": row.get("transfermarkt_player_id") or row.get("player_id"),
        "snapshot_date": row.get("snapshot_date") or row.get("observed_at"),
    }


def _player_membership_identity(row: Mapping[str, Any]) -> str:
    return str(row.get("membership_hash") or stable_hash(_player_membership_identity_payload(row)))


def _player_membership_identity_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "transfermarkt_player_id": row.get("transfermarkt_player_id"),
        "transfermarkt_club_id": row.get("transfermarkt_club_id") or row.get("club_id"),
        "observed_at": row.get("observed_at") or row.get("snapshot_date"),
    }


def _team_value_identity(row: Mapping[str, Any]) -> str:
    return str(
        row.get("natural_identity")
        or stable_hash(
            {
                "team_external_id": row.get("team_external_id"),
                "competition_id": row.get("competition_id"),
                "as_of": row.get("as_of"),
            }
        )
    )
