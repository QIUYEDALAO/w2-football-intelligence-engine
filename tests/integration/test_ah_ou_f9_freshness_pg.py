"""F9 新鲜度门（断供 vs 休赛 vs 前瞻偏差）：隔离 PG 真实链，非 mock。

F1：比赛日历最近 FT 的对照基准改用 ``matchday_fixture_identities.fixture_status='FT'``
（独立于 xG 链）。断供 = xG 链冻结但 fixture_status 照常推进 → F9 门必须报
F9_SNAPSHOT_STALE；休赛 = 无新 FT → 不误杀；前瞻偏差 = captured_at 晚于 decision_at
的 FT 不可见 → 不引入未来信息。

每个测试函数用独立的 ``chain``（``_build_chain`` 每次新建独立数据库），决策一次即
冻结 cohort，故「正常」与「断供」必须分属独立 fixture 链。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.matchday_intake_models import MatchdayFixtureIdentityModel
from w2.prematch.analysis_calculator import ReadModelService

pytest_plugins = ["tests.integration.test_ah_ou_v9_system_pg"]


def _latest_ft_kickoff(repo, team_w2_id: str) -> datetime | None:
    """比赛日历（matchday_fixture_identities.fixture_status='FT'）最近 kickoff。"""
    with Session(repo.engine) as session:
        home = session.scalar(
            select(func.max(MatchdayFixtureIdentityModel.kickoff_utc)).where(
                MatchdayFixtureIdentityModel.home_w2_team_id == team_w2_id,
                MatchdayFixtureIdentityModel.fixture_status == "FT",
            )
        )
        away = session.scalar(
            select(func.max(MatchdayFixtureIdentityModel.kickoff_utc)).where(
                MatchdayFixtureIdentityModel.away_w2_team_id == team_w2_id,
                MatchdayFixtureIdentityModel.fixture_status == "FT",
            )
        )
    candidates = [t for t in (home, away) if t is not None]
    return max(candidates) if candidates else None


def _inject_ft(repo, *, fixture_id: str, kickoff_utc: datetime, captured_at: datetime) -> datetime:
    """往 matchday_fixture_identities 写一场已完赛 (FT) 赛程（独立于 xG 链）。"""
    with Session(repo.engine) as session:
        session.add(
            MatchdayFixtureIdentityModel(
                fixture_id=f"api_football:{fixture_id}",
                provider="api_football",
                provider_fixture_id=fixture_id,
                competition_id="allsvenskan",
                provider_league_id="113",
                season="2026",
                kickoff_utc=kickoff_utc,
                fixture_status="FT",
                home_provider_team_id="10",
                away_provider_team_id="20",
                home_w2_team_id="H",
                away_w2_team_id="A",
                team_identity_status="PROVIDER_PRIMARY_READY",
                raw_payload_sha256="c" * 64,
                captured_at=captured_at,
                identity_hash="i" * 64,
                payload={},
            )
        )
        session.commit()
    return kickoff_utc


def _inject_stale_ft(repo, kickoff: datetime, fixture_id: str = "9103") -> datetime:
    """断供：一场「更近 FT」且 captured_at <= decision_at（决策时点已可见）。"""
    new_kickoff = kickoff - timedelta(days=2)
    return _inject_ft(
        repo,
        fixture_id=fixture_id,
        kickoff_utc=new_kickoff,
        captured_at=new_kickoff + timedelta(hours=2),
    )


def _inject_lookahead_ft(repo, kickoff: datetime, fixture_id: str = "9104") -> datetime:
    """前瞻：一场「更近 FT」但 captured_at > decision_at（决策时点不可见，须被 PIT 排除）。"""
    new_kickoff = kickoff - timedelta(days=2)
    return _inject_ft(
        repo,
        fixture_id=fixture_id,
        kickoff_utc=new_kickoff,
        captured_at=kickoff + timedelta(hours=1),  # 晚于 decision_at（kickoff-2h）
    )


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
    """① 断供：fixture_status 日历最近 FT 比快照 xG 覆盖边界新 → SKIP F9_SNAPSHOT_STALE。"""
    repo, future, _, _ = chain
    kickoff = datetime.fromisoformat(future["fixture"]["date"]).astimezone(UTC)
    home_before = _latest_ft_kickoff(repo, "H")
    assert home_before is None  # chain 无 matchday FT 日历

    # 决策前注入断供：推进 fixture_status 日历，但不更新 xG。
    _inject_stale_ft(repo, kickoff)
    assert _latest_ft_kickoff(repo, "H") is not None  # 比赛日历已推进

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


def test_f9_freshness_gate_no_lookahead(chain):
    """④ 前瞻偏差防护：captured_at > decision_at 的 FT 不可见 → 不 STALE（不误读未来）。"""
    repo, future, _, _ = chain
    kickoff = datetime.fromisoformat(future["fixture"]["date"]).astimezone(UTC)

    # 注入一场「更近 FT」但采集时点晚于 decision_at（决策时点尚未可见）。
    _inject_lookahead_ft(repo, kickoff)

    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=kickoff
    )
    ah_ou = card["ah_ou_result"]
    assert ah_ou["status"] == "READY", ah_ou
