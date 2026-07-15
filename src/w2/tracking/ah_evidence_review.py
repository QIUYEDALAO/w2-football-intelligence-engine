from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any

from w2.tracking.ah_direction_bias import build_ah_direction_bias

SETTLEMENT_STATES = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")


def build_ah_evidence_review(
    records: Sequence[Mapping[str, Any]],
    *,
    clv_rows: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    eligible = [dict(record) for record in records if _eligible(record)]
    eligible = _latest_distinct(eligible, key_fields=("fixture_id", "strategy_version"))
    bias = build_ah_direction_bias(eligible)
    settled = len(eligible)
    concentration = bias["overall"]
    conclusion = _conclusion(settled, str(concentration.get("status") or ""))
    return {
        "schema_version": "w2.ah_evidence_review.v1",
        "status": "ACCUMULATING" if settled < 35 else "REVIEW_READY",
        "conclusion": conclusion,
        "corrected_settled_count": settled,
        "home_ah_count": sum(row.get("selection") == "HOME_AH" for row in eligible),
        "away_ah_count": sum(row.get("selection") == "AWAY_AH" for row in eligible),
        "review_35": _threshold(settled, 35, "REVIEW_ELIGIBLE"),
        "maturity_100": _threshold(settled, 100, "MATURE"),
        "wide_vs_strict": _group_metrics(eligible, clv_rows, "strategy_version"),
        "by_selection": _group_metrics(eligible, clv_rows, "selection"),
        "by_league": _group_metrics(eligible, clv_rows, "league"),
        "by_artifact": _group_metrics(eligible, clv_rows, "artifact"),
        "by_line_bucket": _group_metrics(eligible, clv_rows, "line_bucket"),
        "overall_metrics": _metrics(eligible, clv_rows),
        "concentration": concentration,
        "corrected_evidence_only": True,
        "automatic_direction_enable": False,
        "automatic_recommend_enable": False,
        "automatic_lock_enable": False,
        "provider_calls": 0,
        "db_writes": 0,
    }


def _eligible(record: Mapping[str, Any]) -> bool:
    shadow = record.get("analysis_gate_v2_shadow")
    return bool(
        record.get("record_type") == "outcome"
        and record.get("settled_side") == "shadow_pick"
        and record.get("market") == "ASIAN_HANDICAP"
        and record.get("selection") in {"HOME_AH", "AWAY_AH"}
        and record.get("canonical_performance_key")
        and record.get("estimate_id")
        and record.get("quote_id")
        and record.get("source_capture_hash")
        and record.get("strategy_version")
        and isinstance(shadow, Mapping)
        and shadow.get("evidence_eligible") is True
        and shadow.get("semantic_status") == "VERIFIED"
        and not (
            shadow.get("confirmation_required") is True
            and shadow.get("confirmation_status") != "CONFIRMED"
        )
    )


def _latest_distinct(
    rows: Sequence[Mapping[str, Any]], *, key_fields: tuple[str, ...]
) -> list[dict[str, Any]]:
    latest: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in sorted(rows, key=_time):
        key = tuple(str(row.get(field) or "") for field in key_fields)
        if all(key):
            latest[key] = {**dict(row), **_dimensions(row)}
    return sorted(latest.values(), key=_time)


def _group_metrics(
    rows: Sequence[Mapping[str, Any]],
    clv_rows: Sequence[Mapping[str, Any]],
    field: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(field) or f"UNKNOWN_{field.upper()}")].append(row)
    return [{"key": key, **_metrics(items, clv_rows)} for key, items in sorted(grouped.items())]


def _metrics(
    rows: Sequence[Mapping[str, Any]], clv_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    fixture_ids = {str(row.get("fixture_id") or "") for row in rows}
    profits = [value for row in rows if (value := _profit(row)) is not None]
    matching_clv = [row for row in clv_rows if str(row.get("fixture_id") or "") in fixture_ids]
    decimal_clv = [
        float(row["clv_decimal"])
        for row in matching_clv
        if isinstance(row.get("clv_decimal"), int | float)
    ]
    line_clv = [
        float(row["line_clv"])
        for row in matching_clv
        if isinstance(row.get("line_clv"), int | float)
    ]
    brier = [value for row in rows if (value := _five_state_brier(row)) is not None]
    return {
        "settled_count": len(rows),
        "roi": round(sum(profits) / len(profits), 6) if profits else None,
        "profit_units": round(sum(profits), 6),
        "median_clv_decimal": median(decimal_clv) if decimal_clv else None,
        "median_line_clv": median(line_clv) if line_clv else None,
        "five_state_brier": round(sum(brier) / len(brier), 8) if brier else None,
        "max_drawdown_units": _max_drawdown(profits),
        "full_loss_rate": (
            round(sum(row.get("settlement_outcome") == "LOSS" for row in rows) / len(rows), 6)
            if rows
            else None
        ),
    }


def _dimensions(row: Mapping[str, Any]) -> dict[str, str]:
    shadow = row.get("analysis_gate_v2_shadow")
    artifact = shadow.get("artifact_hash") if isinstance(shadow, Mapping) else None
    return {
        "league": str(
            row.get("league")
            or row.get("competition_name")
            or row.get("competition_id")
            or "UNKNOWN_LEAGUE"
        ),
        "artifact": str(artifact or "UNKNOWN_ARTIFACT"),
        "line_bucket": _line_bucket(row.get("entry_line")),
    }


def _threshold(count: int, target: int, reached: str) -> dict[str, Any]:
    return {
        "target": target,
        "current": count,
        "remaining": max(target - count, 0),
        "status": reached if count >= target else "ACCUMULATING",
    }


def _conclusion(count: int, concentration_status: str) -> str:
    if count < 35:
        return "ACCUMULATING"
    if concentration_status == "BLOCKED":
        return "RETUNE_AND_REREGISTER"
    return "KEEP_SHADOW_ONLY"


def _profit(row: Mapping[str, Any]) -> float | None:
    outcome = str(row.get("settlement_outcome") or "")
    try:
        price = float(str(row.get("entry_price")))
    except (TypeError, ValueError):
        return None
    return {
        "WIN": price - 1.0,
        "HALF_WIN": (price - 1.0) / 2.0,
        "PUSH": 0.0,
        "HALF_LOSS": -0.5,
        "LOSS": -1.0,
    }.get(outcome)


def _five_state_brier(row: Mapping[str, Any]) -> float | None:
    shadow = row.get("analysis_gate_v2_shadow")
    probabilities = shadow.get("settlement_probabilities") if isinstance(shadow, Mapping) else None
    outcome = str(row.get("settlement_outcome") or "")
    if not isinstance(probabilities, Mapping) or outcome not in SETTLEMENT_STATES:
        return None
    try:
        return sum(
            (float(probabilities.get(state, 0.0)) - (1.0 if outcome == state else 0.0)) ** 2
            for state in SETTLEMENT_STATES
        ) / len(SETTLEMENT_STATES)
    except (TypeError, ValueError):
        return None


def _max_drawdown(profits: Sequence[float]) -> float | None:
    if not profits:
        return None
    equity = peak = drawdown = 0.0
    for value in profits:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return round(drawdown, 6)


def _line_bucket(value: object) -> str:
    try:
        line = abs(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return "UNKNOWN"
    if line == 0:
        return "ZERO"
    fraction = line % 1
    if fraction in {Decimal("0.25"), Decimal("0.75")}:
        return "QUARTER_THREE_QUARTER"
    if fraction == Decimal("0.5"):
        return "HALF"
    if fraction == 0:
        return "INTEGER"
    return "UNKNOWN"


def _time(row: Mapping[str, Any]) -> datetime:
    for field in ("source_captured_at", "captured_at", "settled_at"):
        value = row.get(field)
        if not isinstance(value, str) or not value:
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return datetime.min.replace(tzinfo=UTC)
