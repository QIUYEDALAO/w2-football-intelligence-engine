from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from w2.domain.enums import DecisionTier


@dataclass(frozen=True, kw_only=True)
class LegacyDecisionView:
    decision_tier: DecisionTier
    lock_eligible: bool
    recommendation_id: str | None
    legacy_formal: bool = False


def legacy_decision_view(
    card: Mapping[str, Any],
    market: Mapping[str, Any] | None = None,
) -> LegacyDecisionView:
    recommendation_id = _first_raw_text(
        _get(card, "recommendation_id"),
        _get(card, "id"),
        _get(market, "recommendation_id"),
        _get(market, "id"),
    )
    formal = _truthy(_get(card, "formal_recommendation")) or _truthy(
        _get(market, "formal_recommendation")
    )
    tier = legacy_decision_tier(card, market)
    return LegacyDecisionView(
        decision_tier=tier,
        lock_eligible=formal and recommendation_id is not None,
        recommendation_id=recommendation_id,
        legacy_formal=formal,
    )


def legacy_decision_tier(
    card: Mapping[str, Any],
    market: Mapping[str, Any] | None = None,
) -> DecisionTier:
    explicit_decision_tier = _first_text(
        _get(card, "decision_tier"),
        _get(market, "decision_tier"),
    )
    if explicit_decision_tier is not None:
        return DecisionTier(explicit_decision_tier)

    if _truthy(_get(card, "formal_recommendation")) or _truthy(
        _get(market, "formal_recommendation")
    ):
        return DecisionTier.ANALYSIS_PICK

    explicit = _first_text(
        _get(card, "tier"),
        _get(market, "tier"),
    )
    if explicit in {"FORMAL", "RECOMMEND"}:
        return DecisionTier.ANALYSIS_PICK
    if explicit in {"NO_RECOMMENDATION", "SKIP"}:
        return DecisionTier.SKIP

    decision = _first_text(
        _get(market, "analysis_decision"),
        _get(market, "decision"),
        _get(card, "analysis_decision"),
        _get(card, "decision"),
    )
    if decision in {"ANALYSIS_PICK", "PICK"}:
        return DecisionTier.ANALYSIS_PICK
    if decision == "WATCH":
        return DecisionTier.WATCH
    if decision in {"NO_RECOMMENDATION", "SKIP"}:
        return DecisionTier.SKIP

    if _truthy(_get(card, "candidate")) or _truthy(_get(market, "candidate")):
        return DecisionTier.WATCH
    return DecisionTier.SKIP


def _get(mapping: Mapping[str, Any] | None, key: str) -> Any:
    if mapping is None:
        return None
    return mapping.get(key)


def _first_text(*values: Any) -> str | None:
    text = _first_raw_text(*values)
    if text is None:
        return None
    return text.upper()


def _first_raw_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False
