"""Single canonical identity authority repository (ARCH-P1-03 M2A, team side).

Team identity is resolved from ``provider_team_identity_crosswalks`` +
``canonical_teams``; player identity from ``player_identity_mappings``. This
repository never constructs a canonical ID from a provider ID and never reads
the legacy crosswalk tables (``team_identity_crosswalks``,
``football_data_team_crosswalks``, ``player_identity_crosswalks``). Unknown
provider identity resolves to ``None`` (callers fail closed); nothing is
auto-created.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from w2.config import Settings
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.factor_model_models import (
    ProviderTeamIdentityCrosswalkModel,
)
from w2.infrastructure.persistence.models import PlayerIdentityMappingModel

_TEAM_READY_STATUS = "PROVIDER_PRIMARY_READY"
_PLAYER_REVIEWED_STATUS = "REVIEWED"


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
                )
            ).all()
        valid = [r.provider_team_id for r in rows if _valid_at(r.valid_from, r.valid_to, as_of)]
        if len(set(valid)) != 1:
            return None
        return valid[0]

    # --- session-scoped bulk resolution --------------------------------------

    @staticmethod
    def provider_team_mapping_in_session(
        session: Session,
        *,
        provider: str,
        competition: str,
        season: str,
    ) -> dict[str, str]:
        """``provider_team_id -> w2_team_id`` for one provider/competition/season.

        Session-scoped so callers inside an open transaction resolve against the
        authority rows they have already flushed. Provider ids absent from the
        authority are simply absent from the mapping, so callers fail closed
        rather than constructing an identity.
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
        return {row.provider_team_id: row.w2_team_id for row in rows}

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
    # Only REVIEWED mappings with a non-null canonical_player_id and current
    # validity are model-consumable. Team/competition/season scoping columns
    # land with the player-side migration; player identity data is currently
    # empty, so these resolve to None/[] and never fabricate an identity.

    def resolve_player(
        self,
        api_football_player_id: str,
        w2_team_id: str,
        competition: str,
        season: str,
        as_of: datetime,
    ) -> str | None:
        """Canonical player id for an API-Football player, or ``None``."""
        with Session(self.engine) as session:
            rows = session.scalars(
                select(PlayerIdentityMappingModel).where(
                    PlayerIdentityMappingModel.api_football_player_id == api_football_player_id,
                    PlayerIdentityMappingModel.mapping_status == _PLAYER_REVIEWED_STATUS,
                    PlayerIdentityMappingModel.canonical_player_id.is_not(None),
                )
            ).all()
        valid = [
            r.canonical_player_id
            for r in rows
            if _valid_at(r.valid_from, r.valid_to, as_of)
        ]
        if len(set(valid)) != 1:
            return None
        return valid[0]

    def approved_players_for_team(
        self,
        w2_team_id: str,
        competition: str,
        season: str,
        as_of: datetime,
    ) -> list[str]:
        """Canonical player ids approved for a team (empty until player-side M2)."""
        return []
