from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

SOURCE = "w2.dashboard.degradation.v1"


def build_dashboard_degradation(day_view: Mapping[str, Any]) -> dict[str, Any]:
    counts = _mapping(day_view.get("counts"))
    freshness = _mapping(day_view.get("freshness"))
    environment = _optional_text(day_view.get("environment"))
    total = _int(counts.get("total"))
    stale = _int(counts.get("stale"))
    blocked = _int(counts.get("blocked"))
    lock_eligible = _int(counts.get("lock_eligible"))
    analysis_pick = _int(counts.get("analysis_pick"))
    next_eval_at = _optional_text(
        freshness.get("next_refresh_tick"),
        _first_card_value(day_view, "next_eval_at"),
    )
    provider_budget_status = _optional_text(freshness.get("provider_budget_status"))
    stale_or_blocked_count = stale + blocked

    if total == 0:
        return _state(
            "EMPTY_DAY",
            "info",
            "今日暂无比赛",
            "当前比赛日没有可展示 fixture。",
            "等待下一次刷新或切换比赛日。",
            next_eval_at=next_eval_at,
            reason_code="NO_FIXTURES",
            provider_budget_status=provider_budget_status,
            stale_or_blocked_count=stale_or_blocked_count,
        )
    if _upper(provider_budget_status) == "EXHAUSTED":
        return _state(
            "PROVIDER_BUDGET_EXHAUSTED",
            "warning",
            "provider 预算耗尽",
            "当前 provider 预算已耗尽，页面保留现有只读结果。",
            "等待下一 tick 或预算恢复。",
            next_eval_at=next_eval_at,
            reason_code="PROVIDER_BUDGET_EXHAUSTED",
            provider_budget_status=provider_budget_status,
            stale_or_blocked_count=stale_or_blocked_count,
        )
    if blocked == total and total > 0:
        return _state(
            "BLOCKED_DAY",
            "blocked",
            "今日数据被阻断",
            "全部比赛都处于 BLOCKED，暂不能形成可行动建议。",
            "查看未就绪原因，等待数据补齐。",
            next_eval_at=next_eval_at,
            reason_code="BLOCKED_DAY",
            provider_budget_status=provider_budget_status,
            stale_or_blocked_count=stale_or_blocked_count,
        )
    if stale > 0:
        return _state(
            "STALE_DATA",
            "warning",
            "存在陈旧数据",
            f"当前有 {stale} 场比赛数据陈旧，建议等待刷新后再审批。",
            "等待下一次刷新完成。",
            next_eval_at=next_eval_at,
            reason_code="DATA_STALE",
            provider_budget_status=provider_budget_status,
            stale_or_blocked_count=stale_or_blocked_count,
        )
    if _truthy(day_view.get("refreshing")) or _truthy(freshness.get("refreshing")):
        return _state(
            "REFRESHING",
            "info",
            "刷新中",
            "比赛日数据正在刷新，当前页面可能短暂滞后。",
            "刷新完成后自动查看最新结果。",
            next_eval_at=next_eval_at,
            reason_code="REFRESHING",
            provider_budget_status=provider_budget_status,
            stale_or_blocked_count=stale_or_blocked_count,
        )
    if lock_eligible == 0:
        if environment == "production":
            return _state(
                "NO_LOCK_ELIGIBLE",
                "info",
                "当前无正式可锁推荐",
                "今天暂时没有 production 正式可锁推荐，这不是系统故障。",
                "继续观察分析推荐、观察名单和未就绪原因。",
                next_eval_at=next_eval_at,
                reason_code="NO_LOCK_ELIGIBLE",
                provider_budget_status=provider_budget_status,
                stale_or_blocked_count=stale_or_blocked_count,
            )
        return _state(
            "NO_LOCK_ELIGIBLE",
            "info",
            "当前无可锁审批候选",
            "今天暂时没有 lock_eligible=true 的卡片，这不是系统故障。",
            "继续观察分析推荐和未就绪原因。",
            next_eval_at=next_eval_at,
            reason_code="NO_LOCK_ELIGIBLE",
            provider_budget_status=provider_budget_status,
            stale_or_blocked_count=stale_or_blocked_count,
        )
    if analysis_pick == 0:
        return _state(
            "NO_ANALYSIS_PICK",
            "info",
            "当前无分析推荐",
            "今天暂时没有 ANALYSIS_PICK 卡片，这不是系统故障。",
            "继续观察正式推荐、观察名单和未就绪原因。",
            next_eval_at=next_eval_at,
            reason_code="NO_ANALYSIS_PICK",
            provider_budget_status=provider_budget_status,
            stale_or_blocked_count=stale_or_blocked_count,
        )
    return _state(
        "OK",
        "info",
        "Dashboard 正常",
        "当前比赛日页面可读。",
        "按 L1/L2 信息继续审批或观察。",
        next_eval_at=next_eval_at,
        provider_budget_status=provider_budget_status,
        stale_or_blocked_count=stale_or_blocked_count,
    )


def build_api_unavailable_degradation(
    message: str,
    *,
    next_eval_at: str | None = None,
) -> dict[str, Any]:
    return _state(
        "API_UNAVAILABLE",
        "blocked",
        "Dashboard API 暂不可用",
        message,
        "稍后重试或查看服务健康状态。",
        next_eval_at=next_eval_at,
        reason_code="API_UNAVAILABLE",
        provider_budget_status=None,
        stale_or_blocked_count=0,
    )


def _state(
    state: str,
    severity: str,
    title: str,
    message: str,
    action: str,
    *,
    next_eval_at: str | None = None,
    reason_code: str | None = None,
    provider_budget_status: str | None = None,
    stale_or_blocked_count: int = 0,
) -> dict[str, Any]:
    return {
        "state": state,
        "severity": severity,
        "title": title,
        "message": message,
        "action": action,
        "next_eval_at": next_eval_at,
        "reason_code": reason_code,
        "provider_budget_status": provider_budget_status,
        "stale_or_blocked_count": stale_or_blocked_count,
        "source": SOURCE,
    }


def _first_card_value(day_view: Mapping[str, Any], key: str) -> Any:
    cards = day_view.get("cards")
    if not isinstance(cards, list | tuple):
        return None
    for card in cards:
        if isinstance(card, Mapping) and card.get(key) is not None:
            return card.get(key)
    return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _optional_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, datetime):
            return value.isoformat().replace("+00:00", "Z")
        text = str(value).strip()
        if text:
            return text
    return None


def _upper(value: Any) -> str:
    return str(value or "").upper()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0
