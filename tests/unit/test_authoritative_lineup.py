from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from w2.ingestion.authoritative_lineup import (
    AuthoritativeLineupError,
    validate_authoritative_lineup,
)

KICKOFF = datetime(2026, 8, 8, 18, tzinfo=UTC)
CAPTURED_AT = KICKOFF - timedelta(minutes=45)


def _team(team_id: int, player_offset: int) -> dict[str, object]:
    return {
        "team": {"id": team_id, "name": f"Team {team_id}"},
        "formation": "4-3-3",
        "startXI": [
            {"player": {"id": player_offset + index, "name": f"P{index}"}}
            for index in range(11)
        ],
        "substitutes": [],
    }


def _validate(response: object):  # type: ignore[no-untyped-def]
    return validate_authoritative_lineup(
        response,
        expected_team_ids=("10", "20"),
        captured_at=CAPTURED_AT,
        kickoff_utc=KICKOFF,
    )


def test_authoritative_lineup_is_exact_and_idempotent() -> None:
    response = [_team(10, 100), _team(20, 200)]

    first = _validate(response)
    second = _validate(response)

    assert first == second
    assert [len(team.starters) for team in first.teams] == [11, 11]
    assert len({player.player_id for team in first.teams for player in team.starters}) == 22


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda rows: rows.pop(), "LINEUP_TEAMS_INCOMPLETE"),
        (
            lambda rows: rows.__setitem__(1, _team(30, 200)),
            "LINEUP_FIXTURE_TEAM_IDENTITY_CONFLICT",
        ),
        (
            lambda rows: rows[0]["startXI"].pop(),  # type: ignore[index,union-attr]
            "STARTING_XI_INCOMPLETE",
        ),
        (
            lambda rows: rows[1]["startXI"][10]["player"].__setitem__("id", 100),  # type: ignore[index,union-attr]
            "LINEUP_FIXTURE_PLAYER_IDENTITY_CONFLICT",
        ),
    ],
)
def test_authoritative_lineup_conflicts_fail_closed(mutate, reason: str) -> None:  # type: ignore[no-untyped-def]
    response = [_team(10, 100), _team(20, 200)]
    mutate(response)

    with pytest.raises(AuthoritativeLineupError, match=reason):
        _validate(response)


def test_authoritative_lineup_rejects_post_kickoff_capture() -> None:
    with pytest.raises(AuthoritativeLineupError, match="POST_KICKOFF_LINEUP_REJECTED"):
        validate_authoritative_lineup(
            [_team(10, 100), _team(20, 200)],
            expected_team_ids=("10", "20"),
            captured_at=KICKOFF,
            kickoff_utc=KICKOFF,
        )
