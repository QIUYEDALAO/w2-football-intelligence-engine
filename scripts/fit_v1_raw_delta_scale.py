#!/usr/bin/env python3
"""Fit the preregistered V1 raw-delta scale from frozen PIT xG exports."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import deque
from pathlib import Path
from typing import Any

csv.field_size_limit(2**31 - 1)


def _mean(values: deque[tuple[float, float]]) -> tuple[float, float]:
    n = len(values)
    return sum(v[0] for v in values) / n, sum(v[1] for v in values) / n


def load_rows(home_away_path: Path, xg_path: Path) -> list[dict[str, Any]]:
    home_away = {
        row["fixture_id"]: row
        for row in csv.DictReader(home_away_path.open(newline="", encoding="utf-8"))
    }
    matches: dict[str, dict[str, dict[str, Any]]] = {}
    for row in csv.DictReader(xg_path.open(newline="", encoding="utf-8")):
        matches.setdefault(row["fixture_id"], {})[row["team_id"]] = row
    history: dict[str, deque[tuple[float, float]]] = {}
    result: list[dict[str, Any]] = []
    for fixture_id, teams in sorted(
        matches.items(),
        key=lambda item: (
            min(row["kickoff_at"] for row in item[1].values()),
            item[0],
        ),
    ):
        identity = home_away.get(fixture_id)
        if identity is None:
            continue
        home = teams.get(identity["home_id"])
        away = teams.get(identity["away_id"])
        if home is None or away is None:
            continue
        home_history = history.setdefault(identity["home_id"], deque(maxlen=5))
        away_history = history.setdefault(identity["away_id"], deque(maxlen=5))
        if len(home_history) == 5 and len(away_history) == 5:
            home_for, home_against = _mean(home_history)
            away_for, away_against = _mean(away_history)
            result.append(
                {
                    "fixture_id": fixture_id,
                    "kickoff_at": home["kickoff_at"],
                    "base_home": (home_for + away_against) / 2.0,
                    "base_away": (away_for + home_against) / 2.0,
                    "goals_home": int(home["goals_for"]),
                    "goals_away": int(home["goals_against"]),
                }
            )
        home_history.append((float(home["xg_for"]), float(home["xg_against"])))
        away_history.append((float(away["xg_for"]), float(away["xg_against"])))
    if len(result) != 8659:
        raise ValueError(f"expected frozen eligible fixture count 8659, got {len(result)}")
    return result


def _poisson_nll(row: dict[str, Any], scale: float) -> float:
    total = min(max(row["base_home"] + row["base_away"], 1.35), 4.4)
    delta = scale * (row["base_home"] - row["base_away"]) + 0.30
    home = min(max((total + delta) / 2.0, 0.15), 4.25)
    away = min(max((total - delta) / 2.0, 0.15), 4.25)
    return (
        home - row["goals_home"] * math.log(home) + math.lgamma(row["goals_home"] + 1)
        + away
        - row["goals_away"] * math.log(away)
        + math.lgamma(row["goals_away"] + 1)
    )


def fit(rows: list[dict[str, Any]], low: float = 0.5, high: float = 3.0) -> float:
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    left, right = low, high
    c = right - (right - left) / phi
    d = left + (right - left) / phi
    while right - left > 1e-6:
        fc = sum(_poisson_nll(row, c) for row in rows)
        fd = sum(_poisson_nll(row, d) for row in rows)
        if fc <= fd:
            right, d = d, c
            c = right - (right - left) / phi
        else:
            left, c = c, d
            d = left + (right - left) / phi
    return round((left + right) / 2.0, 6)


def _lambda_difference(row: dict[str, Any], scale: float) -> float:
    total = min(max(row["base_home"] + row["base_away"], 1.35), 4.4)
    delta = scale * (row["base_home"] - row["base_away"]) + 0.30
    home = min(max((total + delta) / 2.0, 0.15), 4.25)
    away = min(max((total - delta) / 2.0, 0.15), 4.25)
    return home - away


def _regression(x: list[float], y: list[float]) -> dict[str, float]:
    mean_x, mean_y = sum(x) / len(x), sum(y) / len(y)
    slope = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y, strict=True)) / sum(
        (a - mean_x) ** 2 for a in x
    )
    return {"slope": round(slope, 6), "intercept": round(mean_y - slope * mean_x, 6)}


def rolling_origin(rows: list[dict[str, Any]]) -> dict[str, Any]:
    warmup, folds = 1500, 10
    remaining = len(rows) - warmup
    base, extra = divmod(remaining, folds)
    start = warmup
    results = []
    oof_x: list[float] = []
    oof_y: list[float] = []
    for index in range(folds):
        size = base + (1 if index < extra else 0)
        stop = start + size
        value = fit(rows[:start])
        fold = rows[start:stop]
        oof_x.extend(_lambda_difference(row, value) for row in fold)
        oof_y.extend(row["goals_home"] - row["goals_away"] for row in fold)
        results.append(
            {
                "fold": index + 1,
                "train_count": start,
                "validation_count": size,
                "validation_kickoff_start": fold[0]["kickoff_at"],
                "validation_kickoff_end": fold[-1]["kickoff_at"],
                "fitted_value": value,
            }
        )
        start = stop
    return {
        "warmup_fixtures": warmup,
        "folds": results,
        "oof_fixture_count": len(oof_x),
        "oof_net_margin_regression": _regression(oof_x, oof_y),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home-away", type=Path, required=True)
    parser.add_argument("--xg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = load_rows(args.home_away, args.xg)
    value = fit(rows)
    payload = {
        "schema": "w2.v1.raw_delta_scale_fit.v1",
        "fixture_count": len(rows),
        "parameter": "raw_delta_scale",
        "bounds": [0.5, 3.0],
        "home_advantage_goals": 0.30,
        "optimizer": "golden_section_width_le_1e-6",
        "fitted_value": value,
        "source": {
            "home_away_sha256": _sha256(args.home_away),
            "xg_sha256": _sha256(args.xg),
        },
        "full_train_net_margin_regression": _regression(
            [_lambda_difference(row, value) for row in rows],
            [row["goals_home"] - row["goals_away"] for row in rows],
        ),
        "rolling_origin": rolling_origin(rows),
        "data_role": "TRAIN_DEVELOPMENT_ONLY",
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
