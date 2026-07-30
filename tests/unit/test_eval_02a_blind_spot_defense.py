from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from w2.analysis.market_movement import classify_divergence_origin
from w2.lineups.intelligence import build_team_rotation_prior

KICKOFF = datetime(2026, 7, 30, 12, tzinfo=UTC)
CURRENT = KICKOFF - timedelta(hours=1)


def _observation(
    *,
    observation_id: str,
    odds: float,
    captured_at: datetime,
    line: float = -0.5,
) -> dict[str, object]:
    return {
        "observation_id": observation_id,
        "fixture_id": "api_football:42",
        "canonical_market": "ASIAN_HANDICAP",
        "selection": "HOME",
        "line": line,
        "decimal_odds": odds,
        "captured_at": captured_at.isoformat(),
        "live": False,
        "suspended": False,
    }


def _classification(
    opening_odds: float,
    *,
    current_odds: float = 2.4,
    current_ev: float = 0.2,
    observations: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    rows = observations or [
        _observation(
            observation_id="opening",
            odds=opening_odds,
            captured_at=CURRENT - timedelta(hours=5),
        ),
        _observation(
            observation_id="current",
            odds=current_odds,
            captured_at=CURRENT,
        ),
    ]
    return classify_divergence_origin(
        fixture_id="42",
        market="ASIAN_HANDICAP",
        selection="HOME",
        line=-0.5,
        model_probability=0.5,
        current_decimal_odds=current_odds,
        current_expected_value=current_ev,
        current_captured_at=CURRENT,
        kickoff_utc=KICKOFF,
        current_quote_identity_status="COMPLETE",
        current_quote_freshness_status="COMPLETE",
        observations=rows,
    )


def test_divergence_classifier_freezes_registered_boundaries() -> None:
    moved = _classification(2.0)
    half = _classification(2.2)
    stable = _classification(2.24)

    assert moved["raw_classification"] == "MOVEMENT_CREATED_DIVERGENCE"
    assert moved["effective_risk_class"] == "MOVED"
    assert half["movement_ev_share"] == 0.5
    assert half["raw_classification"] == "INDETERMINATE"
    assert half["effective_risk_class"] == "MOVED_CONSERVATIVE"
    assert stable["divergence_age_ratio"] == 0.6
    assert stable["raw_classification"] == "STABLE_DIVERGENCE"
    assert stable["effective_risk_class"] == "STABLE"


def test_divergence_classifier_rejects_cross_line_future_and_post_kickoff_openings() -> None:
    rows = [
        _observation(
            observation_id="cross-line",
            odds=2.0,
            line=-0.25,
            captured_at=CURRENT - timedelta(hours=4),
        ),
        _observation(
            observation_id="future",
            odds=2.0,
            captured_at=CURRENT + timedelta(minutes=1),
        ),
        _observation(
            observation_id="post-kickoff",
            odds=2.0,
            captured_at=KICKOFF + timedelta(minutes=1),
        ),
        _observation(observation_id="current", odds=2.4, captured_at=CURRENT),
    ]
    result = _classification(2.0, observations=rows)

    assert result["raw_classification"] == "INDETERMINATE"
    assert result["input_observation_ids"] == ["current"]
    assert "SAME_LINE_OPENING_NOT_AVAILABLE" in result["blockers"]


def test_divergence_classifier_fails_closed_on_current_ev_parity_conflict() -> None:
    result = _classification(2.0, current_ev=0.21)

    assert result["status"] == "BLOCKED"
    assert "EV_IDENTITY_PARITY_CONFLICT" in result["blockers"]


def _lineup_rows(*, changes: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    starters = [str(value) for value in range(11)]
    for index in range(6):
        kickoff = KICKOFF - timedelta(days=12 - index * 2)
        rows.append(
            {
                "fixture_id": f"fixture-{index}",
                "team_external_id": "team-1",
                "kickoff_at": kickoff,
                "captured_at": kickoff - timedelta(hours=1),
                "confirmed": True,
                "starters": [{"player_id": player_id} for player_id in starters],
                "lineup_identity_hash": f"lineup-{index}",
            }
        )
        starters = starters[changes:] + [
            str(100 + index * changes + offset) for offset in range(changes)
        ]
    return rows


def test_rotation_prior_uses_four_of_eleven_boundary_and_stable_input_hash() -> None:
    rows = _lineup_rows(changes=4)
    forward = build_team_rotation_prior(
        rows,
        team_external_id="team-1",
        as_of=KICKOFF,
    )
    reverse = build_team_rotation_prior(
        list(reversed(rows)),
        team_external_id="team-1",
        as_of=KICKOFF,
    )

    assert forward["status"] == "READY"
    assert forward["transition_count"] == 5
    assert forward["rotation_rate"] == pytest.approx(4 / 11)
    assert forward["classification"] == "HIGH_ROTATION"
    assert reverse["input_hash"] == forward["input_hash"]


def test_rotation_prior_excludes_incomplete_future_and_old_same_fixture_snapshots() -> None:
    rows = _lineup_rows(changes=3)
    rows.extend(
        [
            {
                **rows[-1],
                "captured_at": KICKOFF - timedelta(days=2, hours=1, minutes=1),
                "starters": [{"player_id": "old"}] * 11,
            },
            {
                **rows[-1],
                "fixture_id": "future",
                "kickoff_at": KICKOFF + timedelta(days=1),
                "captured_at": KICKOFF,
            },
            {
                **rows[-1],
                "fixture_id": "incomplete",
                "starters": [{"player_id": str(value)} for value in range(10)],
            },
        ]
    )
    result = build_team_rotation_prior(
        rows,
        team_external_id="team-1",
        as_of=KICKOFF,
    )

    assert result["match_count"] == 6
    assert result["classification"] == "NORMAL"
