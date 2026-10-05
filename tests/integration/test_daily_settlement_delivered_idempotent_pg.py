"""V3_DAILY_CONTENT_CONFLICT 修复：已 DELIVERED 报告幂等跳过重算校验。

根因：10-04 的 AH_OU_V3_DAILY_SETTLEMENT 报告在结算修复前冻结（blocked=6），
delivery_status=DELIVERED 且 payload 是 append-only immutable 的；结算修复后真实
状态变 blocked=0，candidate_notification_schedule 每 120s 重算发现冲突抛异常。

修复：enqueue_v3_daily_settlement_in_session 对「已 DELIVERED 报告」幂等跳过
（return None，不重算校验），非 DELIVERED 报告仍走 _verify_current_outbox_in_session。
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from apps.worker.celery_app import result_materialize
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.integration.test_ah_ou_v11_postmatch_pg import _ft_capture

from w2.dashboard.date_window import FOOTBALL_DAY_TZ, football_day_for_kickoff
from w2.infrastructure.persistence.dynamic_prematch_models import CandidateNotificationOutboxModel
from w2.prematch.analysis_calculator import ReadModelService
from w2.prematch.candidate_notifications import (
    V3_DAILY_SETTLEMENT,
    _event_id,
    enqueue_v3_daily_settlement_in_session,
)

pytest_plugins = ["tests.integration.test_ah_ou_v9_system_pg"]


def _daily_at(future) -> datetime:
    kickoff = datetime.fromisoformat(future["fixture"]["date"]).astimezone(UTC)
    football_day = football_day_for_kickoff(kickoff)
    return datetime.combine(
        football_day + timedelta(days=1), time(12), tzinfo=FOOTBALL_DAY_TZ
    ).astimezone(UTC)


def _event_id_for(daily_at: datetime) -> str:
    day = daily_at.astimezone(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1)
    return _event_id(day.isoformat(), V3_DAILY_SETTLEMENT)


def _frozen_payload(daily_at: datetime, *, blocked: int, settled: int) -> dict:
    """模拟结算修复前冻结的旧报告信封（blocked/settled 与当前状态不一致）。"""
    day = daily_at.astimezone(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1)
    return {
        "schema_version": "w2.ah_ou_v3_daily_settlement.v1",
        "event_type": V3_DAILY_SETTLEMENT,
        "football_day": day.isoformat(),
        "selected": 2,
        "pending": 0,
        "blocked": blocked,
        "void": 0,
        "settled": settled,
        "net_units": "0",
        "items": [],
        "dashboard_url": f"/?date={day.isoformat()}",
        "created_at": daily_at.isoformat(),
    }


def _settle_two_decisions(repo, future) -> None:
    """真实链：触发 2 场 selected 决策落账本 + FT 结算（blocked=0, settled=2）。"""
    card = ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False,
        evaluation_time=datetime.fromisoformat(future["fixture"]["date"]).astimezone(UTC),
    )
    assert card["ah_ou_result"]["recording"]["status"] == "COMMITTED"
    _ft_capture(repo, future)
    assert result_materialize.run(fixture_ids=["api_football:1489404"])["status"] == "PASS"


def _insert_report(repo, event_id: str, *, delivery_status: str, payload: dict) -> None:
    with Session(repo.engine) as session, session.begin():
        session.add(
            CandidateNotificationOutboxModel(
                notification_event_id=event_id,
                opportunity_identity_hash=None,
                attempt_identity_hash=None,
                event_type=V3_DAILY_SETTLEMENT,
                previous_state=None,
                current_state="SETTLED",
                payload=payload,
                created_at=datetime.now(UTC),
                delivered_at=datetime.now(UTC) if delivery_status == "DELIVERED" else None,
                delivery_status=delivery_status,
                delivery_attempt_count=1 if delivery_status == "DELIVERED" else 0,
                last_error=None,
            )
        )


def test_delivered_report_skips_reverify(chain):
    """① 已 DELIVERED 报告（内容冻结）→ 重算幂等跳过，零 V3_DAILY_CONTENT_CONFLICT。"""
    repo, future, _, _ = chain
    # 真实链结算：2 场 selected 落库（当前状态 blocked=0, settled=2）。
    _settle_two_decisions(repo, future)

    daily_at = _daily_at(future)
    event_id = _event_id_for(daily_at)
    # 模拟生产历史：结算修复前冻结的旧报告，blocked=2 与当前 blocked=0 不一致。
    _insert_report(
        repo, event_id, delivery_status="DELIVERED",
        payload=_frozen_payload(daily_at, blocked=2, settled=0),
    )

    # 重算 enqueue → 已 DELIVERED，幂等跳过，不抛冲突、不重复 enqueue。
    with Session(repo.engine) as session:
        result = enqueue_v3_daily_settlement_in_session(session, now=daily_at)
    assert result is None

    with Session(repo.engine) as session:
        rows = list(
            session.scalars(
                select(CandidateNotificationOutboxModel).where(
                    CandidateNotificationOutboxModel.notification_event_id == event_id
                )
            )
        )
        assert len(rows) == 1
        assert rows[0].delivery_status == "DELIVERED"


def test_pending_report_still_verified(chain):
    """④ 非 DELIVERED（PENDING）报告 → 仍走内容校验，冲突时抛异常（不回归）。"""
    repo, future, _, _ = chain
    _settle_two_decisions(repo, future)

    daily_at = _daily_at(future)
    event_id = _event_id_for(daily_at)
    _insert_report(
        repo, event_id, delivery_status="PENDING",
        payload=_frozen_payload(daily_at, blocked=2, settled=0),
    )

    with Session(repo.engine) as session:
        with pytest.raises(ValueError, match="V3_DAILY_CONTENT_CONFLICT:blocked"):
            enqueue_v3_daily_settlement_in_session(session, now=daily_at)


def test_new_report_still_generated(chain):
    """③ 无 existing 记录 → 新报告正常生成（不被误跳过）。"""
    repo, future, _, _ = chain
    _settle_two_decisions(repo, future)

    daily_at = _daily_at(future)
    event_id = _event_id_for(daily_at)
    with Session(repo.engine) as session, session.begin():
        inserted = enqueue_v3_daily_settlement_in_session(session, now=daily_at)
    assert inserted == event_id

    with Session(repo.engine) as session:
        row = session.get(CandidateNotificationOutboxModel, event_id)
        assert row is not None
        assert row.delivery_status == "PENDING"
        assert row.payload["blocked"] == 0
        assert row.payload["settled"] == 2
