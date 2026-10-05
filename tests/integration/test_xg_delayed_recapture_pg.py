"""xG 赛后延迟重采：跳过键 raw_statistics_fixture_ids 区分「完整双边 xG」vs「无 expected_goals」。"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime

pytest_plugins = ["tests.integration.test_ah_ou_v9_system_pg"]


def _save_statistics(repo, *, fixture_id: str, with_xg: bool) -> None:
    response = (
        [
            {"team": {"id": 10}, "statistics": [{"type": "expected_goals", "value": "3.8"}]},
            {"team": {"id": 20}, "statistics": [{"type": "expected_goals", "value": "0.4"}]},
        ]
        if with_xg
        else []
    )
    repo.save_raw_payload(
        sha256=hashlib.sha256(f"stats|{fixture_id}|{with_xg}".encode()).hexdigest(),
        endpoint="statistics",
        captured_at=datetime.now(UTC),
        payload={"parameters": {"fixture": fixture_id}, "response": response},
    )


def test_raw_statistics_fixture_ids_complete_vs_incomplete(chain):
    """单变量攻击：statistics raw 无 expected_goals（延迟发布）→ 不计入「完整 xG」集合。

    这是延迟重采的跳过键数据源：只有「完整双边 xG」才跳过；「有 raw 但 expected_goals
    为空」的 fixture 必须保留为补采目标，否则实时采集采到空 expected_goals 后永久漏采。
    """
    repo, _future, _plan, _producer = chain
    _save_statistics(repo, fixture_id="999902", with_xg=False)  # 无 expected_goals（延迟）
    _save_statistics(repo, fixture_id="999903", with_xg=True)  # 完整双边 xG

    ids = repo.raw_statistics_fixture_ids()
    assert "999903" in ids  # 完整双边 xG → 跳过键命中
    assert "999902" not in ids  # 无 expected_goals → 仍须延迟重采


def test_raw_statistics_fixture_ids_excludes_incomplete_only(chain):
    """反向控制：只有 parameters 无 response 的 statistics raw 也不算完整 xG。"""
    repo, _future, _plan, _producer = chain
    repo.save_raw_payload(
        sha256=hashlib.sha256(b"bare-params").hexdigest(),
        endpoint="statistics",
        captured_at=datetime.now(UTC),
        payload={"parameters": {"fixture": "999904"}},
    )
    ids = repo.raw_statistics_fixture_ids()
    assert "999904" not in ids
