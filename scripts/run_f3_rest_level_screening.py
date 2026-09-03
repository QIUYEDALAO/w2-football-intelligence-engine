#!/usr/bin/env python3
"""Boundary-first loader for the preregistered TRAIN-2024 rest-level screening."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any

from w2.models.independent import normalized_score_matrix
from w2.strategy.calibration import LambdaCalibrationParams, calibrate_lambdas

BURNED_PENALTYBLOG_SEASONS = frozenset(
    {"2012", "2013", "2014", "2015", "2016", "2012/13", "2013/14", "2014/15", "2015/16", "2016/17"}
)
DATE_FIELDS = ("target_kickoff", "kickoff_utc", "kickoff", "kickoff_at", "date")
CONSTRUCTIONS = ("F3L_MIN_REST", "F3L_MEAN_REST")
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 20_260_905
BONFERRONI_ALPHA = 0.025


@dataclass(frozen=True)
class LoadedRecords:
    records: tuple[dict[str, Any], ...]
    audit: dict[str, Any]


@dataclass(frozen=True)
class MeasurementRow:
    fixture_id: str
    actual: str
    baseline_home: float
    baseline_away: float
    value: float


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


def _fixture_id(value: Any) -> str:
    text = str(value)
    return text if ":" in text else f"api_football:{text}"


def _probabilities(home_mu: float, away_mu: float) -> dict[str, float]:
    matrix = normalized_score_matrix(home_mu, away_mu, max_goals=10)
    return {
        "HOME": sum(p for (home, away), p in matrix.items() if home > away),
        "DRAW": sum(p for (home, away), p in matrix.items() if home == away),
        "AWAY": sum(p for (home, away), p in matrix.items() if home < away),
    }


def _candidate_probabilities(
    row: MeasurementRow, standardized: float, beta: float
) -> dict[str, float]:
    params = LambdaCalibrationParams()
    total = row.baseline_home + row.baseline_away + beta * standardized
    delta = row.baseline_home - row.baseline_away
    home = min(max((total + delta) / 2, params.minimum_lambda), params.maximum_lambda)
    away = min(max((total - delta) / 2, params.minimum_lambda), params.maximum_lambda)
    return _probabilities(home, away)


def _brier(probabilities: dict[str, float], actual: str) -> float:
    return sum(
        (probability - float(label == actual)) ** 2
        for label, probability in probabilities.items()
    )


def _log_loss(rows: list[MeasurementRow], mean: float, std: float, beta: float) -> float:
    return fmean(
        -math.log(
            max(
                _candidate_probabilities(row, (row.value - mean) / std, beta)[row.actual],
                1e-15,
            )
        )
        for row in rows
    )


def _fit(rows: list[MeasurementRow]) -> tuple[float, float, float]:
    mean = fmean(row.value for row in rows)
    std = pstdev(row.value for row in rows)
    if std == 0:
        raise ValueError("FAIL_NEAR_CONSTANT")
    left, right = -2.0, 2.0
    ratio = (math.sqrt(5) - 1) / 2
    c = right - ratio * (right - left)
    d = left + ratio * (right - left)
    fc = _log_loss(rows, mean, std, c)
    fd = _log_loss(rows, mean, std, d)
    for _ in range(96):
        if fc <= fd:
            right, d, fd = d, c, fc
            c = right - ratio * (right - left)
            fc = _log_loss(rows, mean, std, c)
        else:
            left, c, fc = c, d, fd
            d = left + ratio * (right - left)
            fd = _log_loss(rows, mean, std, d)
    return (left + right) / 2, mean, std


def _fold(fixture_id: str) -> int:
    return int(hashlib.sha256(fixture_id.encode()).hexdigest()[:8], 16) % 5


def _oof_probabilities(
    rows: list[MeasurementRow],
) -> tuple[list[dict[str, float]], list[dict[str, float]], list[dict[str, float | int | bool]]]:
    baseline_by_fixture: dict[str, dict[str, float]] = {}
    candidate_by_fixture: dict[str, dict[str, float]] = {}
    fits: list[dict[str, float | int | bool]] = []
    for fold in range(5):
        fitting = [row for row in rows if _fold(row.fixture_id) != fold]
        held_out = [row for row in rows if _fold(row.fixture_id) == fold]
        beta, mean, std = _fit(fitting)
        fits.append(
            {
                "fold": fold,
                "fit_count": len(fitting),
                "held_out_count": len(held_out),
                "beta": beta,
                "beta_at_search_boundary": abs(beta) >= 1.999999,
                "standardization_mean": mean,
                "standardization_population_std": std,
            }
        )
        for row in held_out:
            baseline_by_fixture[row.fixture_id] = _probabilities(
                row.baseline_home, row.baseline_away
            )
            candidate_by_fixture[row.fixture_id] = _candidate_probabilities(
                row, (row.value - mean) / std, beta
            )
    return (
        [baseline_by_fixture[row.fixture_id] for row in rows],
        [candidate_by_fixture[row.fixture_id] for row in rows],
        fits,
    )


def _secondary_metrics(
    probabilities: list[dict[str, float]], rows: list[MeasurementRow]
) -> dict[str, Any]:
    labels = ("HOME", "DRAW", "AWAY")
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
        "log_loss": fmean(
            -math.log(max(probability[row.actual], 1e-15))
            for probability, row in zip(probabilities, rows, strict=True)
        ),
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
    return (
        draws[int(0.05 * BOOTSTRAP_REPLICATES)],
        (1 + sum(value <= 0 for value in draws)) / (BOOTSTRAP_REPLICATES + 1),
    )


def _distribution(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)

    def percentile(q: float) -> float:
        return ordered[round((len(ordered) - 1) * q)]

    return {
        "count": len(values),
        "min": ordered[0],
        "p05": percentile(0.05),
        "p10": percentile(0.10),
        "p25": percentile(0.25),
        "median": percentile(0.5),
        "p75": percentile(0.75),
        "max": ordered[-1],
        "mean": fmean(values),
        "population_std": pstdev(values),
        "zero_count": sum(value == 0 for value in values),
        "count_le_2": sum(value <= 2 for value in values),
        "count_le_3": sum(value <= 3 for value in values),
        "count_le_4": sum(value <= 4 for value in values),
    }


def _measurement_rows(
    history: LoadedRecords, snapshots: LoadedRecords, xg: LoadedRecords
) -> tuple[dict[str, list[MeasurementRow]], dict[str, int]]:
    outcome_sides: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in history.records:
        outcome_sides[_fixture_id(row["fixture_id"])][str(row["team_side"])] = row
    snapshot_by_fixture = {
        _fixture_id(row["target_fixture_id"]): row for row in snapshots.records
    }
    xg_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in xg.records:
        xg_by_team[str(row["team_id"])].append(row)
    output = {construction: [] for construction in CONSTRUCTIONS}
    exclusions: Counter[str] = Counter()
    for fixture_id, sides in outcome_sides.items():
        if set(sides) != {"HOME", "AWAY"}:
            exclusions["INCOMPLETE_OUTCOME_SIDES"] += 1
            continue
        snapshot = snapshot_by_fixture.get(fixture_id)
        if snapshot is None:
            exclusions["MISSING_SNAPSHOT"] += 1
            continue
        home, away = sides["HOME"], sides["AWAY"]
        kickoff = _kickoff(home)
        target_raw_id = str(home["provider_fixture_id"])
        rolling: dict[str, tuple[float, float]] = {}
        for side, team_id in (("HOME", str(home["team_id"])), ("AWAY", str(away["team_id"]))):
            prior = sorted(
                (
                    row
                    for row in xg_by_team[team_id]
                    if _kickoff(row) < kickoff and str(row["fixture_id"]) != target_raw_id
                ),
                key=lambda row: str(row["kickoff_at"]),
            )[-5:]
            if len(prior) >= 3:
                rolling[side] = (
                    fmean(float(row["xg_for"]) for row in prior),
                    fmean(float(row["xg_against"]) for row in prior),
                )
        if set(rolling) != {"HOME", "AWAY"}:
            exclusions["MISSING_PIT_XG"] += 1
            continue
        factors = snapshot.get("factors")
        f3 = factors.get("F3_REST_FITNESS") if isinstance(factors, dict) else None
        if not isinstance(f3, dict) or f3.get("missing"):
            exclusions["MISSING_F3"] += 1
            continue
        try:
            home_rest = float(f3["home_rest_days"])
            away_rest = float(f3["away_rest_days"])
        except (KeyError, TypeError, ValueError):
            exclusions["MISSING_REST_LEVEL_INPUT"] += 1
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
        values = {
            "F3L_MIN_REST": min(home_rest, away_rest),
            "F3L_MEAN_REST": (home_rest + away_rest) / 2,
        }
        for construction, value in values.items():
            output[construction].append(
                MeasurementRow(
                    fixture_id=fixture_id,
                    actual=actual,
                    baseline_home=baseline.lambda_home,
                    baseline_away=baseline.lambda_away,
                    value=value,
                )
            )
    return output, dict(sorted(exclusions.items()))


def _measure(construction: str, rows: list[MeasurementRow]) -> dict[str, Any]:
    base = {
        "construction": construction,
        "fixture_count": len(rows),
        "cluster_count": len({row.fixture_id for row in rows}),
        "distribution": _distribution([row.value for row in rows]) if rows else None,
    }
    if len(rows) < 300:
        return {**base, "verdict": "FAIL_NOT_MEASURABLE"}
    if pstdev(row.value for row in rows) == 0:
        return {**base, "verdict": "FAIL_NEAR_CONSTANT"}
    baseline, candidate, fits = _oof_probabilities(rows)
    improvements = [
        _brier(base_probability, row.actual) - _brier(candidate_probability, row.actual)
        for row, base_probability, candidate_probability in zip(
            rows, baseline, candidate, strict=True
        )
    ]
    point = fmean(improvements)
    lower, p_value = _bootstrap(improvements)
    passed = point > 0 and lower > 0 and p_value < BONFERRONI_ALPHA
    return {
        **base,
        "axis": "TOTAL",
        "fold_fits": fits,
        "baseline_metrics": _secondary_metrics(baseline, rows),
        "candidate_metrics": _secondary_metrics(candidate, rows),
        "brier_improvement": point,
        "one_sided_95_lower": lower,
        "p_value": p_value,
        "bonferroni_alpha": BONFERRONI_ALPHA,
        "verdict": "PASS_SCREENING" if passed else "FAIL_SCREENING",
    }


def run_measurement(args: argparse.Namespace) -> dict[str, Any]:
    history = load_train_2024_records(args.history, records_key="history_rows")
    snapshots = load_train_2024_records(args.snapshots)
    xg = load_train_2024_records(args.xg)
    rows, exclusions = _measurement_rows(history, snapshots, xg)
    return {
        "schema_version": "w2.f3_rest_level_screening.results.v1",
        "task_id": "W2-F3-REST-LEVEL-REMEASURE",
        "preregistration_commit": "d5024e5d",
        "screening_only": True,
        "validation_2025_consumed": False,
        "holdout_2026_consumed": False,
        "bootstrap": {
            "unit": "fixture",
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": BOOTSTRAP_SEED,
        },
        "load_audits": {
            "history": history.audit,
            "snapshots": snapshots.audit,
            "xg": xg.audit,
        },
        "exclusions": exclusions,
        "results": [_measure(construction, rows[construction]) for construction in CONSTRUCTIONS],
        "provider_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect", type=Path)
    parser.add_argument("--records-key")
    parser.add_argument("--inspect-rest-inputs", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--history", type=Path)
    parser.add_argument("--snapshots", type=Path)
    parser.add_argument("--xg", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.run:
        if not all((args.history, args.snapshots, args.xg, args.output)):
            raise SystemExit("--run requires --history, --snapshots, --xg, and --output")
        args.output.write_text(
            json.dumps(run_measurement(args), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    if args.inspect is None:
        raise SystemExit("Use --inspect or --run; direct data probing is disabled.")
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
