"""回测接线：计数 → 门 → 达标执行 → 结果落地 checkpoint → API 读取（指令书 B 最小设计）。

防线（12 条红线适用）：
- 门唯一权威：``MIN_LAMBDA_FIT_SETTLED_LOCK_SAMPLES=200`` 只在 ``lambda_fit_gate.py`` 定义，
  本模块只 import 不复制、不新写阈值；
- 全程 0 Provider 调用、0 决策链写入（``enabled_for_online_path`` 恒 False）；
- 水位线幂等：199→200 翻转触发一次，同水位线重跑不重复触发，199 不触发（门 BLOCKED）；
- 结果 canonical hash（w2.canonical-json.v2，``HashDomain.BACKTEST_LATEST``）可重复。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from w2.backtest.lambda_fit_gate import (
    MIN_LAMBDA_FIT_SETTLED_LOCK_SAMPLES,
    build_lambda_fit_gap_report,
)
from w2.domain.canonical_serialization import HashDomain, canonical_sha256

BACKTESTS_LATEST_KEY = "backtests:latest"
BACKTESTS_WATERMARK_KEY = "backtests:watermark"


def count_settled_lock_samples(repository=None) -> int:
    """settled lock 样本数——复用 formal_results.endpoint_summary（唯一权威口径）。"""
    from w2.tracking.formal_results import endpoint_summary

    return int(endpoint_summary(repository=repository).get("sample_count", 0) or 0)


def build_backtest_gate_report(
    *,
    settled_lock_sample_count: int,
    generated_at: str,
) -> dict[str, Any]:
    """计数 → 门（唯一权威 ``build_lambda_fit_gap_report``）。"""
    return build_lambda_fit_gap_report(
        settled_lock_sample_count=settled_lock_sample_count,
        generated_at=generated_at,
    )


def gate_is_ready(gate: dict[str, Any]) -> bool:
    return gate.get("status") == "READY_FOR_OFFLINE_REVIEW"


def should_dispatch(*, gate: dict[str, Any], watermark: dict[str, Any] | None) -> bool:
    """门 READY 且水位线未消费 200 门槛 → 触发；同水位线重跑不重复触发。"""
    if not gate_is_ready(gate):
        return False
    consumed = int((watermark or {}).get("consumed_sample_count", 0) or 0)
    return consumed < MIN_LAMBDA_FIT_SETTLED_LOCK_SAMPLES


def build_watermark_payload(*, sample_count: int, at: str) -> dict[str, Any]:
    return {"consumed_sample_count": sample_count, "consumed_at": at}


def run_backtest_execution(
    *,
    generated_at: str,
    fixture_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """执行 walk-forward（纯离线、0 provider），产出报告 + canonical source_hash。

    fixture_rows 缺省时走 ``build_real_handicap_walkforward_report`` 的本地 timeline 快照；
    测试可注入 fixture_rows 做确定性执行。
    """
    from w2.backtest.handicap_walkforward import (
        RealWalkForwardInputs,
        build_real_handicap_walkforward_report,
    )

    report = build_real_handicap_walkforward_report(
        RealWalkForwardInputs(fixture_rows=fixture_rows)
    )
    payload: dict[str, Any] = {
        "schema_version": "w2.backtest.latest.v1",
        "generated_at": generated_at,
        "status": "READY" if report.get("authoritative") else "NOT_READY",
        "report": report,
        "provider_calls": 0,
        "db_writes": 1,  # 仅 checkpoint 写入
        "enabled_for_online_path": False,
    }
    source_hash = canonical_sha256(payload, domain=HashDomain.BACKTEST_LATEST)
    return {**payload, "source_hash": source_hash}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def read_checkpoint_payload(engine, key: str) -> dict[str, Any] | None:
    """读 read_model_checkpoint 的 payload（不存在返回 None）。"""
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel

    with Session(engine) as session:
        row = session.scalar(
            select(ReadModelCheckpointModel).where(
                ReadModelCheckpointModel.checkpoint_key == key
            )
        )
        return dict(row.payload) if row is not None else None


def upsert_checkpoint(engine, key: str, source_hash: str, payload: dict[str, Any]) -> None:
    """upsert read_model_checkpoint（幂等，仅此一处 checkpoint 写入）。"""
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel

    now = datetime.now(UTC)
    with Session(engine) as session:
        existing = session.scalar(
            select(ReadModelCheckpointModel).where(
                ReadModelCheckpointModel.checkpoint_key == key
            )
        )
        if existing is None:
            session.add(
                ReadModelCheckpointModel(
                    checkpoint_key=key,
                    source_hash=source_hash,
                    created_at=now,
                    payload=payload,
                )
            )
        else:
            existing.source_hash = source_hash
            existing.created_at = now
            existing.payload = payload
        session.commit()
