"""D2.1 决策派发去重（指令书 D2 §二 D2.1 + 修订裁决2）。

指令书 D2 诊断链：60s tick × 全部未选中 due 场（AH 当前永不 selected ⇒ 永不离开
重派集）× task_id 带 uuid4 跨 tick 不去重 → 默认队列洪泛（20 场 × 60/hr ≈ 1200 条/hr）
→ 与 110s/条的 future_fixture_refresh 共抢并发 1 的 worker → 真决策排队 1-4h
→ 16/40 行开球后落账（废单）。

修订裁决2 要求**同构复用** providers/control.py 的既有 task-key 去重门（同一 gate 类、
同一 redis 后端），只换 key 命名空间，禁止另起 NX 实现。

本文件用**真实 gate + 假 redis** 驱动，因此同时钉住三件事：
命名空间 `w2:decision-task-key:{fixture_id}`、TTL=900、NX 语义；
再加一条结构性断言防「第二套 NX 实现」回归。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from apps.scheduler import main as scheduler_main
from apps.scheduler.main import (
    DECISION_DISPATCH_DEDUP_TTL_SECONDS,
    DECISION_TASK_KEY_NAMESPACE,
    ah_ou_decision_forward_tick,
)
from apps.worker.celery_app import celery_app
from sqlalchemy import delete
from sqlalchemy.orm import Session

import w2.ingestion.future_refresh_repository as future_refresh_repository
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
    AhOuDecisionLedgerModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayFixtureIdentityModel,
)
from w2.providers.control import (
    DEFAULT_TASK_KEY_NAMESPACE,
    DUPLICATE_TASK_KEY_SUPPRESSED,
    PROVIDER_SCHEDULER_DEDUP_UNAVAILABLE,
    provider_task_key_gate,
)

NOW = datetime(2026, 10, 9, 20, 30, tzinfo=UTC)
FIXTURE_ID = "1493170"
SCHEDULER_MAIN = Path(__file__).resolve().parents[2] / "apps" / "scheduler" / "main.py"


class _FakeRedis:
    """最小 redis 替身：只实现 gate 用到的 ``set(..., nx=True, ex=ttl)``。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.calls: list[dict[str, Any]] = []

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> object:
        self.calls.append({"key": key, "value": value, "nx": nx, "ex": ex})
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True


class _FakeRepo:
    def __init__(self, engine: Any) -> None:
        self.engine = engine


class _FrozenDatetime:
    @staticmethod
    def now(tz: Any = None) -> datetime:
        return NOW

    fromisoformat = staticmethod(datetime.fromisoformat)


def _cleanup(engine: Any) -> None:
    with Session(engine) as session:
        session.execute(
            delete(AhOuDecisionLedgerModel).where(
                AhOuDecisionLedgerModel.fixture_id == FIXTURE_ID
            )
        )
        session.execute(
            delete(MatchdayFixtureIdentityModel).where(
                MatchdayFixtureIdentityModel.provider_fixture_id == FIXTURE_ID
            )
        )
        session.commit()


@pytest.fixture()
def engine() -> Any:
    eng = create_engine()
    _cleanup(eng)
    try:
        yield eng
    finally:
        _cleanup(eng)


def _insert_due_fixture(engine: Any) -> None:
    """插入一场「decision_at 已到（kickoff-2h）、尚未开赛」的 fixture。"""
    with Session(engine) as session:
        session.add(
            MatchdayFixtureIdentityModel(
                fixture_id=FIXTURE_ID,
                provider="api-football",
                provider_fixture_id=FIXTURE_ID,
                competition_id="premier_league",
                provider_league_id="39",
                season="2026",
                kickoff_utc=NOW + timedelta(hours=1),
                fixture_status="NS",
                home_provider_team_id="home-1",
                away_provider_team_id="away-2",
                team_identity_status="MATCHED",
                raw_payload_sha256="a" * 64,
                captured_at=NOW - timedelta(hours=3),
                identity_hash="b" * 64,
                payload={},
            )
        )
        session.commit()


def _insert_selected_ledger_row(engine: Any) -> None:
    with Session(engine) as session:
        session.add(
            AhOuDecisionLedgerModel(
                decision_id="d2-test-decision",
                fixture_id=FIXTURE_ID,
                market="AH",
                decision_at=NOW - timedelta(minutes=5),
                model_version="test-model",
                calibration_version="test-calibration",
                input_hash="c" * 64,
                full_distribution={},
                quote_identity_hash="d" * 64,
                source_capture_sha256="e" * 64,
                capture_id="d2-test-capture",
                source_id="matchday_market_observations",
                home_team_id="home-1",
                away_team_id="away-2",
                selected=True,
                direction="HOME",
                score="0.0",
                created_at=NOW - timedelta(minutes=5),
            )
        )
        session.commit()


def _install_harness(monkeypatch: Any, engine: Any, gate: Any) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []
    monkeypatch.setenv("W2_AH_OU_DECISION_FORWARD_ENABLED", "true")
    # tick 内部是函数级 import，必须打桩源模块（打 scheduler_main 的同名属性无效）。
    monkeypatch.setattr(
        future_refresh_repository,
        "FutureRefreshDbRepository",
        lambda *args, **kwargs: _FakeRepo(engine),
    )
    monkeypatch.setattr(scheduler_main, "datetime", _FrozenDatetime)
    monkeypatch.setattr(
        celery_app,
        "send_task",
        lambda name, **kwargs: sent.append({"name": name, **kwargs}),
    )
    monkeypatch.setattr(scheduler_main, "provider_task_key_gate", gate)
    return sent


def _real_gate_with_fake_redis(fake_redis: _FakeRedis):  # type: ignore[no-untyped-def]
    """转发到真实 gate：证明 tick 走的就是既有去重机制，而非另造一套。"""

    def gate(**kwargs: Any) -> Any:
        return provider_task_key_gate(redis_client=fake_redis, **kwargs)

    return gate


def test_decision_dispatch_dedup_suppresses_resend_within_window(
    monkeypatch: Any, engine: Any
) -> None:
    """同 fixture 在 900s 窗口内第二次 tick 不再派发（指令书验收点 2）。"""
    _insert_due_fixture(engine)
    fake_redis = _FakeRedis()
    sent = _install_harness(monkeypatch, engine, _real_gate_with_fake_redis(fake_redis))

    first = ah_ou_decision_forward_tick()
    second = ah_ou_decision_forward_tick()

    assert first["status"] == "QUEUED"
    assert first["dispatched"] == 1
    assert second["status"] == DUPLICATE_TASK_KEY_SUPPRESSED
    assert second["dispatched"] == 0
    assert second["suppressed"] == 1
    assert len(sent) == 1, "第二次 tick 不得再派发"

    # 命名空间与 TTL 是修订裁决2 的明文要求，逐字钉住。
    assert set(fake_redis.store) == {f"{DECISION_TASK_KEY_NAMESPACE}:{FIXTURE_ID}"}
    assert DECISION_TASK_KEY_NAMESPACE == "w2:decision-task-key"
    assert fake_redis.calls[0]["nx"] is True
    assert fake_redis.calls[0]["ex"] == DECISION_DISPATCH_DEDUP_TTL_SECONDS == 900


def test_decision_dispatch_allows_resend_after_window_expires(
    monkeypatch: Any, engine: Any
) -> None:
    """窗口过期（key 自然消失）后可再派——不能变成「永久只派一次」。"""
    _insert_due_fixture(engine)
    fake_redis = _FakeRedis()
    sent = _install_harness(monkeypatch, engine, _real_gate_with_fake_redis(fake_redis))

    assert ah_ou_decision_forward_tick()["status"] == "QUEUED"
    fake_redis.store.clear()  # 模拟 900s TTL 到期
    assert ah_ou_decision_forward_tick()["status"] == "QUEUED"

    assert len(sent) == 2


def test_decision_dispatch_fails_closed_when_dedup_backend_unavailable(
    monkeypatch: Any, engine: Any
) -> None:
    """去重后端不可用 → 不派发（沿用既有 gate 语义，禁止退化为无门直派）。"""
    _insert_due_fixture(engine)

    def unavailable_gate(**kwargs: Any) -> Any:
        return type(
            "Gate",
            (),
            {
                "allowed": False,
                "status": PROVIDER_SCHEDULER_DEDUP_UNAVAILABLE,
                "backend": None,
            },
        )()

    sent = _install_harness(monkeypatch, engine, unavailable_gate)

    result = ah_ou_decision_forward_tick()

    assert result["status"] == PROVIDER_SCHEDULER_DEDUP_UNAVAILABLE
    assert result["dispatched"] == 0
    assert sent == [], "后端不可用时必须 fail-closed，绝不无门直派"
    assert result["provider_calls"] == 0
    assert result["db_writes"] == 0


def test_decision_dispatch_skips_fixture_with_selected_ledger_row(
    monkeypatch: Any, engine: Any
) -> None:
    """既有语义回归：已有 selected=true 最终决策行的场次不进重派集。"""
    _insert_due_fixture(engine)
    _insert_selected_ledger_row(engine)
    fake_redis = _FakeRedis()
    sent = _install_harness(monkeypatch, engine, _real_gate_with_fake_redis(fake_redis))

    result = ah_ou_decision_forward_tick()

    assert result["status"] == "NOTHING_DUE"
    assert sent == []
    assert fake_redis.store == {}


def test_gate_default_namespace_is_unchanged_for_provider_queue() -> None:
    """同构前提：不传 namespace 时 provider 侧键名与历史完全一致（不可被本改动影响）。"""
    fake_redis = _FakeRedis()
    provider_gate = provider_task_key_gate(task_key="odds:1", redis_client=fake_redis)

    assert provider_gate.allowed is True
    assert set(fake_redis.store) == {f"{DEFAULT_TASK_KEY_NAMESPACE}:odds:1"}
    assert DEFAULT_TASK_KEY_NAMESPACE == "w2:provider-task-key"


def test_scheduler_main_has_no_second_nx_implementation() -> None:
    """结构性防回归：scheduler 侧不得再出现第二套 NX 去重实现（修订裁决2 明文禁止）。"""
    source = SCHEDULER_MAIN.read_text(encoding="utf-8")

    assert "nx=True" not in source
    assert "setnx" not in source.lower()
