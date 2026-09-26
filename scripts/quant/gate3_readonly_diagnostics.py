"""Pure Gate 3 attribution and drift summaries; no I/O or policy decisions."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from scripts.quant.run_gate3_shadow_diagnostics import settle_outcome

ATTRIBUTION_FIELDS = (
    "market", "selection", "competition_id", "tier", "edge_bucket", "odds_band",
    "line_movement_direction",
)
# 8 weeks: mirrors F5_COLDSTART_GRACE_SECONDS (the factor-gate cold-start grace
# period). A competition whose settled-history span is below this is still a
# "new league" in cold start; at or above it is a "mature league".
LEAGUE_MATURITY_MIN_HISTORY_DAYS = 56
ATTRIBUTION_MIN_N = 20
DRIFT_MIN_N = 20
DRIFT_WINDOWS_DAYS = (7, 30)


def _dated(row: Mapping[str, Any]) -> datetime:
    value = row["evaluated_at"].replace("Z", "+00:00")
    return datetime.fromisoformat(value)


def _scored(row: Mapping[str, Any]) -> tuple[float, float, float] | None:
    if row.get("home") in (None, "") or not row.get("distribution"):
        return None
    distribution = json.loads(row["distribution"])
    if not isinstance(distribution, Mapping):
        return None
    outcome = settle_outcome(
        row["market"], row["selection"], float(row["line"]),
        int(row["home"]), int(row["away"]),
    )
    predicted = float(distribution["WIN"]) + 0.5 * float(distribution["HALF_WIN"])
    realized = 1.0 if outcome == "WIN" else 0.5 if outcome == "HALF_WIN" else 0.0
    loss = -math.log(max(float(distribution[outcome]), 1e-15))
    return predicted - realized, loss, predicted


def _league_maturity_by_competition(rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Classify each competition as ``NEW_LEAGUE`` or ``MATURE_LEAGUE``.

    Maturity is the observed settled-history span (earliest -> latest
    ``evaluated_at``) for a competition within the cohort.  A span under
    ``LEAGUE_MATURITY_MIN_HISTORY_DAYS`` is still in cold start (new league);
    at or above it the league is mature.  Missing competitions stay "MISSING".
    """
    spans: dict[str, list[datetime]] = {}
    for row in rows:
        competition_id = str(row.get("competition_id") or "MISSING")
        try:
            at = _dated(row)
        except (KeyError, ValueError):
            continue
        if competition_id not in spans:
            spans[competition_id] = [at, at]
        else:
            spans[competition_id][0] = min(spans[competition_id][0], at)
            spans[competition_id][1] = max(spans[competition_id][1], at)
    return {
        competition_id: (
            "MATURE_LEAGUE"
            if (last - first).days >= LEAGUE_MATURITY_MIN_HISTORY_DAYS
            else "NEW_LEAGUE"
        )
        for competition_id, (first, last) in spans.items()
    }


def attribution(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Rank the independent one-dimensional slices, never N-way sparse cells."""
    maturity = _league_maturity_by_competition(rows)
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        for field in ATTRIBUTION_FIELDS:
            groups[(field, str(row.get(field) or "MISSING"))].append(row)
        groups[(
            "league_maturity",
            maturity.get(str(row.get("competition_id") or "MISSING"), "MISSING"),
        )].append(row)
    result = []
    for (field, value), group in groups.items():
        scored = [metric for row in group if (metric := _scored(row)) is not None]
        n = len(scored)
        result.append({
            "dimension": field,
            "value": value,
            "n": n,
            "fixture_count": len({row["fixture_id"] for row in group if row.get("fixture_id")}),
            "missing_rate": (len(group) - n) / len(group),
            "evidence": "SUFFICIENT" if n >= ATTRIBUTION_MIN_N else "证据不足",
            "bias": sum(item[0] for item in scored) / n if n else None,
            "logloss": sum(item[1] for item in scored) / n if n else None,
        })
    # Frozen order: larger sample first, then absolute bias, then loss, then
    # dimension/value as stable tie-breakers. Insufficient cells remain visible.
    return sorted(result, key=lambda item: (
        -item["n"],
        -abs(item["bias"] or 0.0),
        -(item["logloss"] or 0.0),
        item["dimension"], item["value"],
    ))


def attribution_top3(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return only adequately populated, actually observed slices."""
    return [
        item for item in attribution(rows)
        if item["evidence"] == "SUFFICIENT" and item["value"] != "MISSING"
    ][:3]


def drift_observation(
    rows: Sequence[Mapping[str, Any]], *, as_of: datetime
) -> list[dict[str, Any]]:
    """Describe fixed windows and a zero-reference CUSUM, without alerting."""
    result = []
    for days in DRIFT_WINDOWS_DAYS:
        start = as_of - timedelta(days=days)
        cohort = [row for row in rows if start <= _dated(row) <= as_of]
        scored = [metric for row in cohort if (metric := _scored(row)) is not None]
        n = len(scored)
        cusum = 0.0
        for bias, _, _ in scored:
            cusum += bias
        result.append({
            "window_days": days,
            "n": n,
            "fixture_count": len({row["fixture_id"] for row in cohort if row.get("fixture_id")}),
            "missing_rate": (len(cohort) - n) / len(cohort) if cohort else None,
            "evidence": "SUFFICIENT" if n >= DRIFT_MIN_N else "证据不足",
            "bias": cusum / n if n else None,
            "mean_logloss": sum(item[1] for item in scored) / n if n else None,
            "cusum_zero_reference": cusum,
            "market_delta": None,  # absent paired market distribution is never imputed
            "decision": "HUMAN_REVIEW_ONLY",
        })
    return result
