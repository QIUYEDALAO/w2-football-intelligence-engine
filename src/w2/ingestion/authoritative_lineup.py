from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class AuthoritativeLineupError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, kw_only=True)
class ValidatedLineupPlayer:
    player_id: str
    player_name: str
    shirt_number: int | None
    provider_position: str | None
    grid: str | None
    captain: bool

    def as_persistence_dict(self, *, starter: bool) -> dict[str, Any]:
        return {
            "api_football_player_id": self.player_id,
            "player_name": self.player_name,
            "starter": starter,
            "shirt_number": self.shirt_number,
            "provider_position": self.provider_position,
            "grid": self.grid,
            "captain": self.captain,
        }


@dataclass(frozen=True, kw_only=True)
class ValidatedLineupTeam:
    team_id: str
    team_name: str
    formation: str | None
    starters: tuple[ValidatedLineupPlayer, ...]
    substitutes: tuple[ValidatedLineupPlayer, ...]


@dataclass(frozen=True, kw_only=True)
class ValidatedAuthoritativeLineup:
    teams: tuple[ValidatedLineupTeam, ValidatedLineupTeam]


def validate_authoritative_lineup(
    response: object,
    *,
    expected_team_ids: tuple[str, str] | None,
    captured_at: datetime | None,
    kickoff_utc: datetime | None,
) -> ValidatedAuthoritativeLineup:
    """Validate one provider lineup response against one immutable fixture identity."""
    if not isinstance(response, list):
        raise AuthoritativeLineupError("LINEUP_RESPONSE_INVALID")
    if len(response) != 2:
        raise AuthoritativeLineupError("LINEUP_TEAMS_INCOMPLETE")
    if captured_at is not None and captured_at.tzinfo is None:
        raise AuthoritativeLineupError("LINEUP_CAPTURE_TIMEZONE_INVALID")
    if kickoff_utc is not None and kickoff_utc.tzinfo is None:
        raise AuthoritativeLineupError("LINEUP_KICKOFF_TIMEZONE_INVALID")
    if (
        captured_at is not None
        and kickoff_utc is not None
        and captured_at.astimezone(UTC) >= kickoff_utc.astimezone(UTC)
    ):
        raise AuthoritativeLineupError("POST_KICKOFF_LINEUP_REJECTED")

    teams = tuple(_team(row) for row in response)
    if len({team.team_id for team in teams}) != 2:
        raise AuthoritativeLineupError("LINEUP_TEAMS_INCOMPLETE")
    if expected_team_ids is not None:
        expected = {str(team_id) for team_id in expected_team_ids if str(team_id)}
        if len(expected) != 2 or {team.team_id for team in teams} != expected:
            raise AuthoritativeLineupError("LINEUP_FIXTURE_TEAM_IDENTITY_CONFLICT")

    all_starter_ids: list[str] = []
    for team in teams:
        starter_ids = [player.player_id for player in team.starters]
        if len(starter_ids) != 11:
            raise AuthoritativeLineupError("STARTING_XI_INCOMPLETE")
        if len(set(starter_ids)) != 11:
            raise AuthoritativeLineupError("DUPLICATE_STARTER")
        all_starter_ids.extend(starter_ids)
    if len(set(all_starter_ids)) != 22:
        raise AuthoritativeLineupError("LINEUP_FIXTURE_PLAYER_IDENTITY_CONFLICT")
    return ValidatedAuthoritativeLineup(teams=teams)  # type: ignore[arg-type]


def _team(value: object) -> ValidatedLineupTeam:
    if not isinstance(value, Mapping):
        raise AuthoritativeLineupError("LINEUP_RESPONSE_INVALID")
    raw_team = value.get("team")
    team = raw_team if isinstance(raw_team, Mapping) else {}
    team_id = str(team.get("id") or value.get("team_id") or "")
    if not team_id:
        raise AuthoritativeLineupError("LINEUP_TEAMS_INCOMPLETE")
    return ValidatedLineupTeam(
        team_id=team_id,
        team_name=str(team.get("name") or value.get("team_name") or team_id),
        formation=str(value.get("formation") or "") or None,
        starters=_players(value.get("startXI") or value.get("starters")),
        substitutes=_players(value.get("substitutes")),
    )


def _players(value: object) -> tuple[ValidatedLineupPlayer, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return ()
    players: list[ValidatedLineupPlayer] = []
    for wrapper in value:
        raw = wrapper.get("player") if isinstance(wrapper, Mapping) else None
        player = (
            raw
            if isinstance(raw, Mapping)
            else wrapper
            if isinstance(wrapper, Mapping)
            else {}
        )
        player_id = str(player.get("id") or player.get("player_id") or "")
        if not player_id:
            continue
        number = player.get("number")
        try:
            shirt_number = int(number) if number is not None else None
        except (TypeError, ValueError):
            shirt_number = None
        players.append(
            ValidatedLineupPlayer(
                player_id=player_id,
                player_name=str(player.get("name") or player.get("player_name") or ""),
                shirt_number=shirt_number,
                provider_position=str(player.get("pos") or player.get("provider_position") or "")
                or None,
                grid=str(player.get("grid") or "") or None,
                captain=bool(player.get("captain", False)),
            )
        )
    return tuple(players)
