from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from w2.domain.decision_card import compute_card_hash

DEFAULT_DAILY_ANALYSIS_PICK_CAP = 3


def apply_daily_analysis_pick_cap(
    cards: Sequence[Mapping[str, Any]],
    *,
    cap: int = DEFAULT_DAILY_ANALYSIS_PICK_CAP,
) -> list[dict[str, Any]]:
    output = [deepcopy(dict(card)) for card in cards]
    candidates_by_day: dict[str, list[dict[str, Any]]] = {}
    for card in output:
        if str(card.get("decision_tier")) != "ANALYSIS_PICK":
            continue
        candidates_by_day.setdefault(_football_day(card), []).append(card)
    for candidates in candidates_by_day.values():
        candidates.sort(key=_selection_key)
        for card in candidates[max(cap, 0) :]:
            _downgrade_to_watch(card)
    return output


def _selection_key(card: Mapping[str, Any]) -> tuple[float, int, datetime, str]:
    gate = card.get("analysis_gate")
    gate = gate if isinstance(gate, Mapping) else {}
    strength = _number(gate.get("strength_quarter_lines")) or 0.0
    data_rank = {"READY": 0, "PARTIAL": 1, "STALE": 2, "BLOCKED": 3}.get(
        str(card.get("data_status")),
        9,
    )
    kickoff = _parse_time(card.get("kickoff_utc")) or datetime.max.replace(tzinfo=UTC)
    return (-strength, data_rank, kickoff, str(card.get("fixture_id") or ""))


def _downgrade_to_watch(card: dict[str, Any]) -> None:
    contract = card.get("decision_contract")
    contract = dict(contract) if isinstance(contract, Mapping) else {}
    non_pick = {
        "reason_code": "SELECTIVITY_DAILY_CAP",
        "reason_human": "当日更强分析信号已达 3 场上限",
        "action": "保留在观察列表，不降低阈值凑数",
        "next_eval_at": _next_eval(card),
    }
    for payload in (card, contract):
        payload["decision_tier"] = "WATCH"
        payload["outcome_tracked"] = False
        payload["lock_eligible"] = False
        payload["pick"] = None
        payload["non_pick"] = dict(non_pick)
        payload["reason_code"] = "SELECTIVITY_DAILY_CAP"
        payload["action"] = non_pick["action"]
        payload["one_liner"] = "存在分歧，但当日只展示最强 3 场分析参考。"
    contract["card_hash"] = compute_card_hash(contract)
    card["card_hash"] = contract["card_hash"]
    card["decision_contract"] = contract
    recommendation = card.get("recommendation")
    if isinstance(recommendation, Mapping):
        recommendation = dict(recommendation)
        recommendation["tier"] = "WATCH"
        recommendation["decision_tier"] = "WATCH"
        recommendation["reason_code"] = "SELECTIVITY_DAILY_CAP"
        card["recommendation"] = recommendation


def _football_day(card: Mapping[str, Any]) -> str:
    for field in ("football_day", "operational_date", "date"):
        value = card.get(field)
        if isinstance(value, str) and value:
            return value
    kickoff = _parse_time(card.get("kickoff_utc"))
    return kickoff.date().isoformat() if kickoff is not None else "unknown"


def _next_eval(card: Mapping[str, Any]) -> str | None:
    gate = card.get("analysis_gate")
    if isinstance(gate, Mapping) and gate.get("next_eval_at"):
        return str(gate["next_eval_at"])
    return None


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _number(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None
