"""T4 测试数据污染：清理脚本删 fx1/fx2 + snap-H/A，守卫拒绝绕过写入器的直写。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.ah_ou_decision_ledger_models import AhOuDecisionLedgerModel
from w2.infrastructure.persistence.future_refresh_models import TeamXgRollingSnapshotModel
from w2.prematch.analysis_calculator import ReadModelService

pytest_plugins = ["tests.integration.test_ah_ou_v9_system_pg"]


def _drop_guard(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE ah_ou_decision_ledger "
            "DROP CONSTRAINT IF EXISTS ck_ahou_decision_contract_not_empty"
        ))
        conn.execute(text(
            "ALTER TABLE team_xg_rolling_snapshot "
            "DROP CONSTRAINT IF EXISTS ck_team_xg_snapshot_source_system_not_sys"
        ))


def _add_guard(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE ah_ou_decision_ledger "
            "ADD CONSTRAINT ck_ahou_decision_contract_not_empty "
            "CHECK (decision_contract IS NULL OR decision_contract <> '') NOT VALID"
        ))
        conn.execute(text(
            "ALTER TABLE team_xg_rolling_snapshot "
            "ADD CONSTRAINT ck_team_xg_snapshot_source_system_not_sys "
            "CHECK (source_system <> 'sys') NOT VALID"
        ))


def _seed_pollution(engine, decision_at: datetime) -> None:
    """绕过写入器直插 fx1/fx2 + snap-H/A（须先 DROP guard 才能写入非法值）。"""
    with Session(engine) as session, session.begin():
        session.execute(text(
            "ALTER TABLE ah_ou_decision_ledger DISABLE TRIGGER w2_ahou_terms_immutable"
        ))
        for idx, fid in enumerate(("fx1", "fx2")):
            session.add(AhOuDecisionLedgerModel(
                decision_id=("f" * 63) + str(idx),
                fixture_id=fid,
                market="ASIAN_HANDICAP",
                decision_at=decision_at,
                model_version="m1",
                calibration_version="c1",
                input_hash="h" * 64,
                full_distribution={"selection": {"selected": True, "side": "HOME", "score": 0.1}},
                decision_contract="",
                quote_identity_hash="q" * 64,
                source_capture_sha256="s" * 64,
                capture_id="cap-t",
                source_id="src-t",
                home_team_id="H",
                away_team_id="A",
                selected=True,
                direction="HOME",
                score="0.1",
                created_at=datetime.now(UTC),
            ))
        session.execute(text(
            "ALTER TABLE ah_ou_decision_ledger ENABLE TRIGGER w2_ahou_terms_immutable"
        ))
        for team, snap_id in (("H", "snap-H"), ("A", "snap-A")):
            session.add(TeamXgRollingSnapshotModel(
                snapshot_id=snap_id,
                team_id=team,
                as_of_fixture_id="FIX1",
                as_of_time=decision_at - timedelta(days=1),
                match_count=3,
                rolling_xg_for=1.5,
                rolling_xg_against=1.0,
                rolling_goals_for=1.5,
                rolling_goals_against=1.0,
                regression_index=0.0,
                source_system="sys",
            ))


def test_t4_direct_write_guard_rejects_pollution(chain):
    """守卫：绕过写入器直插非法值（decision_contract='' / source_system='sys'）被拒。"""
    repo, future, _, _ = chain
    decision_at = datetime.fromisoformat(future["fixture"]["date"]).astimezone(UTC) - timedelta(hours=2)
    # 账本：decision_contract='' 被 CHECK 拒绝。
    with pytest.raises(IntegrityError):
        with Session(repo.engine) as session, session.begin():
            session.add(AhOuDecisionLedgerModel(
                decision_id="a" * 64,
                fixture_id="fx-direct",
                market="ASIAN_HANDICAP",
                decision_at=decision_at,
                model_version="m1",
                calibration_version="c1",
                input_hash="h" * 64,
                full_distribution={"selection": {"selected": True}},
                decision_contract="",
                quote_identity_hash="q" * 64,
                source_capture_sha256="s" * 64,
                capture_id="cap-t",
                source_id="src-t",
                home_team_id="H",
                away_team_id="A",
                selected=True,
                direction="HOME",
                score="0.1",
                created_at=datetime.now(UTC),
            ))
    # 快照：source_system='sys' 被 CHECK 拒绝。
    with pytest.raises(IntegrityError):
        with Session(repo.engine) as session, session.begin():
            session.add(TeamXgRollingSnapshotModel(
                snapshot_id="snap-direct",
                team_id="H",
                as_of_fixture_id="FIX1",
                as_of_time=decision_at - timedelta(days=1),
                match_count=3,
                rolling_xg_for=1.5,
                rolling_xg_against=1.0,
                rolling_goals_for=1.5,
                rolling_goals_against=1.0,
                regression_index=0.0,
                source_system="sys",
            ))


def test_t4_cleanup_removes_pollution_preserves_real_data(chain):
    """清理：删 fx1/fx2 + snap-H/A，真实决策/快照零误删。"""
    from scripts.cleanup_t4_test_pollution import cleanup

    repo, future, _, _ = chain
    kickoff = datetime.fromisoformat(future["fixture"]["date"]).astimezone(UTC)
    decision_at = kickoff - timedelta(hours=2)
    # 真实链落 2 个真实决策 + 2 个真实快照（作为「零误删」对照）。
    ReadModelService().public_analysis_card_bounded(
        "1489404", use_frozen_canary=False, evaluation_time=kickoff
    )
    with Session(repo.engine) as session:
        real_decisions = {
            row.fixture_id for row in session.scalars(select(AhOuDecisionLedgerModel))
        }
        real_snapshots = {
            row.snapshot_id for row in session.scalars(select(TeamXgRollingSnapshotModel))
        }
    assert real_decisions == {"1489404"}
    assert len(real_snapshots) >= 2
    # 绕过写入器直插污染数据（先临时 DROP guard，再恢复）。
    _drop_guard(repo.engine)
    _seed_pollution(repo.engine, decision_at)
    _add_guard(repo.engine)
    # 清理：只删 fx1/fx2 + snap-H/A，不动真实数据。
    deleted = cleanup(repo.engine, dry_run=False)
    assert deleted["ah_ou_decision_ledger"] == 2, deleted
    assert deleted["team_xg_rolling_snapshot"] == 2, deleted
    with Session(repo.engine) as session:
        remaining_decisions = {
            row.fixture_id for row in session.scalars(select(AhOuDecisionLedgerModel))
        }
        remaining_snapshots = {
            row.snapshot_id for row in session.scalars(select(TeamXgRollingSnapshotModel))
        }
    assert remaining_decisions == real_decisions
    assert remaining_snapshots == real_snapshots
    # 幂等：再次清理零删除。
    deleted_again = cleanup(repo.engine, dry_run=False)
    assert deleted_again == {"ah_ou_decision_ledger": 0, "team_xg_rolling_snapshot": 0}
