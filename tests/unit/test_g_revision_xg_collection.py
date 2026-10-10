"""指令书 G 修订（2026-10-10）：xG 采集设计修正的回归测试。

覆盖四条规格：
  F1  赛后最小年龄门参数化（env `W2_XG_POSTMATCH_MIN_AGE_HOURS`，默认 24h；禁止第二处定义）
  F2  缓存有效性 = **完整双侧 expected_goals**（空壳 payload 不算已缓存 ⇒ 可重抓）
  F3  POSTMATCH_RESULT 每窗尝试 statistics（幂等跳过完整 xG；>7 天标 PROVIDER_XG_UNAVAILABLE）
  F4  采集目标选择去掉年龄门（只以 complete-xG 为判据）
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.ingestion import future_refresh as fr
from w2.ingestion import xg_backfill as xg

NOW = datetime(2026, 10, 10, 3, 0, tzinfo=UTC)
FR_SOURCE = Path(fr.__file__)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _raw(sha: str, payload: dict[str, Any]) -> RawPayloadModel:
    return RawPayloadModel(
        sha256=sha,
        endpoint="statistics",
        captured_at=NOW,
        storage_uri="memory://raw",
        payload=payload,
    )


def _shell_payload(fixture_id: str) -> dict[str, Any]:
    """xG 发布前抓到的**空壳**：两队俱在，但 statistics 只有常规项、没有 expected_goals。

    生产实测形态（2026-10-10，15 场未覆盖场次全部如此）：
    entries=16，types = [Passes accurate, Shots insidebox, …, Ball Possession]，无 xG。
    """
    return {
        "parameters": {"fixture": fixture_id},
        "response": [
            {"team": {"id": 10}, "statistics": [{"type": "Total Shots", "value": 12}]},
            {"team": {"id": 20}, "statistics": [{"type": "Total Shots", "value": 7}]},
        ],
    }


def _complete_payload(fixture_id: str, home: str = "1.7", away: str = "0.8") -> dict[str, Any]:
    return {
        "parameters": {"fixture": fixture_id},
        "response": [
            {"team": {"id": 10}, "statistics": [{"type": "expected_goals", "value": home}]},
            {"team": {"id": 20}, "statistics": [{"type": "expected_goals", "value": away}]},
        ],
    }


def _one_sided_payload(fixture_id: str) -> dict[str, Any]:
    """只有一侧有 expected_goals ⇒ 不算完整。"""
    return {
        "parameters": {"fixture": fixture_id},
        "response": [
            {"team": {"id": 10}, "statistics": [{"type": "expected_goals", "value": "1.7"}]},
            {"team": {"id": 20}, "statistics": [{"type": "Total Shots", "value": 7}]},
        ],
    }


def finished_fixture(
    fixture_id: str,
    kickoff: datetime,
    *,
    season: str = "2026",
) -> dict[str, Any]:
    return {
        "fixture": {
            "id": fixture_id,
            "date": kickoff.isoformat().replace("+00:00", "Z"),
            "status": {"short": "FT"},
        },
        "league": {"id": 71, "season": season},
        "teams": {"home": {"id": 10}, "away": {"id": 20}},
        "goals": {"home": 2, "away": 1},
    }


# ─────────────────────────────────────────────────────────────────────────────
# F1 / F3c 阈值参数化
# ─────────────────────────────────────────────────────────────────────────────


def test_min_age_reads_env_and_defaults_to_24h(monkeypatch) -> None:
    """F1：48h 硬编码 → env（默认 24h），且不得再存在同名硬编码常量。"""
    monkeypatch.delenv("W2_XG_POSTMATCH_MIN_AGE_HOURS", raising=False)
    assert xg.xg_postmatch_min_age() == timedelta(hours=24)

    monkeypatch.setenv("W2_XG_POSTMATCH_MIN_AGE_HOURS", "36")
    assert xg.xg_postmatch_min_age() == timedelta(hours=36)

    monkeypatch.setenv("W2_XG_POSTMATCH_MIN_AGE_HOURS", "-2")
    with pytest.raises(xg.XgBackfillError):
        xg.xg_postmatch_min_age()

    # 旧常量必须消失：留着它就会有人再写一处（历史上正是硬编码被复制成两处）
    assert not hasattr(xg, "XG_POSTMATCH_MIN_AGE")


def test_provider_unavailable_archive_age_reads_env(monkeypatch) -> None:
    """F3c：无 xG 留档阈值同样参数化（默认 7 天）。"""
    monkeypatch.delenv("W2_XG_UNAVAILABLE_ARCHIVE_DAYS", raising=False)
    assert xg.xg_provider_unavailable_archive_age() == timedelta(days=7)

    monkeypatch.setenv("W2_XG_UNAVAILABLE_ARCHIVE_DAYS", "3")
    assert xg.xg_provider_unavailable_archive_age() == timedelta(days=3)


# ─────────────────────────────────────────────────────────────────────────────
# F2 缓存有效性 = 完整双侧 xG
# ─────────────────────────────────────────────────────────────────────────────


def test_empty_shell_statistics_is_not_treated_as_cached() -> None:
    """F2：空壳 payload 不算已缓存（⇒ 下一窗口自动重抓）；只有**双侧** xG 才算。

    修复前若把「存在任何 statistics raw」当已缓存，就会发生毒化缓存：
    某场在 xG 发布前被抓到空壳 ⇒ 永远跳过重抓 ⇒ 空壳物化不出行 ⇒ 洞永不愈合。
    """
    engine = _engine()
    with Session(engine) as session:
        session.add(_raw("a" * 64, _shell_payload("111")))
        session.add(_raw("b" * 64, _complete_payload("222")))
        session.add(_raw("c" * 64, _one_sided_payload("333")))
        session.commit()

    repo = FutureRefreshDbRepository(engine=engine)
    cached = repo.raw_statistics_fixture_ids()

    assert "222" in cached, "完整双侧 expected_goals 应视为已缓存"
    assert "111" not in cached, "空壳 payload 必须保持可重抓（否则毒化缓存）"
    assert "333" not in cached, "只有单侧 xG 仍不完整，必须可重抓"


# ─────────────────────────────────────────────────────────────────────────────
# F3b 幂等：完整 xG 跳过，其余照采
# ─────────────────────────────────────────────────────────────────────────────


def _enrichment_service(monkeypatch, cached: set[str]):
    """构造一个只够跑 _fetch_feature_enrichment 的服务壳（不触网、不落库）。"""
    svc = fr.FutureFixtureRefreshService.__new__(fr.FutureFixtureRefreshService)
    svc.config = SimpleNamespace(
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("statistics",),
        feature_enrichment_request_budget=5,
        request_budget=10,
        provider_refresh_batch_size=5,
        quota_reserve=0,
    )
    svc.now = NOW
    svc._audit = []
    svc._attempt_count = 0
    svc._latest_remaining = None
    svc._feature_enrichment_batch_count = 0

    class _Repo:
        def raw_statistics_fixture_ids(self) -> set[str]:
            return set(cached)

    monkeypatch.setattr(svc, "_db_repository", lambda: _Repo())
    monkeypatch.setattr(svc, "_endpoint_authorized", lambda endpoint: True)

    requested: list[tuple[str, dict[str, str]]] = []

    class _Resp:
        status_code = 200
        payload: dict[str, Any] = {"response": []}
        captured_at = NOW

    def _fake_request(endpoint: str, params: dict[str, str]) -> Any:
        requested.append((endpoint, params))
        return _Resp()

    monkeypatch.setattr(svc, "_request", _fake_request)
    return svc, requested


def test_enrichment_skips_complete_xg_and_requests_the_rest(monkeypatch) -> None:
    """F3b：已有完整双侧 xG 的场次跳过（幂等、不发请求），其余照采。"""
    svc, requested = _enrichment_service(monkeypatch, cached={"222"})

    svc._fetch_feature_enrichment(
        [
            finished_fixture("222", NOW - timedelta(hours=30)),
            finished_fixture("111", NOW - timedelta(hours=30)),
        ]
    )

    assert [params["fixture"] for _, params in requested] == ["111"]
    codes = [item.get("error_code") for item in svc._audit]
    assert "STATISTICS_XG_COMPLETE" in codes


def test_enrichment_retries_when_cache_lookup_unavailable(monkeypatch) -> None:
    """F3b 边界：缓存查询失败时按「未缓存」处理（宁可多采一次，也不永久跳过），并留痕。"""

    class _Broken:
        def raw_statistics_fixture_ids(self) -> set[str]:
            raise RuntimeError("cache down")

    svc = fr.FutureFixtureRefreshService.__new__(fr.FutureFixtureRefreshService)
    svc.config = SimpleNamespace(
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("statistics",),
        feature_enrichment_request_budget=5,
        request_budget=10,
        provider_refresh_batch_size=5,
        quota_reserve=0,
    )
    svc.now = NOW
    svc._audit = []
    svc._attempt_count = 0
    svc._latest_remaining = None
    svc._feature_enrichment_batch_count = 0
    monkeypatch.setattr(svc, "_db_repository", lambda: _Broken())
    monkeypatch.setattr(svc, "_endpoint_authorized", lambda endpoint: True)

    requested: list[str] = []

    class _Resp:
        status_code = 200
        payload: dict[str, Any] = {"response": []}
        captured_at = NOW

    def _fake_request(endpoint: str, params: dict[str, str]) -> Any:
        requested.append(params["fixture"])
        return _Resp()

    monkeypatch.setattr(svc, "_request", _fake_request)

    svc._fetch_feature_enrichment([finished_fixture("111", NOW - timedelta(hours=30))])

    assert requested == ["111"], "缓存不可查时必须照采，不得静默跳过"
    assert "STATISTICS_XG_CACHE_UNAVAILABLE" in [
        item.get("error_code") for item in svc._audit
    ]


# ─────────────────────────────────────────────────────────────────────────────
# F4 + F3c 采集目标选择
# ─────────────────────────────────────────────────────────────────────────────


def _backfill_service() -> Any:
    """batch4 目标选择属 ProStatisticsBackfillService（这里只调纯选择逻辑，不发请求）。"""

    class _Repo:
        def raw_statistics_fixture_ids(self) -> set[str]:
            return set()

    return xg.ProStatisticsBackfillService(
        repository=_Repo(),
        now=NOW,
        config=xg.ProStatisticsBackfillConfig(batch=4, request_budget=10),
    )


def test_batch4_drops_age_gate(monkeypatch) -> None:
    """F4：batch4 的 2026 目标选择**不再看年龄**，只看是否已有完整双侧 xG。

    注意 F3c 的「>7 天留档」**不在 batch4**：batch4 是历史回补（20-30 天前的场次正是它的
    目标，既有测试即如此构造），在此归档等于把射程剪掉。F3c 归赛后新鲜度链，
    实现与测试见 `XgHistoryBackfillService.run()`。
    """
    svc = _backfill_service()

    fresh = finished_fixture("1", NOW - timedelta(hours=2))
    stale = finished_fixture("2", NOW - timedelta(days=30))

    targets = svc._batch4_targets([fresh, stale])
    ids = {xg.fixture_id_from_payload(item) for item in targets}

    assert ids == {"1", "2"}, "年龄门必须去掉：能采就采，不看年龄（F4）"


def test_batch4_skips_only_complete_xg(monkeypatch) -> None:
    """F4 + F2：唯一跳过判据 = 已有完整双侧 xG（空壳不算）。"""

    class _Repo:
        def raw_statistics_fixture_ids(self) -> set[str]:
            return {"done"}

    svc = xg.ProStatisticsBackfillService(
        repository=_Repo(),
        now=NOW,
        config=xg.ProStatisticsBackfillConfig(batch=4, request_budget=10),
    )
    done = finished_fixture("done", NOW - timedelta(days=30))
    shell = finished_fixture("shell", NOW - timedelta(days=30))

    ids = {
        xg.fixture_id_from_payload(item)
        for item in svc._batch4_targets([done, shell])
    }

    assert ids == {"shell"}, "完整 xG 才跳过；空壳场次必须保持可重抓"


def test_unavailable_archive_decision_uses_env_threshold(monkeypatch) -> None:
    """F3c：留档 = **已尝试过** 且 kickoff 超阈值（env `W2_XG_UNAVAILABLE_ARCHIVE_DAYS`，默认 7 天）。

    `already_attempted` 是关键限定：从未抓过的旧场次必须继续采（补采射程不能按年龄剪掉）。
    """
    monkeypatch.delenv("W2_XG_UNAVAILABLE_ARCHIVE_DAYS", raising=False)
    assert (
        xg.xg_unavailable_archived(NOW - timedelta(days=9), NOW, already_attempted=True)
        is True
    )
    assert (
        xg.xg_unavailable_archived(NOW - timedelta(days=2), NOW, already_attempted=True)
        is False
    )
    assert xg.xg_unavailable_archived(None, NOW, already_attempted=True) is False
    assert (
        xg.xg_unavailable_archived(NOW - timedelta(days=9), NOW, already_attempted=False)
        is False
    ), "从未抓过的旧场次不得归档"

    monkeypatch.setenv("W2_XG_UNAVAILABLE_ARCHIVE_DAYS", "3")
    assert (
        xg.xg_unavailable_archived(NOW - timedelta(days=5), NOW, already_attempted=True)
        is True
    )
    assert (
        xg.xg_unavailable_archived(NOW - timedelta(days=2), NOW, already_attempted=True)
        is False
    )


# ─────────────────────────────────────────────────────────────────────────────
# F3a POSTMATCH 每窗尝试（结构性：该分支的 enrichment 必须含 statistics）
# ─────────────────────────────────────────────────────────────────────────────


def test_postmatch_checkpoint_enables_statistics_enrichment() -> None:
    """F3a：POSTMATCH_RESULT 的 checkpoint 分支必须为 statistics 打开 enrichment。

    此前该分支只允许 lineups（`lineups_count > 0`），而 POSTMATCH 计划 endpoints 是
    {status, fixtures} ⇒ enrichment 整体关闭 ⇒ 赛后从不尝试 xG。
    ⚠️ 只扩 enrichment endpoints，**不动计划自身 endpoints**——`_checkpoint_mode()` 靠
    `endpoints == {"status","fixtures"}` 识别 POSTMATCH，动它等于改 checkpoint 模式判定。
    """
    source = FR_SOURCE.read_text(encoding="utf-8")

    assert 'str(item.get("checkpoint") or "") == "POSTMATCH_RESULT"' in source
    assert "feature_enrichment_enabled=(lineups_count > 0 or postmatch_count > 0)" in source
    assert '(("statistics",) if postmatch_count > 0 else ())' in source
    assert "feature_enrichment_request_budget=lineups_count + postmatch_count" in source
    # 计划自身 endpoints 必须保持 {status, fixtures}
    plan_source = (
        Path(fr.__file__).resolve().parents[1] / "ingestion" / "checkpoint_refresh.py"
    ).read_text(encoding="utf-8")
    assert 'endpoints=("status", "fixtures")' in plan_source
