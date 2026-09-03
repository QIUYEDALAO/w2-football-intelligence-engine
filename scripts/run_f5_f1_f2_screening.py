#!/usr/bin/env python3
"""Boundary-first loader for the preregistered burned-2026 screening."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
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
MINIMUM_USABLE_FIXTURES = 300


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


def _fixture_id(value: Any) -> str:
    text = str(value)
    return text if ":" in text else f"api_football:{text}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _has_baseline(row: dict[str, Any]) -> bool:
    try:
        values = [
            float(row[field])
            for field in (
                "home_xg_for",
                "home_xg_against",
                "away_xg_for",
                "away_xg_against",
            )
        ]
    except (KeyError, TypeError, ValueError):
        return False
    return all(value >= 0 for value in values)


def _factor_value(row: dict[str, Any], factor_id: str) -> float | None:
    factors = row.get("factors")
    factor = factors.get(factor_id) if isinstance(factors, dict) else None
    if isinstance(factor, dict) and not factor.get("missing"):
        value = factor.get("raw_value")
        if value is not None:
            return float(value)
    contributions = row.get("feature_contributions")
    if isinstance(contributions, list):
        for item in contributions:
            if (
                isinstance(item, dict)
                and item.get("id") == factor_id
                and item.get("score") is not None
            ):
                return float(item["score"])
    value = row.get(factor_id)
    return float(value) if value is not None else None


def _screening_counts(
    history: LoadedRecords,
    snapshots: LoadedRecords,
    capture_inputs: LoadedRecords,
) -> tuple[dict[str, Any], dict[str, dict[str, int]]]:
    sides: dict[str, set[str]] = defaultdict(set)
    for row in history.records:
        sides[_fixture_id(row["fixture_id"])].add(str(row["team_side"]))
    completed = {fixture_id for fixture_id, values in sides.items() if values == {"HOME", "AWAY"}}
    snapshot_by_fixture = {
        _fixture_id(row["target_fixture_id"]): row for row in snapshots.records
    }
    baseline_by_fixture = {
        _fixture_id(row["fixture_id"]): row
        for row in capture_inputs.records
        if _has_baseline(row)
    }
    values = {factor_id: [] for factor_id in FACTOR_IDS}
    exclusions = {factor_id: Counter() for factor_id in FACTOR_IDS}
    for fixture_id in completed:
        baseline = baseline_by_fixture.get(fixture_id)
        if baseline is None:
            for factor_id in FACTOR_IDS:
                exclusions[factor_id]["MISSING_BASELINE_CAPTURE"] += 1
            continue
        snapshot = snapshot_by_fixture.get(fixture_id)
        if snapshot is None:
            for factor_id in FACTOR_IDS:
                exclusions[factor_id]["MISSING_FACTOR_SNAPSHOT"] += 1
            continue
        for factor_id in FACTOR_IDS:
            value = _factor_value(snapshot, factor_id)
            if value is None:
                exclusions[factor_id]["MISSING_FACTOR"] += 1
            else:
                values[factor_id].append(value)
    results = {
        factor_id: {
            "factor_id": factor_id,
            "axis": "DELTA",
            "fixture_count": len(factor_values),
            "cluster_count": len(factor_values),
            "distribution": None,
            "brier_improvement": None,
            "one_sided_95_lower": None,
            "p_value": None,
            "bonferroni_alpha": 0.016667,
            "verdict": "FAIL_NOT_MEASURABLE",
            "stopped_before_fit": len(factor_values) < MINIMUM_USABLE_FIXTURES,
        }
        for factor_id, factor_values in values.items()
    }
    return results, {
        factor_id: dict(sorted(counts.items())) for factor_id, counts in exclusions.items()
    }


def run_screening(args: argparse.Namespace) -> dict[str, Any]:
    history = load_screening_records(
        args.history, records_key="history_rows", require_finished=True
    )
    snapshots = load_screening_records(args.snapshots)
    capture_inputs = load_screening_records(args.capture_inputs)
    fixture_identities = load_screening_records(args.fixture_identities)
    results, exclusions = _screening_counts(history, snapshots, capture_inputs)
    return {
        "schema_version": "w2.f5_f1_f2_screening.results.v1",
        "task_id": "W2-F5-F1-F2-SCREENING",
        "preregistration_commit": "4652a5f8",
        "screening_only": True,
        "clean_confirmation_set_consumed": False,
        "minimum_usable_fixtures": MINIMUM_USABLE_FIXTURES,
        "load_audits": {
            "history": history.audit,
            "snapshots": snapshots.audit,
            "capture_inputs": capture_inputs.audit,
            "fixture_identities": fixture_identities.audit,
        },
        "source_sha256": {
            "history": _sha256(args.history),
            "snapshots": _sha256(args.snapshots),
            "capture_inputs": _sha256(args.capture_inputs),
            "fixture_identities": _sha256(args.fixture_identities),
        },
        "exclusions": exclusions,
        "results": [results[factor_id] for factor_id in FACTOR_IDS],
        "fit_count": 0,
        "bootstrap_replicates_executed": 0,
        "provider_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect", type=Path)
    parser.add_argument("--records-key")
    parser.add_argument("--require-finished", action="store_true")
    parser.add_argument("--inspect-factor-schema", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--history", type=Path)
    parser.add_argument("--snapshots", type=Path)
    parser.add_argument("--capture-inputs", type=Path)
    parser.add_argument("--fixture-identities", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.run:
        required = (
            args.history,
            args.snapshots,
            args.capture_inputs,
            args.fixture_identities,
            args.output,
        )
        if not all(required):
            raise SystemExit(
                "--run requires --history, --snapshots, --capture-inputs, "
                "--fixture-identities, and --output"
            )
        args.output.write_text(
            json.dumps(run_screening(args), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    if args.inspect is None:
        raise SystemExit("Use --inspect or --run; direct data probing is disabled.")
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
