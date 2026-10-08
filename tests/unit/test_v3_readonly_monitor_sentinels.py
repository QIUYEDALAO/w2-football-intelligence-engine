"""VPS 巡检业务哨兵（B1-B4）+ Bark 推送幂等/严重度 单测。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "ops/host/w2-v3-readonly-monitor.py"


def _load_monitor():
    spec = importlib.util.spec_from_file_location("v3_readonly_monitor", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


monitor = _load_monitor()


def test_b1_recommendation_chain_no_selected_issues_alert() -> None:
    assert monitor.recommendation_chain_issue([]) is None
    assert monitor.recommendation_chain_issue(
        [{"selected_count": 0, "due_count": 3}]
    ) == "NO_RECOMMENDATION_TODAY:due=3"
    # 有推荐或有到点场次=0 → 静默
    assert monitor.recommendation_chain_issue(
        [{"selected_count": 1, "due_count": 3}]
    ) is None
    assert monitor.recommendation_chain_issue(
        [{"selected_count": 0, "due_count": 0}]
    ) is None


def test_b2_skip_reason_anomaly_threshold() -> None:
    assert monitor.skip_reason_anomaly_issue([]) is None
    assert monitor.skip_reason_anomaly_issue(
        [{"skip_reason": "QUOTE_DUPLICATE_SIDE", "count": 2}]
    ) is None
    assert monitor.skip_reason_anomaly_issue(
        [
            {"skip_reason": "QUOTE_DUPLICATE_SIDE", "count": 2},
            {"skip_reason": "TERMS_INCOMPLETE", "count": 1},
        ]
    ) == "SKIP_REASON_ANOMALY:count=3"


def test_b3_data_source_consistency_conflict() -> None:
    assert monitor.data_source_consistency_issue("OK", True) is None
    assert monitor.data_source_consistency_issue("BLOCKED_DAY", False) is None
    assert monitor.data_source_consistency_issue(None, True) is None
    assert monitor.data_source_consistency_issue(
        "BLOCKED_DAY", True
    ) == "DATA_SOURCE_CONSISTENCY_CONFLICT:BLOCKED_DAY"


def test_b4_xg_coverage_lag_threshold() -> None:
    assert monitor.xg_coverage_lag_issue([]) is None
    assert monitor.xg_coverage_lag_issue([{"lag_hours": 47.9}]) is None
    assert monitor.xg_coverage_lag_issue(
        [{"lag_hours": 48.1}]
    ) == "F9_SNAPSHOT_LAG:lag_hours=48.10"


def test_bark_issue_severity_mapping() -> None:
    assert monitor.bark_issue_severity("NO_RECOMMENDATION_TODAY:due=1") == "RED"
    assert monitor.bark_issue_severity("F9_SNAPSHOT_LAG:lag_hours=50.00") == "RED"
    assert monitor.bark_issue_severity("XG_STALE:lag_hours=18.73") == "RED"
    assert monitor.bark_issue_severity("SKIP_REASON_ANOMALY:count=3") == "YELLOW"
    assert monitor.bark_issue_severity("DATA_SOURCE_CONSISTENCY_CONFLICT:X") == "YELLOW"
    assert monitor.bark_issue_severity("FENCE_UNCERTAIN_STALE:count=68") == "YELLOW"
    assert monitor.bark_issue_severity("SERVICE_NOT_HEALTHY") is None


def test_fence_uncertain_stale_issue() -> None:
    assert monitor.fence_uncertain_stale_issue([]) is None
    assert monitor.fence_uncertain_stale_issue(
        [{"task_id": "t1", "stage": "xg", "state": "SIDE_EFFECT_UNCERTAIN"}]
    ) == "FENCE_UNCERTAIN_STALE:count=1"
    assert monitor.fence_uncertain_stale_issue(
        [{"stage": "xg"}, {"stage": "task"}, {"stage": "h2h"}]
    ) == "FENCE_UNCERTAIN_STALE:count=3"


def test_push_bark_alerts_idempotent_once_per_day(tmp_path, monkeypatch) -> None:
    from datetime import UTC, datetime

    monkeypatch.setenv("W2_BARK_ENDPOINT", "https://api.day.app/example")
    monkeypatch.setenv("W2_BARK_DEVICE_KEY", "key1,key2")
    posted: list[dict] = []

    def fake_post(endpoint: str, payload: dict) -> None:
        posted.append({"endpoint": endpoint, "payload": payload})

    monkeypatch.setattr(monitor, "_post_bark", fake_post)
    now = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
    issues = ["NO_RECOMMENDATION_TODAY:due=1", "SKIP_REASON_ANOMALY:count=3", "SERVICE_NOT_HEALTHY"]

    assert monitor.push_bark_alerts(issues, out_dir=tmp_path, now=now) == 2
    assert len(posted) == 2
    assert posted[0]["payload"]["title"] == "W2 业务哨兵·告警"
    assert posted[1]["payload"]["title"] == "W2 业务哨兵·提示"

    # 同一天再次推送 → 幂等 0 条
    posted.clear()
    assert monitor.push_bark_alerts(issues, out_dir=tmp_path, now=now) == 0
    assert posted == []

    # 次日再次推送 → 重新推送
    next_day = now.replace(day=9)
    assert monitor.push_bark_alerts(issues, out_dir=tmp_path, now=next_day) == 2
    assert len(posted) == 2


def test_bark_issue_identity_strips_dynamic_suffix() -> None:
    assert monitor.bark_issue_identity("NO_RECOMMENDATION_TODAY:due=1") == "NO_RECOMMENDATION_TODAY"
    assert monitor.bark_issue_identity("NO_RECOMMENDATION_TODAY:due=6") == "NO_RECOMMENDATION_TODAY"
    assert monitor.bark_issue_identity("SKIP_REASON_ANOMALY:count=3") == "SKIP_REASON_ANOMALY"
    assert (
        monitor.bark_issue_identity("DATA_SOURCE_CONSISTENCY_CONFLICT:BLOCKED_DAY")
        == "DATA_SOURCE_CONSISTENCY_CONFLICT"
    )
    assert (
        monitor.bark_issue_identity("F9_SNAPSHOT_LAG:lag_hours=48.10") == "F9_SNAPSHOT_LAG"
    )
    assert monitor.bark_issue_identity("CHECKPOINT_FAILED") == "CHECKPOINT_FAILED"


def test_push_bark_alerts_dynamic_due_not_bombarded(tmp_path, monkeypatch) -> None:
    """① due 1→6 递增同日只推 1 条；② 次日新足球日可再推（跨日不误伤）。"""
    from datetime import UTC, datetime

    monkeypatch.setenv("W2_BARK_ENDPOINT", "https://api.day.app/example")
    monkeypatch.setenv("W2_BARK_DEVICE_KEY", "key1")
    posted: list[dict] = []

    def fake_post(endpoint: str, payload: dict) -> None:
        posted.append({"endpoint": endpoint, "payload": payload})

    monkeypatch.setattr(monitor, "_post_bark", fake_post)
    now = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)

    # ① due 从 1 涨到 6，同一天只推 1 条（不再重复轰炸）
    for due in range(1, 7):
        assert monitor.push_bark_alerts(
            [f"NO_RECOMMENDATION_TODAY:due={due}"], out_dir=tmp_path, now=now
        ) == (1 if due == 1 else 0)
    assert len(posted) == 1
    assert posted[0]["payload"]["body"] == "NO_RECOMMENDATION_TODAY:due=1"

    # ② 次日新足球日 → 可再推（跨日不误伤）
    next_day = now.replace(day=9)
    posted.clear()
    assert monitor.push_bark_alerts(
        ["NO_RECOMMENDATION_TODAY:due=6"], out_dir=tmp_path, now=next_day
    ) == 1
    assert len(posted) == 1
    assert posted[0]["payload"]["body"] == "NO_RECOMMENDATION_TODAY:due=6"


def test_push_bark_alerts_silent_without_config(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("W2_BARK_ENDPOINT", raising=False)
    monkeypatch.delenv("W2_BARK_DEVICE_KEY", raising=False)
    assert monitor.push_bark_alerts(["NO_RECOMMENDATION_TODAY:due=1"], out_dir=tmp_path) == 0


def test_anomalous_skip_reasons_synced() -> None:
    """F10：死原因 QUOTE_NOT_PINNACLE 移除，补上现行合同的新原因 QUOTE_SOURCE_CONTENT_MISMATCH。"""
    assert "QUOTE_NOT_PINNACLE" not in monitor.ANOMALOUS_SKIP_REASONS
    assert "QUOTE_SOURCE_CONTENT_MISMATCH" in monitor.ANOMALOUS_SKIP_REASONS
    assert "QUOTE_DUPLICATE_SIDE" in monitor.ANOMALOUS_SKIP_REASONS
    assert "TERMS_INCOMPLETE" in monitor.ANOMALOUS_SKIP_REASONS


def test_football_day_decision_lo() -> None:
    """F7：B1「今日」下界与 dashboard 足球日窗口同口径（北京 12:00 截断 - 2h 决策提前量）。"""
    from datetime import UTC, datetime

    # 北京 10-08 15:00（>=12:00）→ 足球日 10-08，lo = 10-08 04:00 UTC - 2h = 02:00 UTC
    assert monitor._football_day_decision_lo(
        datetime(2026, 10, 8, 7, 0, tzinfo=UTC)
    ).isoformat() == "2026-10-08T02:00:00+00:00"
    # 北京 10-08 08:00（<12:00）→ 足球日 10-07，lo = 10-07 04:00 UTC - 2h = 02:00 UTC
    assert monitor._football_day_decision_lo(
        datetime(2026, 10, 8, 0, 0, tzinfo=UTC)
    ).isoformat() == "2026-10-07T02:00:00+00:00"
