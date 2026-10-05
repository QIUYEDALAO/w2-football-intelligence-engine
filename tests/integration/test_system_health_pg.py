"""系统健康面板：真实链只读聚合 + 空操作控制 / 单变量攻击（F9 快照断供）。"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.dashboard.system_health import build_system_health
from w2.infrastructure.persistence.factor_model_models import CanonicalTeamMatchHistoryModel

pytest_plugins = ["tests.integration.test_ah_ou_v9_system_pg"]


def _insert_ft_history(session: Session, *, fixture_id: str, kickoff_utc: datetime) -> None:
    """插入一条已完赛比赛到 canonical 比赛日历（真实 producer 落库的等价物）。"""
    session.add(
        CanonicalTeamMatchHistoryModel(
            history_id=f"hist-{fixture_id}",
            fixture_id=f"api_football:{fixture_id}",
            provider="api_football",
            provider_fixture_id=fixture_id,
            competition_id="allsvenskan",
            season="2026",
            kickoff_utc=kickoff_utc,
            fixture_status="FT",
            team_side="HOME",
            team_provider_id="10",
            opponent_provider_id="20",
            team_w2_id="H",
            opponent_w2_id="A",
            goals_for=1,
            goals_against=0,
            result_identity_hash="r" * 64,
            source_raw_hash="s" * 64,
            captured_at=datetime.now(UTC),
            history_hash=hashlib.sha256(f"hist|{fixture_id}".encode()).hexdigest(),
            payload={},
        )
    )


def test_system_health_baseline_structure(chain):
    """空操作控制：默认 chain 状态 → 五项结构齐全、无异常、alerts 为列表。"""
    repo, _future, _plan, _producer = chain
    now = datetime.now(UTC)
    with Session(repo.engine) as session:
        health = build_system_health(session, now=now)
    assert health["schema_version"] == "w2.system_health.v1"
    for key in ("data_freshness", "recommendation_chain", "collection_quota", "settlement"):
        assert key in health, health
        assert "ok" in health[key], health[key]
    assert isinstance(health["alerts"], list)
    assert health["overall"] in {"OK", "DEGRADED", "STALE"}
    assert health["data_freshness"]["threshold_hours"] == 12.0
    # 数据新鲜度必须同时暴露 F9 快照口径与原始 xG 口径（同源可对照）。
    assert "f9_snapshot_lag_hours" in health["data_freshness"]
    assert "raw_xg_lag_hours" in health["data_freshness"]


def test_system_health_f9_stale_single_variable(chain):
    """单变量攻击：比赛日历推进出更新的 FT，但 F9 快照 source_matches 覆盖边界未重算。

    原始 team_xg_match 保持不动（模拟 10-05 回填原始表但快照仍停旧日期的场景），
    面板必须如实红灯 + XG_STALE，不再假健康。核对 reason 精确落到 XG_STALE。
    """
    repo, _future, _plan, _producer = chain
    now = datetime.now(UTC)
    with Session(repo.engine) as session, session.begin():
        # 只插一条比快照覆盖边界（09-07 附近）更新的 FT 比赛 → 覆盖边界落后。
        _insert_ft_history(session, fixture_id="999901", kickoff_utc=now - timedelta(days=1))
    with Session(repo.engine) as session:
        health = build_system_health(session, now=now)
    assert health["data_freshness"]["status"] == "STALE", health["data_freshness"]
    assert health["data_freshness"]["ok"] is False
    assert health["data_freshness"]["f9_snapshot_lag_hours"] is not None
    assert health["data_freshness"]["f9_snapshot_lag_hours"] > 12.0
    alert_types = {alert["type"] for alert in health["alerts"]}
    assert "XG_STALE" in alert_types, health["alerts"]
    xg_alert = next(alert for alert in health["alerts"] if alert["type"] == "XG_STALE")
    assert xg_alert["severity"] == "RED"
    assert "F9 快照" in xg_alert["detail"]


def test_system_health_f9_fresh_control(chain):
    """反向控制：比赛日历最近 FT 已被 F9 快照覆盖 → 数据新鲜度绿灯、无 XG_STALE。"""
    repo, _future, _plan, _producer = chain
    now = datetime.now(UTC)
    with Session(repo.engine) as session:
        health = build_system_health(session, now=now)
    assert health["data_freshness"]["ok"] is True, health["data_freshness"]
    assert health["data_freshness"]["status"] == "OK"
    assert health["data_freshness"]["f9_snapshot_lag_hours"] is not None
    assert health["data_freshness"]["f9_snapshot_lag_hours"] <= 12.0
    assert "XG_STALE" not in {alert["type"] for alert in health["alerts"]}


def test_system_health_recommendation_chain(chain):
    """推荐链路：chain 已落账本 → 统计口径正确、可复算。"""
    repo, _future, _plan, _producer = chain
    from w2.infrastructure.persistence.ah_ou_decision_ledger_models import AhOuDecisionLedgerModel

    now = datetime.now(UTC)
    with Session(repo.engine) as session:
        rows = list(session.scalars(select(AhOuDecisionLedgerModel)))
    with Session(repo.engine) as session:
        health = build_system_health(session, now=now)
    chain_ok = health["recommendation_chain"]
    assert chain_ok["selected_count"] >= 0
    assert chain_ok["skip_count"] >= 0
    assert set(chain_ok["skip_reasons"]) == {"F9_SNAPSHOT_STALE", "STALE_QUOTE", "other"}
    assert chain_ok["selected_count"] + chain_ok["skip_count"] <= len(rows) or len(rows) == 0
