from __future__ import annotations

from typing import Any

from w2.providers.quota import (
    API_FOOTBALL_BACKFILL_STOP_RATIO,
    API_FOOTBALL_CORE_ONLY_RATIO,
    API_FOOTBALL_DAILY_BUDGET,
    API_FOOTBALL_RESERVE_BUCKET,
    parse_int,
)

PREMATCH_TASKS = frozenset({"prematch_odds", "prematch_lineups", "odds", "lineups"})
BACKFILL_TASKS = frozenset(
    {
        "team_fixture_history_backfill",
        "h2h_backfill",
        "squad_value_mapping",
        "ratings_backfill",
    }
)


def independent_signal_quota_decision(
    *,
    remaining_quota: Any,
    task_type: str,
    daily_budget: int = API_FOOTBALL_DAILY_BUDGET,
    reserve_bucket: int = API_FOOTBALL_RESERVE_BUCKET,
) -> dict[str, Any]:
    remaining = parse_int(remaining_quota)
    normalized = task_type.lower()
    backfill_stop = int(daily_budget * API_FOOTBALL_BACKFILL_STOP_RATIO)
    core_only = int(daily_budget * API_FOOTBALL_CORE_ONLY_RATIO)
    is_prematch = normalized in PREMATCH_TASKS
    is_backfill = normalized in BACKFILL_TASKS or "backfill" in normalized
    if remaining is None:
        return _decision(
            allowed=is_prematch,
            reason=None if is_prematch else "DAILY_QUOTA_UNKNOWN",
            mode="CORE_ONLY" if is_prematch else "BLOCKED",
            remaining=None,
            daily_budget=daily_budget,
            reserve_bucket=reserve_bucket,
            task_type=task_type,
            backfill_stop=backfill_stop,
            core_only=core_only,
        )
    if remaining < core_only and not is_prematch:
        return _decision(
            allowed=False,
            reason="QUOTA_CRITICAL_CORE_ONLY",
            mode="CORE_ONLY",
            remaining=remaining,
            daily_budget=daily_budget,
            reserve_bucket=reserve_bucket,
            task_type=task_type,
            backfill_stop=backfill_stop,
            core_only=core_only,
        )
    if is_backfill and remaining < max(reserve_bucket, backfill_stop):
        return _decision(
            allowed=False,
            reason="BACKFILL_QUOTA_GUARD",
            mode="BACKFILL_STOPPED",
            remaining=remaining,
            daily_budget=daily_budget,
            reserve_bucket=reserve_bucket,
            task_type=task_type,
            backfill_stop=backfill_stop,
            core_only=core_only,
        )
    if remaining < reserve_bucket and not is_prematch:
        return _decision(
            allowed=False,
            reason="QUOTA_BELOW_RESERVE",
            mode="RESERVE_LOCKED",
            remaining=remaining,
            daily_budget=daily_budget,
            reserve_bucket=reserve_bucket,
            task_type=task_type,
            backfill_stop=backfill_stop,
            core_only=core_only,
        )
    return _decision(
        allowed=True,
        reason=None,
        mode="CORE_ONLY" if remaining < core_only else "NORMAL",
        remaining=remaining,
        daily_budget=daily_budget,
        reserve_bucket=reserve_bucket,
        task_type=task_type,
        backfill_stop=backfill_stop,
        core_only=core_only,
    )


def _decision(
    *,
    allowed: bool,
    reason: str | None,
    mode: str,
    remaining: int | None,
    daily_budget: int,
    reserve_bucket: int,
    task_type: str,
    backfill_stop: int,
    core_only: int,
) -> dict[str, Any]:
    return {
        "allowed": allowed,
        "reason": reason,
        "blocker": reason,
        "mode": mode,
        "remaining_quota": remaining,
        "daily_budget": daily_budget,
        "reserve_bucket": reserve_bucket,
        "available_after_reserve": None
        if remaining is None
        else max(remaining - reserve_bucket, 0),
        "reserve_locked": None if remaining is None else remaining < reserve_bucket,
        "backfill_stop_threshold": backfill_stop,
        "core_only_threshold": core_only,
        "task_type": task_type,
    }
