"""AH/OU 决策编排（build_ah_ou_selections + build_softmax_market_analyses）单测。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from w2.strategy.ah_ou_decision import build_ah_ou_selections
from w2.strategy.analysis_recommendation import (
    AnalysisDecision,
    build_softmax_market_analyses,
)

KICKOFF = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


class FakeRepository:
    def __init__(self, snapshots: dict, history: list) -> None:
        self.snapshots = snapshots
        self.history = history

    def team_xg_rolling_snapshots_for_w2_teams(
        self, team_ids, *, before, competition_id, season
    ):
        return [self.snapshots[t] for t in team_ids if t in self.snapshots]

    def canonical_match_history_for_teams(self, team_ids, *, before, limit_per_team=20):
        return [r for r in self.history if r["team_w2_id"] in team_ids]


def _snapshot(team_id: str) -> dict:
    return {
        "team_id": team_id,
        "rolling_xg_for": 1.2,
        "rolling_xg_against": 0.8,
    }


def _meetings() -> list[dict]:
    return [
        {
            "team_w2_id": "H",
            "opponent_w2_id": "A",
            "kickoff_utc": (KICKOFF - timedelta(days=30)).isoformat(),
            "team_side": "AWAY",
            "goals_for": 1,
            "goals_against": 0,
        },
        {
            "team_w2_id": "H",
            "opponent_w2_id": "A",
            "kickoff_utc": (KICKOFF - timedelta(days=10)).isoformat(),
            "team_side": "HOME",
            "goals_for": 2,
            "goals_against": 1,
        },
    ]


def _ready_repository() -> FakeRepository:
    return FakeRepository(
        snapshots={"H": _snapshot("H"), "A": _snapshot("A")},
        history=_meetings(),
    )


def test_build_ah_ou_selections_ready() -> None:
    result = build_ah_ou_selections(
        _ready_repository(),
        home_team_id="H", away_team_id="A", kickoff=KICKOFF,
        competition_id="c", season="s",
        ah_line=-0.5, ah_home_odds=1.8, ah_away_odds=2.2,
        ou_line=2.5, ou_over_odds=1.9, ou_under_odds=1.9,
    )
    assert result["status"] == "READY"
    assert result["ah"]["side"] in {"HOME", "AWAY"}
    assert "selected" in result["ah"]
    assert 0.0 <= result["ou"]["factor_over_share"] <= 1.0


def test_build_ah_ou_selections_f9_missing() -> None:
    repo = _ready_repository()
    repo.snapshots = {"H": _snapshot("H")}  # 缺 A 队快照
    result = build_ah_ou_selections(
        repo, home_team_id="H", away_team_id="A", kickoff=KICKOFF,
        competition_id="c", season="s",
        ah_line=-0.5, ah_home_odds=1.8, ah_away_odds=2.2,
        ou_line=2.5, ou_over_odds=1.9, ou_under_odds=1.9,
    )
    assert result["status"] == "F9_ROLLING_SNAPSHOT_MISSING"
    assert result["ah"] is None and result["ou"] is None


def test_build_ah_ou_selections_f6_missing() -> None:
    repo = _ready_repository()
    repo.history = []  # 无交锋
    result = build_ah_ou_selections(
        repo, home_team_id="H", away_team_id="A", kickoff=KICKOFF,
        competition_id="c", season="s",
        ah_line=-0.5, ah_home_odds=1.8, ah_away_odds=2.2,
        ou_line=2.5, ou_over_odds=1.9, ou_under_odds=1.9,
    )
    assert result["status"] == "F6_H2H_MISSING"


def test_softmax_market_analyses_ah_pick() -> None:
    ah, ou = build_softmax_market_analyses(
        ah_selection={"side": "HOME", "score": 0.12, "selected": True,
                      "factor_home_cover_p": 0.6, "market_home_cover_p": 0.55},
        ou_selection={"edge": 0.01, "selected": False,
                      "factor_over_share": 0.51, "market_over_q": 0.5},
        status="READY",
    )
    assert ah.decision == AnalysisDecision.ANALYSIS_PICK
    assert ah.tendency == "HOME_AH"
    assert ou.decision == AnalysisDecision.NO_EDGE


def test_softmax_market_analyses_ou_pick() -> None:
    ah, ou = build_softmax_market_analyses(
        ah_selection={"side": "AWAY", "score": 0.02, "selected": False,
                      "factor_home_cover_p": 0.4, "market_home_cover_p": 0.45},
        ou_selection={"edge": 0.06, "selected": True,
                      "factor_over_share": 0.56, "market_over_q": 0.5},
        status="READY",
    )
    assert ah.decision == AnalysisDecision.NO_EDGE
    assert ou.decision == AnalysisDecision.ANALYSIS_PICK
    assert ou.tendency == "OVER"


def test_softmax_market_analyses_skip_on_missing() -> None:
    ah, ou = build_softmax_market_analyses(
        ah_selection=None, ou_selection=None, status="F9_ROLLING_SNAPSHOT_MISSING"
    )
    assert ah.decision == AnalysisDecision.SKIP
    assert ou.decision == AnalysisDecision.SKIP
