from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def build_ah_direction_bias(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    eligible: list[dict[str, Any]] = []
    excluded = 0
    for record in records:
        shadow = record.get("analysis_gate_v2_shadow")
        if not isinstance(shadow, Mapping) or not _eligible_ah_outcome(record, shadow):
            if _is_ah_shadow_outcome(record):
                excluded += 1
            continue
        eligible.append(
            {
                **dict(record),
                "artifact": str(shadow.get("artifact_hash") or "UNKNOWN_ARTIFACT"),
                "league": str(
                    record.get("league")
                    or record.get("competition_name")
                    or record.get("competition_id")
                    or "UNKNOWN_LEAGUE"
                ),
                "handicap_role": _handicap_role(record),
                "line_bucket": _line_bucket(record.get("entry_line")),
            }
        )

    canonical = _latest_distinct_fixture(eligible)
    dimensions = {
        "selection": _counts(canonical, "selection"),
        "handicap_role": _counts(canonical, "handicap_role"),
        "line_bucket": _counts(canonical, "line_bucket"),
        "league": _counts(canonical, "league"),
        "artifact": _counts(canonical, "artifact"),
        "strategy_version": _counts(canonical, "strategy_version"),
    }
    return {
        "schema_version": "w2.ah_direction_bias.v1",
        "corrected_evidence_only": True,
        "distinct_fixture_only": True,
        "overall": _concentration(canonical),
        "dimensions": dimensions,
        "groups": {
            field: _group_reports(canonical, field)
            for field in ("league", "artifact", "strategy_version", "handicap_role", "line_bucket")
        },
        "excluded_record_count": excluded,
        "safety_only": True,
        "affects_model": False,
        "affects_decision": False,
    }


def _eligible_ah_outcome(record: Mapping[str, Any], shadow: object) -> bool:
    if not _is_ah_shadow_outcome(record) or not isinstance(shadow, Mapping):
        return False
    if (
        not record.get("canonical_performance_key")
        or not record.get("estimate_id")
        or not record.get("quote_id")
        or not record.get("source_capture_hash")
        or not record.get("strategy_version")
    ):
        return False
    if shadow.get("evidence_eligible") is not True or shadow.get("semantic_status") != "VERIFIED":
        return False
    return not (
        shadow.get("confirmation_required") is True
        and shadow.get("confirmation_status") != "CONFIRMED"
    )


def _is_ah_shadow_outcome(record: Mapping[str, Any]) -> bool:
    return (
        str(record.get("record_type") or "") == "outcome"
        and str(record.get("settled_side") or "") == "shadow_pick"
        and str(record.get("market") or "") == "ASIAN_HANDICAP"
        and str(record.get("selection") or "") in {"HOME_AH", "AWAY_AH"}
    )


def _latest_distinct_fixture(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=_event_time):
        fixture_id = str(row.get("fixture_id") or "")
        if fixture_id:
            latest[fixture_id] = dict(row)
    return sorted(latest.values(), key=_event_time)


def _concentration(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    directions = [str(row.get("selection") or "") for row in rows]
    sample_count = len(directions)
    latest_10 = directions[-10:]
    latest_8 = directions[-8:]
    dominant_10 = max(Counter(latest_10).values(), default=0)
    if sample_count < 8:
        status = "INSUFFICIENT_SAMPLE"
    elif sample_count >= 10 and dominant_10 >= 9:
        status = "BLOCKED"
    elif sample_count >= 10 and dominant_10 == 8:
        status = "WARNING"
    elif len(latest_8) == 8 and len(set(latest_8)) == 1:
        status = "EARLY_WARNING"
    else:
        status = "PASS"
    return {
        "status": status,
        "blocked": status == "BLOCKED",
        "distinct_fixture_count": sample_count,
        "home_ah_count": directions.count("HOME_AH"),
        "away_ah_count": directions.count("AWAY_AH"),
        "latest_8_dominant_count": max(Counter(latest_8).values(), default=0),
        "latest_10_dominant_count": dominant_10,
    }


def _group_reports(rows: Sequence[Mapping[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(field) or f"UNKNOWN_{field.upper()}")].append(row)
    return [{"key": key, **_concentration(items)} for key, items in sorted(grouped.items())]


def _counts(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(field) or "UNKNOWN") for row in rows).items()))


def _handicap_role(record: Mapping[str, Any]) -> str:
    line = _decimal(record.get("entry_line"))
    selection = str(record.get("selection") or "")
    if line is None or line == 0:
        return "ZERO_LINE"
    if selection == "HOME_AH":
        return "HOME_FAVORITE" if line < 0 else "HOME_UNDERDOG"
    return "AWAY_FAVORITE" if line < 0 else "AWAY_UNDERDOG"


def _line_bucket(value: object) -> str:
    line = _decimal(value)
    if line is None:
        return "UNKNOWN"
    absolute = abs(line)
    if absolute == 0:
        return "ZERO"
    fraction = absolute % 1
    if fraction in {Decimal("0.25"), Decimal("0.75")}:
        return "QUARTER_THREE_QUARTER"
    if fraction == Decimal("0.5"):
        return "HALF"
    if fraction == 0:
        return "INTEGER"
    return "UNKNOWN"


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _event_time(record: Mapping[str, Any]) -> datetime:
    for field in ("source_captured_at", "captured_at", "settled_at"):
        value = record.get(field)
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
