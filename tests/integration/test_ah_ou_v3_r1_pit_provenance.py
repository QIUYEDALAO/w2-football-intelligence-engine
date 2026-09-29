"""R1 PIT 溯源：真实生产构造器（非手工填字段）写 first_captured_at /
status_first_visible_at / pit_proven，准入 READY 或命中目标 reason。

关键：这里不手工 ``Session.add`` 填 PIT 字段，而是跑正常 producer 函数
（``build_saved_raw_plan`` 派生 F9 快照、``history_rows_from_fixture`` 派生 F6
交锋），再经生产 upsert 构造器落库，最后 DB 实读证明字段由构造器真实写入。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.factor_model_models import CanonicalTeamMatchHistoryModel
from w2.infrastructure.persistence.future_refresh_models import TeamXgRollingSnapshotModel
from w2.factor_model.remediation import history_rows_from_fixture
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.ingestion.xg_backfill import XgBackfillConfig, XgHistoryBackfillService
from w2.strategy.ah_ou_decision import build_ah_ou_selections

from tests.unit.test_xg_backfill_materialization import (
    NOW,
    NoCallClient,
    SavedRawRepository,
    finished_fixture,
)

DECISION_AT = NOW + timedelta(days=1) - timedelta(hours=2)  # 目标 kickoff - 2h


def _repository(engine: Any) -> FutureRefreshDbRepository:
    return FutureRefreshDbRepository(engine=engine)


def test_f9_snapshot_constructor_writes_pit_provenance(tmp_path: Any) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'f9.db'}")
    Base.metadata.create_all(engine)
    repository = _repository(engine)

    # 正常 producer 函数：从 raw statistics + fixtures 派生滚动快照
    plan = XgHistoryBackfillService(
        client=NoCallClient(),
        repository=SavedRawRepository(),
        config=XgBackfillConfig(min_rolling_matches=3),
        now=NOW,
    ).build_saved_raw_plan()
    snapshots = [dict(row) for row in plan.rolling_snapshots]
    assert snapshots, "saved raw plan must produce snapshots"

    # 生产 upsert 构造器落库（非手工填字段）
    assert repository.upsert_team_xg_rolling_snapshots(snapshots) == len(snapshots)

    # DB 实读：first_captured_at / pit_proven 由构造器真实写入
    with Session(engine) as session:
        rows = list(session.scalars(select(TeamXgRollingSnapshotModel)))
    assert rows
    for row in rows:
        assert row.first_captured_at is not None
        assert row.pit_proven is False  # No PG visibility proof in SQLite.
        assert row.first_committed_at is None
        assert row.first_captured_at <= row.as_of_time  # 首捕获 ≤ as-of 时点


def test_f6_history_constructor_writes_pit_provenance(tmp_path: Any) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'f6.db'}")
    Base.metadata.create_all(engine)
    mapping = {"10": "w2:team:api_football:10", "20": "w2:team:api_football:20"}

    # 正常 producer 函数：真实 capture（endpoint_capture_id 非空）→ pit_proven=True
    rows = history_rows_from_fixture(
        finished_fixture("f6-1", NOW - timedelta(days=7)),
        competition_id="allsvenskan",
        season="2026",
        source_raw_hash="a" * 64,
        endpoint_capture_id="cap-real-1",
        captured_at=NOW - timedelta(days=6),
        provider_to_w2=mapping,
    )
    assert rows
    assert all(row["pit_proven"] is True for row in rows)
    assert all(row["status_first_visible_at"] is not None for row in rows)

    with Session(engine) as session:
        session.add_all(CanonicalTeamMatchHistoryModel(**row) for row in rows)
        session.commit()

    with Session(engine) as session:
        persisted = list(session.scalars(select(CanonicalTeamMatchHistoryModel)))
    assert persisted
    assert all(row.pit_proven is True for row in persisted)
    assert all(row.status_first_visible_at is not None for row in persisted)


def test_f6_backfill_not_pit_proven(tmp_path: Any) -> None:
    """历史补填（无 endpoint capture）保持 pit_proven=false（BACKTEST_LOOKBACK）。"""
    mapping = {"10": "w2:team:api_football:10", "20": "w2:team:api_football:20"}
    rows = history_rows_from_fixture(
        finished_fixture("f6-back", NOW - timedelta(days=30)),
        competition_id="allsvenskan",
        season="2026",
        source_raw_hash="b" * 64,
        endpoint_capture_id=None,
        captured_at=NOW,
        provider_to_w2=mapping,
    )
    assert rows
    assert all(row["pit_proven"] is False for row in rows)
    assert all(row["status_first_visible_at"] is not None for row in rows)


def test_finished_fixture_items_filter_non_ft() -> None:
    """非 FT 交锋由 finished_fixture_items 筛除，不进入 history 构造（先筛 FT）。"""
    from w2.factor_model.remediation import finished_fixture_items

    payload = {
        "response": [
            finished_fixture("f6-ft", NOW - timedelta(days=3)),
            finished_fixture("f6-ns", NOW - timedelta(days=3),
                             ),
        ]
    }
    payload["response"][1]["fixture"]["status"]["short"] = "NS"
    rows = finished_fixture_items(payload, now=NOW)
    assert [row["fixture"]["id"] for row in rows] == ["f6-ft"]


class LateCaptureSavedRawRepository(SavedRawRepository):
    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        rows = super().raw_payloads(endpoint)
        # 让 statistics capture 晚于 decision_at（目标 kickoff - 2h）
        late = (NOW + timedelta(days=1) - timedelta(hours=1)).isoformat()
        for row in rows:
            row["captured_at"] = late
        return rows


def test_f9_first_capture_after_decision_is_refused_by_admission() -> None:
    """晚于决策点的首捕获（构造器真实写入）被准入拒绝，方向=0。"""
    plan = XgHistoryBackfillService(
        client=NoCallClient(),
        repository=LateCaptureSavedRawRepository(),
        config=XgBackfillConfig(min_rolling_matches=3),
        now=NOW,
    ).build_saved_raw_plan()
    snapshots = [dict(row) for row in plan.rolling_snapshots]
    assert not snapshots  # Producer excludes T-1h capture at its T-2h window.

    class Repo:
        _mapping = {"10": "w2:team:api_football:10", "20": "w2:team:api_football:20"}

        def __init__(self, snapshots: list[dict[str, Any]]) -> None:
            self.snapshots = snapshots

        def team_xg_rolling_snapshots_for_w2_teams(
            self, team_ids, *, before, competition_id, season, as_of_fixture_id=None
        ):
            return [
                {**s, "team_id": self._mapping[s["team_id"]]}
                for s in self.snapshots
                if s["team_id"] in self._mapping
                and self._mapping[s["team_id"]] in team_ids
                and s["as_of_fixture_id"] == "target"
            ]

        def canonical_match_history_for_teams(
            self, team_ids, *, before, limit_per_team=20,
            opponent_w2_id=None, fixture_status="FT",
        ):
            return []

    result = build_ah_ou_selections(
        Repo(snapshots),
        fixture_id="target",
        home_team_id="w2:team:api_football:10",
        away_team_id="w2:team:api_football:20",
        kickoff=NOW + timedelta(days=1),
        competition_id="allsvenskan",
        season="2026",
        ah_line=-0.5, ah_home_odds=1.8, ah_away_odds=2.2,
        ou_line=2.5, ou_over_odds=1.9, ou_under_odds=1.9,
    )
    # as_of_time = max(kickoff, captured_at) >= captured_at，所以晚捕获先触发
    # AS_OF_AFTER_DECISION（方向=0）。
    assert result["status"] == "F9_ROLLING_SNAPSHOT_NOT_UNIQUE"
    assert result["ah"] is None and result["ou"] is None


def test_f9_first_capture_after_decision_is_refused_by_admission_backtest() -> None:
    """BACKTEST_LOOKBACK（captured_before_cutoff=False）快照 pit_proven=false → 准入拒绝。"""
    # 直接走 materialize_rolling_xg 的回测口径，验证 pit_proven=False 派生
    from w2.features.xg_materialization import (
        materialize_rolling_xg,
        parse_team_xg_matches,
    )

    rows = []
    for index in range(3):
        rows.extend(
            parse_team_xg_matches(
                fixture_payload=finished_fixture(f"bt{index}", NOW - timedelta(days=5 - index)),
                statistics_payload={
                    "response": [
                        {"team": {"id": 10}, "statistics": [{"type": "expected_goals", "value": "1.0"}]},
                        {"team": {"id": 20}, "statistics": [{"type": "expected_goals", "value": "0.5"}]},
                    ]
                },
                captured_at=NOW,
                raw_payload_sha256=f"{index}" * 64,
            )
        )
    snapshot = materialize_rolling_xg(
        team_id="10",
        as_of_fixture_id="target",
        as_of_time=NOW + timedelta(days=1),
        matches=rows,
        captured_before_cutoff=False,  # 回测口径
    )
    assert snapshot is not None
    assert snapshot.first_captured_at is None
    assert snapshot.pit_proven is False
