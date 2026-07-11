from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from typing import Any

SAMPLE_TARGET = 200
SETTLED_OUTCOMES = {
    "HIT": "hit",
    "WIN": "hit",
    "HALF_WIN": "hit",
    "MISS": "miss",
    "LOSS": "miss",
    "HALF_LOSS": "miss",
    "PUSH": "push",
    "VOID": "void",
}


def forward_ledger_performance(
    runtime_root: Path,
    *,
    sample_target: int = SAMPLE_TARGET,
) -> dict[str, Any]:
    root = runtime_root / "forward_outcome_ledger"
    records = list(load_forward_ledger_records(root))
    outcome_counts = _outcome_counts(records, side="pick")
    outcome_shadow_counts = _outcome_counts(records, side="shadow_pick")
    clv_rows = _clv_rows(records, key_fn=_clv_key)
    shadow_capture_records = _expanded_shadow_capture_records(records)
    clv_shadow_rows = _clv_rows(shadow_capture_records, key_fn=_clv_shadow_key)
    clv_values = _clv_values(clv_rows)
    clv_shadow_values = _clv_values(clv_shadow_rows)
    fixture_ids = {
        _text(record.get("fixture_id")) for record in records if _text(record.get("fixture_id"))
    }
    double_snapshot_fixture_ids = {
        _text(row.get("fixture_id"))
        for row in clv_shadow_rows
        if _text(row.get("fixture_id"))
    }
    return {
        "schema_version": "w2.forward_ledger_performance.v1",
        "source": "runtime/forward_outcome_ledger",
        "sample_target": sample_target,
        "record_count": len(records),
        "fixture_count": len(fixture_ids),
        "double_snapshot_fixture_count": len(double_snapshot_fixture_ids),
        "settled_sample_count": sum(outcome_counts.values()),
        "hit_count": outcome_counts["hit"],
        "miss_count": outcome_counts["miss"],
        "push_count": outcome_counts["push"],
        "void_count": outcome_counts["void"],
        "hit_rate": _hit_rate(outcome_counts),
        "outcomes": _outcome_summary(outcome_counts),
        "outcomes_shadow": _outcome_summary(outcome_shadow_counts),
        "accumulation_label": _accumulation_label(len(fixture_ids), sample_target),
        "clv": _clv_summary(
            clv_values,
            clv_rows,
            method="entry_minus_closing_decimal_odds_same_line",
        ),
        "clv_shadow": _clv_summary(
            clv_shadow_values,
            clv_shadow_rows,
            method="shadow_pick_entry_minus_closing_same_line; not_displayed_direction",
        ),
        "accrual_note": (
            "shadow CLV 为积累期证据流,用于未来按预注册规则放行 direction_allowed;非展示战绩"
        ),
        "by_league": _league_rows(
            records,
            clv_rows,
            clv_shadow_rows,
            outcome_counts_by_league(records, side="pick"),
            outcome_counts_by_league(records, side="shadow_pick"),
        ),
        "by_league_market": _league_market_rows(
            shadow_capture_records,
            clv_shadow_rows,
            records,
        ),
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
        "mock_data": False,
    }


def load_forward_ledger_records(root: Path) -> Iterable[dict[str, Any]]:
    if not root.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    records.append(payload)
    return records


def _outcome_counts(
    records: Sequence[Mapping[str, Any]],
    *,
    side: str,
) -> defaultdict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    for record in records:
        if _outcome_side(record) != side:
            continue
        bucket = SETTLED_OUTCOMES.get(_outcome(record))
        if bucket:
            counts[bucket] += 1
    return counts


def outcome_counts_by_league(
    records: Sequence[Mapping[str, Any]],
    *,
    side: str = "pick",
) -> dict[str, defaultdict[str, int]]:
    by_league: dict[str, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))
    for record in records:
        if _outcome_side(record) != side:
            continue
        bucket = SETTLED_OUTCOMES.get(_outcome(record))
        if bucket:
            by_league[_league_key(record)][bucket] += 1
    return by_league


def _outcome_summary(counts: Mapping[str, int]) -> dict[str, Any]:
    return {
        "settled_sample_count": sum(counts.values()),
        "hit_count": int(counts.get("hit", 0)),
        "miss_count": int(counts.get("miss", 0)),
        "push_count": int(counts.get("push", 0)),
        "void_count": int(counts.get("void", 0)),
        "hit_rate": _hit_rate(counts),
    }


def _clv_values(rows: Sequence[Mapping[str, Any]]) -> list[float]:
    return [
        float(row["clv_decimal"]) for row in rows if isinstance(row.get("clv_decimal"), int | float)
    ]


def _clv_summary(
    values: Sequence[float],
    rows: Sequence[Mapping[str, Any]],
    *,
    method: str,
) -> dict[str, Any]:
    window_values = [
        float(row["clv_decimal"])
        for row in rows
        if row.get("entry_window_met") is True and isinstance(row.get("clv_decimal"), int | float)
    ]
    return {
        "sample_count": len(values),
        "median_decimal": median(values) if values else None,
        "valid_pair_count": len([row for row in rows if row.get("excluded_reason") is None]),
        "entry_window_met_count": len([row for row in rows if row.get("entry_window_met") is True]),
        "median_decimal_window_met": median(window_values) if window_values else None,
        "positive_count": len([value for value in values if value > 0]),
        "negative_count": len([value for value in values if value < 0]),
        "push_count": len([value for value in values if value == 0]),
        "line_changed_count": len([row for row in rows if row.get("line_changed") is True]),
        "line_clv_sample_count": len(
            [row for row in rows if isinstance(row.get("line_clv"), int | float)]
        ),
        "median_line_clv": _median_field(rows, "line_clv"),
        "excluded_no_prematch_closing": len(
            [row for row in rows if row.get("excluded_reason") == "NO_PREMATCH_CLOSING"]
        ),
        "entry_line_mismatch_count": len(
            [row for row in rows if row.get("entry_line_mismatch") is True]
        ),
        "method": method,
    }


def _clv_rows(
    records: Sequence[Mapping[str, Any]],
    *,
    key_fn: Any,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        key = key_fn(record)
        if key is not None:
            grouped[key].append(record)

    rows: list[dict[str, Any]] = []
    for (fixture_id, market, selection), items in grouped.items():
        ordered = sorted(
            items,
            key=lambda item: (
                _parse_time(item.get("captured_at")) or datetime.min.replace(tzinfo=UTC)
            ),
        )
        if len(ordered) < 2:
            continue
        entry = _entry_record(ordered)
        closing = _closing_record(ordered)
        if closing is None:
            entry_quote = _quote(entry, market, selection)
            entry_line = entry_quote[0] if entry_quote is not None else None
            rows.append(
                {
                    "fixture_id": fixture_id,
                    "league": _league_key(entry),
                    "market": market,
                    "selection": selection,
                    "entry_captured_at": _text(entry.get("captured_at")),
                    "closing_captured_at": None,
                    "entry_window_met": _entry_window_met(entry),
                    "line_changed": False,
                    "entry_line_mismatch": _entry_line_mismatch(entry, entry_line),
                    "excluded_reason": "NO_PREMATCH_CLOSING",
                    "clv_decimal": None,
                }
            )
            continue
        entry_quote = _quote(entry, market, selection)
        closing_quote = _quote(closing, market, selection)
        if entry_quote is None or closing_quote is None:
            continue
        entry_line, entry_price = entry_quote
        closing_line, closing_price = closing_quote
        line_changed = entry_line != closing_line
        rows.append(
            {
                "fixture_id": fixture_id,
                "league": _league_key(entry),
                "market": market,
                "selection": selection,
                "entry_captured_at": _text(entry.get("captured_at")),
                "closing_captured_at": _text(closing.get("captured_at")),
                "entry_window_met": _entry_window_met(entry),
                "line_changed": line_changed,
                "entry_line_mismatch": _entry_line_mismatch(entry, entry_line),
                "clv_decimal": None if line_changed else round(entry_price - closing_price, 6),
                "line_clv": _directional_line_clv(
                    market=market,
                    selection=selection,
                    entry_line=entry_line,
                    closing_line=closing_line,
                )
                if line_changed
                else None,
            }
        )
    return rows


def _entry_record(records: list[Mapping[str, Any]]) -> Mapping[str, Any]:
    for record in records:
        kickoff = _parse_time(record.get("kickoff_utc"))
        captured = _parse_time(record.get("captured_at"))
        if kickoff and captured and (kickoff - captured).total_seconds() >= 23 * 3600:
            return record
    return records[0]


def _closing_record(records: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    before_kickoff = [
        record
        for record in records
        if (kickoff := _parse_time(record.get("kickoff_utc")))
        and (captured := _parse_time(record.get("captured_at")))
        and captured <= kickoff
    ]
    return before_kickoff[-1] if before_kickoff else None


def _entry_window_met(record: Mapping[str, Any]) -> bool:
    kickoff = _parse_time(record.get("kickoff_utc"))
    captured = _parse_time(record.get("captured_at"))
    return bool(kickoff and captured and (kickoff - captured).total_seconds() >= 23 * 3600)


def _entry_line_mismatch(record: Mapping[str, Any], entry_line: str | None) -> bool:
    shadow_pick = record.get("shadow_pick")
    if not isinstance(shadow_pick, Mapping) or entry_line is None:
        return False
    market_line = shadow_pick.get("market_line_at_capture")
    if market_line is None:
        return False
    entry_decimal = _decimal_value(entry_line)
    market_decimal = _decimal_value(market_line)
    if entry_decimal is not None and market_decimal is not None:
        return entry_decimal != market_decimal
    return _text(entry_line) != _text(market_line)


def _clv_key(record: Mapping[str, Any]) -> tuple[str, str, str] | None:
    if _record_type(record) != "capture":
        return None
    fixture_id = _text(record.get("fixture_id"))
    pick = record.get("pick")
    if not fixture_id or not isinstance(pick, Mapping):
        return None
    market = _text(pick.get("market"))
    selection = _text(pick.get("selection"))
    if market not in {"ASIAN_HANDICAP", "TOTALS"} or not selection:
        return None
    return (fixture_id, market, selection)


def _clv_shadow_key(record: Mapping[str, Any]) -> tuple[str, str, str] | None:
    if _record_type(record) != "capture":
        return None
    fixture_id = _text(record.get("fixture_id"))
    shadow_pick = record.get("shadow_pick")
    if not fixture_id or not isinstance(shadow_pick, Mapping):
        return None
    market = _text(shadow_pick.get("market"))
    selection = _text(shadow_pick.get("selection"))
    if market not in {"ASIAN_HANDICAP", "TOTALS"} or not selection:
        return None
    return (fixture_id, market, selection)


def _expanded_shadow_capture_records(
    records: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    expanded: list[Mapping[str, Any]] = []
    for record in records:
        if _record_type(record) != "capture":
            continue
        shadow_picks = record.get("shadow_picks")
        if isinstance(shadow_picks, Sequence) and not isinstance(
            shadow_picks, str | bytes | bytearray
        ):
            for item in shadow_picks:
                if isinstance(item, Mapping):
                    expanded.append({**record, "shadow_pick": dict(item)})
            continue
        if isinstance(record.get("shadow_pick"), Mapping):
            expanded.append(record)
    return expanded


def _quote(record: Mapping[str, Any], market: str, selection: str) -> tuple[str, float] | None:
    odds = record.get("current_odds")
    if not isinstance(odds, Mapping):
        return None
    if market == "ASIAN_HANDICAP":
        ah = odds.get("ah")
        if not isinstance(ah, Mapping):
            return None
        if selection == "HOME_AH":
            return _line_price(ah.get("home_line"), ah.get("home_price"))
        if selection == "AWAY_AH":
            return _line_price(ah.get("away_line"), ah.get("away_price"))
    if market == "TOTALS":
        ou = odds.get("ou")
        if not isinstance(ou, Mapping):
            return None
        if selection == "OVER":
            return _line_price(ou.get("line"), ou.get("over_price"))
        if selection == "UNDER":
            return _line_price(ou.get("line"), ou.get("under_price"))
    return None


def _line_price(line: Any, price: Any) -> tuple[str, float] | None:
    value = _number(price)
    if value is None:
        return None
    return (_text(line), value)


def _league_rows(
    records: Sequence[Mapping[str, Any]],
    clv_rows: Sequence[Mapping[str, Any]],
    clv_shadow_rows: Sequence[Mapping[str, Any]],
    league_outcomes: dict[str, defaultdict[str, int]],
    league_shadow_outcomes: dict[str, defaultdict[str, int]],
) -> list[dict[str, Any]]:
    league_records: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        league_records[_league_key(record)].append(record)
    clv_by_league: dict[str, list[float]] = defaultdict(list)
    for row in clv_rows:
        value = row.get("clv_decimal")
        if isinstance(value, int | float):
            clv_by_league[_text(row.get("league"))].append(value)
    clv_shadow_by_league: dict[str, list[float]] = defaultdict(list)
    for row in clv_shadow_rows:
        value = row.get("clv_decimal")
        if isinstance(value, int | float):
            clv_shadow_by_league[_text(row.get("league"))].append(value)
    rows: list[dict[str, Any]] = []
    for league, items in league_records.items():
        outcomes = league_outcomes.get(league, defaultdict(int))
        shadow_outcomes = league_shadow_outcomes.get(league, defaultdict(int))
        values = clv_by_league.get(league, [])
        shadow_values = clv_shadow_by_league.get(league, [])
        double_snapshot_fixture_ids = {
            _text(row.get("fixture_id"))
            for row in clv_shadow_rows
            if _text(row.get("league")) == league and _text(row.get("fixture_id"))
        }
        fixture_ids = {
            _text(item.get("fixture_id")) for item in items if _text(item.get("fixture_id"))
        }
        rows.append(
            {
                "league": league,
                "record_count": len(items),
                "fixture_count": len(fixture_ids),
                "double_snapshot_fixture_count": len(double_snapshot_fixture_ids),
                "settled_sample_count": sum(outcomes.values()),
                "hit_count": outcomes["hit"],
                "miss_count": outcomes["miss"],
                "push_count": outcomes["push"],
                "void_count": outcomes["void"],
                "hit_rate": _hit_rate(outcomes),
                "shadow_settled_sample_count": sum(shadow_outcomes.values()),
                "shadow_hit_count": shadow_outcomes["hit"],
                "shadow_miss_count": shadow_outcomes["miss"],
                "shadow_push_count": shadow_outcomes["push"],
                "shadow_void_count": shadow_outcomes["void"],
                "shadow_hit_rate": _hit_rate(shadow_outcomes),
                "clv_sample_count": len(values),
                "clv_median_decimal": median(values) if values else None,
                "clv_shadow_sample_count": len(shadow_values),
                "clv_shadow_median_decimal": median(shadow_values) if shadow_values else None,
            }
        )
    return sorted(rows, key=lambda row: (-int(row["record_count"]), str(row["league"])))


def _league_market_rows(
    shadow_captures: Sequence[Mapping[str, Any]],
    clv_rows: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    fixtures: dict[tuple[str, str], set[str]] = defaultdict(set)
    for record in shadow_captures:
        shadow_pick = record.get("shadow_pick")
        if not isinstance(shadow_pick, Mapping):
            continue
        key = (_league_key(record), _text(shadow_pick.get("market")))
        fixture_id = _text(record.get("fixture_id"))
        if key[1] and fixture_id:
            fixtures[key].add(fixture_id)
    rows_by_key: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in clv_rows:
        rows_by_key[(_text(row.get("league")), _text(row.get("market")))].append(row)
    outcomes_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for record in records:
        if _record_type(record) != "outcome" or _outcome_side(record) != "shadow_pick":
            continue
        key = (_league_key(record), _text(record.get("market")))
        fixture_id = _text(record.get("fixture_id"))
        if key[1] and fixture_id and _outcome(record) != "VOID":
            outcomes_by_key[key].add(fixture_id)
    output: list[dict[str, Any]] = []
    for key in sorted(set(fixtures) | set(rows_by_key)):
        league, market = key
        market_rows = rows_by_key.get(key, [])
        same_line = [
            float(row["clv_decimal"])
            for row in market_rows
            if isinstance(row.get("clv_decimal"), int | float)
        ]
        valid_pairs = [row for row in market_rows if row.get("excluded_reason") is None]
        fixture_count = len(fixtures.get(key, set()))
        entry_window_count = len(
            [row for row in valid_pairs if row.get("entry_window_met") is True]
        )
        outcome_count = len(outcomes_by_key.get(key, set()))
        output.append(
            {
                "league": league,
                "market": market,
                "fixture_count": fixture_count,
                "valid_closing_pair_count": len(valid_pairs),
                "closing_pair_coverage_rate": _ratio(len(valid_pairs), fixture_count),
                "same_line_decimal_clv_sample_count": len(same_line),
                "median_decimal_clv": median(same_line) if same_line else None,
                "line_clv_sample_count": len(
                    [row for row in market_rows if isinstance(row.get("line_clv"), int | float)]
                ),
                "median_line_clv": _median_field(market_rows, "line_clv"),
                "entry_window_met_count": entry_window_count,
                "entry_window_met_rate": _ratio(entry_window_count, len(valid_pairs)),
                "outcome_count": outcome_count,
                "outcome_coverage_rate": _ratio(outcome_count, len(valid_pairs)),
            }
        )
    return output


def _directional_line_clv(
    *,
    market: str,
    selection: str,
    entry_line: str,
    closing_line: str,
) -> float | None:
    entry = _number(entry_line)
    closing = _number(closing_line)
    if entry is None or closing is None:
        return None
    if market == "TOTALS" and selection == "OVER":
        return round(closing - entry, 6)
    return round(entry - closing, 6)


def _median_field(rows: Sequence[Mapping[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if isinstance(row.get(field), int | float)]
    return median(values) if values else None


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _league_key(record: Mapping[str, Any]) -> str:
    competition_id = _text(record.get("competition_id"))
    if competition_id:
        return competition_id
    name = _text(record.get("competition_name"))
    normalized = name.lower()
    for marker, canonical in (
        ("allsvenskan", "allsvenskan"),
        ("eliteserien", "eliteserien"),
        ("super league", "chinese_super_league"),
        ("world cup", "world_cup_2026"),
    ):
        if marker in normalized:
            return canonical
    return name or "UNKNOWN"


def _outcome(record: Mapping[str, Any]) -> str:
    for key in ("settlement_outcome", "outcome", "result_outcome"):
        value = _text(record.get(key)).upper()
        if value:
            return value
    validation = record.get("validation")
    if isinstance(validation, Mapping):
        return _text(validation.get("settlement")).upper()
    settlement = record.get("settlement")
    if isinstance(settlement, Mapping):
        return _text(settlement.get("outcome") or settlement.get("settlement")).upper()
    return ""


def _outcome_side(record: Mapping[str, Any]) -> str:
    side = _text(record.get("settled_side"))
    if side in {"pick", "shadow_pick"}:
        return side
    return ""


def _record_type(record: Mapping[str, Any]) -> str:
    return _text(record.get("record_type") or "capture")


def _hit_rate(counts: Mapping[str, int]) -> float | None:
    denominator = int(counts.get("hit", 0)) + int(counts.get("miss", 0))
    if not denominator:
        return None
    return int(counts.get("hit", 0)) / denominator


def _accumulation_label(record_count: int, sample_target: int) -> str:
    if record_count < sample_target:
        return f"积累中 {record_count}/{sample_target}"
    return f"已达样本底线 {record_count}/{sample_target}"


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
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
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _decimal_value(value: Any) -> Decimal | None:
    text = _text(value)
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
