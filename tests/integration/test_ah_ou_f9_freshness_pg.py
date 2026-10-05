"""F9 新鲜度门（断供 vs 休赛）：隔离 PG 真实链，非 mock。

用真实 producer 构造器（history_rows_from_fixture / capture_h2h_for_pair）把
一场「更近 FT」写进 canonical_team_match_history（比赛日历），但 team_xg_match
不更新（模拟 api-football 对次级联赛停止返回 expected_goals），从而让
latest_finished_fixture_kickoffs_for_teams 返回的比赛日历最新 FT 比 F9 快照
source_matches 的 xG 覆盖边界更新 → 决策 SKIP F9_SNAPSHOT_STALE（selected=false）。

每个测试函数用独立的 ``chain``（``_build_chain`` 每次新建独立数据库），决策
一次即冻结 cohort，故「正常」与「断供」必须分属独立 fixture 链。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.factor_model.remediation import history_rows_from_fixture
from w2.infrastructure.persistence.factor_model_models import CanonicalTeamMatchHistoryModel
from w2.ingestion.h2h_capture import capture_h2h_for_pair
from w2.prematch.analysis_calculator import ReadModelService
from w2.providers.api_football import LiveApiFootballResponse

pytest_plugins = ["tests.integration.test_ah_ou_v9_system_pg"]


def _latest_ft_kickoff(repo, team_w2_id: str) -> datetime | None:
    with Session(repo.engine) as session:
        rows = list(
            session.scalars(
                select(CanonicalTeamMatchHistoryModel)
                .where(
                    CanonicalTeamMatchHistoryModel.team_w2_id == team_w2_id,
                    CanonicalTeamMatchHistoryModel.fixture_status == "FT",
                )
                .order_by(CanonicalTeamMatchHistoryModel.kickoff_utc.desc())
            )
        )
    return rows[0].kickoff_utc if rows else None


def _inject_stale_ft(repo, kickoff: datetime, fixture_id: str = "9103") -> datetime:
    """用真实 producer 构造器把一场「更近 FT」写进比赛日历（无对应 xG）。"""
    new_kickoff = kickoff - timedelta(days=2)
    rows = history_rows_from_fixture(
        {
            "fixture": {
                "id": fixture_id,
                "date": new_kickoff.isoformat(),
                "status": {"short": "FT"},
            },
            "league": {"id": 113, "season": "2026"},
            "teams": {"home": {"id": 10}, "away": {"id": 20}},
            "goals": {"home": 2, "away": 1},
        },
        competition_id="allsvenskan",
        season="2026",
        source_raw_hash="c" * 64,
        endpoint_capture_id=None,
        captured_at=new_kickoff + timedelta(hours=2),
        provider_to_w2={"10": "H", "20": "A"},
    )
    assert len(rows) == 2  # HOME + AWAY 各一行
    with Session(repo.engine) as session:
        session.add_all(CanonicalTeamMatchHistoryModel(**row) for row in rows)
        session.commit()
    return new_kickoff


def _stale_decision_assertions(card: dict) -> None:
    """断供断言：status=F9_SNAPSHOT_STALE、方向 0、落账本为 SKIP 且 reason 曝光。"""
    ah_ou = card["ah_ou_result"]
    assert ah_ou["status"] == "F9_SNAPSHOT_STALE"
    assert ah_ou["ah"] is None and ah_ou["ou"] is None
    assert ah_ou["market_reasons"] == {
        "ASIAN_HANDICAP": "F9_SNAPSHOT_STALE",
        "TOTALS": "F9_SNAPSHOT_STALE",
    }
    decisions = ah_ou["recording"]["receipt"]["decisions"]
    assert {d["market"] for d in decisions} == {"ASIAN_HANDICAP", "TOTALS"}
    assert all(not d["selected"] for d in decisions)
    assert all(d["skip_reason"] == "F9_SNAPSHOT_STALE" for d in decisions)


def test_f9_freshness_gate_reject_stale(chain):
    """① 断供：比赛日历最近 FT 比快照 xG 覆盖边界新 → SKIP F9_SNAPSHOT_STALE。"""
    repo, future, _, _ = chain
    kickoff = datetime.fromisoformat(future["fixture"]["date"]).astimezone(UTC)
    home_before = _latest_ft_kickoff(repo, "H")
    assert home_before is not None

    # 决策前注入断供：推进比赛日历，但不更新 xG。
    _inject_stale_ft(repo, kickoff)
    assert _latest_ft_kickoff(repo, "H") > home_before  # 比赛日历已推进

    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=kickoff
    )
    _stale_decision_assertions(card)


def test_f9_freshness_gate_recess_not_refused(chain):
    """② 休赛 + ③ 正常：无断供注入，比赛日历未推进 → 不误杀（正常决策）。"""
    _, future, _, _ = chain
    kickoff = datetime.fromisoformat(future["fixture"]["date"]).astimezone(UTC)
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=kickoff
    )
    ah_ou = card["ah_ou_result"]
    assert ah_ou["status"] == "READY", ah_ou
    assert ah_ou["recording"]["status"] == "COMMITTED"


def _freshness_h2h_client(repo, now, extra_kickoff):
    """真实 h2h producer client：在既有 FT 之外追加一场「更近 FT」。"""

    class H2H:
        def request_live(self, endpoint, params):
            assert endpoint == "h2h"
            from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel

            with Session(repo.engine) as session:
                raw_rows = list(
                    session.scalars(
                        select(RawPayloadModel).where(RawPayloadModel.endpoint == "fixtures")
                    )
                )
            items = []
            for row in raw_rows:
                for item in row.payload.get("response", []):
                    status = (item.get("fixture") or {}).get("status") or {}
                    if status.get("short") == "FT":
                        items.append(item)
            items.append(
                {
                    "fixture": {
                        "id": 9103,
                        "date": extra_kickoff.isoformat(),
                        "status": {"short": "FT"},
                    },
                    "league": {"id": 113, "season": 2026},
                    "teams": {"home": {"id": 10}, "away": {"id": 20}},
                    "goals": {"home": 2, "away": 1},
                }
            )
            return LiveApiFootballResponse(
                endpoint=endpoint,
                params=params,
                status_code=200,
                elapsed_ms=1,
                payload={"response": items},
                headers={},
                captured_at=now,
                requested_at=now,
            )

    return H2H()


def test_f9_freshness_gate_stale_via_real_h2h_producer(chain):
    """① 断供经真实 h2h producer（capture_h2h_for_pair）写入比赛日历 → SKIP。"""
    repo, future, _, _ = chain
    kickoff = datetime.fromisoformat(future["fixture"]["date"]).astimezone(UTC)
    now = datetime.now(UTC)
    extra_kickoff = kickoff - timedelta(days=2)
    client = _freshness_h2h_client(repo, now, extra_kickoff)
    inserted = capture_h2h_for_pair(
        home_provider_team_id="10",
        away_provider_team_id="20",
        competition_id="allsvenskan",
        season="2026",
        client=client,
    )
    assert inserted > 0, "h2h producer must insert the newer FT"

    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=kickoff
    )
    _stale_decision_assertions(card)
