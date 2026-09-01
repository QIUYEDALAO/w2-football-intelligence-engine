#!/usr/bin/env python3
"""Score the frozen V1 historical predictions after their pre-result commit."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from statistics import mean, median
from typing import Any

from scripts.build_v1_historical_closing_predictions import (
    COMPETITION_FILES,
    _same_team,
)

from w2.domain.odds import settle_asian_handicap, settle_total_goals

OUTCOME_SCORE = {"WIN": 1.0, "HALF_WIN": 0.75, "PUSH": 0.5, "HALF_LOSS": 0.25, "LOSS": 0.0}
OPPOSITE_OUTCOME = {
    "WIN": "LOSS",
    "HALF_WIN": "HALF_LOSS",
    "PUSH": "PUSH",
    "HALF_LOSS": "HALF_WIN",
    "LOSS": "WIN",
}
BOOTSTRAP_RESAMPLES = 8000
BOOTSTRAP_SEED_BASE = 20261001


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _result_rows(source_root: Path, competition: str) -> list[dict[str, Any]]:
    path = source_root / "extracted" / "2324" / f"{COMPETITION_FILES[competition]}.csv"
    rows = []
    with path.open(encoding="latin1", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                home_goals, away_goals = int(row["FTHG"]), int(row["FTAG"])
            except (KeyError, TypeError, ValueError):
                continue
            rows.append(
                {
                    "date": row.get("Date", "").strip(),
                    "home": row.get("HomeTeam", "").strip(),
                    "away": row.get("AwayTeam", "").strip(),
                    "home_goals": home_goals,
                    "away_goals": away_goals,
                }
            )
    return rows


def _probability(distribution: dict[str, str]) -> float:
    return (
        float(distribution["WIN"])
        + 0.75 * float(distribution["HALF_WIN"])
        + 0.5 * float(distribution["PUSH"])
        + 0.25 * float(distribution["HALF_LOSS"])
    )


def _scores(probability: float, actual: float) -> tuple[float, float]:
    safe = min(max(probability, 1e-12), 1.0 - 1e-12)
    return (probability - actual) ** 2, -actual * math.log(safe) - (1.0 - actual) * math.log(
        1.0 - safe
    )


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _bootstrap(values: list[float], seed_offset: int) -> dict[str, float | int]:
    rng = random.Random(BOOTSTRAP_SEED_BASE + seed_offset)  # noqa: S311
    size = len(values)
    estimates = [
        sum(values[rng.randrange(size)] for _ in range(size)) / size
        for _ in range(BOOTSTRAP_RESAMPLES)
    ]
    return {
        "resamples": BOOTSTRAP_RESAMPLES,
        "seed": BOOTSTRAP_SEED_BASE + seed_offset,
        "mean": round(mean(values), 9),
        "upper_95": round(_percentile(estimates, 0.95), 9),
    }


def _calibration(rows: list[tuple[float, float]]) -> dict[str, Any]:
    bins = []
    for index in range(10):
        selected = [row for row in rows if index / 10 <= row[0] < (index + 1) / 10]
        if selected:
            bins.append(
                {
                    "lower": index / 10,
                    "upper": (index + 1) / 10,
                    "count": len(selected),
                    "mean_probability": round(mean(row[0] for row in selected), 9),
                    "mean_actual": round(mean(row[1] for row in selected), 9),
                }
            )
    ece = sum(
        row["count"] / len(rows) * abs(row["mean_probability"] - row["mean_actual"]) for row in bins
    )
    return {"ece_10": round(ece, 9), "bins": bins}


def _profit(outcome: str, odds: float) -> float:
    return {
        "WIN": odds - 1.0,
        "HALF_WIN": 0.5 * (odds - 1.0),
        "PUSH": 0.0,
        "HALF_LOSS": -0.5,
        "LOSS": -1.0,
    }[outcome]


def build(prediction_path: Path, source_root: Path, supplement_path: Path) -> dict[str, Any]:
    supplement = json.loads(supplement_path.read_text(encoding="utf-8"))
    expected = supplement["frozen_prediction_artifact"]["sha256"]
    if _sha(prediction_path) != expected:
        raise ValueError("frozen prediction artifact sha256 mismatch")
    predictions = json.loads(prediction_path.read_text(encoding="utf-8"))["predictions"]
    source_rows = {
        competition: _result_rows(source_root, competition) for competition in COMPETITION_FILES
    }
    scored: dict[str, list[dict[str, Any]]] = {"ASIAN_HANDICAP": [], "TOTALS": []}
    recommendations: dict[str, dict[str, list[dict[str, Any]]]] = {
        market_name: {arm: [] for arm in ("production", "ah_candidate", "totals_candidate")}
        for market_name in scored
    }
    for prediction in predictions:
        market = prediction["market"]
        matches = [
            row
            for row in source_rows[prediction["competition"]]
            if abs(
                (
                    datetime.strptime(row["date"], "%d/%m/%Y").date()
                    - datetime.fromisoformat(market["date"]).date()
                ).days
            )
            <= 1
            and _same_team(row["home"], prediction["home_team"])
            and _same_team(row["away"], prediction["away_team"])
        ]
        if len(matches) != 1:
            raise ValueError(f"result mapping count {len(matches)} for {prediction['fixture_id']}")
        result = matches[0]
        outcomes = {
            "ASIAN_HANDICAP": settle_asian_handicap(
                result["home_goals"],
                result["away_goals"],
                "HOME",
                line=Decimal(str(market["ah_line"])),
            ).value,
            "TOTALS": settle_total_goals(
                result["home_goals"] + result["away_goals"],
                "OVER",
                line=Decimal("2.5"),
            ).value,
        }
        for market_name, quote_key, selection_key in (
            ("ASIAN_HANDICAP", "home", "HOME"),
            ("TOTALS", "over", "OVER"),
        ):
            actual = OUTCOME_SCORE[outcomes[market_name]]
            model_rows: dict[str, Any] = {}
            for arm, model in prediction["models"].items():
                quote = model["market_quotes"][market_name][quote_key]
                probability = _probability(quote["settlement_distribution"])
                brier, logloss = _scores(probability, actual)
                model_rows[arm] = {
                    "probability": probability,
                    "brier": brier,
                    "logloss": logloss,
                    "cashflow_price_edge": float(quote["cashflow_price_edge"]),
                }
            market_probability = prediction["models"]["production"]["devig_market_probability"][
                market_name
            ][selection_key]
            market_brier, market_logloss = _scores(market_probability, actual)
            scored[market_name].append(
                {
                    "fixture_id": prediction["fixture_id"],
                    "actual_outcome": outcomes[market_name],
                    "actual_cashflow_score": actual,
                    "market_probability": market_probability,
                    "market_brier": market_brier,
                    "market_logloss": market_logloss,
                    "models": model_rows,
                }
            )
            opposite_key = "away" if market_name == "ASIAN_HANDICAP" else "under"
            for arm, model in prediction["models"].items():
                quotes = model["market_quotes"][market_name]
                selected = max(
                    (quotes[quote_key], quotes[opposite_key]),
                    key=lambda row: float(row["cashflow_price_edge"]),
                )
                outcome = (
                    outcomes[market_name]
                    if selected["selection"] == selection_key
                    else OPPOSITE_OUTCOME[outcomes[market_name]]
                )
                recommendations[market_name][arm].append(
                    {
                        "selection": selected["selection"],
                        "edge": float(selected["cashflow_price_edge"]),
                        "odds": float(selected["decimal_odds"]),
                        "outcome": outcome,
                    }
                )

    seed = 0
    reports: dict[str, Any] = {}
    for market_name, rows in scored.items():
        candidate = "ah_candidate" if market_name == "ASIAN_HANDICAP" else "totals_candidate"
        paired: dict[str, Any] = {}
        for comparator, metric in (
            ("production", "brier"),
            ("production", "logloss"),
            ("market", "brier"),
            ("market", "logloss"),
        ):
            differences = [
                row["models"][candidate][metric]
                - (
                    row["models"]["production"][metric]
                    if comparator == "production"
                    else row[f"market_{metric}"]
                )
                for row in rows
            ]
            paired[f"{metric}_vs_{comparator}"] = _bootstrap(differences, seed)
            seed += 1
        arms: dict[str, Any] = {}
        for arm in ("production", candidate):
            probabilities = [
                (row["models"][arm]["probability"], row["actual_cashflow_score"]) for row in rows
            ]
            edges = [row["models"][arm]["cashflow_price_edge"] for row in rows]
            eligible = [row for row in recommendations[market_name][arm] if row["edge"] >= 0.05]
            arms[arm] = {
                "mean_brier": round(mean(row["models"][arm]["brier"] for row in rows), 9),
                "mean_logloss": round(mean(row["models"][arm]["logloss"] for row in rows), 9),
                "calibration": _calibration(probabilities),
                "cashflow_price_edge": {
                    "mean": round(mean(edges), 9),
                    "median": round(median(edges), 9),
                    "minimum": round(min(edges), 9),
                    "maximum": round(max(edges), 9),
                    "ge_0_05": sum(value >= 0.05 for value in edges),
                },
                "hypothetical_closing_recommendations": {
                    "count": len(eligible),
                    "selection_counts": {
                        selection: sum(row["selection"] == selection for row in eligible)
                        for selection in (
                            ("HOME", "AWAY")
                            if market_name == "ASIAN_HANDICAP"
                            else ("OVER", "UNDER")
                        )
                    },
                    "settlement_counts": {
                        outcome: sum(row["outcome"] == outcome for row in eligible)
                        for outcome in OUTCOME_SCORE
                    },
                    "p_and_l_units": round(
                        sum(_profit(row["outcome"], row["odds"]) for row in eligible), 6
                    ),
                    "display_only_not_a_gate": True,
                },
            }
        market_probs = [(row["market_probability"], row["actual_cashflow_score"]) for row in rows]
        checks = {
            "minimum_500_fixtures": len(rows) >= 500,
            **{
                f"{name}_upper_95_le_zero": value["upper_95"] <= 0 for name, value in paired.items()
            },
        }
        reports[market_name] = {
            "fixture_count": len(rows),
            "candidate": candidate,
            "arms": arms,
            "closing_market": {
                "mean_brier": round(mean(row["market_brier"] for row in rows), 9),
                "mean_logloss": round(mean(row["market_logloss"] for row in rows), 9),
                "calibration": _calibration(market_probs),
            },
            "paired_differences": paired,
            "checks": checks,
            "decision": "PASS" if all(checks.values()) else "REJECTED",
        }
    return {
        "schema": "w2.v1.historical_closing_blindtest.result.v1",
        "sources": {
            "predictions_sha256": _sha(prediction_path),
            "supplement_sha256": _sha(supplement_path),
        },
        "markets": reports,
        "decision": "PASS"
        if all(row["decision"] == "PASS" for row in reports.values())
        else "REJECTED",
        "safety": {
            "post_freeze_provider_calls": 0,
            "production_writes": 0,
            "ledger_writes": 0,
            "github_operations": 0,
            "deployment": 0,
            "post_result_refit": 0,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--supplement", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build(args.predictions, args.source_root, args.supplement)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"decision": payload["decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
