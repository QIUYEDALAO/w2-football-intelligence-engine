from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from w2.ingestion.market_timeline import parse_utc

TIMELINE_SOURCE = "market_timeline_snapshots"
UNVALIDATED = "UNVALIDATED"


def build_market_movement(timeline: dict[str, Any] | None) -> dict[str, Any]:
    snapshots = _market_snapshots(timeline, "ASIAN_HANDICAP")
    checkpoints = [str(item.get("checkpoint") or "") for item in snapshots]
    base = {
        "line_moved": False,
        "line_move_direction": "UNKNOWN",
        "line_move_magnitude": None,
        "water_drift_home": None,
        "water_drift_away": None,
        "pattern": "INSUFFICIENT",
        "timing": "UNKNOWN",
        "checkpoints_seen": checkpoints,
        "as_of_latest": None,
        "source": TIMELINE_SOURCE,
    }
    if not snapshots:
        return {"status": "INSUFFICIENT", **base}
    if len(snapshots) == 1:
        latest = snapshots[-1]
        return {
            "status": "PARTIAL",
            **base,
            "pattern": "INSUFFICIENT",
            "timing": _timing(str(latest.get("checkpoint") or "")),
            "as_of_latest": latest.get("as_of"),
        }

    opening = _opening_snapshot(snapshots)
    latest = _latest_snapshot(snapshots)
    opening_line = _number(opening.get("line"))
    latest_line = _number(latest.get("line"))
    if opening_line is None or latest_line is None:
        return {"status": "INSUFFICIENT", **base}
    magnitude = round(abs(latest_line - opening_line), 4)
    home_drift = _price_drift(opening.get("home_price"), latest.get("home_price"))
    away_drift = _price_drift(opening.get("away_price"), latest.get("away_price"))
    direction = _line_move_direction(opening_line, latest_line)
    pattern = _movement_pattern(snapshots)
    return {
        "status": "READY",
        "line_moved": magnitude >= 0.005,
        "line_move_direction": direction,
        "line_move_magnitude": magnitude,
        "water_drift_home": home_drift,
        "water_drift_away": away_drift,
        "pattern": pattern,
        "timing": _timing(str(latest.get("checkpoint") or "")),
        "checkpoints_seen": checkpoints,
        "as_of_latest": latest.get("as_of"),
        "source": TIMELINE_SOURCE,
    }


def build_market_timeline_reference(timeline: dict[str, Any] | None) -> dict[str, Any]:
    snapshots = _market_snapshots(timeline, "ASIAN_HANDICAP")
    base = {
        "source": TIMELINE_SOURCE,
        "label": "盘口时间线 · 参照 · 未验证",
        "verified": False,
        "direction_allowed": False,
        "open": None,
        "current": None,
        "as_of": None,
        "pattern": "INSUFFICIENT",
        "checkpoints_seen": [str(item.get("checkpoint") or "") for item in snapshots],
    }
    if not snapshots:
        return {"status": "INSUFFICIENT", **base}
    opening = _opening_snapshot(snapshots)
    latest = _latest_snapshot(snapshots)
    pattern = _movement_pattern(snapshots) if len(snapshots) > 1 else "INSUFFICIENT"
    return {
        "status": "READY" if len(snapshots) > 1 else "PARTIAL",
        **base,
        "open": _timeline_point(opening),
        "current": _timeline_point(latest),
        "as_of": latest.get("as_of"),
        "pattern": pattern,
    }


def build_market_divergence(
    *,
    pricing_shadow: dict[str, Any] | None,
    market_movement: dict[str, Any] | None,
    timeline: dict[str, Any] | None,
    home_team_name: str | None = None,
    away_team_name: str | None = None,
) -> dict[str, Any]:
    shadow = pricing_shadow if isinstance(pricing_shadow, dict) else {}
    fair_ah = _number(shadow.get("fair_ah"))
    snapshots = _market_snapshots(timeline, "ASIAN_HANDICAP")
    opening = _opening_snapshot(snapshots) if snapshots else None
    latest = _latest_snapshot(snapshots) if snapshots else None
    market_open = _number(opening.get("line")) if opening else None
    market_lock = _number(latest.get("line")) if latest else None
    leader = _factor_leader(shadow)
    base = {
        "factor_leader": leader,
        "factor_leader_team": _leader_team(leader, home_team_name, away_team_name),
        "model_family": _text(shadow.get("model_family")) or "FITTED_CALIBRATED",
        "model_family_fallback_reason": _optional_text(
            shadow.get("model_family_fallback_reason")
        ),
        "model_probabilities": _mapping_copy(shadow.get("model_probabilities")),
        "fair_ah": fair_ah,
        "market_open_ah": market_open,
        "market_lock_ah": market_lock,
        "open_divergence": None,
        "lock_divergence": None,
        "book_deeper_than_factors": False,
        "book_deeper_side": "UNKNOWN",
        "magnitude": None,
        "calibration_status": UNVALIDATED,
        "direction_allowed": False,
    }
    if fair_ah is None or market_open is None or market_lock is None:
        return {"status": "INSUFFICIENT", **base}
    open_divergence = round(fair_ah - market_open, 4)
    lock_divergence = round(fair_ah - market_lock, 4)
    deeper_side = _book_deeper_side(fair_ah, market_lock)
    movement_status = str((market_movement or {}).get("status") or "")
    return {
        "status": "READY" if movement_status == "READY" else "UNVALIDATED",
        **base,
        "open_divergence": open_divergence,
        "lock_divergence": lock_divergence,
        "book_deeper_than_factors": deeper_side != "UNKNOWN",
        "book_deeper_side": deeper_side,
        "magnitude": round(abs(lock_divergence), 4),
    }


def build_bookmaker_hypothesis(
    *,
    market_movement: dict[str, Any] | None,
    market_divergence: dict[str, Any] | None,
) -> dict[str, Any]:
    movement_status = str((market_movement or {}).get("status") or "INSUFFICIENT")
    divergence_status = str((market_divergence or {}).get("status") or "INSUFFICIENT")
    alternatives = [
        "伤停或阵容信息",
        "公众热度",
        "盘口保护",
        "我们的规则盘未校准",
    ]
    if movement_status != "READY" or divergence_status not in {"READY", "UNVALIDATED"}:
        return {
            "status": "PARTIAL" if movement_status == "PARTIAL" else "INSUFFICIENT",
            "label": "盘口假设 · 未验证",
            "hypothesis": "盘口轨迹不足，暂不形成假设；仅作观察，不给方向。",
            "alternative_explanations": alternatives,
            "sample_status": "观察中",
            "sample_count": 0,
            "verified": False,
            "direction_allowed": False,
        }
    pattern = str((market_movement or {}).get("pattern") or "STABLE")
    deeper_side = str((market_divergence or {}).get("book_deeper_side") or "UNKNOWN")
    if deeper_side == "HOME":
        relation = "市场主队侧盘口深于未校准规则盘"
    elif deeper_side == "AWAY":
        relation = "市场客队侧盘口深于未校准规则盘"
    else:
        relation = "市场与未校准规则盘差距有限"
    return {
        "status": "READY",
        "label": "盘口假设 · 未验证",
        "hypothesis": (
            f"{relation}，盘口轨迹为{_pattern_label(pattern)}；这是未验证假设，"
            "这可能来自伤停、公众热度、盘口保护，或我们的规则盘未校准；仅作观察，不给方向。"
        ),
        "alternative_explanations": alternatives,
        "sample_status": "观察中",
        "sample_count": 0,
        "verified": False,
        "direction_allowed": False,
    }


def _timeline_point(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "line": _number(snapshot.get("line")),
        "home_price": _number(snapshot.get("home_price")),
        "away_price": _number(snapshot.get("away_price")),
        "as_of": snapshot.get("as_of"),
        "checkpoint": snapshot.get("checkpoint"),
        "bookmaker_count": snapshot.get("bookmaker_count"),
    }


def _market_snapshots(timeline: dict[str, Any] | None, market: str) -> list[dict[str, Any]]:
    raw = timeline.get("snapshots") if isinstance(timeline, dict) else []
    if not isinstance(raw, list):
        raw = []
    snapshots = [item for item in raw if isinstance(item, dict) and item.get("market") == market]
    return sorted(snapshots, key=lambda item: _sort_key(item))


def _opening_snapshot(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    for item in snapshots:
        if item.get("checkpoint") == "opening":
            return item
    return snapshots[0]


def _latest_snapshot(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    lock = [item for item in snapshots if item.get("checkpoint") == "lock"]
    return lock[-1] if lock else snapshots[-1]


def _sort_key(item: dict[str, Any]) -> tuple[datetime, int]:
    parsed = parse_utc(item.get("as_of")) or datetime.min.replace(tzinfo=UTC)
    checkpoint = str(item.get("checkpoint") or "")
    order = {"opening": 0, "T-24h": 1, "T-12h": 2, "T-6h": 3, "T-3h": 4, "T-1h": 5, "lock": 6}
    return (parsed, order.get(checkpoint, 99))


def _number(value: Any) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _mapping_copy(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _price_drift(opening: Any, latest: Any) -> float | None:
    start = _number(opening)
    end = _number(latest)
    if start is None or end is None:
        return None
    return round(end - start, 4)


def _line_move_direction(opening: float, latest: float) -> str:
    diff = latest - opening
    if abs(diff) < 0.005:
        return "STABLE"
    return "HOME_DEEPENED" if diff < 0 else "AWAY_DEEPENED"


def _movement_pattern(snapshots: list[dict[str, Any]]) -> str:
    lines = [_number(item.get("line")) for item in snapshots]
    values = [item for item in lines if item is not None]
    if len(values) < 2:
        return "INSUFFICIENT"
    if max(values) - min(values) >= 0.5:
        return "JUMP_LINE"
    deltas = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    signed = [delta for delta in deltas if abs(delta) >= 0.005]
    if not signed:
        return "STABLE"
    if all(delta <= 0 for delta in signed) or all(delta >= 0 for delta in signed):
        return "ONE_WAY"
    return "EARLY_DROP_LATE_REBOUND"


def _timing(checkpoint: str) -> str:
    if checkpoint in {"opening", "T-24h", "T-12h"}:
        return "EARLY"
    if checkpoint in {"T-6h", "T-3h"}:
        return "MID"
    if checkpoint == "T-1h":
        return "LATE"
    if checkpoint == "lock":
        return "LOCK_ONLY"
    return "UNKNOWN"


def _factor_leader(shadow: dict[str, Any]) -> str:
    raw_team_score = shadow.get("team_score")
    team_score: dict[str, Any] = raw_team_score if isinstance(raw_team_score, dict) else {}
    home = _number(team_score.get("home"))
    away = _number(team_score.get("away"))
    if home is None or away is None:
        return "UNKNOWN"
    diff = home - away
    if abs(diff) < 0.05:
        return "NEUTRAL"
    return "HOME" if diff > 0 else "AWAY"


def _leader_team(leader: str, home: str | None, away: str | None) -> str | None:
    if leader == "HOME":
        return home
    if leader == "AWAY":
        return away
    if leader == "NEUTRAL":
        return "两队接近"
    return None


def _book_deeper_side(fair_ah: float, market_ah: float) -> str:
    if abs(market_ah) <= abs(fair_ah) + 0.005:
        return "UNKNOWN"
    if market_ah < fair_ah:
        return "HOME"
    if market_ah > fair_ah:
        return "AWAY"
    return "UNKNOWN"


def _pattern_label(pattern: str) -> str:
    return {
        "STABLE": "稳定",
        "ONE_WAY": "单边变化",
        "EARLY_DROP_LATE_REBOUND": "早段变化后回补",
        "JUMP_LINE": "跳线",
    }.get(pattern, "观察中")
