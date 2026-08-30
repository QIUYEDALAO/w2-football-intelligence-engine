#!/usr/bin/env python3
"""Compare persisted model-vs-market divergence against realised outcomes.

Input is a committed COPY snapshot.  No network, provider, database, or model
fitting is performed.  Fixture-cluster bootstrap keeps AH and TOTALS rows from
the same match in the same resampled cluster.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from statistics import mean
from typing import Any

from w2.domain.five_state_pricing import (
    SettlementDistribution,
    cashflow_price_edge,
    fair_decimal_odds,
)
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.markets.settlement_probability import effective_settlement_probability

TARGET = {"WIN": 1.0, "HALF_WIN": 0.5, "PUSH": 0.5, "HALF_LOSS": 0.0, "LOSS": 0.0}
BINS = ((0.0, 0.05), (0.05, 0.10), (0.10, 0.15), (0.15, 0.25), (0.25, float("inf")))


def _bin(value: float) -> str:
    if value < 0:
        return "[-inf,0)"
    for low, high in BINS:
        if low <= value < high:
            return f"[{low:g},{high:g})" if high != float("inf") else f"[{low:g},inf)"
    return "INVALID"


def _row(raw: dict[str, str]) -> dict[str, Any]:
    evaluation = json.loads(raw["evaluation_payload"])
    distribution = evaluation["model_settlement_distribution"]
    model_probability = float(effective_settlement_probability(distribution))
    delta = float(evaluation["current_delta"])
    market_probability = model_probability - delta
    line = Decimal(str(evaluation["exact_line"]))
    selection = str(evaluation["selection"])
    home, away = int(raw["home_goals"]), int(raw["away_goals"])
    if raw["market"] == "ASIAN_HANDICAP":
        outcome = settle_asian_handicap(home, away, selection, line).value
    else:
        outcome = settle_total_goals(home + away, selection, line).value
    target = TARGET[outcome]
    priced = SettlementDistribution(
        full_win_probability=Decimal(str(distribution["WIN"])),
        half_win_probability=Decimal(str(distribution["HALF_WIN"])),
        push_probability=Decimal(str(distribution["PUSH"])),
        half_loss_probability=Decimal(str(distribution["HALF_LOSS"])),
        full_loss_probability=Decimal(str(distribution["LOSS"])),
    )
    edge = float(
        cashflow_price_edge(Decimal(str(evaluation["decimal_odds"])), fair_decimal_odds(priced))
    )
    lifecycle_pass = bool(
        float(evaluation["current_ev"]) > 0
        and delta >= 0.05
        and float(evaluation["current_ev_minus_se"]) > 0
    )
    cashflow_pass = bool(
        float(evaluation["current_ev"]) > 0
        and edge >= 0.05
        and float(evaluation["current_ev_minus_se"]) > 0
    )
    return {
        "fixture_id": raw["fixture_id"],
        "market": raw["market"],
        "state": raw["opportunity_state"],
        "candidate": raw["opportunity_state"] == "EVALUATED_CANDIDATE",
        "lifecycle_economic_pass": lifecycle_pass,
        "cashflow_economic_pass": cashflow_pass,
        "delta": delta,
        "delta_bin": _bin(delta),
        "ev_bin": _bin(float(evaluation["current_ev"])),
        "model_probability": model_probability,
        "market_probability": market_probability,
        "target": target,
        "outcome": outcome,
        "model_brier": (model_probability - target) ** 2,
        "market_brier": (market_probability - target) ** 2,
        "model_abs_error": abs(model_probability - target),
        "market_abs_error": abs(market_probability - target),
        "ev": evaluation.get("current_ev"),
        "cashflow_price_edge": edge,
        "ev_minus_se": evaluation.get("current_ev_minus_se"),
        "evaluation_id": raw["evaluation_id"],
    }


def _stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    return {
        "n": len(rows),
        "model_brier": round(mean(r["model_brier"] for r in rows), 8),
        "market_brier": round(mean(r["market_brier"] for r in rows), 8),
        "model_minus_market_brier": round(
            mean(r["model_brier"] - r["market_brier"] for r in rows), 8
        ),
        "model_abs_error": round(mean(r["model_abs_error"] for r in rows), 8),
        "market_abs_error": round(mean(r["market_abs_error"] for r in rows), 8),
        "model_minus_market_abs_error": round(
            mean(r["model_abs_error"] - r["market_abs_error"] for r in rows), 8
        ),
    }


def _cluster_bootstrap(
    rows: list[dict[str, Any]], group: str, *, reps: int = 5000, seed: int = 20260831
) -> dict[str, Any]:
    fixtures = defaultdict(list)
    for row in rows:
        fixtures[row["fixture_id"]].append(row)
    ids = list(fixtures)
    if len(ids) < 2:
        return {"reps": 0, "ci95": None}
    rng = random.Random(seed)  # noqa: S311 - deterministic statistical bootstrap
    differences: list[float] = []
    for _ in range(reps):
        sampled = [fixtures[rng.choice(ids)] for _ in ids]
        positive = [row for cluster in sampled for row in cluster if row[group]]
        negative = [row for cluster in sampled for row in cluster if not row[group]]
        if positive and negative:
            differences.append(
                mean(r["model_brier"] - r["market_brier"] for r in positive)
                - mean(r["model_brier"] - r["market_brier"] for r in negative)
            )
    differences.sort()
    if not differences:
        return {"reps": 0, "ci95": None}
    point_positive = [r for r in rows if r[group]]
    point_negative = [r for r in rows if not r[group]]
    point = mean(r["model_brier"] - r["market_brier"] for r in point_positive) - mean(
        r["model_brier"] - r["market_brier"] for r in point_negative
    )
    return {
        "contrast": f"{group}=true minus false",
        "point": round(point, 8),
        "reps": len(differences),
        "ci95": [
            round(differences[int(len(differences) * 0.025)], 8),
            round(differences[int(len(differences) * 0.975)], 8),
        ],
    }


def audit(path: Path) -> dict[str, Any]:
    raw_rows = list(csv.DictReader(path.open(newline="")))
    rows = [_row(raw) for raw in raw_rows]
    output: dict[str, Any] = {
        "input_rows": len(rows),
        "markets": {},
        "gate_counts": {},
        "cluster_bootstrap": {},
    }
    output["gate_counts"] = {
        "ev_positive": sum(float(r["ev"]) > 0 for r in rows if r["ev"] is not None),
        "delta_ge_005": sum(float(r["delta"]) >= 0.05 for r in rows),
        "cashflow_edge_ge_005": sum(float(r["cashflow_price_edge"]) >= 0.05 for r in rows),
        "ev_minus_se_positive": sum(
            float(r["ev_minus_se"]) > 0 for r in rows if r["ev_minus_se"] is not None
        ),
    }
    output["candidate_gate_anomalies"] = {
        "persisted_delta_below_005": [
            r["evaluation_id"] for r in rows if r["candidate"] and r["delta"] < 0.05
        ],
        "recomputed_cashflow_edge_below_005": [
            r["evaluation_id"] for r in rows if r["candidate"] and r["cashflow_price_edge"] < 0.05
        ],
    }
    for market in ("ASIAN_HANDICAP", "TOTALS"):
        scoped = [r for r in rows if r["market"] == market]
        for row in scoped:
            row["high_delta_ge_010"] = row["delta"] >= 0.10
        groups = {
            "all": scoped,
            "candidate": [r for r in scoped if r["candidate"]],
            "noncandidate": [r for r in scoped if not r["candidate"]],
            "lifecycle_economic_pass": [r for r in scoped if r["lifecycle_economic_pass"]],
            "lifecycle_economic_fail": [r for r in scoped if not r["lifecycle_economic_pass"]],
            "cashflow_economic_pass": [r for r in scoped if r["cashflow_economic_pass"]],
            "cashflow_economic_fail": [r for r in scoped if not r["cashflow_economic_pass"]],
        }
        bins = {
            label: _stats([r for r in scoped if r["delta_bin"] == label])
            for label in sorted({_bin(r["delta"]) for r in scoped})
        }
        ev_bins = {
            label: _stats([r for r in scoped if r["ev_bin"] == label])
            for label in sorted({r["ev_bin"] for r in scoped})
        }
        output["markets"][market] = {
            "groups": {name: _stats(value) for name, value in groups.items()},
            "delta_bins": bins,
            "ev_bins": ev_bins,
        }
        output["cluster_bootstrap"][market] = {
            group: _cluster_bootstrap(scoped, group)
            for group in (
                "candidate",
                "lifecycle_economic_pass",
                "cashflow_economic_pass",
                "high_delta_ge_010",
            )
        }
    output["rows"] = rows
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.input)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "input_rows",
                    "gate_counts",
                    "candidate_gate_anomalies",
                    "markets",
                    "cluster_bootstrap",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
