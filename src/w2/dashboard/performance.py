from __future__ import annotations

from typing import Any

from w2.dashboard.readiness import readiness_summary

OFFICIAL_TIERS = {"FORMAL", "CANDIDATE"}
ANALYSIS_TIER = "ANALYSIS_PICK"


def dashboard_performance(cards: list[dict[str, Any]]) -> dict[str, Any]:
    official = _validations_for_tiers(cards, OFFICIAL_TIERS)
    analysis = _validations_for_tiers(cards, {ANALYSIS_TIER})
    recommendations = [card for card in cards if card.get("recommendation")]
    confidence_values = [
        float(reco["confidence"])
        for card in recommendations
        if isinstance((reco := card.get("recommendation")), dict)
        and isinstance(reco.get("confidence"), int | float)
    ]
    official_summary = _summary(official)
    analysis_summary = _summary(analysis)
    return {
        **official_summary,
        **readiness_summary(cards),
        "market_hit_rate": official_summary["hit_rate"],
        "score_hit_rate": _score_hit_rate(cards, tier_filter=OFFICIAL_TIERS),
        "average_confidence": sum(confidence_values) / len(confidence_values)
        if confidence_values
        else None,
        "today_count": len(cards),
        "next36_count": len([card for card in cards if str(card.get("status")) != "FINISHED"]),
        "formal_count": len([card for card in cards if _tier(card) == "FORMAL"]),
        "candidate_count": len([card for card in cards if _tier(card) == "CANDIDATE"]),
        "analysis_pick_count": len([card for card in cards if _tier(card) == ANALYSIS_TIER]),
        "watch_count": len([card for card in cards if _tier(card) == "WATCH"]),
        "no_recommendation_count": len(
            [card for card in cards if _tier(card) == "NO_RECOMMENDATION"]
        ),
        "finished_count": len([card for card in cards if str(card.get("status")) == "FINISHED"]),
        "data_health_status": "READ_ONLY",
        "official": official_summary,
        "analysis_shadow": analysis_summary,
        "by_market": _by_market(cards),
        "score_exact": {
            "sample_size": len(
                [
                    card
                    for card in cards
                    if (validation := _validation(card)) is not None
                    and validation.get("score_exact_hit") is not None
                    and _tier(card) == ANALYSIS_TIER
                ]
            ),
            "hit_count": len(
                [
                    card
                    for card in cards
                    if (validation := _validation(card)) is not None
                    and validation.get("score_exact_hit") is True
                    and _tier(card) == ANALYSIS_TIER
                ]
            ),
            "hit_rate": _score_hit_rate(cards, tier_filter={ANALYSIS_TIER}),
        },
    }


def _tier(card: dict[str, Any]) -> str:
    reco = card.get("recommendation")
    if isinstance(reco, dict):
        return str(reco.get("tier") or "NO_RECOMMENDATION")
    return "NO_RECOMMENDATION"


def _validation(card: dict[str, Any]) -> dict[str, Any] | None:
    validation = card.get("validation")
    return validation if isinstance(validation, dict) else None


def _validations_for_tiers(
    cards: list[dict[str, Any]],
    tiers: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for card in cards:
        if _tier(card) not in tiers:
            continue
        validation = _validation(card)
        if validation is not None and _countable(validation):
            rows.append(validation)
    return rows


def _countable(validation: dict[str, Any]) -> bool:
    return str(validation.get("settlement")) in {"HIT", "MISS", "PUSH", "VOID"}


def _summary(validations: list[dict[str, Any]]) -> dict[str, Any]:
    hit = len([item for item in validations if item.get("settlement") == "HIT"])
    miss = len([item for item in validations if item.get("settlement") == "MISS"])
    push = len([item for item in validations if item.get("settlement") == "PUSH"])
    void = len([item for item in validations if item.get("settlement") == "VOID"])
    sample = hit + miss
    return {
        "sample_size": len(validations),
        "hit_count": hit,
        "miss_count": miss,
        "push_count": push,
        "void_count": void,
        "hit_rate": (hit / sample) if sample else None,
    }


def _score_hit_rate(cards: list[dict[str, Any]], *, tier_filter: set[str]) -> float | None:
    rows = [
        validation
        for card in cards
        if _tier(card) in tier_filter
        and (validation := _validation(card)) is not None
        and validation.get("score_exact_hit") is not None
    ]
    if not rows:
        return None
    return len([item for item in rows if item.get("score_exact_hit") is True]) / len(rows)


def _by_market(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for card in cards:
        if _tier(card) not in OFFICIAL_TIERS:
            continue
        reco = card.get("recommendation")
        validation = _validation(card)
        if not isinstance(reco, dict) or validation is None or not _countable(validation):
            continue
        market = str(reco.get("market") or "UNKNOWN")
        buckets.setdefault(market, []).append(validation)
    return [
        {
            "market": market,
            "sample_size": len(rows),
            "hit_rate": _summary(rows)["hit_rate"],
        }
        for market, rows in sorted(buckets.items())
    ]
