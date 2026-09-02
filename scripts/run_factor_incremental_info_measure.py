#!/usr/bin/env python3
"""Offline, preregistered four-factor information measurement."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any

from w2.models.independent import normalized_score_matrix
from w2.strategy.calibration import LambdaCalibrationParams, calibrate_lambdas

ALLOWED_YEARS = frozenset({2024, 2025})
BURNED_PENALTYBLOG_SEASONS = frozenset(
    {"2012", "2013", "2014", "2015", "2016", "2012/13", "2013/14", "2014/15", "2015/16", "2016/17"}
)
FACTOR_IDS = (
    "F3_REST_FITNESS",
    "F5_RECENT_AH_COVER",
    "F1_MARKET_MOVEMENT",
    "F2_BOOKMAKER_INTENT",
)
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 20_260_903
BONFERRONI_ALPHA = 0.0125


@dataclass(frozen=True)
class LoadAudit:
    source_year_counts: dict[int, int]
    loaded_year_counts: dict[int, int]
    holdout_2026_count: int
    future_2027_count: int
    burned_penaltyblog_count: int
    assertion_trigger_count: int
    field_names: tuple[str, ...]


@dataclass(frozen=True)
class LoadedRecords:
    records: tuple[dict[str, Any], ...]
    audit: LoadAudit


@dataclass(frozen=True)
class MeasurementRow:
    fixture_id: str
    year: int
    actual: str
    baseline_home: float
    baseline_away: float
    factor_value: float


def _parse_year(record: dict[str, Any], date_fields: tuple[str, ...]) -> int:
    for field in date_fields:
        value = record.get(field)
        if value not in (None, ""):
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).year
    raise ValueError("MEASUREMENT_RECORD_KICKOFF_REQUIRED")


def _read_records(path: Path, records_key: str | None) -> list[dict[str, Any]]:
    if path.suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    records = payload[records_key] if records_key else payload
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError("MEASUREMENT_RECORD_LIST_REQUIRED")
    return records


def load_measurement_records(
    path: Path,
    *,
    records_key: str | None = None,
    date_fields: tuple[str, ...] = (
        "target_kickoff",
        "kickoff",
        "kickoff_utc",
        "kickoff_at",
        "date",
    ),
    season_fields: tuple[str, ...] = ("season",),
) -> LoadedRecords:
    """Load target rows through the frozen 2024/2025 information boundary."""
    source = _read_records(path, records_key)
    source_years = Counter(_parse_year(row, date_fields) for row in source)
    loaded = tuple(row for row in source if _parse_year(row, date_fields) in ALLOWED_YEARS)
    loaded_years = Counter(_parse_year(row, date_fields) for row in loaded)
    holdout_2026 = sum(year == 2026 for year in loaded_years.elements())
    future_2027 = sum(year == 2027 for year in loaded_years.elements())
    burned = sum(
        any(str(row.get(field, "")) in BURNED_PENALTYBLOG_SEASONS for field in season_fields)
        for row in loaded
    )
    assertion_trigger_count = sum((holdout_2026 > 0, future_2027 > 0, burned > 0))
    if holdout_2026:
        raise AssertionError("HOLDOUT_2026_PRESENT_AFTER_LOAD")
    if future_2027:
        raise AssertionError("FUTURE_2027_PRESENT_AFTER_LOAD")
    if burned:
        raise AssertionError("BURNED_PENALTYBLOG_SEASON_PRESENT_AFTER_LOAD")
    fields = tuple(sorted({field for row in loaded for field in row}))
    return LoadedRecords(
        records=loaded,
        audit=LoadAudit(
            source_year_counts=dict(sorted(source_years.items())),
            loaded_year_counts=dict(sorted(loaded_years.items())),
            holdout_2026_count=holdout_2026,
            future_2027_count=future_2027,
            burned_penaltyblog_count=burned,
            assertion_trigger_count=assertion_trigger_count,
            field_names=fields,
        ),
    )


def schema_and_counts(loaded: LoadedRecords) -> dict[str, Any]:
    """Return structure only; never print or return row contents."""
    return {
        "field_names": list(loaded.audit.field_names),
        "source_year_counts": loaded.audit.source_year_counts,
        "loaded_year_counts": loaded.audit.loaded_year_counts,
        "assertions": {
            "year_2026": loaded.audit.holdout_2026_count,
            "year_2027": loaded.audit.future_2027_count,
            "burned_penaltyblog": loaded.audit.burned_penaltyblog_count,
            "trigger_count": loaded.audit.assertion_trigger_count,
        },
    }


def nested_schema(loaded: LoadedRecords, field: str) -> dict[str, Any]:
    """Describe requested nested dictionaries without returning values."""
    items: list[dict[str, Any]] = []
    for row in loaded.records:
        value = row.get(field)
        if isinstance(value, dict):
            items.append(value)
        elif isinstance(value, list):
            items.extend(item for item in value if isinstance(item, dict))
    return {
        "field": field,
        "item_count": len(items),
        "field_names": sorted({key for item in items for key in item}),
    }


def container_schema(path: Path) -> dict[str, Any]:
    """Describe a JSON container without returning any values or row contents."""
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        return {
            "container": "dict",
            "fields": {
                key: {
                    "type": type(value).__name__,
                    "length": len(value) if hasattr(value, "__len__") else None,
                }
                for key, value in sorted(payload.items())
            },
        }
    return {"container": type(payload).__name__, "length": len(payload)}


def _validate_rows(rows: Iterable[dict[str, Any]]) -> None:
    for row in rows:
        if _parse_year(row, ("kickoff",)) not in ALLOWED_YEARS:
            raise AssertionError("NON_MEASUREMENT_YEAR_ESCAPED_LOADER")


def _probabilities(home_mu: float, away_mu: float) -> dict[str, float]:
    matrix = normalized_score_matrix(home_mu, away_mu, max_goals=10)
    return {
        "HOME": sum(p for (home, away), p in matrix.items() if home > away),
        "DRAW": sum(p for (home, away), p in matrix.items() if home == away),
        "AWAY": sum(p for (home, away), p in matrix.items() if home < away),
    }


def _candidate_probabilities(
    row: MeasurementRow,
    standardized: float,
    beta: float,
    axis: str,
) -> dict[str, float]:
    params = LambdaCalibrationParams()
    total = row.baseline_home + row.baseline_away
    delta = row.baseline_home - row.baseline_away
    if axis == "DELTA":
        delta += beta * standardized
    else:
        total += beta * standardized
    home = min(max((total + delta) / 2, params.minimum_lambda), params.maximum_lambda)
    away = min(max((total - delta) / 2, params.minimum_lambda), params.maximum_lambda)
    return _probabilities(home, away)


def _log_loss(rows: list[MeasurementRow], mean: float, std: float, beta: float, axis: str) -> float:
    return fmean(
        -math.log(
            max(
                _candidate_probabilities(row, (row.factor_value - mean) / std, beta, axis)[
                    row.actual
                ],
                1e-15,
            )
        )
        for row in rows
    )


def _fit(rows: list[MeasurementRow], axis: str) -> tuple[float, float, float]:
    mean = fmean(row.factor_value for row in rows)
    std = pstdev(row.factor_value for row in rows)
    if std == 0:
        raise ValueError("FAIL_NEAR_CONSTANT")
    left, right = -2.0, 2.0
    ratio = (math.sqrt(5) - 1) / 2
    c = right - ratio * (right - left)
    d = left + ratio * (right - left)
    fc = _log_loss(rows, mean, std, c, axis)
    fd = _log_loss(rows, mean, std, d, axis)
    for _ in range(96):
        if fc <= fd:
            right, d, fd = d, c, fc
            c = right - ratio * (right - left)
            fc = _log_loss(rows, mean, std, c, axis)
        else:
            left, c, fc = c, d, fd
            d = left + ratio * (right - left)
            fd = _log_loss(rows, mean, std, d, axis)
    return (left + right) / 2, mean, std


def _brier(probabilities: dict[str, float], actual: str) -> float:
    return sum(
        (probability - float(label == actual)) ** 2
        for label, probability in probabilities.items()
    )


def _evaluate(
    rows: list[MeasurementRow], mean: float, std: float, beta: float, axis: str
) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
    baseline = [_probabilities(row.baseline_home, row.baseline_away) for row in rows]
    candidate = [
        _candidate_probabilities(row, (row.factor_value - mean) / std, beta, axis) for row in rows
    ]
    return baseline, candidate


def _pooled_oof_brier(rows: list[MeasurementRow], axis: str) -> float:
    scored: list[float] = []
    for fold in range(5):
        fitting = [row for row in rows if _fold(row.fixture_id) != fold]
        held_out = [row for row in rows if _fold(row.fixture_id) == fold]
        beta, mean, std = _fit(fitting, axis)
        _, candidate = _evaluate(held_out, mean, std, beta, axis)
        scored.extend(
            _brier(probability, row.actual)
            for row, probability in zip(held_out, candidate, strict=True)
        )
    return fmean(scored)


def _fold(fixture_id: str) -> int:
    return int(hashlib.sha256(fixture_id.encode()).hexdigest()[:8], 16) % 5


def _secondary_metrics(
    probabilities: list[dict[str, float]], rows: list[MeasurementRow]
) -> dict[str, Any]:
    labels = ("HOME", "DRAW", "AWAY")
    log_loss = fmean(
        -math.log(max(probability[row.actual], 1e-15))
        for probability, row in zip(probabilities, rows, strict=True)
    )
    ece: dict[str, float] = {}
    reliability = 0.0
    resolution = 0.0
    for label in labels:
        base_rate = fmean(float(row.actual == label) for row in rows)
        label_ece = 0.0
        for bin_index in range(10):
            members = [
                index
                for index, probability in enumerate(probabilities)
                if min(int(probability[label] * 10), 9) == bin_index
            ]
            if not members:
                continue
            forecast = fmean(probabilities[index][label] for index in members)
            observed = fmean(float(rows[index].actual == label) for index in members)
            weight = len(members) / len(rows)
            label_ece += weight * abs(forecast - observed)
            reliability += weight * (forecast - observed) ** 2
            resolution += weight * (observed - base_rate) ** 2
        ece[label] = label_ece
    return {
        "brier": fmean(
            _brier(probability, row.actual)
            for probability, row in zip(probabilities, rows, strict=True)
        ),
        "log_loss": log_loss,
        "ece_by_class": ece,
        "ece_mean": fmean(ece.values()),
        "reliability_sum": reliability,
        "resolution_sum": resolution,
    }


def _bootstrap(improvements: list[float]) -> tuple[float, float]:
    rng = random.Random(BOOTSTRAP_SEED)  # noqa: S311 - frozen statistical PRNG
    size = len(improvements)
    draws = sorted(
        fmean(rng.choices(improvements, k=size)) for _ in range(BOOTSTRAP_REPLICATES)
    )
    lower = draws[int(0.05 * BOOTSTRAP_REPLICATES)]
    p_value = (1 + sum(value <= 0 for value in draws)) / (BOOTSTRAP_REPLICATES + 1)
    return lower, p_value


def _distribution(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    def percentile(q: float) -> float:
        return ordered[round((len(ordered) - 1) * q)]
    return {
        "count": len(values),
        "min": ordered[0],
        "p25": percentile(0.25),
        "median": percentile(0.5),
        "p75": percentile(0.75),
        "max": ordered[-1],
        "mean": fmean(values),
        "population_std": pstdev(values),
        "zero_count": sum(value == 0 for value in values),
    }


def _fixture_id(value: Any) -> str:
    text = str(value)
    return text if ":" in text else f"api_football:{text}"


def _measurement_rows(
    history: LoadedRecords,
    snapshots: LoadedRecords,
    xg: LoadedRecords,
) -> tuple[dict[str, list[MeasurementRow]], dict[str, Any]]:
    _validate_rows({**row, "kickoff": row["kickoff_utc"]} for row in history.records)
    _validate_rows({**row, "kickoff": row["target_kickoff"]} for row in snapshots.records)
    _validate_rows({**row, "kickoff": row["kickoff_at"]} for row in xg.records)
    outcome_sides: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in history.records:
        outcome_sides[_fixture_id(row["fixture_id"])][str(row["team_side"])] = row
    snapshot_by_fixture = {_fixture_id(row["target_fixture_id"]): row for row in snapshots.records}
    xg_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in xg.records:
        xg_by_team[str(row["team_id"])].append(row)
    output = {factor_id: [] for factor_id in FACTOR_IDS}
    exclusions = {factor_id: Counter() for factor_id in FACTOR_IDS}
    for fixture_id, sides in outcome_sides.items():
        snapshot = snapshot_by_fixture.get(fixture_id)
        if snapshot is None or set(sides) != {"HOME", "AWAY"}:
            continue
        home, away = sides["HOME"], sides["AWAY"]
        kickoff = datetime.fromisoformat(str(home["kickoff_utc"]).replace("Z", "+00:00"))
        target_raw_id = str(home["provider_fixture_id"])
        rolling: dict[str, tuple[float, float]] = {}
        for side, team_id in (("HOME", str(home["team_id"])), ("AWAY", str(away["team_id"]))):
            prior = sorted(
                (
                    row
                    for row in xg_by_team[team_id]
                    if datetime.fromisoformat(
                        str(row["kickoff_at"]).replace("Z", "+00:00")
                    )
                    < kickoff
                    and str(row["fixture_id"]) != target_raw_id
                ),
                key=lambda row: str(row["kickoff_at"]),
            )[-5:]
            if len(prior) >= 3:
                rolling[side] = (
                    fmean(float(row["xg_for"]) for row in prior),
                    fmean(float(row["xg_against"]) for row in prior),
                )
        if set(rolling) != {"HOME", "AWAY"}:
            for factor_id in FACTOR_IDS:
                exclusions[factor_id]["MISSING_PIT_XG"] += 1
            continue
        baseline = calibrate_lambdas(
            home_xg_for=rolling["HOME"][0],
            home_xg_against=rolling["HOME"][1],
            away_xg_for=rolling["AWAY"][0],
            away_xg_against=rolling["AWAY"][1],
            home_elo=None,
            away_elo=None,
            home_squad_value_eur=None,
            away_squad_value_eur=None,
        )
        actual = (
            "HOME"
            if int(home["goals_for"]) > int(away["goals_for"])
            else "DRAW"
            if int(home["goals_for"]) == int(away["goals_for"])
            else "AWAY"
        )
        year = kickoff.year
        factors = snapshot.get("factors")
        f3 = factors.get("F3_REST_FITNESS") if isinstance(factors, dict) else None
        if isinstance(f3, dict) and not f3.get("missing") and f3.get("raw_value") is not None:
            output["F3_REST_FITNESS"].append(
                MeasurementRow(
                    fixture_id=fixture_id,
                    year=year,
                    actual=actual,
                    baseline_home=baseline.lambda_home,
                    baseline_away=baseline.lambda_away,
                    factor_value=max(min(float(f3["raw_value"]) / 4, 1.0), -1.0),
                )
            )
        else:
            exclusions["F3_REST_FITNESS"]["MISSING_FACTOR"] += 1
        for factor_id in FACTOR_IDS[1:]:
            factor = factors.get(factor_id) if isinstance(factors, dict) else None
            if isinstance(factor, dict) and factor.get("raw_value") is not None:
                output[factor_id].append(
                    MeasurementRow(
                        fixture_id=fixture_id,
                        year=year,
                        actual=actual,
                        baseline_home=baseline.lambda_home,
                        baseline_away=baseline.lambda_away,
                        factor_value=float(factor["raw_value"]),
                    )
                )
            else:
                exclusions[factor_id]["MISSING_FACTOR"] += 1
    return output, {factor_id: dict(counts) for factor_id, counts in exclusions.items()}


def _measure_factor(factor_id: str, rows: list[MeasurementRow]) -> dict[str, Any]:
    train = [row for row in rows if row.year == 2024]
    validation = [row for row in rows if row.year == 2025]
    base = {
        "factor_id": factor_id,
        "train_fixture_count": len(train),
        "train_cluster_count": len({row.fixture_id for row in train}),
        "validation_fixture_count": len(validation),
        "validation_cluster_count": len({row.fixture_id for row in validation}),
        "train_distribution": _distribution([row.factor_value for row in train]) if train else None,
        "validation_distribution": _distribution([row.factor_value for row in validation])
        if validation
        else None,
    }
    if len(train) < 300 or len(validation) < 100:
        return {**base, "verdict": "FAIL_NOT_MEASURABLE"}
    if pstdev(row.factor_value for row in train) == 0:
        return {**base, "verdict": "FAIL_NEAR_CONSTANT"}
    axes = ("DELTA", "TOTAL") if factor_id == "F3_REST_FITNESS" else ("DELTA",)
    oof = {axis: _pooled_oof_brier(train, axis) for axis in axes}
    axis = "TOTAL" if len(axes) == 2 and oof["TOTAL"] <= oof["DELTA"] else "DELTA"
    beta, mean, std = _fit(train, axis)
    baseline, candidate = _evaluate(validation, mean, std, beta, axis)
    baseline_metrics = _secondary_metrics(baseline, validation)
    candidate_metrics = _secondary_metrics(candidate, validation)
    improvements = [
        _brier(base_probability, row.actual) - _brier(candidate_probability, row.actual)
        for row, base_probability, candidate_probability in zip(
            validation, baseline, candidate, strict=True
        )
    ]
    point = fmean(improvements)
    lower, p_value = _bootstrap(improvements)
    passed = point > 0 and lower > 0 and p_value < BONFERRONI_ALPHA
    return {
        **base,
        "selected_axis": axis,
        "train_oof_candidate_brier_by_axis": oof,
        "beta": beta,
        "beta_at_search_boundary": abs(beta) >= 1.999999,
        "train_standardization_mean": mean,
        "train_standardization_population_std": std,
        "baseline_metrics": baseline_metrics,
        "candidate_metrics": candidate_metrics,
        "brier_improvement": point,
        "one_sided_95_lower": lower,
        "p_value": p_value,
        "bonferroni_alpha": BONFERRONI_ALPHA,
        "verdict": "PASS" if passed else "FAIL",
    }


def run_measurement(args: argparse.Namespace) -> dict[str, Any]:
    history = load_measurement_records(args.history, records_key="history_rows")
    snapshots = load_measurement_records(args.snapshots)
    xg = load_measurement_records(args.xg)
    factor_rows, exclusions = _measurement_rows(history, snapshots, xg)
    results = [_measure_factor(factor_id, factor_rows[factor_id]) for factor_id in FACTOR_IDS]
    return {
        "schema_version": "w2.factor_incremental_info_measure.results.v1",
        "task_id": "W2-FACTOR-INCREMENTAL-INFO-MEASURE",
        "preregistration_commit": "00eb9556",
        "family_size": 4,
        "bootstrap": {
            "unit": "fixture",
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": BOOTSTRAP_SEED,
            "known_limitation": (
                "Same-team same-season residual correlation is not clustered; "
                "intervals may be slightly narrow."
            ),
        },
        "load_audits": {
            "history": schema_and_counts(history),
            "snapshots": schema_and_counts(snapshots),
            "xg": schema_and_counts(xg),
        },
        "exclusions": exclusions,
        "results": results,
        "provider_calls": 0,
    }


def result_summary(path: Path) -> dict[str, Any]:
    """Return aggregate measurement results; the artifact contains no fixture rows."""
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return {
        "load_audits": payload["load_audits"],
        "results": [
            {
                key: row.get(key)
                for key in (
                    "factor_id",
                    "verdict",
                    "train_fixture_count",
                    "validation_fixture_count",
                    "selected_axis",
                    "train_oof_candidate_brier_by_axis",
                    "beta",
                    "beta_at_search_boundary",
                    "brier_improvement",
                    "one_sided_95_lower",
                    "p_value",
                    "train_distribution",
                    "validation_distribution",
                    "baseline_metrics",
                    "candidate_metrics",
                )
            }
            for row in payload["results"]
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect", type=Path)
    parser.add_argument("--inspect-container", type=Path)
    parser.add_argument("--inspect-nested-field")
    parser.add_argument("--records-key")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--history", type=Path)
    parser.add_argument("--snapshots", type=Path)
    parser.add_argument("--xg", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summarize-results", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.summarize_results is not None:
        print(json.dumps(result_summary(args.summarize_results)))
        return 0
    if args.run:
        if not all((args.history, args.snapshots, args.xg, args.output)):
            raise SystemExit("--run requires --history, --snapshots, --xg, and --output")
        result = run_measurement(args)
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return 0
    if args.inspect_container is not None:
        print(json.dumps(container_schema(args.inspect_container)))
        return 0
    if args.inspect is None:
        raise SystemExit("Use --inspect or --inspect-container; direct data probing is disabled.")
    loaded = load_measurement_records(args.inspect, records_key=args.records_key)
    output = (
        nested_schema(loaded, args.inspect_nested_field)
        if args.inspect_nested_field
        else schema_and_counts(loaded)
    )
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
