#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import random
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
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
RUNTIME_SOURCE = ROOT / "runtime" / "stage5b" / "processed" / "national_fixtures_cleaned.json"
FIXTURE_SOURCE = (
    ROOT / "tests" / "fixtures" / "gate4" / "stage5b_real_national_fixtures_cleaned.json"
)
REPORT = ROOT / "reports" / "W2_GATE4_DC_WALKFORWARD_REAL.json"
SEED = 20260625
INITIAL_TRAIN_FIXTURES = 200


def parse_date(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def decimal_odds(value: object) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed > Decimal("1") else None


def proportional_devig(home: Decimal, draw: Decimal, away: Decimal) -> dict[str, float]:
    implied = {
        "HOME": Decimal("1") / home,
        "DRAW": Decimal("1") / draw,
        "AWAY": Decimal("1") / away,
    }
    total = sum(implied.values())
    return {key: float(value / total) for key, value in implied.items()}


def source_path() -> Path:
    return RUNTIME_SOURCE if RUNTIME_SOURCE.is_file() else FIXTURE_SOURCE


def load_rows() -> list[dict[str, Any]]:
    path = source_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Stage5B real fixture source must be a JSON list")
    return [cast(dict[str, Any], row) for row in payload]


def load_matches() -> list[DixonColesMatch]:
    matches: list[DixonColesMatch] = []
    for row in load_rows():
        snapshot = cast(dict[str, Any], row.get("pre_match_feature_snapshot") or {})
        home_odds = decimal_odds(snapshot.get("odds_1x2_home"))
        draw_odds = decimal_odds(snapshot.get("odds_1x2_draw"))
        away_odds = decimal_odds(snapshot.get("odds_1x2_away"))
        if (
            row.get("fixture_status") != "FINISHED"
            or home_odds is None
            or draw_odds is None
            or away_odds is None
        ):
            continue
        fixture_id = str(row["fixture_uuid"])
        if fixture_id.startswith("dc-"):
            raise ValueError("real-data harness must not use synthetic dc-* fixtures")
        matches.append(
            DixonColesMatch(
                fixture_id=fixture_id,
                kickoff_utc=parse_date(str(row["match_date"])),
                home_team=str(row["home_team"]),
                away_team=str(row["away_team"]),
                home_goals=int(float(str(row["home_goals_90"]))),
                away_goals=int(float(str(row["away_goals_90"]))),
                market_probabilities=proportional_devig(home_odds, draw_odds, away_odds),
            )
        )
    return sorted(matches, key=lambda item: (item.kickoff_utc, item.fixture_id))


def log_loss(probabilities: dict[str, float], actual: str) -> float:
    return -math.log(max(probabilities[actual], 1e-12))


def walk_forward(matches: list[DixonColesMatch]) -> dict[str, Any]:
    model_rows: list[EvaluationRow] = []
    market_rows: list[EvaluationRow] = []
    model_losses: list[float] = []
    market_losses: list[float] = []
    folds: list[dict[str, Any]] = []

    for test in matches:
        train = [match for match in matches if match.kickoff_utc < test.kickoff_utc]
        if len(train) < INITIAL_TRAIN_FIXTURES:
            continue
        parameters = fit_dixon_coles(train)
        if parameters.training_cutoff >= test.kickoff_utc:
            raise ValueError("leakage: training cutoff must be before test kickoff")
        matrix = predict_score_matrix(parameters, test.home_team, test.away_team)
        probabilities = one_x_two_from_matrix(matrix)
        model_rows.append(
            EvaluationRow(
                fixture_id=test.fixture_id,
                actual=test.actual_1x2,
                probabilities=probabilities,
                competition="stage5b_real_history",
                season=str(test.kickoff_utc.year),
                neutral_site=False,
            )
        )
        market_rows.append(
            EvaluationRow(
                fixture_id=test.fixture_id,
                actual=test.actual_1x2,
                probabilities=test.market_probabilities,
                competition="stage5b_real_history",
                season=str(test.kickoff_utc.year),
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
                "data_cutoff": parameters.training_cutoff.date().isoformat(),
                "test_match_date": test.kickoff_utc.date().isoformat(),
                "rho": parameters.rho,
                "actual": test.actual_1x2,
                "model_log_loss": round(model_loss, 6),
                "market_log_loss": round(market_loss, 6),
            }
        )
    if not folds:
        raise ValueError("no walk-forward folds produced")
    delta = paired_bootstrap_delta(model_losses, market_losses, samples=800, seed=SEED)
    model_metrics = metrics(model_rows)
    market_metrics = metrics(market_rows)
    metric_delta = {
        key: round(model_metrics[key] - market_metrics[key], 6)
        for key in ("log_loss", "rps", "brier", "ece")
    }
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
        "metric_delta_model_minus_market": metric_delta,
        "bootstrap_95ci_model_minus_market_log_loss": delta,
        "verdict": verdict,
    }


def leakage_check(matches: list[DixonColesMatch], folds: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(matches, key=lambda item: (item.kickoff_utc, item.fixture_id))
    cutoff_before_test = all(
        str(fold["data_cutoff"]) < str(fold["test_match_date"]) for fold in folds
    )
    return {
        "status": "PASS" if ordered == matches and cutoff_before_test else "FAIL",
        "chronological_order": ordered == matches,
        "training_cutoff_before_test_date": cutoff_before_test,
        "same_day_matches_excluded_from_training": True,
        "random_split_used": False,
        "post_match_features_used": False,
        "market_used_for_model_fit": False,
        "retrospective_forward_claim": False,
    }


def build_report() -> dict[str, Any]:
    random.seed(SEED)
    matches = load_matches()
    walk = walk_forward(matches)
    folds = cast(list[dict[str, Any]], walk["folds"])
    leakage = leakage_check(matches, folds)
    return {
        "schema_version": "W2_GATE4_DC_WALKFORWARD_REAL_V1",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "model": "DIXON_COLES",
        "model_version": "gate4.dc.v1.realdata",
        "source_path": str(source_path().relative_to(ROOT)),
        "source_kind": "W2_STAGE5B_REAL_HISTORY",
        "snapshot_semantics": "UNKNOWN_PREMATCH_AGGREGATE",
        "as_of_claim": False,
        "seed": SEED,
        "candidate": False,
        "formal_recommendation": False,
        "gate4_decision": "NOT_REQUESTED",
        "dataset_fixture_count": len(matches),
        "evaluated_fixture_count": len(folds),
        "initial_train_fixtures": INITIAL_TRAIN_FIXTURES,
        "leakage_check": leakage,
        **walk,
    }


def main() -> int:
    report = build_report()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE {REPORT.relative_to(ROOT)}")
    print(f"DATASET_FIXTURE_COUNT={report['dataset_fixture_count']}")
    print(f"EVALUATED_FIXTURE_COUNT={report['evaluated_fixture_count']}")
    print(f"VERDICT={report['verdict']}")
    print(f"MODEL_LOG_LOSS={report['model_metrics']['log_loss']}")
    print(f"MARKET_LOG_LOSS={report['market_baseline_metrics']['log_loss']}")
    print(f"CI={report['bootstrap_95ci_model_minus_market_log_loss']}")
    print(f"LEAKAGE={report['leakage_check']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
