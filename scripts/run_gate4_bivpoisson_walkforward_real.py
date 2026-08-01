#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from w2.models.bivariate_poisson import (
    BivariatePoissonMatch,
    fit_bivariate_poisson,
    one_x_two_probabilities,
)
from w2.models.evaluation import EvaluationRow, metrics, paired_bootstrap_delta

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DATASET = ROOT / "runtime" / "stage5b" / "processed" / "national_fixtures_cleaned.json"
FIXTURE_DATASET = (
    ROOT / "tests" / "fixtures" / "gate4" / "stage5b_real_national_fixtures_cleaned.json"
)
REPORT = ROOT / "reports" / "W2_GATE4_BIVPOISSON_WALKFORWARD_REAL.json"
SEED = 20260625
INITIAL_TRAIN_FIXTURES = 240


def parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def normalize_market_probabilities(snapshot: dict[str, Any]) -> dict[str, float]:
    odds = {
        "HOME": float(snapshot["odds_1x2_home"]),
        "DRAW": float(snapshot["odds_1x2_draw"]),
        "AWAY": float(snapshot["odds_1x2_away"]),
    }
    if any(value <= 1.0 for value in odds.values()):
        raise ValueError("1X2 odds must be greater than one")
    implied = {key: 1.0 / value for key, value in odds.items()}
    total = sum(implied.values())
    return {key: value / total for key, value in implied.items()}


def parse_match(row: dict[str, Any]) -> BivariatePoissonMatch:
    snapshot = cast(dict[str, Any], row["pre_match_feature_snapshot"])
    return BivariatePoissonMatch(
        fixture_id=str(row["fixture_uuid"]),
        kickoff_utc=parse_date(str(row["match_date"])),
        home_team=str(row["home_team"]),
        away_team=str(row["away_team"]),
        home_goals=int(row["home_goals_90"]),
        away_goals=int(row["away_goals_90"]),
        market_probabilities=normalize_market_probabilities(snapshot),
        competition=str(row["competition"]),
        season=str(row["season"]),
        neutral_site=bool(row["neutral_site"]),
    )


def dataset_path() -> Path:
    return RUNTIME_DATASET if RUNTIME_DATASET.exists() else FIXTURE_DATASET


def load_matches() -> list[BivariatePoissonMatch]:
    source = dataset_path()
    rows = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Stage5B real fixture dataset must be a list")
    matches: list[BivariatePoissonMatch] = []
    for row in rows:
        typed_row = cast(dict[str, Any], row)
        if typed_row.get("fixture_status") != "FINISHED":
            continue
        if typed_row.get("odds_semantics") != "UNKNOWN_PREMATCH_AGGREGATE":
            continue
        try:
            matches.append(parse_match(typed_row))
        except (TypeError, ValueError):
            continue
    if any(match.fixture_id.startswith("dc-") for match in matches):
        raise ValueError("real-data harness must not use synthetic dc-* fixtures")
    return sorted(matches, key=lambda item: (item.kickoff_utc, item.fixture_id))


def dataset_source_row_count() -> int:
    rows = json.loads(dataset_path().read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Stage5B real fixture dataset must be a list")
    return len(rows)


def log_loss(probabilities: dict[str, float], actual: str) -> float:
    return -math.log(max(probabilities[actual], 1e-12))


def walk_forward(matches: list[BivariatePoissonMatch]) -> dict[str, Any]:
    if len(matches) <= INITIAL_TRAIN_FIXTURES:
        raise ValueError("real Stage5B dataset is too small for walk-forward")
    model_rows: list[EvaluationRow] = []
    market_rows: list[EvaluationRow] = []
    model_losses: list[float] = []
    market_losses: list[float] = []
    folds: list[dict[str, Any]] = []

    for test in matches:
        train = [match for match in matches if match.kickoff_utc < test.kickoff_utc]
        if len(train) < INITIAL_TRAIN_FIXTURES:
            continue
        parameters = fit_bivariate_poisson(train)
        probabilities = one_x_two_probabilities(parameters, test.home_team, test.away_team)
        if parameters.training_cutoff >= test.kickoff_utc:
            raise ValueError("leakage: training cutoff must be before test kickoff")
        model_rows.append(
            EvaluationRow(
                fixture_id=test.fixture_id,
                actual=test.actual_1x2,
                probabilities=probabilities,
                competition=test.competition,
                season=test.season,
                neutral_site=test.neutral_site,
            )
        )
        market_rows.append(
            EvaluationRow(
                fixture_id=test.fixture_id,
                actual=test.actual_1x2,
                probabilities=test.market_probabilities,
                competition=test.competition,
                season=test.season,
                neutral_site=test.neutral_site,
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
                "shared_lambda": parameters.shared_lambda,
                "actual": test.actual_1x2,
                "model_log_loss": round(model_loss, 6),
                "market_log_loss": round(market_loss, 6),
            }
        )
    delta = paired_bootstrap_delta(model_losses, market_losses, samples=800, seed=SEED)
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


def leakage_check(
    matches: list[BivariatePoissonMatch],
    folds: list[dict[str, Any]],
) -> dict[str, Any]:
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
    folds = cast(list[dict[str, Any]], walk["folds"])
    leakage = leakage_check(matches, folds)
    source = dataset_path()
    return {
        "schema_version": "W2_GATE4_BIVPOISSON_WALKFORWARD_REAL_V1",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "model": "BIVARIATE_POISSON",
        "model_version": "gate4.bivariate_poisson.v1",
        "dataset_kind": "W2_STAGE5B_REAL_HISTORY",
        "dataset_path": str(source.relative_to(ROOT)),
        "dataset_source_rows": dataset_source_row_count(),
        "dataset_fixture_count": len(matches),
        "excluded_row_count": dataset_source_row_count() - len(matches),
        "snapshot_semantics": "UNKNOWN_PREMATCH_AGGREGATE",
        "as_of_claim": False,
        "seed": SEED,
        "candidate": False,
        "formal_recommendation": False,
        "gate4_decision": "NOT_REQUESTED",
        "initial_train_fixtures": INITIAL_TRAIN_FIXTURES,
        "fold_count": len(folds),
        "leakage_check": leakage,
        **walk,
    }


def main() -> int:
    report = build_report()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE {REPORT.relative_to(ROOT)}")
    print(f"DATASET_FIXTURES={report['dataset_fixture_count']}")
    print(f"VERDICT={report['verdict']}")
    print(f"MODEL_LOG_LOSS={report['model_metrics']['log_loss']}")
    print(f"MARKET_LOG_LOSS={report['market_baseline_metrics']['log_loss']}")
    print(f"CI={report['bootstrap_95ci_model_minus_market_log_loss']}")
    print(f"LEAKAGE={report['leakage_check']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
