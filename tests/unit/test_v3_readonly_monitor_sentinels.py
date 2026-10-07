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
    assert monitor.bark_issue_severity("SKIP_REASON_ANOMALY:count=3") == "YELLOW"
    assert monitor.bark_issue_severity("DATA_SOURCE_CONSISTENCY_CONFLICT:X") == "YELLOW"
    assert monitor.bark_issue_severity("SERVICE_NOT_HEALTHY") is None


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


def test_push_bark_alerts_silent_without_config(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("W2_BARK_ENDPOINT", raising=False)
    monkeypatch.delenv("W2_BARK_DEVICE_KEY", raising=False)
    assert monitor.push_bark_alerts(["NO_RECOMMENDATION_TODAY:due=1"], out_dir=tmp_path) == 0
