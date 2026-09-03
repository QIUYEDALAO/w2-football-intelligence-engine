#!/usr/bin/env python3
"""Boundary-first loader for the preregistered TRAIN-2024 rest-level screening."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BURNED_PENALTYBLOG_SEASONS = frozenset(
    {"2012", "2013", "2014", "2015", "2016", "2012/13", "2013/14", "2014/15", "2015/16", "2016/17"}
)
DATE_FIELDS = ("target_kickoff", "kickoff_utc", "kickoff", "kickoff_at", "date")


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
        raise ValueError("REST_LEVEL_RECORD_LIST_REQUIRED")
    return rows


def _kickoff(row: dict[str, Any]) -> datetime:
    for field in DATE_FIELDS:
        if row.get(field) not in (None, ""):
            value = datetime.fromisoformat(str(row[field]).replace("Z", "+00:00"))
            return value if value.tzinfo else value.replace(tzinfo=UTC)
    raise ValueError("REST_LEVEL_RECORD_KICKOFF_REQUIRED")


def load_train_2024_records(
    path: Path,
    *,
    records_key: str | None = None,
    season_fields: tuple[str, ...] = ("season",),
) -> LoadedRecords:
    source = _read(path, records_key)
    exclusions: Counter[str] = Counter()
    loaded: list[dict[str, Any]] = []
    for row in source:
        if _kickoff(row).year != 2024:
            exclusions["YEAR_NOT_2024_FORBIDDEN"] += 1
        elif any(str(row.get(field, "")) in BURNED_PENALTYBLOG_SEASONS for field in season_fields):
            exclusions["BURNED_PENALTYBLOG_SEASON"] += 1
        else:
            loaded.append(row)
    wrong_year = sum(_kickoff(row).year != 2024 for row in loaded)
    burned = sum(
        any(str(row.get(field, "")) in BURNED_PENALTYBLOG_SEASONS for field in season_fields)
        for row in loaded
    )
    triggers = sum((wrong_year > 0, burned > 0))
    if wrong_year:
        raise AssertionError("NON_2024_RECORD_PRESENT_AFTER_LOAD")
    if burned:
        raise AssertionError("BURNED_PENALTYBLOG_SEASON_PRESENT_AFTER_LOAD")
    return LoadedRecords(
        records=tuple(loaded),
        audit={
            "source_count": len(source),
            "loaded_count": len(loaded),
            "loaded_year_counts": dict(
                sorted(Counter(_kickoff(row).year for row in loaded).items())
            ),
            "field_names": sorted({field for row in loaded for field in row}),
            "exclusions": dict(sorted(exclusions.items())),
            "assertions": {
                "year_not_2024": wrong_year,
                "burned_penaltyblog": burned,
                "trigger_count": triggers,
            },
        },
    )


def rest_input_schema(loaded: LoadedRecords) -> dict[str, Any]:
    """Return F3 structure only, never factor values or fixture rows."""
    factors = [row.get("factors") for row in loaded.records]
    f3_rows = [
        value.get("F3_REST_FITNESS")
        for value in factors
        if isinstance(value, dict)
    ]
    f3 = [value for value in f3_rows if isinstance(value, dict)]
    inputs = [value.get("inputs") for value in f3]
    input_rows = [value for value in inputs if isinstance(value, dict)]
    return {
        "factor_id": "F3_REST_FITNESS",
        "factor_count": len(f3),
        "factor_field_names": sorted({key for row in f3 for key in row}),
        "inputs_count": len(input_rows),
        "input_field_names": sorted({key for row in input_rows for key in row}),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect", type=Path, required=True)
    parser.add_argument("--records-key")
    parser.add_argument("--inspect-rest-inputs", action="store_true")
    args = parser.parse_args()
    loaded = load_train_2024_records(args.inspect, records_key=args.records_key)
    print(
        json.dumps(
            rest_input_schema(loaded) if args.inspect_rest_inputs else loaded.audit,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
