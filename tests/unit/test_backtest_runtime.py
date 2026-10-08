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


def test_watermark_idempotent_200_flip() -> None:
    """199→200 翻转触发一次；同水位线（consumed>=200）不重复触发。"""
    gate = _gate(200)
    assert should_dispatch(gate=gate, watermark=None) is True
    assert should_dispatch(gate=gate, watermark={"consumed_sample_count": 200}) is False
    assert should_dispatch(gate=gate, watermark={"consumed_sample_count": 250}) is False


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
