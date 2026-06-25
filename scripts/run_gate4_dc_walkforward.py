#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from w2.models.dixon_coles import (
    DixonColesMatch,
    fit_dixon_coles,
    one_x_two_from_matrix,
    predict_score_matrix,
)
from w2.models.evaluation import EvaluationRow, metrics, paired_bootstrap_delta

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "tests" / "fixtures" / "gate4" / "dixon_coles_matches.json"
REPORT = ROOT / "reports" / "W2_GATE4_DC_WALKFORWARD.json"
SEED = 20260625
INITIAL_TRAIN_SIZE = 12


def parse_match(row: dict[str, Any]) -> DixonColesMatch:
    return DixonColesMatch(
        fixture_id=str(row["fixture_id"]),
        kickoff_utc=datetime.fromisoformat(str(row["kickoff_utc"]).replace("Z", "+00:00")),
        home_team=str(row["home_team"]),
        away_team=str(row["away_team"]),
        home_goals=int(row["home_goals"]),
        away_goals=int(row["away_goals"]),
        market_probabilities=cast(dict[str, float], row["market_probabilities"]),
    )


def load_matches() -> list[DixonColesMatch]:
    rows = json.loads(DATASET.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Dixon-Coles fixture dataset must be a list")
    return sorted(
        [parse_match(cast(dict[str, Any], row)) for row in rows],
        key=lambda item: (item.kickoff_utc, item.fixture_id),
    )


def log_loss(probabilities: dict[str, float], actual: str) -> float:
    return -math.log(max(probabilities[actual], 1e-12))


def walk_forward(matches: list[DixonColesMatch]) -> dict[str, Any]:
    if len(matches) <= INITIAL_TRAIN_SIZE:
        raise ValueError("dataset too small for walk-forward")
    model_rows: list[EvaluationRow] = []
    market_rows: list[EvaluationRow] = []
    model_losses: list[float] = []
    market_losses: list[float] = []
    folds: list[dict[str, Any]] = []

    for index in range(INITIAL_TRAIN_SIZE, len(matches)):
        train = matches[:index]
        test = matches[index]
        parameters = fit_dixon_coles(train)
        matrix = predict_score_matrix(parameters, test.home_team, test.away_team)
        probabilities = one_x_two_from_matrix(matrix)
        if parameters.training_cutoff >= test.kickoff_utc:
            raise ValueError("leakage: training cutoff must be before test kickoff")
        model_rows.append(
            EvaluationRow(
                fixture_id=test.fixture_id,
                actual=test.actual_1x2,
                probabilities=probabilities,
                competition="fixed_gate4_fixture",
                season="2024",
                neutral_site=False,
            )
        )
        market_rows.append(
            EvaluationRow(
                fixture_id=test.fixture_id,
                actual=test.actual_1x2,
                probabilities=test.market_probabilities,
                competition="fixed_gate4_fixture",
                season="2024",
                neutral_site=False,
            )
        )
        model_loss = log_loss(probabilities, test.actual_1x2)
        market_loss = log_loss(test.market_probabilities, test.actual_1x2)
        model_losses.append(model_loss)
        market_losses.append(market_loss)
        folds.append(
            {
                "fixture_id": test.fixture_id,
                "train_size": len(train),
                "data_cutoff": parameters.training_cutoff.isoformat().replace("+00:00", "Z"),
                "kickoff_utc": test.kickoff_utc.isoformat().replace("+00:00", "Z"),
                "rho": parameters.rho,
                "actual": test.actual_1x2,
                "model_log_loss": round(model_loss, 6),
                "market_log_loss": round(market_loss, 6),
            }
        )
    delta = paired_bootstrap_delta(model_losses, market_losses, samples=600, seed=SEED)
    model_metrics = metrics(model_rows)
    market_metrics = metrics(market_rows)
    verdict = (
        "BEATEN"
        if model_metrics["log_loss"] < market_metrics["log_loss"]
        and delta["ci_high"] < 0
        and model_metrics["ece"] <= market_metrics["ece"]
        else "NOT_BEATEN"
    )
    return {
        "folds": folds,
        "model_metrics": model_metrics,
        "market_baseline_metrics": market_metrics,
        "bootstrap_95ci_model_minus_market_log_loss": delta,
        "verdict": verdict,
    }


def leakage_check(matches: list[DixonColesMatch], folds: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(matches, key=lambda item: (item.kickoff_utc, item.fixture_id))
    monotonic = ordered == matches
    cutoff_before_kickoff = all(
        datetime.fromisoformat(str(fold["data_cutoff"]).replace("Z", "+00:00"))
        < datetime.fromisoformat(str(fold["kickoff_utc"]).replace("Z", "+00:00"))
        for fold in folds
    )
    return {
        "status": "PASS" if monotonic and cutoff_before_kickoff else "FAIL",
        "chronological_order": monotonic,
        "cutoff_before_test_kickoff": cutoff_before_kickoff,
        "random_split_used": False,
        "closing_or_result_used_as_feature": False,
        "retrospective_forward_claim": False,
    }


def build_report() -> dict[str, Any]:
    random.seed(SEED)
    matches = load_matches()
    walk = walk_forward(matches)
    leakage = leakage_check(matches, cast(list[dict[str, Any]], walk["folds"]))
    return {
        "schema_version": "W2_GATE4_DC_WALKFORWARD_V1",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "model": "DIXON_COLES",
        "model_version": "gate4.dc.v1",
        "dataset_path": str(DATASET.relative_to(ROOT)),
        "seed": SEED,
        "candidate": False,
        "formal_recommendation": False,
        "gate4_decision": "NOT_REQUESTED",
        "sample_count": len(matches),
        "initial_train_size": INITIAL_TRAIN_SIZE,
        "fold_count": len(walk["folds"]),
        "leakage_check": leakage,
        **walk,
    }


def main() -> int:
    report = build_report()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE {REPORT.relative_to(ROOT)}")
    print(f"VERDICT={report['verdict']}")
    print(f"MODEL_LOG_LOSS={report['model_metrics']['log_loss']}")
    print(f"MARKET_LOG_LOSS={report['market_baseline_metrics']['log_loss']}")
    print(f"LEAKAGE={report['leakage_check']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
