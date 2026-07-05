from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from w2.dashboard.l2_diagnostics import build_l2_diagnostics
from w2.domain.enums import DataStatus, DecisionTier

ANALYSIS_PICK_DISCLAIMER = "分析参考·非稳赢；production 动作需 RECOMMEND"

_TIER_RANK = {
    DecisionTier.RECOMMEND.value: 0,
    DecisionTier.ANALYSIS_PICK.value: 1,
    DecisionTier.WATCH.value: 2,
    DecisionTier.NOT_READY.value: 3,
    DecisionTier.SKIP.value: 4,
}


def build_boss_dashboard_l1(day_view: Mapping[str, Any]) -> dict[str, Any]:
    counts = _mapping_copy(day_view.get("counts"))
    environment = _text(day_view.get("environment"), "unknown")
    cards = [_l1_card(card, environment=environment) for card in _cards(day_view)]
    ordered_cards = sorted(cards, key=_sort_key)
    sections = {
        "lock_eligible_recommendations": _lock_section_cards(
            ordered_cards,
            environment=environment,
        ),
        "analysis_picks": [
            card
            for card in ordered_cards
            if card["decision_tier"] == DecisionTier.ANALYSIS_PICK.value
        ],
        "watchlist": [
            card for card in ordered_cards if card["decision_tier"] == DecisionTier.WATCH.value
        ],
        "not_ready": [
            card
            for card in ordered_cards
            if card["decision_tier"] == DecisionTier.NOT_READY.value
        ],
        "skipped": [
            card for card in ordered_cards if card["decision_tier"] == DecisionTier.SKIP.value
        ],
        "reason_summary": _reason_summary(ordered_cards),
    }
    return {
        "football_day": _text(day_view.get("football_day"), day_view.get("date")),
        "environment": environment,
        "as_of": _text(day_view.get("generated_at")),
        "generated_at": _text(day_view.get("generated_at")),
        "freshness": _mapping_copy(day_view.get("freshness")),
        "navigation": _mapping_copy(day_view.get("navigation")),
        "degradation": _mapping_copy(day_view.get("degradation")),
        "headline": _headline(
            counts=counts,
            cards=cards,
            environment=environment,
            freshness=day_view.get("freshness"),
        ),
        "counts": counts,
        "cards": ordered_cards,
        "sections": sections,
    }


def _l1_card(card: Mapping[str, Any], *, environment: str) -> dict[str, Any]:
    pick = _mapping(card.get("pick"))
    non_pick = _mapping(card.get("non_pick"))
    decision_tier = _text(card.get("decision_tier"), DecisionTier.SKIP.value)
    reason_code = _optional_text(card.get("reason_code"), non_pick.get("reason_code"))
    action = _optional_text(card.get("action"), non_pick.get("action"))
    one_liner = _optional_text(card.get("one_liner"))
    if not one_liner:
        one_liner = _missing_one_liner(reason_code=reason_code, action=action)
    disclaimer = _optional_text(pick.get("disclaimer"))
    if decision_tier == DecisionTier.ANALYSIS_PICK.value:
        disclaimer = ANALYSIS_PICK_DISCLAIMER
    lock_eligible = card.get("lock_eligible") is True
    staging_only = (
        environment != "production"
        and lock_eligible
        and decision_tier == DecisionTier.ANALYSIS_PICK.value
    )
    return {
        "fixture_id": _text(card.get("fixture_id")),
        "kickoff_utc": _optional_text(card.get("kickoff_utc")),
        "match": _match_label(card),
        "decision_tier": decision_tier,
        "data_status": _text(card.get("data_status"), DataStatus.PARTIAL.value),
        "lock_eligible": lock_eligible,
        "staging_only": staging_only,
        "action_label": _action_label(
            decision_tier=decision_tier,
            lock_eligible=lock_eligible,
            staging_only=staging_only,
        ),
        "recommendation_id": _optional_text(card.get("recommendation_id")),
        "one_liner": one_liner,
        "reason_code": reason_code,
        "action": action,
        "next_eval_at": _optional_text(
            card.get("next_eval_at"),
            non_pick.get("next_eval_at"),
        ),
        "market": _optional_text(pick.get("market")),
        "selection": _optional_text(pick.get("selection")),
        "line": _optional_text(pick.get("line")),
        "odds": _optional_text(pick.get("odds")),
        "disclaimer": disclaimer,
        "source": _optional_text(card.get("source")),
        "diagnostics": build_l2_diagnostics(card),
    }


def _lock_section_cards(
    cards: Sequence[Mapping[str, Any]],
    *,
    environment: str,
) -> list[Mapping[str, Any]]:
    if environment == "production":
        return [
            card
            for card in cards
            if card.get("lock_eligible") is True
            and card.get("decision_tier") == DecisionTier.RECOMMEND.value
        ]
    return [card for card in cards if card.get("lock_eligible") is True]


def _action_label(
    *,
    decision_tier: str,
    lock_eligible: bool,
    staging_only: bool,
) -> str | None:
    if staging_only:
        return "需要审批"
    if lock_eligible and decision_tier == DecisionTier.RECOMMEND.value:
        return "正式可锁"
    return None


def _headline(
    *,
    counts: Mapping[str, Any],
    cards: Sequence[Mapping[str, Any]],
    environment: str,
    freshness: Any,
) -> str:
    provider_budget_status = _text(_mapping(freshness).get("provider_budget_status")).upper()
    if not cards:
        return "今日暂无比赛"
    if provider_budget_status == "EXHAUSTED":
        return "provider 预算耗尽，等待下一 tick 或预算恢复"
    lock_count = _int(counts.get("lock_eligible"))
    if environment == "production":
        if lock_count <= 0:
            return "当前无正式可锁推荐"
        return f"今日有 {lock_count} 场正式可锁推荐"
    if lock_count <= 0:
        return "当前无可锁审批候选"
    return f"今日有 {lock_count} 场可锁审批候选"


def _reason_summary(cards: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counter = Counter(
        str(card.get("reason_code"))
        for card in cards
        if _optional_text(card.get("reason_code")) is not None
    )
    return [
        {"reason_code": reason_code, "count": count}
        for reason_code, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _sort_key(card: Mapping[str, Any]) -> tuple[int, int, str]:
    lock_rank = 0 if card.get("lock_eligible") is True else 1
    tier_rank = _TIER_RANK.get(str(card.get("decision_tier")), 99)
    return (lock_rank, tier_rank, _text(card.get("kickoff_utc")))


def _cards(day_view: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = day_view.get("cards")
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _match_label(card: Mapping[str, Any]) -> str:
    home = _optional_text(card.get("home_team_name"))
    away = _optional_text(card.get("away_team_name"))
    if home and away:
        return f"{home} vs {away}"
    return _text(card.get("fixture_id"), "未命名比赛")


def _missing_one_liner(*, reason_code: str | None, action: str | None) -> str:
    detail = " / ".join(item for item in (reason_code, action) if item)
    if detail:
        return f"缺少人话解释，显示 reason/action：{detail}"
    return "缺少人话解释，等待下一次刷新"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_copy(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(*values: Any) -> str:
    value = _first(*values)
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def _optional_text(*values: Any) -> str | None:
    value = _first(*values)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


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
