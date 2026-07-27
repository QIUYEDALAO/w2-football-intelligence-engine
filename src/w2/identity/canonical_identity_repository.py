"""Single canonical identity authority repository (ARCH-P1-03 M2A, team side).

Team identity is resolved from ``provider_team_identity_crosswalks`` +
``canonical_teams``; player identity from ``player_identity_mappings``. This
repository never constructs a canonical ID from a provider ID and never reads
the retired legacy crosswalk tables. Unknown
provider identity resolves to ``None`` (callers fail closed); nothing is
auto-created.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from w2.config import Settings
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.factor_model_models import (
    ProviderTeamIdentityCrosswalkModel,
)
from w2.infrastructure.persistence.models import PlayerIdentityMappingModel

_TEAM_READY_STATUS = "PROVIDER_PRIMARY_READY"
_REVIEWED_STATUSES = ("REVIEWED", "APPROVED")


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize to UTC-aware; sqlite returns naive datetimes, postgres aware."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _valid_at(valid_from: datetime | None, valid_to: datetime | None, as_of: datetime) -> bool:
    as_of = _as_utc(as_of)  # type: ignore[assignment]
    vf, vt = _as_utc(valid_from), _as_utc(valid_to)
    if vf is not None and vf > as_of:
        return False
    if vt is not None and vt <= as_of:
        return False
    return True


class CanonicalIdentityRepository:
    """Read-only resolver for canonical team/player identity."""

    def __init__(self, *, engine: Engine | None = None, settings: Settings | None = None) -> None:
        self.engine = engine or create_engine(settings)

    # --- team ---------------------------------------------------------------

    def resolve_team(
        self,
        provider: str,
        provider_team_id: str,
        competition: str,
        season: str,
        as_of: datetime,
    ) -> str | None:
        """Canonical ``w2_team_id`` for a provider team identity, or ``None``."""
        with Session(self.engine) as session:
            rows = session.scalars(
                select(ProviderTeamIdentityCrosswalkModel).where(
                    ProviderTeamIdentityCrosswalkModel.provider == provider,
                    ProviderTeamIdentityCrosswalkModel.provider_team_id == provider_team_id,
                    ProviderTeamIdentityCrosswalkModel.competition_id == competition,
                    ProviderTeamIdentityCrosswalkModel.season == season,
                    ProviderTeamIdentityCrosswalkModel.identity_status == _TEAM_READY_STATUS,
                    ProviderTeamIdentityCrosswalkModel.review_status.in_(_REVIEWED_STATUSES),
                    ProviderTeamIdentityCrosswalkModel.reviewed_by.is_not(None),
                    ProviderTeamIdentityCrosswalkModel.reviewed_at.is_not(None),
                )
            ).all()
        valid = [r.w2_team_id for r in rows if _valid_at(r.valid_from, r.valid_to, as_of)]
        if len(set(valid)) != 1:
            return None
        return valid[0]

    def provider_identity_for_team(
        self,
        w2_team_id: str,
        provider: str,
        competition: str,
        season: str,
        as_of: datetime,
    ) -> str | None:
        """Provider team id for a canonical team under one provider, or ``None``."""
        with Session(self.engine) as session:
            rows = session.scalars(
                select(ProviderTeamIdentityCrosswalkModel).where(
                    ProviderTeamIdentityCrosswalkModel.w2_team_id == w2_team_id,
                    ProviderTeamIdentityCrosswalkModel.provider == provider,
                    ProviderTeamIdentityCrosswalkModel.competition_id == competition,
                    ProviderTeamIdentityCrosswalkModel.season == season,
                    ProviderTeamIdentityCrosswalkModel.identity_status == _TEAM_READY_STATUS,
                    ProviderTeamIdentityCrosswalkModel.review_status.in_(_REVIEWED_STATUSES),
                    ProviderTeamIdentityCrosswalkModel.reviewed_by.is_not(None),
                    ProviderTeamIdentityCrosswalkModel.reviewed_at.is_not(None),
                )
            ).all()
        valid = [r.provider_team_id for r in rows if _valid_at(r.valid_from, r.valid_to, as_of)]
        if len(set(valid)) != 1:
            return None
        return valid[0]

    # --- session-scoped bulk resolution --------------------------------------

    @staticmethod
    def reviewed_team_authority_in_session(
        session: Session,
        *,
        provider: str,
        provider_team_id: str,
        season: str,
        as_of: datetime,
    ) -> ProviderTeamIdentityCrosswalkModel | None:
        """Unique reviewed team authority when the source lacks a competition key."""
        rows = session.scalars(
            select(ProviderTeamIdentityCrosswalkModel).where(
                ProviderTeamIdentityCrosswalkModel.provider == provider,
                ProviderTeamIdentityCrosswalkModel.provider_team_id
                == provider_team_id,
                ProviderTeamIdentityCrosswalkModel.season == season,
                ProviderTeamIdentityCrosswalkModel.identity_status
                == _TEAM_READY_STATUS,
                ProviderTeamIdentityCrosswalkModel.review_status.in_(
                    _REVIEWED_STATUSES
                ),
                ProviderTeamIdentityCrosswalkModel.reviewed_by.is_not(None),
                ProviderTeamIdentityCrosswalkModel.reviewed_at.is_not(None),
            )
        ).all()
        valid = [
            row for row in rows if _valid_at(row.valid_from, row.valid_to, as_of)
        ]
        return valid[0] if len(valid) == 1 else None

    @staticmethod
    def provider_team_mapping_in_session(
        session: Session,
        *,
        provider: str,
        competition: str,
        season: str,
        as_of: datetime,
    ) -> dict[str, str]:
        """``provider_team_id -> w2_team_id`` for one provider/competition/season.

        Session-scoped so callers inside an open transaction resolve against the
        authority rows they have already flushed. Fail-closed by omission on both
        axes: rows outside their validity window at ``as_of`` are ignored, and a
        provider id that resolves to more than one canonical team is dropped
        entirely rather than silently picking one (same rule as
        :meth:`resolve_team`). Absent provider ids never yield a constructed id.
        """
        rows = session.scalars(
            select(ProviderTeamIdentityCrosswalkModel)
            .where(
                ProviderTeamIdentityCrosswalkModel.provider == provider,
                ProviderTeamIdentityCrosswalkModel.competition_id == competition,
                ProviderTeamIdentityCrosswalkModel.season == season,
                ProviderTeamIdentityCrosswalkModel.identity_status == _TEAM_READY_STATUS,
            )
            .order_by(ProviderTeamIdentityCrosswalkModel.provider_team_id)
        ).all()
        candidates: dict[str, set[str]] = {}
        for row in rows:
            if not _valid_at(row.valid_from, row.valid_to, as_of):
                continue
            candidates.setdefault(row.provider_team_id, set()).add(row.w2_team_id)
        return {
            provider_team_id: next(iter(targets))
            for provider_team_id, targets in candidates.items()
            if len(targets) == 1
        }

    @staticmethod
    def canonical_team_source_mapping_in_session(
        session: Session,
        *,
        provider: str,
        competition: str,
        season: str,
        as_of: datetime,
    ) -> dict[str, str]:
        """``w2_team_id -> provider_team_id`` (the reverse direction).

        Used to reach provider-keyed source tables (xG feeds, raw payloads)
        starting from a canonical id. Fails closed on the reverse axis too: a
        canonical team that maps to more than one provider team id under the same
        provider is dropped, so callers never silently pick one source identity.
        Do not build this by inverting
        :meth:`provider_team_mapping_in_session` -- inversion hides exactly this
        ambiguity.
        """
        rows = session.scalars(
            select(ProviderTeamIdentityCrosswalkModel)
            .where(
                ProviderTeamIdentityCrosswalkModel.provider == provider,
                ProviderTeamIdentityCrosswalkModel.competition_id == competition,
                ProviderTeamIdentityCrosswalkModel.season == season,
                ProviderTeamIdentityCrosswalkModel.identity_status == _TEAM_READY_STATUS,
            )
            .order_by(ProviderTeamIdentityCrosswalkModel.w2_team_id)
        ).all()
        candidates: dict[str, set[str]] = {}
        for row in rows:
            if not _valid_at(row.valid_from, row.valid_to, as_of):
                continue
            candidates.setdefault(row.w2_team_id, set()).add(row.provider_team_id)
        return {
            w2_team_id: next(iter(sources))
            for w2_team_id, sources in candidates.items()
            if len(sources) == 1
        }

    # --- season-agnostic team resolution (F5 historical, no season axis) -----

    def resolve_team_canonical(
        self, provider: str, provider_team_id: str, competition: str, as_of: datetime
    ) -> str | None:
        """Canonical ``w2_team_id`` for a provider team, any season, or ``None``.

        F5 historical resolution has no season axis; the canonical team identity
        is stable across seasons, so resolve by provider/team/competition valid
        at ``as_of`` and require a single canonical target (fail closed on
        ambiguity; never constructs an id).
        """
        with Session(self.engine) as session:
            rows = session.scalars(
                select(ProviderTeamIdentityCrosswalkModel).where(
                    ProviderTeamIdentityCrosswalkModel.provider == provider,
                    ProviderTeamIdentityCrosswalkModel.provider_team_id == provider_team_id,
                    ProviderTeamIdentityCrosswalkModel.competition_id == competition,
                    ProviderTeamIdentityCrosswalkModel.identity_status == _TEAM_READY_STATUS,
                )
            ).all()
        valid = {r.w2_team_id for r in rows if _valid_at(r.valid_from, r.valid_to, as_of)}
        if len(valid) != 1:
            return None
        return next(iter(valid))

    def provider_identity_for_team_canonical(
        self, w2_team_id: str, provider: str, competition: str, as_of: datetime
    ) -> str | None:
        """Provider team id for a canonical team, any season, or ``None``."""
        with Session(self.engine) as session:
            rows = session.scalars(
                select(ProviderTeamIdentityCrosswalkModel).where(
                    ProviderTeamIdentityCrosswalkModel.w2_team_id == w2_team_id,
                    ProviderTeamIdentityCrosswalkModel.provider == provider,
                    ProviderTeamIdentityCrosswalkModel.competition_id == competition,
                    ProviderTeamIdentityCrosswalkModel.identity_status == _TEAM_READY_STATUS,
                )
            ).all()
        valid = {r.provider_team_id for r in rows if _valid_at(r.valid_from, r.valid_to, as_of)}
        if len(valid) != 1:
            return None
        return next(iter(valid))

    # --- player -------------------------------------------------------------

    @staticmethod
    def player_mapping_in_session(
        session: Session,
        *,
        api_football_player_id: str,
        w2_team_id: str,
        competition: str,
        season: str,
        as_of: datetime,
    ) -> PlayerIdentityMappingModel | None:
        """Return one reviewed mapping under the exact canonical team authority."""
        team_rows = session.scalars(
            select(ProviderTeamIdentityCrosswalkModel).where(
                ProviderTeamIdentityCrosswalkModel.provider == "api_football",
                ProviderTeamIdentityCrosswalkModel.w2_team_id == w2_team_id,
                ProviderTeamIdentityCrosswalkModel.competition_id == competition,
                ProviderTeamIdentityCrosswalkModel.season == season,
                ProviderTeamIdentityCrosswalkModel.identity_status == _TEAM_READY_STATUS,
                ProviderTeamIdentityCrosswalkModel.review_status.in_(_REVIEWED_STATUSES),
                ProviderTeamIdentityCrosswalkModel.reviewed_by.is_not(None),
                ProviderTeamIdentityCrosswalkModel.reviewed_at.is_not(None),
            )
        ).all()
        provider_team_ids = {
            row.provider_team_id
            for row in team_rows
            if _valid_at(row.valid_from, row.valid_to, as_of)
        }
        if len(provider_team_ids) != 1:
            return None
        team_external_id = next(iter(provider_team_ids))
        rows = session.scalars(
            select(PlayerIdentityMappingModel).where(
                PlayerIdentityMappingModel.api_football_player_id
                == api_football_player_id,
                PlayerIdentityMappingModel.team_external_id == team_external_id,
            )
        ).all()
        active = [row for row in rows if _valid_at(row.valid_from, row.valid_to, as_of)]
        if any(row.mapping_status == "CONFLICT" for row in active):
            return None
        accepted = [
            row
            for row in active
            if row.mapping_status in _REVIEWED_STATUSES
            and row.canonical_player_id
            and row.reviewed_by
            and row.reviewed_at
            and row.evidence.get("canonical_team_id") == w2_team_id
            and row.evidence.get("review_status") in _REVIEWED_STATUSES
        ]
        canonical_ids = {row.canonical_player_id for row in accepted}
        if len(canonical_ids) != 1:
            return None
        identity_hashes = {row.identity_hash for row in accepted}
        if len(identity_hashes) != 1:
            return None
        return accepted[0]

    def resolve_player(
        self,
        api_football_player_id: str,
        w2_team_id: str,
        competition: str,
        season: str,
        as_of: datetime,
    ) -> str | None:
        """Canonical player id for an API-Football player, or ``None``."""
        try:
            with Session(self.engine) as session:
                row = self.player_mapping_in_session(
                    session,
                    api_football_player_id=api_football_player_id,
                    w2_team_id=w2_team_id,
                    competition=competition,
                    season=season,
                    as_of=as_of,
                )
        except SQLAlchemyError:
            return None
        return row.canonical_player_id if row else None

    def approved_players_for_team(
        self,
        w2_team_id: str,
        competition: str,
        season: str,
        as_of: datetime,
    ) -> list[str]:
        """Stable, deduplicated reviewed roster under one exact team authority."""
        try:
            with Session(self.engine) as session:
                team_id = self.provider_identity_for_team_in_session(
                    session,
                    w2_team_id=w2_team_id,
                    provider="api_football",
                    competition=competition,
                    season=season,
                    as_of=as_of,
                )
                if team_id is None:
                    return []
                player_ids = session.scalars(
                    select(PlayerIdentityMappingModel.api_football_player_id)
                    .where(PlayerIdentityMappingModel.team_external_id == team_id)
                    .distinct()
                    .order_by(PlayerIdentityMappingModel.api_football_player_id)
                ).all()
                resolved = {
                    row.canonical_player_id
                    for player_id in player_ids
                    if (
                        row := self.player_mapping_in_session(
                            session,
                            api_football_player_id=player_id,
                            w2_team_id=w2_team_id,
                            competition=competition,
                            season=season,
                            as_of=as_of,
                        )
                    )
                    is not None
                    and row.canonical_player_id
                }
                return sorted(resolved)
        except SQLAlchemyError:
            return []

    @staticmethod
    def provider_identity_for_team_in_session(
        session: Session,
        *,
        w2_team_id: str,
        provider: str,
        competition: str,
        season: str,
        as_of: datetime,
    ) -> str | None:
        """Session-scoped reverse team lookup with reviewed authority."""
        rows = session.scalars(
            select(ProviderTeamIdentityCrosswalkModel).where(
                ProviderTeamIdentityCrosswalkModel.w2_team_id == w2_team_id,
                ProviderTeamIdentityCrosswalkModel.provider == provider,
                ProviderTeamIdentityCrosswalkModel.competition_id == competition,
                ProviderTeamIdentityCrosswalkModel.season == season,
                ProviderTeamIdentityCrosswalkModel.identity_status == _TEAM_READY_STATUS,
                ProviderTeamIdentityCrosswalkModel.review_status.in_(_REVIEWED_STATUSES),
                ProviderTeamIdentityCrosswalkModel.reviewed_by.is_not(None),
                ProviderTeamIdentityCrosswalkModel.reviewed_at.is_not(None),
            )
        ).all()
        valid = {
            row.provider_team_id
            for row in rows
            if _valid_at(row.valid_from, row.valid_to, as_of)
        }
        return next(iter(valid)) if len(valid) == 1 else None

    def approved_player_source_mapping(
        self,
        w2_team_id: str,
        competition: str,
        season: str,
        as_of: datetime,
    ) -> dict[str, str]:
        """Transfermarkt player id to canonical player id for a reviewed roster."""
        try:
            with Session(self.engine) as session:
                team_id = self.provider_identity_for_team_in_session(
                    session,
                    w2_team_id=w2_team_id,
                    provider="api_football",
                    competition=competition,
                    season=season,
                    as_of=as_of,
                )
                if team_id is None:
                    return {}
                provider_ids = session.scalars(
                    select(PlayerIdentityMappingModel.api_football_player_id)
                    .where(PlayerIdentityMappingModel.team_external_id == team_id)
                    .distinct()
                ).all()
                pairs: dict[str, set[str]] = {}
                for player_id in provider_ids:
                    row = self.player_mapping_in_session(
                        session,
                        api_football_player_id=player_id,
                        w2_team_id=w2_team_id,
                        competition=competition,
                        season=season,
                        as_of=as_of,
                    )
                    if row and row.transfermarkt_player_id and row.canonical_player_id:
                        pairs.setdefault(row.transfermarkt_player_id, set()).add(
                            row.canonical_player_id
                        )
                return {
                    source_id: next(iter(canonical_ids))
                    for source_id, canonical_ids in sorted(pairs.items())
                    if len(canonical_ids) == 1
                }
        except SQLAlchemyError:
            return {}
