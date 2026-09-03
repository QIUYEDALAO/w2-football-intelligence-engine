#!/usr/bin/env python3
"""Boundary-first loader for the preregistered burned-2026 screening."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2026, 8, 23, tzinfo=UTC)
BURNED_PENALTYBLOG_SEASONS = frozenset(
    {"2012", "2013", "2014", "2015", "2016", "2012/13", "2013/14", "2014/15", "2015/16", "2016/17"}
)
FINISHED = frozenset({"FT", "AET", "PEN", "FINISHED", "MATCH_FINISHED"})
DATE_FIELDS = ("target_kickoff", "kickoff_utc", "kickoff", "kickoff_at", "date")
STATUS_FIELDS = ("fixture_status", "status", "match_status")
FACTOR_IDS = (
    "F5_RECENT_AH_COVER",
    "F1_MARKET_MOVEMENT",
    "F2_BOOKMAKER_INTENT",
)


@dataclass(frozen=True)
class LoadedRecords:
    records: tuple[dict[str, Any], ...]
    audit: dict[str, Any]


def _read(path: Path, records_key: str | None) -> list[dict[str, Any]]:
    if path.suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    rows = payload[records_key] if records_key else payload
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("SCREENING_RECORD_LIST_REQUIRED")
    return rows


def _kickoff(row: dict[str, Any]) -> datetime:
    for field in DATE_FIELDS:
        if row.get(field) not in (None, ""):
            value = datetime.fromisoformat(str(row[field]).replace("Z", "+00:00"))
            return value if value.tzinfo else value.replace(tzinfo=UTC)
    raise ValueError("SCREENING_RECORD_KICKOFF_REQUIRED")


def _finished(row: dict[str, Any]) -> bool:
    values = [str(row.get(field) or "").upper() for field in STATUS_FIELDS]
    return any(value in FINISHED for value in values)


def load_screening_records(
    path: Path,
    *,
    records_key: str | None = None,
    require_finished: bool = False,
    season_fields: tuple[str, ...] = ("season",),
) -> LoadedRecords:
    source = _read(path, records_key)
    exclusions: Counter[str] = Counter()
    loaded: list[dict[str, Any]] = []
    for row in source:
        kickoff = _kickoff(row)
        if kickoff < START:
            exclusions["BEFORE_SCREENING_WINDOW"] += 1
        elif kickoff >= END:
            exclusions["AFTER_2026_08_22_FORBIDDEN"] += 1
        elif require_finished and not _finished(row):
            exclusions["NOT_FINISHED"] += 1
        elif any(str(row.get(field, "")) in BURNED_PENALTYBLOG_SEASONS for field in season_fields):
            exclusions["BURNED_PENALTYBLOG_SEASON"] += 1
        else:
            loaded.append(row)
    future = sum(_kickoff(row) >= END for row in loaded)
    old_year = sum(_kickoff(row).year in {2024, 2025} for row in loaded)
    burned = sum(
        any(str(row.get(field, "")) in BURNED_PENALTYBLOG_SEASONS for field in season_fields)
        for row in loaded
    )
    triggers = sum((future > 0, old_year > 0, burned > 0))
    if future:
        raise AssertionError("POST_2026_08_22_PRESENT_AFTER_LOAD")
    if old_year:
        raise AssertionError("YEAR_2024_2025_PRESENT_AFTER_LOAD")
    if burned:
        raise AssertionError("BURNED_PENALTYBLOG_SEASON_PRESENT_AFTER_LOAD")
    return LoadedRecords(
        records=tuple(loaded),
        audit={
            "source_count": len(source),
            "loaded_count": len(loaded),
            "loaded_month_counts": dict(
                sorted(Counter(_kickoff(row).strftime("%Y-%m") for row in loaded).items())
            ),
            "field_names": sorted({field for row in loaded for field in row}),
            "exclusions": dict(sorted(exclusions.items())),
            "assertions": {
                "kickoff_after_2026_08_22": future,
                "year_2024_or_2025": old_year,
                "burned_penaltyblog": burned,
                "trigger_count": triggers,
            },
        },
    )


def factor_presence_schema(loaded: LoadedRecords) -> dict[str, Any]:
    """Count factor structures without returning values or fixture rows."""
    nested: Counter[str] = Counter()
    contributions: Counter[str] = Counter()
    top_level: Counter[str] = Counter()
    for row in loaded.records:
        factors = row.get("factors")
        if isinstance(factors, dict):
            nested.update(str(key) for key in factors)
        items = row.get("feature_contributions")
        if isinstance(items, list):
            contributions.update(
                str(item["id"])
                for item in items
                if isinstance(item, dict) and item.get("id")
            )
        top_level.update(factor_id for factor_id in FACTOR_IDS if factor_id in row)
    return {
        "loaded_count": len(loaded.records),
        "nested_factor_counts": dict(sorted(nested.items())),
        "contribution_id_counts": dict(sorted(contributions.items())),
        "top_level_factor_counts": dict(sorted(top_level.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect", type=Path, required=True)
    parser.add_argument("--records-key")
    parser.add_argument("--require-finished", action="store_true")
    parser.add_argument("--inspect-factor-schema", action="store_true")
    args = parser.parse_args()
    loaded = load_screening_records(
        args.inspect,
        records_key=args.records_key,
        require_finished=args.require_finished,
    )
    print(
        json.dumps(
            factor_presence_schema(loaded) if args.inspect_factor_schema else loaded.audit,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
