"""今日推荐健康度主动通知：真实链 enqueue 幂等 + 断供/正常/静默三档。"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.dashboard.date_window import football_day_for_kickoff
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import AhOuDecisionLedgerModel
from w2.infrastructure.persistence.dynamic_prematch_models import CandidateNotificationOutboxModel
from w2.prematch.analysis_calculator import ReadModelService
from w2.prematch.candidate_notifications import (
    TODAY_RECOMMEND_HEALTH,
    _event_id,
    deliver_pending_notifications,
    enqueue_today_recommend_health_in_session,
    render_bark_message,
)

pytest_plugins = ["tests.integration.test_ah_ou_v9_system_pg"]


def _skip_decision_id(fixture_id: str, market: str, skip_reason: str) -> str:
    return hashlib.sha256(f"health-skip|{fixture_id}|{market}|{skip_reason}".encode()).hexdigest()


def _insert_skip_row(repo, *, fixture_id: str, decision_at: datetime, skip_reason: str) -> None:
    """测试 setup：插入一条 SKIP 账本行，模拟 F9 断供/报价旧等 SKIP 场景。"""
    with Session(repo.engine) as session, session.begin():
        session.add(
            AhOuDecisionLedgerModel(
                decision_id=_skip_decision_id(fixture_id, "TOTALS", skip_reason),
                fixture_id=fixture_id,
                market="TOTALS",
                decision_at=decision_at,
                model_version="m1",
                calibration_version="c1",
                input_hash="i" * 64,
                full_distribution={"selection": None},
                decision_contract="w2.ah_ou_decision.v3.1",
                frozen_terms=None,
                terms_hash=None,
                quote_identity_hash="q" * 64,
                source_capture_sha256="s" * 64,
                capture_id="cap-skip",
                source_id="src-skip",
                home_team_id="H",
                away_team_id="A",
                selected=False,
                direction=None,
                score="0",
                skip_reason=skip_reason,
                created_at=decision_at,
            )
        )


def _kickoff(future) -> datetime:
    return datetime.fromisoformat(future["fixture"]["date"]).astimezone(UTC)


def test_health_yellow_with_selected(chain):
    """② 正常场景：有 selected → 推推荐明细（YELLOW）。"""
    repo, future, _, _ = chain
    kickoff = _kickoff(future)
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=kickoff
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    now = kickoff + timedelta(hours=1)
    day = football_day_for_kickoff(now)
    with Session(repo.engine) as session, session.begin():
        event_id = enqueue_today_recommend_health_in_session(session, now=now)
    assert event_id == _event_id(day.isoformat(), TODAY_RECOMMEND_HEALTH)
    with Session(repo.engine) as session:
        row = session.get(CandidateNotificationOutboxModel, event_id)
    assert row.payload["level"] == "YELLOW"
    assert row.payload["selected_count"] == 2
    assert row.payload["skip_count"] == 0
    assert len(row.payload["recommendations"]) == 2
    # 明细含 fixture + 方向 + 盘口。
    for rec in row.payload["recommendations"]:
        assert rec["fixture_id"] == "1489404"
        assert rec["direction"] in {"HOME", "AWAY", "OVER"}
        assert rec["line"] is not None and rec["decimal_odds"] is not None
    message = render_bark_message(row.payload)
    assert "推荐 2 场" in message["title"]
    assert "数据正常" in message["title"]


def test_health_red_all_f9_stale(chain, tmp_path, monkeypatch):
    """① 断供场景：今日全是 F9_SNAPSHOT_STALE → 推警示（RED）。"""
    from tests.integration.test_ah_ou_v9_system_pg import _build_chain

    # 空操作控制用 chain 的 future kickoff；攻击库独立 _build_chain，只插 SKIP 行。
    _, future, _, _ = chain
    kickoff = _kickoff(future)
    attack_root = tmp_path / "health_red"
    attack_root.mkdir()
    attack_chain = _build_chain(attack_root, monkeypatch)
    repo, item, _, _ = next(attack_chain)
    decision_at = _kickoff(item) - timedelta(hours=2)
    for fid in ("1489404", "1489405", "1489406"):
        _insert_skip_row(repo, fixture_id=fid, decision_at=decision_at, skip_reason="F9_SNAPSHOT_STALE")
    now = decision_at + timedelta(hours=3)
    day = football_day_for_kickoff(now)
    with Session(repo.engine) as session, session.begin():
        event_id = enqueue_today_recommend_health_in_session(session, now=now)
    assert event_id == _event_id(day.isoformat(), TODAY_RECOMMEND_HEALTH)
    with Session(repo.engine) as session:
        row = session.get(CandidateNotificationOutboxModel, event_id)
    assert row.payload["level"] == "RED"
    assert row.payload["selected_count"] == 0
    assert row.payload["skip_count"] == 3
    assert row.payload["skip_reasons"] == {"F9_SNAPSHOT_STALE": 3, "STALE_QUOTE": 0, "other": 0}
    message = render_bark_message(row.payload)
    assert "xG 断供" in message["title"]
    assert "请检查数据源" in message["title"]
    assert "3 场" in message["body"]


def test_health_silent_no_matches(chain, tmp_path, monkeypatch):
    """③ 无比赛 → 静默不推。"""
    from tests.integration.test_ah_ou_v9_system_pg import _build_chain

    _, future, _, _ = chain
    attack_root = tmp_path / "health_silent"
    attack_root.mkdir()
    attack_chain = _build_chain(attack_root, monkeypatch)
    repo, item, _, _ = next(attack_chain)
    now = _kickoff(item) + timedelta(hours=1)
    with Session(repo.engine) as session:
        event_id = enqueue_today_recommend_health_in_session(session, now=now)
    assert event_id is None
    with Session(repo.engine) as session:
        rows = list(
            session.scalars(
                select(CandidateNotificationOutboxModel).where(
                    CandidateNotificationOutboxModel.event_type == TODAY_RECOMMEND_HEALTH
                )
            )
        )
    assert not rows


def test_health_idempotent(chain):
    """④ 幂等：同一天重复跑只推一次。"""
    repo, future, _, _ = chain
    kickoff = _kickoff(future)
    ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=kickoff
    )
    now = kickoff + timedelta(hours=1)
    day = football_day_for_kickoff(now)
    expected = _event_id(day.isoformat(), TODAY_RECOMMEND_HEALTH)
    with Session(repo.engine) as session, session.begin():
        first = enqueue_today_recommend_health_in_session(session, now=now)
    assert first == expected
    with Session(repo.engine) as session:
        second = enqueue_today_recommend_health_in_session(session, now=now)
    assert second is None
    with Session(repo.engine) as session:
        rows = list(
            session.scalars(
                select(CandidateNotificationOutboxModel).where(
                    CandidateNotificationOutboxModel.notification_event_id == expected
                )
            )
        )
    assert len(rows) == 1


def test_health_delivery_routes_send(chain, monkeypatch):
    """⑤ 会推（route=SEND）：deliver_pending_notifications 用 mock sender 验证推送。"""
    monkeypatch.setenv("W2_BARK_ENDPOINT", "https://api.day.app/example")
    monkeypatch.setenv("W2_BARK_DEVICE_KEY", "test-device-key")
    repo, future, _, _ = chain
    kickoff = _kickoff(future)
    ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=kickoff
    )
    now = kickoff + timedelta(hours=1)
    with Session(repo.engine) as session, session.begin():
        enqueue_today_recommend_health_in_session(session, now=now)
    sent: list[dict] = []
    result = deliver_pending_notifications(now=now, engine=repo.engine, sender=sent.append)
    assert result["status"] == "DELIVERED"
    # chain 里触发 2 个 V3 推荐确认 + 1 个今日推荐健康度，健康度必须恰好一条且会推。
    health_sent = [p for p in sent if p.get("event_type") == TODAY_RECOMMEND_HEALTH]
    assert len(health_sent) == 1
    assert health_sent[0]["level"] == "YELLOW"
