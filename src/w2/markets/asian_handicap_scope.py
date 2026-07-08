from __future__ import annotations

from typing import Any


def normalize_market_label(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("-", " ").split())


def is_full_time_asian_handicap_label(value: Any) -> bool:
    label = normalize_market_label(value)
    return label in {"asian handicap", "handicap", "ah"}


def is_full_time_asian_handicap_observation(
    row: dict[str, Any],
    *,
    allow_unlabeled: bool = True,
) -> bool:
    raw_label = row.get("raw_market_label")
    if raw_label is None or str(raw_label).strip() == "":
        return allow_unlabeled
    return is_full_time_asian_handicap_label(raw_label)


def is_full_time_totals_label(value: Any) -> bool:
    return normalize_market_label(value) in {"goals over/under", "total goals"}


def is_full_time_totals_observation(
    row: dict[str, Any],
    *,
    allow_unlabeled: bool = True,
) -> bool:
    raw_label = row.get("raw_market_label")
    if raw_label is None or str(raw_label).strip() == "":
        return allow_unlabeled
    return is_full_time_totals_label(raw_label)


def canonical_market_from_label(raw_label: Any) -> str:
    label = normalize_market_label(raw_label)
    if label in {"match winner", "1x2", "winner"}:
        return "ONE_X_TWO"
    if is_full_time_asian_handicap_label(label):
        return "ASIAN_HANDICAP"
    if "asian handicap" in label:
        return str(raw_label).upper().replace(" ", "_").replace("-", "_")
    if "goals over/under" in label or "over/under" in label or label == "total goals":
        return "TOTALS"
    if "both teams" in label or "btts" in label:
        return "BTTS"
    return str(raw_label).upper().replace(" ", "_").replace("-", "_")
