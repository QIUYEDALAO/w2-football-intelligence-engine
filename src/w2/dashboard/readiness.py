from __future__ import annotations

from collections import Counter
from enum import StrEnum
from typing import Any


class AnalysisReadinessStatus(StrEnum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class AnalysisBlocker(StrEnum):
    MISSING_ANALYSIS_CARD = "MISSING_ANALYSIS_CARD"
    ALL_MARKETS_SKIP = "ALL_MARKETS_SKIP"
    MISSING_MARKET_OBSERVATIONS = "MISSING_MARKET_OBSERVATIONS"
    MISSING_BOOKMAKER_QUOTES = "MISSING_BOOKMAKER_QUOTES"
    MISSING_ODDS_TIMELINE = "MISSING_ODDS_TIMELINE"
    MISSING_XG = "MISSING_XG"
    MISSING_SCORE_MATRIX = "MISSING_SCORE_MATRIX"
    MISSING_MODEL_PROBABILITIES = "MISSING_MODEL_PROBABILITIES"
    MISSING_MARKET_PROBABILITIES = "MISSING_MARKET_PROBABILITIES"
    AS_OF_BLOCKED = "AS_OF_BLOCKED"
    SCORE_MARKET_UNAVAILABLE = "SCORE_MARKET_UNAVAILABLE"
    ODDS_UNAVAILABLE = "ODDS_UNAVAILABLE"
    FIXTURE_NOT_UPCOMING = "FIXTURE_NOT_UPCOMING"
    UNSUPPORTED_MARKET = "UNSUPPORTED_MARKET"
    UNKNOWN_BLOCKER = "UNKNOWN_BLOCKER"


class AnalysisNextAction(StrEnum):
    READY_FOR_ANALYSIS = "READY_FOR_ANALYSIS"
    WAIT_MARKET_OBSERVATIONS = "WAIT_MARKET_OBSERVATIONS"
    WAIT_BOOKMAKER_QUOTES = "WAIT_BOOKMAKER_QUOTES"
    WAIT_ODDS_TIMELINE = "WAIT_ODDS_TIMELINE"
    WAIT_XG = "WAIT_XG"
    WAIT_SCORE_MODEL = "WAIT_SCORE_MODEL"
    WAIT_MODEL_PROBABILITIES = "WAIT_MODEL_PROBABILITIES"
    WAIT_MARKET_PROBABILITIES = "WAIT_MARKET_PROBABILITIES"
    WAIT_FIXTURE_STATUS = "WAIT_FIXTURE_STATUS"
    INVESTIGATE_DATA_PIPELINE = "INVESTIGATE_DATA_PIPELINE"


def build_analysis_readiness(
    card: dict[str, Any] | None,
    *,
    fixture_status: str | None,
    result: dict[str, Any] | None,
    scoreline_picks: list[dict[str, Any]],
) -> dict[str, Any]:
    blockers: list[AnalysisBlocker] = []
    available = _available_inputs(card)
    markets = _markets(card)
    source = str(card.get("source") or "") if isinstance(card, dict) else ""
    if card is None or "without_analysis" in source:
        blockers.append(AnalysisBlocker.MISSING_ANALYSIS_CARD)
    if markets and all(str(row.get("decision") or "").upper() == "SKIP" for row in markets):
        blockers.append(AnalysisBlocker.ALL_MARKETS_SKIP)
    if not available["market_observations"]:
        blockers.append(AnalysisBlocker.MISSING_MARKET_OBSERVATIONS)
    if not available["bookmakers"]:
        blockers.append(AnalysisBlocker.MISSING_BOOKMAKER_QUOTES)
    if not available["odds_snapshots"]:
        blockers.append(AnalysisBlocker.MISSING_ODDS_TIMELINE)
    if not available["xg"]:
        blockers.append(AnalysisBlocker.MISSING_XG)
    if not available["market_probabilities"]:
        blockers.append(AnalysisBlocker.MISSING_MARKET_PROBABILITIES)
    if not available["model_probabilities"]:
        blockers.append(AnalysisBlocker.MISSING_MODEL_PROBABILITIES)
    if not available["score_matrix"]:
        blockers.append(AnalysisBlocker.MISSING_SCORE_MATRIX)
    if not scoreline_picks and _score_market_unavailable(markets):
        blockers.append(AnalysisBlocker.SCORE_MARKET_UNAVAILABLE)
    if not _has_current_odds(card):
        blockers.append(AnalysisBlocker.ODDS_UNAVAILABLE)
    status = str(fixture_status or "").upper()
    if result is not None or status in {"FINISHED", "FT", "AET", "PEN"}:
        blockers.append(AnalysisBlocker.FIXTURE_NOT_UPCOMING)

    deduped = [item.value for item in dict.fromkeys(blockers)]
    readiness_status = _status(available, deduped)
    return {
        "status": readiness_status.value,
        "blockers": deduped,
        "available_inputs": available,
        "next_action": _next_action(deduped, readiness_status).value,
    }


def build_watch_recommendation(
    *,
    readiness: dict[str, Any],
    fixture_status: str | None,
) -> dict[str, Any] | None:
    if readiness.get("status") != AnalysisReadinessStatus.PARTIAL.value:
        return None
    if str(fixture_status or "").upper() == "FINISHED":
        return None
    blockers = [str(item) for item in readiness.get("blockers", [])]
    return {
        "tier": "WATCH",
        "market": "ANALYSIS_READINESS",
        "market_label_cn": "观察",
        "selection": None,
        "selection_label_cn": "等待信号收敛",
        "line": None,
        "odds": None,
        "hong_kong_odds": None,
        "model_probability": None,
        "fair_odds": None,
        "risk_adjusted_ev": None,
        "confidence": 0.0,
        "reasons": _watch_reasons(blockers),
        "risks": ["数据部分就绪但未形成分析倾向。"],
        "generated_at": None,
        "locked_before_kickoff": None,
        "is_live_line": None,
        "candidate": False,
        "formal_recommendation": False,
    }


def readiness_summary(cards: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for card in cards:
        readiness = card.get("analysis_readiness")
        if isinstance(readiness, dict):
            rows.append(readiness)
    statuses = Counter(str(row.get("status") or "UNKNOWN") for row in rows)
    blockers: Counter[str] = Counter()
    for row in rows:
        blockers.update(str(item) for item in row.get("blockers", []) if item)
    ready = statuses.get(AnalysisReadinessStatus.READY.value, 0)
    partial = statuses.get(AnalysisReadinessStatus.PARTIAL.value, 0)
    total = len(cards)
    return {
        "analysis_ready_count": ready,
        "analysis_partial_count": partial,
        "analysis_blocked_count": statuses.get(AnalysisReadinessStatus.BLOCKED.value, 0),
        "analysis_unknown_count": statuses.get(AnalysisReadinessStatus.UNKNOWN.value, 0),
        "analysis_actionable_count": ready + partial,
        "analysis_readiness_rate": ((ready + partial) / total) if total else None,
        "analysis_blocker_distribution": dict(sorted(blockers.items())),
    }


def _available_inputs(card: dict[str, Any] | None) -> dict[str, Any]:
    readiness = card.get("data_readiness", {}) if isinstance(card, dict) else {}
    if not isinstance(readiness, dict):
        readiness = {}
    markets = _markets(card)
    current_odds = card.get("current_odds", {}) if isinstance(card, dict) else {}
    line_movement = card.get("line_movement", {}) if isinstance(card, dict) else {}
    market_observations = _number(readiness.get("market_observations"))
    bookmakers = _number(readiness.get("bookmakers"))
    odds_snapshots = _number(readiness.get("odds_snapshots"))
    if not market_observations:
        market_observations = odds_snapshots
    score_market = next((row for row in markets if row.get("market") == "SCORE"), {})
    return {
        "market_observations": market_observations,
        "bookmakers": bookmakers,
        "odds_snapshots": odds_snapshots,
        "xg": _truthy(readiness.get("xg")),
        "score_matrix": bool(
            score_market.get("score_card")
            or score_market.get("reference_scores")
            or score_market.get("scores")
        ),
        "model_probabilities": bool(card and card.get("model_probabilities")),
        "market_probabilities": bool(card and card.get("market_probabilities")),
        "current_odds": bool(current_odds) if isinstance(current_odds, dict) else False,
        "line_movement": bool(line_movement) if isinstance(line_movement, dict) else False,
    }


def _markets(card: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(card, dict):
        return []
    markets = card.get("markets")
    if not isinstance(markets, list):
        return []
    return [row for row in markets if isinstance(row, dict)]


def _score_market_unavailable(markets: list[dict[str, Any]]) -> bool:
    score = next((row for row in markets if row.get("market") == "SCORE"), None)
    if score is None:
        return True
    reasons = [str(item) for item in score.get("reasons", []) if item]
    return any("SCORE" in item or "MATRIX" in item for item in reasons)


def _has_current_odds(card: dict[str, Any] | None) -> bool:
    if not isinstance(card, dict):
        return False
    current = card.get("current_odds")
    return isinstance(current, dict) and bool(current)


def _status(
    available: dict[str, Any],
    blockers: list[str],
) -> AnalysisReadinessStatus:
    if not blockers:
        return AnalysisReadinessStatus.READY
    partial_inputs = ("market_observations", "bookmakers", "odds_snapshots", "xg")
    if any(available.get(key) for key in partial_inputs):
        return AnalysisReadinessStatus.PARTIAL
    if blockers:
        return AnalysisReadinessStatus.BLOCKED
    return AnalysisReadinessStatus.UNKNOWN


def _next_action(
    blockers: list[str],
    status: AnalysisReadinessStatus,
) -> AnalysisNextAction:
    if status == AnalysisReadinessStatus.READY:
        return AnalysisNextAction.READY_FOR_ANALYSIS
    priority = [
        (AnalysisBlocker.FIXTURE_NOT_UPCOMING.value, AnalysisNextAction.WAIT_FIXTURE_STATUS),
        (
            AnalysisBlocker.MISSING_MARKET_OBSERVATIONS.value,
            AnalysisNextAction.WAIT_MARKET_OBSERVATIONS,
        ),
        (AnalysisBlocker.MISSING_BOOKMAKER_QUOTES.value, AnalysisNextAction.WAIT_BOOKMAKER_QUOTES),
        (AnalysisBlocker.MISSING_ODDS_TIMELINE.value, AnalysisNextAction.WAIT_ODDS_TIMELINE),
        (AnalysisBlocker.MISSING_XG.value, AnalysisNextAction.WAIT_XG),
        (AnalysisBlocker.MISSING_SCORE_MATRIX.value, AnalysisNextAction.WAIT_SCORE_MODEL),
        (AnalysisBlocker.SCORE_MARKET_UNAVAILABLE.value, AnalysisNextAction.WAIT_SCORE_MODEL),
        (
            AnalysisBlocker.MISSING_MODEL_PROBABILITIES.value,
            AnalysisNextAction.WAIT_MODEL_PROBABILITIES,
        ),
        (
            AnalysisBlocker.MISSING_MARKET_PROBABILITIES.value,
            AnalysisNextAction.WAIT_MARKET_PROBABILITIES,
        ),
    ]
    blocker_set = set(blockers)
    for blocker, action in priority:
        if blocker in blocker_set:
            return action
    return AnalysisNextAction.INVESTIGATE_DATA_PIPELINE


def _watch_reasons(blockers: list[str]) -> list[str]:
    if not blockers:
        return ["输入部分就绪，等待信号强度达到 ANALYSIS_PICK。"]
    return [f"仍有阻塞: {item}" for item in blockers[:3]]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value > 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "ready"}
    return False


def _number(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(float(value)))
        except ValueError:
            return 0
    return 0
