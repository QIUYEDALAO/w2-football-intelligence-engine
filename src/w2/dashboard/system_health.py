"""Read-only system health aggregation for the dashboard「系统健康」panel.

Aggregates five signals that answer "can today's recommendations run, and is
data flowing" — all from already-persisted evidence. Zero Provider calls, zero
writes: every query below reads the append-only ledgers / checkpoints / fences
that the background pipelines already maintain.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from w2.dashboard.date_window import football_day_for_kickoff, football_day_window
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
    AhOuDecisionLedgerModel,
)
from w2.infrastructure.persistence.ah_ou_postmatch_models import (
    AhOuV3SettlementModel,
)
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.future_refresh_models import TeamXgMatchModel
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayFixtureIdentityModel,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.infrastructure.persistence.provider_side_effect_fence_models import (
    STATE_SIDE_EFFECT_UNCERTAIN,
    ProviderSideEffectFenceModel,
)
from w2.providers.quota import API_FOOTBALL_RESERVE_BUCKET

SCHEMA_VERSION = "w2.system_health.v1"
# 与 ops/host/w2-xg-materialize 的 XG_LAG_THRESHOLD_HOURS 对齐：xG 组件表最新
# captured_at 落后于已 FT 比赛日历超过该小时数即视为断供。
XG_LAG_THRESHOLD_HOURS = 12.0
PROVIDER_STATUS_CHECKPOINT = "dashboard:provider_status"
FINISHED_RESULT_STATUSES = ("FT", "AET", "PEN")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _xg_freshness(session: Session) -> dict[str, Any]:
    """数据新鲜度：team_xg_match 最新 captured_at 落后于最近已 FT 比赛 kickoff 的滞后。

    复用 ops/host/w2-xg-materialize 的 lag_hours 口径（同一 SQL 语义），
    超阈值或已 FT 比赛存在但 xG 组件表为空 → STALE（断供）。
    """
    latest_ft_kickoff = session.scalar(
        select(func.max(MatchdayFixtureIdentityModel.kickoff_utc))
        .join(
            ResultModel,
            ResultModel.fixture_id == MatchdayFixtureIdentityModel.fixture_id,
        )
        .where(ResultModel.result_status.in_(FINISHED_RESULT_STATUSES))
    )
    latest_xg_capture = session.scalar(select(func.max(TeamXgMatchModel.captured_at)))

    lag_hours: float | None
    if latest_ft_kickoff is not None and latest_xg_capture is not None:
        lag_hours = (_utc(latest_ft_kickoff) - _utc(latest_xg_capture)).total_seconds() / 3600.0
    elif latest_ft_kickoff is not None and latest_xg_capture is None:
        lag_hours = None  # 已 FT 比赛存在，但 xG 组件表完全无数据 → 断供
    else:
        lag_hours = 0.0  # 尚无已 FT 比赛，不存在滞后

    stale = lag_hours is None or lag_hours > XG_LAG_THRESHOLD_HOURS
    if lag_hours is None:
        status = "STALE"
    elif stale:
        status = "STALE"
    else:
        status = "OK"
    return {
        "status": status,
        "ok": not stale,
        "lag_hours": round(lag_hours, 2) if lag_hours is not None else None,
        "threshold_hours": XG_LAG_THRESHOLD_HOURS,
        "latest_ft_kickoff": _utc(latest_ft_kickoff).isoformat() if latest_ft_kickoff else None,
        "latest_xg_capture": _utc(latest_xg_capture).isoformat() if latest_xg_capture else None,
    }


def _recommendation_chain(session: Session, *, now: datetime, day: Any) -> dict[str, Any]:
    """推荐链路：今日比赛数 / 到决策点数 / 推荐(selected)数 / SKIP 数及原因分布。

    复用 d2ddc2b7「今日推荐健康度」通知的统计口径（纯读账本），不写 outbox。
    """
    start, end = football_day_window(day)
    lo = start - timedelta(hours=2)
    hi = end - timedelta(hours=2)
    rows = list(
        session.scalars(
            select(AhOuDecisionLedgerModel).where(
                AhOuDecisionLedgerModel.decision_at >= lo,
                AhOuDecisionLedgerModel.decision_at < hi,
            )
        )
    )
    match_count = len({row.fixture_id for row in rows})
    due = [row for row in rows if _utc(row.decision_at) <= now]
    decision_due_count = len({row.fixture_id for row in due})
    selected = [row for row in rows if row.selected]
    skips = [row for row in rows if not row.selected and row.skip_reason]
    stale_f9 = sum(row.skip_reason == "F9_SNAPSHOT_STALE" for row in skips)
    stale_quote = sum("STALE_QUOTE" in (row.skip_reason or "") for row in skips)
    other = len(skips) - stale_f9 - stale_quote
    # 健康 = 有比赛且（有推荐，或没有全断供的 SKIP）；无比赛/无决策点视为「待运行」非故障。
    ok = match_count == 0 or decision_due_count == 0 or bool(selected) or stale_f9 != len(skips)
    return {
        "match_count": match_count,
        "decision_due_count": decision_due_count,
        "selected_count": len(selected),
        "skip_count": len(skips),
        "skip_reasons": {
            "F9_SNAPSHOT_STALE": stale_f9,
            "STALE_QUOTE": stale_quote,
            "other": other,
        },
        "ok": ok,
    }


def _collection_quota(session: Session) -> dict[str, Any]:
    """采集：Provider 额度（读 api-football status 缓存，不新调 Provider）。"""
    row = session.scalar(
        select(ReadModelCheckpointModel).where(
            ReadModelCheckpointModel.checkpoint_key == PROVIDER_STATUS_CHECKPOINT
        )
    )
    payload = row.payload if row is not None else {}
    remaining_raw = payload.get("remaining_quota")
    try:
        remaining = int(remaining_raw) if remaining_raw is not None else None
    except (TypeError, ValueError):
        remaining = None
    ok = remaining is not None and remaining > API_FOOTBALL_RESERVE_BUCKET
    return {
        "provider": str(payload.get("provider") or "api_football"),
        "status": str(payload.get("status") or "NOT_READY"),
        "remaining_quota": remaining,
        "reserve_bucket": API_FOOTBALL_RESERVE_BUCKET,
        "ok": ok,
    }


def _settlement(session: Session, *, selected: list[Any]) -> dict[str, Any]:
    """结算：今日已结算场数 / 异常数（selected 决策里尚未结算的缺口）。"""
    settled_rows = list(
        session.scalars(select(AhOuV3SettlementModel).where(
            AhOuV3SettlementModel.fixture_id.in_({row.fixture_id for row in selected})
        ))
    ) if selected else []
    settled_fixtures = {row.fixture_id for row in settled_rows}
    selected_fixtures = {row.fixture_id for row in selected}
    anomaly = selected_fixtures - settled_fixtures
    return {
        "settled_count": len(settled_fixtures),
        "anomaly_count": len(anomaly),
        "ok": len(anomaly) == 0,
    }


def build_system_health(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    resolved = _utc(now or datetime.now(UTC))
    day = football_day_for_kickoff(resolved)

    freshness = _xg_freshness(session)
    chain = _recommendation_chain(session, now=resolved, day=day)
    quota = _collection_quota(session)
    selected_rows = list(
        session.scalars(
            select(AhOuDecisionLedgerModel).where(AhOuDecisionLedgerModel.selected.is_(True))
        )
    )
    settlement = _settlement(session, selected=selected_rows)

    alerts: list[dict[str, Any]] = []
    if not freshness["ok"]:
        lag = freshness["lag_hours"]
        detail = (
            f"xG 断供：team_xg_match 最新 captured_at 落后已 FT 比赛 "
            f"{lag:.1f} 小时（阈值 {XG_LAG_THRESHOLD_HOURS:.0f}h）" if lag is not None
            else "xG 断供：team_xg_match 无数据，但存在已 FT 比赛"
        )
        alerts.append({"type": "XG_STALE", "severity": "RED", "detail": detail})
    fence_uncertain = session.scalar(
        select(func.count()).select_from(ProviderSideEffectFenceModel).where(
            ProviderSideEffectFenceModel.state == STATE_SIDE_EFFECT_UNCERTAIN
        )
    ) or 0
    if fence_uncertain:
        alerts.append({
            "type": "SIDE_EFFECT_UNCERTAIN",
            "severity": "YELLOW",
            "detail": f"{fence_uncertain} 条 Provider 副作用状态不确定",
        })
    if not quota["ok"]:
        alerts.append({
            "type": "LOW_QUOTA",
            "severity": "YELLOW",
            "detail": f"Provider 剩余额度 {quota['remaining_quota']} 已触达保留桶 {quota['reserve_bucket']}",
        })
    if not settlement["ok"]:
        alerts.append({
            "type": "SETTLEMENT_GAP",
            "severity": "YELLOW",
            "detail": f"{settlement['anomaly_count']} 场 selected 决策尚未结算",
        })

    overall = "OK"
    if any(alert["severity"] == "RED" for alert in alerts):
        overall = "STALE"
    elif alerts:
        overall = "DEGRADED"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": resolved.isoformat(),
        "football_day": day.isoformat(),
        "overall": overall,
        "data_freshness": freshness,
        "recommendation_chain": chain,
        "collection_quota": quota,
        "settlement": settlement,
        "alerts": alerts,
    }
