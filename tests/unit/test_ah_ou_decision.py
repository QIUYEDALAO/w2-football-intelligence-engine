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
        # F9 新鲜度门：默认无「最近 FT」记录（休赛），供既有测试走「跳过门」路径。
        self.latest_ft_kickoffs: dict[str, datetime] = {}
        # Immutable synthetic source controls; later attacks mutate the
        # projection only, never rewrite its source oracle.
        from w2.domain.canonical_serialization import (
            HashDomain,
            SerializerVersion,
            canonical_sha256,
        )

        self.captures = {}
        for row in history:
            home = row["team_side"] == "HOME"
            item = {
                "fixture": {
                    "id": row["fixture_id"],
                    "date": row["kickoff_utc"],
                    "status": {"short": "FT"},
                },
                "teams": {
                    "home": {"id": "10" if home else "20"},
                    "away": {"id": "20" if home else "10"},
                },
                "goals": {
                    "home": row["goals_for"] if home else row["goals_against"],
                    "away": row["goals_against"] if home else row["goals_for"],
                },
            }
            raw = {"response": [item]}
            sha = canonical_sha256(
                raw,
                domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
                version=SerializerVersion.LEGACY_V1,
            )
            row.update(team_provider_id="10", opponent_provider_id="20", source_raw_hash=sha)
            self.captures[row["endpoint_capture_id"]] = {
                "fixture_id": row["fixture_id"],
                "capture_status": "CAPTURED",
                "status_code": 200,
                "provider_captured_at": row["captured_at"],
                "raw_captured_at": row["captured_at"],
                "raw_payload": raw,
                "raw_payload_sha256": sha,
            }

    def endpoint_captures_for_ids(self, ids):
        return {cid: self.captures[cid] for cid in ids if cid in self.captures}

    def team_xg_rolling_snapshots_for_w2_teams(
        self, team_ids, *, before, competition_id, season, as_of_fixture_id=None
    ):
        rows = [self.snapshots[t] for t in team_ids if t in self.snapshots]
        if as_of_fixture_id is not None:
            rows = [r for r in rows if r.get("as_of_fixture_id") == as_of_fixture_id]
        return rows

    def canonical_match_history_for_teams(
        self,
        team_ids,
        *,
        before,
        limit_per_team=20,
        opponent_w2_id=None,
        fixture_status="FT",
    ):
        return [
            r
            for r in self.history
            if r["team_w2_id"] in team_ids
            and (opponent_w2_id is None or r["opponent_w2_id"] == opponent_w2_id)
            and r.get("fixture_status") == fixture_status
        ]

    def latest_finished_fixture_kickoffs_for_teams(self, team_ids, *, before):
        return {
            team_id: kickoff
            for team_id, kickoff in self.latest_ft_kickoffs.items()
            if team_id in team_ids
        }


def _snapshot(team_id: str, *, source_matches: list[dict] | None = None) -> dict:
    snapshot = {
        "team_id": team_id,
        "as_of_fixture_id": FIXTURE_ID,
        "as_of_time": (KICKOFF - timedelta(days=1)).isoformat(),
        "first_captured_at": (KICKOFF - timedelta(days=1)).isoformat(),
        "first_committed_at": (KICKOFF - timedelta(days=1)).isoformat(),
        "pit_proven": True,
        "rolling_xg_for": 1.2,
        "rolling_xg_against": 0.8,
        "rolling_goals_for": 1.1,
        "rolling_goals_against": 0.7,
    }
    if source_matches is not None:
        snapshot["source_matches"] = source_matches
    return snapshot


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
        home_team_id="H",
        away_team_id="A",
        kickoff=KICKOFF,
        competition_id="c",
        season="s",
        ah_line=-0.5,
        ah_home_odds=1.8,
        ah_away_odds=2.2,
        ou_line=2.5,
        ou_over_odds=1.9,
        ou_under_odds=1.9,
    )
    assert result["status"] == "READY"
    assert result["ah"]["side"] in {"HOME", "AWAY"}
    assert "selected" in result["ah"]
    assert 0.0 <= result["ou"]["factor_over_share"] <= 1.0


def test_build_ah_ou_selections_f9_missing() -> None:
    repo = _ready_repository()
    repo.snapshots = {"H": _snapshot("H")}  # 缺 A 队快照
    result = build_ah_ou_selections(
        repo,
        fixture_id=FIXTURE_ID,
        home_team_id="H",
        away_team_id="A",
        kickoff=KICKOFF,
        competition_id="c",
        season="s",
        ah_line=-0.5,
        ah_home_odds=1.8,
        ah_away_odds=2.2,
        ou_line=2.5,
        ou_over_odds=1.9,
        ou_under_odds=1.9,
    )
    assert result["status"] == "F9_ROLLING_SNAPSHOT_NOT_UNIQUE"
    assert result["ah"] is None and result["ou"] is None


def test_build_ah_ou_selections_f6_missing() -> None:
    repo = _ready_repository()
    repo.history = []  # 无交锋
    result = build_ah_ou_selections(
        repo,
        fixture_id=FIXTURE_ID,
        home_team_id="H",
        away_team_id="A",
        kickoff=KICKOFF,
        competition_id="c",
        season="s",
        ah_line=-0.5,
        ah_home_odds=1.8,
        ah_away_odds=2.2,
        ou_line=2.5,
        ou_over_odds=1.9,
        ou_under_odds=1.9,
    )
    assert result["status"] == "F6_H2H_MISSING"


def test_softmax_market_analyses_ah_pick() -> None:
    ah, ou = build_softmax_market_analyses(
        ah_selection={
            "side": "HOME",
            "score": 0.12,
            "selected": True,
            "factor_home_cover_p": 0.6,
            "market_home_cover_p": 0.55,
        },
        ou_selection={
            "edge": 0.01,
            "selected": False,
            "factor_over_share": 0.51,
            "market_over_q": 0.5,
        },
        status="READY",
    )
    assert ah.decision == AnalysisDecision.ANALYSIS_PICK
    assert ah.tendency == "HOME_AH"
    assert ou.decision == AnalysisDecision.NO_EDGE


def test_softmax_market_analyses_ou_pick() -> None:
    ah, ou = build_softmax_market_analyses(
        ah_selection={
            "side": "AWAY",
            "score": 0.02,
            "selected": False,
            "factor_home_cover_p": 0.4,
            "market_home_cover_p": 0.45,
        },
        ou_selection={
            "edge": 0.06,
            "selected": True,
            "factor_over_share": 0.56,
            "market_over_q": 0.5,
        },
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
        repo,
        fixture_id=FIXTURE_ID,
        home_team_id="H",
        away_team_id="A",
        kickoff=KICKOFF,
        competition_id="c",
        season="s",
        ah_line=-0.5,
        ah_home_odds=1.8,
        ah_away_odds=2.2,
        ou_line=2.5,
        ou_over_odds=1.9,
        ou_under_odds=1.9,
    )


def test_f6_capture_lookup_port_is_required_and_fail_closed() -> None:
    from types import SimpleNamespace

    control = _ready_repository()
    assert _run(control)["status"] == "READY"
    missing = SimpleNamespace(
        team_xg_rolling_snapshots_for_w2_teams=control.team_xg_rolling_snapshots_for_w2_teams,
        canonical_match_history_for_teams=control.canonical_match_history_for_teams,
        latest_finished_fixture_kickoffs_for_teams=(
            control.latest_finished_fixture_kickoffs_for_teams
        ),
    )
    assert _run(missing)["status"] == "F6_H2H_CAPTURE_LOOKUP_REQUIRED"
    control.endpoint_captures_for_ids = lambda ids: (_ for _ in ()).throw(
        RuntimeError("lookup failed")
    )
    assert _run(control)["status"] == "F6_H2H_CAPTURE_LOOKUP_FAILED"


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


def test_f6_raw_earlier_than_provider_is_accepted() -> None:
    # 去重场景：h2h raw 按 sha256 去重，raw.captured_at 停在首次入库（早 5 天），
    # provider_captured_at 是本次采集。raw 早于 provider 合法，不再 MISMATCH。
    repo = _ready_repository()
    repo.captures["cap-1"]["provider_captured_at"] = "2026-07-03T12:00:00+00:00"
    repo.captures["cap-1"]["raw_captured_at"] = "2026-06-28T12:00:00+00:00"
    assert _run(repo)["status"] == "READY"


def test_f6_raw_later_than_provider_is_refused() -> None:
    # 攻击：raw_captured_at 晚于 provider（回填/篡改）→ 仍拒，防线未失效。
    repo = _ready_repository()
    repo.captures["cap-1"]["raw_captured_at"] = "2026-07-03T12:05:00+00:00"
    assert _run(repo)["status"] == "F6_H2H_RAW_CAPTURE_TIME_MISMATCH"


@pytest.mark.parametrize("line", [-0.25, -0.75, -1.25, -1.0, -2.0, -0.5])
def test_build_ah_ou_selections_quarter_increment_ready(line: float) -> None:
    result = build_ah_ou_selections(
        _ready_repository(),
        fixture_id=FIXTURE_ID,
        home_team_id="H",
        away_team_id="A",
        kickoff=KICKOFF,
        competition_id="c",
        season="s",
        ah_line=line,
        ah_home_odds=1.8,
        ah_away_odds=2.2,
        ou_line=2.5,
        ou_over_odds=1.9,
        ou_under_odds=1.9,
    )
    assert result["status"] == "READY"
    assert result["ah"] is not None


def test_build_ah_ou_selections_non_quarter_line_refused() -> None:
    result = build_ah_ou_selections(
        _ready_repository(),
        fixture_id=FIXTURE_ID,
        home_team_id="H",
        away_team_id="A",
        kickoff=KICKOFF,
        competition_id="c",
        season="s",
        ah_line=0.3,
        ah_home_odds=1.8,
        ah_away_odds=2.2,
        ou_line=2.5,
        ou_over_odds=1.9,
        ou_under_odds=1.9,
    )
    assert result["status"] == "AH_LINE_NOT_QUARTER_INCREMENT"
    assert result["ah"] is None
    assert result["ou"] is None
    assert result["market_reasons"] == {
        "ASIAN_HANDICAP": "AH_LINE_NOT_QUARTER_INCREMENT",
        "TOTALS": "DEPENDENCY_BLOCKED",
    }


def test_market_reasons_for_status_ah_ou_independent() -> None:
    from w2.strategy.ah_ou_decision import market_reasons_for_status

    assert market_reasons_for_status("AH_LINE_NOT_QUARTER_INCREMENT") == {
        "ASIAN_HANDICAP": "AH_LINE_NOT_QUARTER_INCREMENT",
        "TOTALS": "DEPENDENCY_BLOCKED",
    }
    assert market_reasons_for_status("OU_LINE_INVALID") == {
        "ASIAN_HANDICAP": "DEPENDENCY_BLOCKED",
        "TOTALS": "OU_LINE_INVALID",
    }
    assert market_reasons_for_status("FIXTURE_IDENTITY_NOT_READY") == {
        "ASIAN_HANDICAP": "FIXTURE_IDENTITY_NOT_READY",
        "TOTALS": "FIXTURE_IDENTITY_NOT_READY",
    }


def _match(kickoff: datetime, fixture_id: str = "PAST-M") -> dict:
    return {"fixture_id": fixture_id, "kickoff_at": kickoff.isoformat()}


def test_f9_stale_snapshot_is_refused() -> None:
    """断供：比赛日历最新 FT 比快照 xG 覆盖到的最新比赛更新 → SKIP F9_SNAPSHOT_STALE。"""
    repo = _ready_repository()
    # 快照 xG 覆盖到 09-20（source_matches 最新一场），但球队 09-27 又打了一场 FT。
    repo.snapshots["H"] = _snapshot(
        "H", source_matches=[_match(KICKOFF - timedelta(days=10))]
    )
    repo.snapshots["A"] = _snapshot(
        "A", source_matches=[_match(KICKOFF - timedelta(days=10))]
    )
    repo.latest_ft_kickoffs = {
        "H": KICKOFF - timedelta(days=3),  # 09-27 比 09-20 新
        "A": KICKOFF - timedelta(days=3),
    }
    result = _run(repo)
    assert result["status"] == "F9_SNAPSHOT_STALE"
    assert result["ah"] is None and result["ou"] is None
    assert result["market_reasons"] == {
        "ASIAN_HANDICAP": "F9_SNAPSHOT_STALE",
        "TOTALS": "F9_SNAPSHOT_STALE",
    }


def test_f9_recess_snapshot_not_refused() -> None:
    """休赛：快照 xG 覆盖到最新 FT（相等）→ 不 SKIP（不误杀冬歇/国际比赛日）。"""
    repo = _ready_repository()
    repo.snapshots["H"] = _snapshot(
        "H", source_matches=[_match(KICKOFF - timedelta(days=10))]
    )
    repo.snapshots["A"] = _snapshot(
        "A", source_matches=[_match(KICKOFF - timedelta(days=10))]
    )
    # 最新 FT == 快照 xG 覆盖到的最后一场（无更新 FT）→ 休赛，不 SKIP。
    repo.latest_ft_kickoffs = {
        "H": KICKOFF - timedelta(days=10),
        "A": KICKOFF - timedelta(days=10),
    }
    assert _run(repo)["status"] == "READY"


def test_f9_fresh_snapshot_not_refused() -> None:
    """正常：每轮都有 xG，快照 xG 覆盖跟上最新 FT → 不 SKIP。"""
    repo = _ready_repository()
    # 快照 xG 覆盖到 09-27（最新 FT 也到 09-27，相等）→ 正常。
    repo.snapshots["H"] = _snapshot(
        "H", source_matches=[_match(KICKOFF - timedelta(days=3))]
    )
    repo.snapshots["A"] = _snapshot(
        "A", source_matches=[_match(KICKOFF - timedelta(days=3))]
    )
    repo.latest_ft_kickoffs = {
        "H": KICKOFF - timedelta(days=3),
        "A": KICKOFF - timedelta(days=3),
    }
    assert _run(repo)["status"] == "READY"


def test_f9_no_ft_history_not_refused() -> None:
    """无 FT 比赛（latest_ft 为空）→ 无法判断断供，跳过门，由其他门把关。"""
    repo = _ready_repository()
    repo.snapshots["H"] = _snapshot(
        "H", source_matches=[_match(KICKOFF - timedelta(days=10))]
    )
    repo.snapshots["A"] = _snapshot(
        "A", source_matches=[_match(KICKOFF - timedelta(days=10))]
    )
    repo.latest_ft_kickoffs = {}  # 无 FT 记录
    assert _run(repo)["status"] == "READY"
