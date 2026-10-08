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
from w2.infrastructure.persistence.future_refresh_models import (
    TeamXgMatchModel,
    TeamXgRollingSnapshotModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayFixtureIdentityModel,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.infrastructure.persistence.provider_side_effect_fence_models import (
    STATE_SIDE_EFFECT_UNCERTAIN,
    ProviderSideEffectFenceModel,
)
from w2.providers.quota import API_FOOTBALL_RESERVE_BUCKET
from w2.providers.status import fetch_provider_quota_live

SCHEMA_VERSION = "w2.system_health.v1"
# 与 ops/host/w2-xg-materialize 的 XG_LAG_THRESHOLD_HOURS 对齐：F9 快照覆盖边界
# 落后于比赛日历最近 FT 超过该小时数即视为断供（与 F9 新鲜度门 F9_SNAPSHOT_STALE 同源）。
# R1：12h 太敏感，休赛期/比赛稀疏时覆盖边界自然落后超 12h 造成误报；放宽到 120h（5 天）
# 只报真正长期断供。注意：这是「告警」阈值，不碰 ah_ou_decision 的 F9 决策门（相对比较）。
XG_LAG_THRESHOLD_HOURS = 120.0
PROVIDER_STATUS_CHECKPOINT = "dashboard:provider_status"
FINISHED_RESULT_STATUSES = ("FT", "AET", "PEN")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_iso_ts(value: Any) -> datetime | None:
    """Strict AS-OF timestamp parse (naive values refused), 与 F9 门 _parse_asof 同口径。"""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else None
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else None
    return None


def _latest_snapshot_source_kickoff(session: Session) -> datetime | None:
    """F9 快照覆盖边界：所有 snapshot 的 source_matches 里最新 kickoff_at。

    与 ``ah_ou_decision._latest_source_match_kickoff`` 完全同源——``source_matches``
    记录滚动窗口的构成 fixture，其最新 ``kickoff_at`` 才是「xG 采到哪场」的正确锚点；
    ``as_of_time`` 是采集/可用时点（不是比赛时点），不能与比赛日历对齐。
    """
    latest: datetime | None = None
    for matches in session.scalars(select(TeamXgRollingSnapshotModel.source_matches)):
        if not matches:
            continue
        for item in matches:
            if not isinstance(item, dict):
                continue
            parsed = _parse_iso_ts(item.get("kickoff_at"))
            if parsed is not None and (latest is None or parsed > latest):
                latest = parsed
    return latest


def _xg_freshness(session: Session) -> dict[str, Any]:
    """数据新鲜度：F9 快照覆盖边界落后于比赛日历最近 FT 的滞后。

    比赛日历最近 FT 改用**独立赛果表 results 口径**（``matchday_fixture_identities``
    JOIN ``results``，``result_status IN (FT/AET/PEN)``），与巡检 B4 及真实赛果同源。
    之前查 ``canonical_team_match_history``（xG 链自己的表）——xG 断供时该表与快照
    一起冻结，导致假健康（ok=true、显示「领先」）；改为 results 口径后，断供时
    results 日历照常推进，红灯判定不再失明。
    - F9 快照覆盖边界 = ``team_xg_rolling_snapshot.source_matches`` 最新 kickoff_at；
    - 比赛日历最近 FT = ``matchday_fixture_identities JOIN results`` 最新 kickoff_utc。
    同时返回「原始 xG 滞后」作参考（team_xg_match captured_at vs FT），红灯只看 F9 快照口径。
    """
    latest_ft_kickoff = session.scalar(
        select(func.max(MatchdayFixtureIdentityModel.kickoff_utc))
        .select_from(MatchdayFixtureIdentityModel)
        .join(
            ResultModel,
            ResultModel.fixture_id == MatchdayFixtureIdentityModel.fixture_id,
        )
        .where(ResultModel.result_status.in_(FINISHED_RESULT_STATUSES))
    )
    latest_snapshot_kickoff = _latest_snapshot_source_kickoff(session)
    latest_xg_capture = session.scalar(select(func.max(TeamXgMatchModel.captured_at)))

    f9_lag_hours: float | None
    if latest_ft_kickoff is not None and latest_snapshot_kickoff is not None:
        f9_lag_hours = (
            _utc(latest_ft_kickoff) - _utc(latest_snapshot_kickoff)
        ).total_seconds() / 3600.0
    elif latest_ft_kickoff is not None and latest_snapshot_kickoff is None:
        f9_lag_hours = None  # 已 FT 比赛存在，但 F9 快照无 source_matches → 断供
    else:
        f9_lag_hours = 0.0  # 尚无已 FT 比赛，不存在滞后

    raw_lag_hours: float | None = None
    if latest_ft_kickoff is not None and latest_xg_capture is not None:
        raw_lag_hours = (
            _utc(latest_ft_kickoff) - _utc(latest_xg_capture)
        ).total_seconds() / 3600.0

    stale = f9_lag_hours is None or f9_lag_hours > XG_LAG_THRESHOLD_HOURS
    return {
        "status": "STALE" if stale else "OK",
        "ok": not stale,
        "f9_snapshot_lag_hours": round(f9_lag_hours, 2) if f9_lag_hours is not None else None,
        "raw_xg_lag_hours": round(raw_lag_hours, 2) if raw_lag_hours is not None else None,
        "threshold_hours": XG_LAG_THRESHOLD_HOURS,
        "latest_ft_kickoff": _utc(latest_ft_kickoff).isoformat() if latest_ft_kickoff else None,
        "latest_snapshot_kickoff": _utc(latest_snapshot_kickoff).isoformat()
        if latest_snapshot_kickoff
        else None,
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
    # P2: 「到决策点」不卡足球日窗口上界，直接判 decision_at <= now（下界 lo 仅用于
    # 排除历史场次）——避免足球日边界（12:00 截断 / 最后 2h 滚动）把已到决策点的
    # 场次（如 MLS 早场）漏计成「到决策点 0 场」。
    due_rows = list(
        session.scalars(
            select(AhOuDecisionLedgerModel).where(
                AhOuDecisionLedgerModel.decision_at >= lo,
                AhOuDecisionLedgerModel.decision_at <= now,
            )
        )
    )
    decision_due_count = len({row.fixture_id for row in due_rows})
    # F7：selected/skip 只统计已到决策点（decision_at <= now）的行——排除预评估遗留的
    # future-dated 行（decision_at 在未来却已落账本），不再污染「今日推荐/SKIP」统计。
    selected = [row for row in due_rows if row.selected]
    skips = [row for row in due_rows if not row.selected and row.skip_reason]
    stale_f9 = sum(row.skip_reason == "F9_SNAPSHOT_STALE" for row in skips)
    stale_quote = sum("STALE_QUOTE" in (row.skip_reason or "") for row in skips)
    other = len(skips) - stale_f9 - stale_quote
    # 健康 = 有比赛且（无决策点 → 待运行非故障；有决策点则必须产出推荐）。
    ok = match_count == 0 or decision_due_count == 0 or bool(selected)
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


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _collection_quota(session: Session) -> dict[str, Any]:
    """采集：Provider 额度——复用 status.py 实时 /status 查询（免费只读豁免，同一 live 源）。

    remaining = limit_day - current 可读 → 真实额度；查不到 → 降级读
    read_model_checkpoint 缓存 remaining_quota（status 标记 DEGRADED），缓存也无 →
    remaining_quota=None（QUOTA_UNKNOWN）。不造假。
    """
    live = fetch_provider_quota_live()
    if live.get("degraded") is False and live.get("remaining") is not None:
        remaining = live["remaining"]
        status = "READY"
        current = live.get("current")
        limit_day = live.get("limit_day")
    else:
        row = session.scalar(
            select(ReadModelCheckpointModel).where(
                ReadModelCheckpointModel.checkpoint_key == PROVIDER_STATUS_CHECKPOINT
            )
        )
        payload = row.payload if row is not None else {}
        remaining = _coerce_int(payload.get("remaining_quota"))
        status = "DEGRADED" if remaining is not None else str(payload.get("status") or "NOT_READY")
        current = None
        limit_day = None
    ok = remaining is not None and remaining > API_FOOTBALL_RESERVE_BUCKET
    return {
        "provider": "api_football",
        "status": status,
        "remaining_quota": remaining,
        "reserve_bucket": API_FOOTBALL_RESERVE_BUCKET,
        "ok": ok,
        "current": current,
        "limit_day": limit_day,
        "source": "live" if status == "READY" else "cache",
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
        lag = freshness["f9_snapshot_lag_hours"]
        detail = (
            f"xG 断供：F9 快照覆盖边界落后已 FT 比赛 "
            f"{lag:.1f} 小时（阈值 {XG_LAG_THRESHOLD_HOURS:.0f}h）" if lag is not None
            else "xG 断供：已 FT 比赛存在，但 F9 快照为空"
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
    if quota["remaining_quota"] is None:
        alerts.append({
            "type": "QUOTA_UNKNOWN",
            "severity": "YELLOW",
            "detail": "Provider 额度未知（status 缓存无 remaining_quota）",
        })
    elif not quota["ok"]:
        alerts.append({
            "type": "LOW_QUOTA",
            "severity": "YELLOW",
            "detail": f"Provider 剩余额度 {quota['remaining_quota']} 已触达保留桶 {quota['reserve_bucket']}",
        })
    if not chain["ok"]:
        alerts.append({
            "type": "NO_RECOMMENDATION_TODAY",
            "severity": "YELLOW",
            "detail": (
                f"今日 {chain['match_count']} 场、{chain['decision_due_count']} 场已到决策点，"
                f"推荐 0 条（SKIP {chain['skip_count']} 条）"
            ),
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
