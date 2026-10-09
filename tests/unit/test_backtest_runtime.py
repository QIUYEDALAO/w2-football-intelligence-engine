from __future__ import annotations

from w2.backtest.backtest_runtime import (
    build_backtest_gate_report,
    run_backtest_execution,
    should_dispatch,
)


def _gate(sample_count: int) -> dict:
    return build_backtest_gate_report(
        settled_lock_sample_count=sample_count,
        generated_at="2026-10-09T00:00:00Z",
    )


def test_gate_blocked_below_200() -> None:
    gate = _gate(199)
    assert gate["status"] == "BLOCKED_WITH_SAMPLE_GATE"
    assert should_dispatch(gate=gate, watermark=None) is False


def test_gate_ready_at_200() -> None:
    gate = _gate(200)
    assert gate["status"] == "READY_FOR_OFFLINE_REVIEW"
    assert should_dispatch(gate=gate, watermark=None) is True


def test_watermark_periodic_dispatch_every_200() -> None:
    """周期语义：200 触发→consumed=200；399 不触发；400 再触发→consumed=400；同水位线不重复。"""
    # 首次：200 触发（consumed 0→200）
    assert should_dispatch(gate=_gate(200), watermark=None) is True
    # 消费后：399 不触发（399 < 200+200=400）
    assert should_dispatch(gate=_gate(399), watermark={"consumed_sample_count": 200}) is False
    # 400 再触发（400 >= 200+200）
    assert should_dispatch(gate=_gate(400), watermark={"consumed_sample_count": 200}) is True
    # 同水位线（consumed=400）不重复（400 < 400+200=600）
    assert should_dispatch(gate=_gate(400), watermark={"consumed_sample_count": 400}) is False


def test_watermark_199_never_dispatches() -> None:
    """199 不触发（门 BLOCKED），即使无水位线。"""
    gate = _gate(199)
    assert should_dispatch(gate=gate, watermark=None) is False


def test_run_backtest_execution_canonical_hash_stable() -> None:
    """同输入两次执行产出 canonical hash 一致（w2.canonical-json.v2）。"""
    fixture_rows = [
        {
            "fixture_id": "api_football:1",
            "kickoff_utc": "2026-10-01T18:00:00Z",
            "final_result": "2-1",
            "fair_ah": 0.5,
            "settlement_outcome": "WIN",
        }
    ]
    first = run_backtest_execution(
        generated_at="2026-10-09T00:00:00Z",
        fixture_rows=fixture_rows,
    )
    second = run_backtest_execution(
        generated_at="2026-10-09T00:00:00Z",
        fixture_rows=fixture_rows,
    )
    assert first["source_hash"] == second["source_hash"]
    assert first["provider_calls"] == 0
    assert first["enabled_for_online_path"] is False


def test_count_settled_lock_samples_matches_direct_sql() -> None:
    """计数函数对真实表（selected JOIN settlement）与直接 SQL 一致（非注入值）。

    覆盖口径：selected=true 且已结算 → 计入；selected=false 已结算 → 不计；
    selected=true 未结算 → 不计。断言 count_settled_lock_samples 与手写 SQL 相等。
    """
    from datetime import UTC, datetime

    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    from w2.backtest.backtest_runtime import count_settled_lock_samples
    from w2.infrastructure.database import Base
    from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
        AhOuDecisionLedgerModel,
    )
    from w2.infrastructure.persistence.ah_ou_postmatch_models import AhOuV3SettlementModel

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)

    def seed_decision(session: Session, decision_id: str, fixture_id: str, selected: bool) -> None:
        session.add(
            AhOuDecisionLedgerModel(
                decision_id=decision_id,
                fixture_id=fixture_id,
                market="TOTALS",
                decision_at=now,
                model_version="m1",
                calibration_version="c1",
                input_hash="i" * 64,
                full_distribution={"selection": {"selected": selected, "edge": 0.1}},
                decision_contract="w2.ah_ou_decision.v3.1",
                frozen_terms={"schema_version": "w2.ah_ou_frozen_terms.v1"},
                terms_hash="t" * 64,
                quote_identity_hash="q" * 64,
                source_capture_sha256="s" * 64,
                capture_id="cap-1",
                source_id="src-1",
                home_team_id="H",
                away_team_id="A",
                selected=selected,
                direction="OVER",
                score="0.1",
                skip_reason=None,
                created_at=now,
            )
        )

    def seed_settlement(session: Session, decision_id: str, fixture_id: str) -> None:
        session.add(
            AhOuV3SettlementModel(
                decision_id=decision_id,
                fixture_id=fixture_id,
                market="TOTALS",
                schema_version="w2.ah_ou_v3_settlement.v1",
                terms_hash="t" * 64,
                result_id=f"r-{fixture_id}",
                result_hash="rh" * 32,
                result_raw_sha256="raw" * 21 + "0",
                result_capture_id="cap-1",
                home_goals=2,
                away_goals=2,
                outcome="WIN",
                net_units="0.83",
                settlement_hash=f"sh-{decision_id}",
                settled_at=now,
            )
        )

    with Session(engine) as session:
        # selected=true 且已结算 → 计入
        seed_decision(session, "d1", "FIX1", True)
        seed_settlement(session, "d1", "FIX1")
        # selected=true 且已结算 → 计入
        seed_decision(session, "d2", "FIX2", True)
        seed_settlement(session, "d2", "FIX2")
        # selected=false 已结算 → 不计
        seed_decision(session, "d3", "FIX3", False)
        seed_settlement(session, "d3", "FIX3")
        # selected=true 未结算 → 不计
        seed_decision(session, "d4", "FIX4", True)
        session.commit()

    assert count_settled_lock_samples(engine=engine) == 2

    with Session(engine) as session:
        direct = session.scalar(
            select(func.count())
            .select_from(AhOuDecisionLedgerModel)
            .join(
                AhOuV3SettlementModel,
                AhOuV3SettlementModel.decision_id == AhOuDecisionLedgerModel.decision_id,
            )
            .where(AhOuDecisionLedgerModel.selected.is_(True))
        )
    assert int(direct or 0) == 2
    assert count_settled_lock_samples(engine=engine) == int(direct or 0)
