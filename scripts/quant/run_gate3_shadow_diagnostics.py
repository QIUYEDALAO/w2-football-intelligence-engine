"""Independent, read-only Gate 3 diagnostics for an exported evaluation TSV.

The script deliberately consumes an export rather than opening a database.  It has
no writer, Provider client, recommendation import, or settlement import.  Its
five-state scoring is an audit-side implementation used to characterize a shadow
cohort; it is not a production metric authority.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

OUTCOME_ORDER = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")


def _sign(value: float) -> int:
    return 1 if value > 1e-9 else (-1 if value < -1e-9 else 0)


def settle_outcome(market: str, selection: str, line: float, home: int, away: int) -> str:
    """Settle a two-sided AH/TOTALS line without importing production code."""

    def sign_at(split_line: float) -> int:
        if market == "TOTALS":
            margin = home + away - split_line
            if selection == "UNDER":
                margin = -margin
        else:
            margin = (home - away if selection == "HOME" else away - home) + split_line
        return _sign(margin)

    if round(line * 4) % 2:
        low = math.floor(line * 2) / 2
        high = math.ceil(line * 2) / 2
        first, second = sign_at(low), sign_at(high)
        if first == second:
            return {1: "WIN", 0: "PUSH", -1: "LOSS"}[first]
        if {first, second} == {0, 1}:
            return "HALF_WIN"
        if {first, second} == {0, -1}:
            return "HALF_LOSS"
        raise ValueError("quarter line has mixed win/loss settlement")
    return {1: "WIN", 0: "PUSH", -1: "LOSS"}[sign_at(line)]


def _row_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for market in ("ASIAN_HANDICAP", "TOTALS"):
        for state in ("ANALYSIS_PICK_ACTIVE", "NO_EDGE_CURRENT", "BLOCKED_BY_FACTOR"):
            cohort = [
                row for row in rows
                if row["market"] == market
                and row["state"] == state
                and row.get("home") not in (None, "")
                and row.get("distribution")
            ]
            if not cohort:
                continue
            logloss = brier = rps = bias = profit = 0.0
            outcomes: Counter[str] = Counter()
            for row in cohort:
                distribution = json.loads(row["distribution"])
                outcome = settle_outcome(
                    market, row["selection"], float(row["line"]),
                    int(row["home"]), int(row["away"]),
                )
                outcomes[outcome] += 1
                logloss -= math.log(max(float(distribution[outcome]), 1e-15))
                brier += sum(
                    (float(distribution[key]) - (1.0 if key == outcome else 0.0)) ** 2
                    for key in OUTCOME_ORDER
                )
                cumulative = 0.0
                observed = 0.0
                for key in OUTCOME_ORDER[:-1]:
                    cumulative += float(distribution[key])
                    observed += 1.0 if key == outcome else 0.0
                    rps += (cumulative - observed) ** 2 / 4.0
                predicted = float(distribution["WIN"]) + 0.5 * float(
                    distribution["HALF_WIN"]
                )
                realized = 1.0 if outcome == "WIN" else 0.5 if outcome == "HALF_WIN" else 0.0
                bias += predicted - realized
                odds = float(row["odds"])
                profit += {
                    "WIN": odds - 1.0,
                    "HALF_WIN": (odds - 1.0) / 2.0,
                    "PUSH": 0.0,
                    "HALF_LOSS": -0.5,
                    "LOSS": -1.0,
                }[outcome]
            n = len(cohort)
            result[f"{market}/{state}"] = {
                "n": n,
                "logloss": logloss / n,
                "brier": brier / n,
                "rps": rps / n,
                "bias": bias / n,
                "profit_units": profit,
                "outcomes": dict(outcomes),
            }
    return result


def load_tsv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="|"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    rows = load_tsv(args.input)
    print(json.dumps({"rows": len(rows), "metrics": _row_metrics(rows)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
