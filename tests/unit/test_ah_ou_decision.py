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
FIXTURE_ID = "FIX1"


class FakeRepository:
    def __init__(self, snapshots: dict, history: list) -> None:
        self.snapshots = snapshots
        self.history = history

    def team_xg_rolling_snapshots_for_w2_teams(
        self, team_ids, *, before, competition_id, season, as_of_fixture_id=None
    ):
        rows = [self.snapshots[t] for t in team_ids if t in self.snapshots]
        if as_of_fixture_id is not None:
            rows = [r for r in rows if r.get("as_of_fixture_id") == as_of_fixture_id]
        return rows

    def canonical_match_history_for_teams(
        self, team_ids, *, before, limit_per_team=20,
        opponent_w2_id=None, fixture_status="FT",
    ):
        return [
            r for r in self.history
            if r["team_w2_id"] in team_ids
            and (opponent_w2_id is None or r["opponent_w2_id"] == opponent_w2_id)
            and r.get("fixture_status") == fixture_status
        ]


def _snapshot(team_id: str) -> dict:
    return {
        "team_id": team_id,
        "as_of_fixture_id": FIXTURE_ID,
        "as_of_time": (KICKOFF - timedelta(days=1)).isoformat(),
        "first_captured_at": (KICKOFF - timedelta(days=1)).isoformat(),
        "pit_proven": True,
        "rolling_xg_for": 1.2,
        "rolling_xg_against": 0.8,
        "rolling_goals_for": 1.1,
        "rolling_goals_against": 0.7,
    }


def _meetings() -> list[dict]:
    return [
        {
            "fixture_id": "FIX-PAST-1",
            "team_w2_id": "H",
            "opponent_w2_id": "A",
            "kickoff_utc": (KICKOFF - timedelta(days=30)).isoformat(),
            "team_side": "AWAY",
            "fixture_status": "FT",
            "goals_for": 1,
            "goals_against": 0,
            "endpoint_capture_id": "cap-1",
            "captured_at": (KICKOFF - timedelta(days=29)).isoformat(),
            "status_first_visible_at": (KICKOFF - timedelta(days=29)).isoformat(),
            "pit_proven": True,
        },
        {
            "fixture_id": "FIX-PAST-2",
            "team_w2_id": "H",
            "opponent_w2_id": "A",
            "kickoff_utc": (KICKOFF - timedelta(days=10)).isoformat(),
            "team_side": "HOME",
            "fixture_status": "FT",
            "goals_for": 2,
            "goals_against": 1,
            "endpoint_capture_id": "cap-2",
            "captured_at": (KICKOFF - timedelta(days=9)).isoformat(),
            "status_first_visible_at": (KICKOFF - timedelta(days=9)).isoformat(),
            "pit_proven": True,
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
        fixture_id=FIXTURE_ID,
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
        repo, fixture_id=FIXTURE_ID,
        home_team_id="H", away_team_id="A", kickoff=KICKOFF,
        competition_id="c", season="s",
        ah_line=-0.5, ah_home_odds=1.8, ah_away_odds=2.2,
        ou_line=2.5, ou_over_odds=1.9, ou_under_odds=1.9,
    )
    assert result["status"] == "F9_ROLLING_SNAPSHOT_NOT_UNIQUE"
    assert result["ah"] is None and result["ou"] is None


def test_build_ah_ou_selections_f6_missing() -> None:
    repo = _ready_repository()
    repo.history = []  # 无交锋
    result = build_ah_ou_selections(
        repo, fixture_id=FIXTURE_ID,
        home_team_id="H", away_team_id="A", kickoff=KICKOFF,
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


def _run(repo) -> dict:
    return build_ah_ou_selections(
        repo, fixture_id=FIXTURE_ID,
        home_team_id="H", away_team_id="A", kickoff=KICKOFF,
        competition_id="c", season="s",
        ah_line=-0.5, ah_home_odds=1.8, ah_away_odds=2.2,
        ou_line=2.5, ou_over_odds=1.9, ou_under_odds=1.9,
    )


def test_f9_backfill_not_pit_proven_is_refused() -> None:
    repo = _ready_repository()
    repo.snapshots["H"]["pit_proven"] = False
    assert _run(repo)["status"] == "F9_SNAPSHOT_NOT_PIT_PROVEN"


def test_f9_missing_first_capture_is_refused() -> None:
    repo = _ready_repository()
    repo.snapshots["H"].pop("first_captured_at")
    assert _run(repo)["status"] == "F9_SNAPSHOT_FIRST_CAPTURE_MISSING"


def test_f9_first_capture_after_decision_is_refused() -> None:
    repo = _ready_repository()
    repo.snapshots["H"]["first_captured_at"] = (
        KICKOFF - timedelta(hours=1)
    ).isoformat()  # 晚于 decision_at (kickoff-2h)
    assert _run(repo)["status"] == "F9_SNAPSHOT_FIRST_CAPTURE_AFTER_DECISION"


def test_f9_naive_asof_is_refused() -> None:
    repo = _ready_repository()
    repo.snapshots["H"]["as_of_time"] = "2026-07-31T12:00:00"  # 无时区
    assert _run(repo)["status"] == "F9_SNAPSHOT_AS_OF_NAIVE"


def test_f9_non_finite_value_is_refused() -> None:
    repo = _ready_repository()
    repo.snapshots["H"]["rolling_xg_for"] = float("nan")
    assert _run(repo)["status"] == "F9_SNAPSHOT_NON_FINITE"


def test_f6_captured_after_decision_is_refused() -> None:
    repo = _ready_repository()
    repo.history[0]["captured_at"] = (KICKOFF - timedelta(hours=1)).isoformat()
    assert _run(repo)["status"] == "F6_H2H_CAPTURED_AFTER_DECISION"


def test_f6_status_not_visible_at_decision_is_refused() -> None:
    repo = _ready_repository()
    repo.history[0]["status_first_visible_at"] = (KICKOFF - timedelta(hours=1)).isoformat()
    assert _run(repo)["status"] == "F6_H2H_STATUS_NOT_VISIBLE"


def test_f6_not_pit_proven_is_refused() -> None:
    repo = _ready_repository()
    repo.history[0]["pit_proven"] = False
    assert _run(repo)["status"] == "F6_H2H_NOT_PIT_PROVEN"


def test_f6_duplicate_meeting_is_refused() -> None:
    repo = _ready_repository()
    repo.history[1]["fixture_id"] = repo.history[0]["fixture_id"]
    assert _run(repo)["status"] == "F6_H2H_DUPLICATE_MEETING"
