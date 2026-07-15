from __future__ import annotations

from collections.abc import Iterable

_PRIORITIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "FIXTURE_LIVE_OR_FINISHED",
        "FIXTURE_STATE",
        (
            "FIXTURE_LIVE_OR_FINISHED",
            "FIXTURE_NOT_UPCOMING",
            "FIXTURE_STATUS_LIVE",
            "FIXTURE_STATUS_FINISHED",
            "LIVE",
            "FINISHED",
        ),
    ),
    ("COVERAGE_NONE", "COVERAGE", ("COVERAGE_NONE", "UNSUPPORTED_COVERAGE")),
    (
        "MARKET_UNAVAILABLE",
        "MARKET",
        (
            "MARKET_UNAVAILABLE",
            "MARKET_NOT_READY",
            "MISSING_AH_MARKET",
            "AH_MARKET_UNAVAILABLE",
            "OU_MARKET_UNAVAILABLE",
        ),
    ),
    (
        "QUOTE_CAPTURE_TIME_MISSING",
        "QUOTE_CAPTURE",
        ("QUOTE_CAPTURE_TIME_MISSING",),
    ),
    ("DATA_STALE_ODDS", "ODDS_FRESHNESS", ("DATA_STALE_ODDS", "STALE_ODDS")),
    (
        "MARKET_QUOTE_INTEGRITY",
        "MARKET_INTEGRITY",
        ("MARKET_QUOTE_INVALID", "QUOTE_INTEGRITY", "MARKET_INTEGRITY"),
    ),
    (
        "FME_PROVENANCE_INCOMPLETE",
        "FME_PROVENANCE",
        (
            "FME_PROVENANCE_INCOMPLETE",
            "MODEL_FAIR_LINE_UNAVAILABLE",
            "DECISION_SOURCE_INCONSISTENT",
        ),
    ),
    (
        "ARTIFACT_UNAVAILABLE",
        "ARTIFACT",
        ("ARTIFACT_UNAVAILABLE", "R4_1_ARTIFACT_INVALID", "R4_1_ARTIFACT_UNAVAILABLE"),
    ),
    (
        "FEATURE_HISTORY_INSUFFICIENT",
        "FEATURE_HISTORY",
        (
            "FEATURE_HISTORY_INSUFFICIENT",
            "R4_1_FEATURE_HISTORY_INSUFFICIENT",
            "DATA_INSUFFICIENT",
            "MISSING_XG",
        ),
    ),
    (
        "STRICT_GATE_EDGE_OR_EVIDENCE",
        "STRICT_EDGE_EVIDENCE",
        (
            "STRICT_GATE",
            "NO_EDGE",
            "EDGE_INSUFFICIENT",
            "FORWARD_EVIDENCE_ACCUMULATING",
        ),
    ),
)


def prioritize_blockers(blockers: Iterable[object]) -> dict[str, object]:
    all_blockers = _unique_blockers(blockers)
    upper = [item.upper() for item in all_blockers]
    for canonical, layer, aliases in _PRIORITIES:
        if any(any(_matches_alias(blocker, alias) for alias in aliases) for blocker in upper):
            return {
                "primary_blocker": canonical,
                "primary_blocker_layer": layer,
                "all_blockers": all_blockers,
            }
    return {
        "primary_blocker": all_blockers[0] if all_blockers else None,
        "primary_blocker_layer": "OTHER" if all_blockers else None,
        "all_blockers": all_blockers,
    }


def _unique_blockers(blockers: Iterable[object]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for blocker in blockers:
        text = str(blocker or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
    return values


def _matches_alias(blocker: str, alias: str) -> bool:
    return blocker == alias or blocker.startswith(f"{alias}:")
