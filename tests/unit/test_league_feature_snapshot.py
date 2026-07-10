from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from w2.api.repository import ReadModelService
from w2.features.league_snapshot import build_league_feature_pair
from w2.features.live_factors import TeamXgSnapshot
from w2.features.team_factors import TeamRatingSnapshot
from w2.models.r4_1_artifacts import build_r4_1_artifact_payload
from w2.models.r4_1_features import (
    r4_1_feature_rows,
    r4_1_feature_rows_from_values,
    r4_1_strength_features_from_rolling,
)

KICKOFF = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def test_offline_and_serving_feature_rows_are_identical() -> None:
    strengths = r4_1_strength_features_from_rolling(
        home_for=1.6,
        home_against=0.9,
        away_for=1.1,
        away_against=1.3,
    )
    sample = SimpleNamespace(
        fixture=SimpleNamespace(competition_id="chinese_super_league"),
        true_features={
            "home_field": 1.0,
            "elo_diff": 80.0,
            **strengths,
        },
    )
    competitions = ("allsvenskan", "chinese_super_league", "eliteserien")
    offline = r4_1_feature_rows(sample, competitions)
    feature_names = (
        "intercept",
        "home_field",
        "attack_xg_for",
        "opponent_xg_against",
        "elo_gap",
        "home_field__allsvenskan",
        "home_field__chinese_super_league",
        "home_field__eliteserien",
    )
    serving = r4_1_feature_rows_from_values(
        competition_id="chinese_super_league",
        neutral_site=False,
        home_attack_strength=strengths["home_attack_strength"],
        home_defence_strength=strengths["home_defence_strength"],
        away_attack_strength=strengths["away_attack_strength"],
        away_defence_strength=strengths["away_defence_strength"],
        elo_gap=0.2,
        feature_names=feature_names,
    )

    assert serving == offline


def test_serving_rows_follow_pooled_artifact_feature_names(tmp_path: Path) -> None:
    feature_names = (
        "intercept",
        "home_field",
        "attack_xg_for",
        "opponent_xg_against",
        "elo_gap",
        "home_field__allsvenskan",
        "home_field__argentina_primera",
        "home_field__chinese_super_league",
        "home_field__eliteserien",
    )
    payload = build_r4_1_artifact_payload(
        competition_id="chinese_super_league",
        coefficients=[0.1] * len(feature_names),
        feature_names=feature_names,
        temperature=1.0,
        rho=0.0,
        train_cutoff_utc=KICKOFF - timedelta(days=30),
        fit_sample_count=300,
        protocol_identity_check="PASS",
    )
    (tmp_path / "chinese_super_league.v1.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    service = ReadModelService(r4_1_artifact_root=tmp_path)

    rows = service._serving_r4_1_feature_rows(  # noqa: SLF001
        competition_id="chinese_super_league",
        kickoff=KICKOFF,
        neutral_site=False,
        home_team_id="home",
        away_team_id="away",
        snapshots=_raw_snapshots(),
        home_xg=_xg("home", 1.6, 0.9),
        away_xg=_xg("away", 1.1, 1.3),
        home_rating=_rating("home", 1580.0),
        away_rating=_rating("away", 1500.0),
        home_value=None,
        away_value=None,
        home_history=[],
        away_history=[],
    )

    assert rows is not None
    assert rows["feature_names"] == list(feature_names)
    assert len(rows["home"]) == len(feature_names)
    assert len(rows["away"]) == len(feature_names)
    assert rows["home"][7] == 1.0
    assert rows["away"][7] == 0.0
    assert rows["snapshots"]["home"]["sample_count"] == 8


def test_feature_snapshot_rejects_inputs_observed_after_kickoff() -> None:
    pair = build_league_feature_pair(
        competition_id="allsvenskan",
        kickoff_utc=KICKOFF,
        home_xg=TeamXgSnapshot(
            team_id="home",
            observed_at=KICKOFF + timedelta(seconds=1),
            xg_for=1.4,
            xg_against=1.0,
            goals_for=1,
            goals_against=1,
        ),
        away_xg=_xg("away", 1.0, 1.4),
        home_rating=_rating("home", 1520.0),
        away_rating=_rating("away", 1490.0),
    )

    assert pair is None


def _xg(team_id: str, xg_for: float, xg_against: float) -> TeamXgSnapshot:
    return TeamXgSnapshot(
        team_id=team_id,
        observed_at=KICKOFF - timedelta(minutes=1),
        xg_for=xg_for,
        xg_against=xg_against,
        goals_for=1,
        goals_against=1,
    )


def _rating(team_id: str, elo: float) -> TeamRatingSnapshot:
    return TeamRatingSnapshot(
        team_id=team_id,
        observed_at=KICKOFF - timedelta(days=1),
        elo=elo,
        attack_strength=1.0,
        defence_strength=1.0,
        form_index=0.0,
    )


def _raw_snapshots() -> list[dict[str, Any]]:
    return cast(
        list[dict[str, Any]],
        [
            {
                "team_id": team_id,
                "as_of_time": (KICKOFF - timedelta(minutes=1)).isoformat(),
                "match_count": 8,
                "rolling_goals_for": 1.2,
                "rolling_goals_against": 1.0,
            }
            for team_id in ("home", "away")
        ],
    )
