#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "src/w2/models/independent.py",
    "src/w2/models/calibration.py",
    "src/w2/models/evaluation.py",
    "src/w2/models/residuals.py",
    "src/w2/infrastructure/persistence/model_experiment_models.py",
    "migrations/versions/0006_create_stage7_independent_models.py",
    "docs/adr/ADR-0007-independent-models.md",
    "docs/models/W2_INDEPENDENT_MODEL_V1.md",
    "docs/models/W2_FEATURE_POLICY_V1.md",
    "docs/models/W2_CALIBRATION_POLICY_V1.md",
    "archive/scripts/run_stage7_model_experiments.py",
    "reports/W2_STAGE7_DATA_COVERAGE.json",
    "reports/W2_STAGE7_NATIONAL_MODEL_COMPARISON.json",
    "reports/W2_STAGE7_CLUB_MODEL_COMPARISON.json",
    "reports/W2_STAGE7_CALIBRATION.json",
    "archive/reports/W2_STAGE7_MARKET_RESIDUAL_RESEARCH.json",
    "archive/reports/W2_STAGE7_GATE4_DECISION.json",
    "reports/W2_STAGE7_RESULT.md",
]


def fail(message: str) -> None:
    print(f"W2 Stage7 model check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def load(path: str) -> object:
    return json.loads(read(path))


def main() -> int:
    for path in REQUIRED:
        if not (ROOT / path).is_file():
            fail(f"missing {path}")
    combined = "\n".join(read(path) for path in REQUIRED if path.endswith((".py", ".md")))
    for token in [
        "FEATURE_ALLOWLIST",
        "FORBIDDEN_MARKET_FIELDS",
        "TIME_DECAY_ELO",
        "INDEPENDENT_POISSON",
        "HISTORICAL_DIXON_COLES",
        "BIVARIATE_POISSON",
        "NEGATIVE_BINOMIAL",
        "HIERARCHICAL_ATTACK_DEFENCE",
        "TIME_DECAY_ATTACK_DEFENCE",
        "PLATT",
        "ISOTONIC",
        "BETA",
        "DIRICHLET_MULTICLASS",
        "paired_bootstrap_delta",
        "independent_minus_market",
        "model_experiment",
        "model_artifact",
        "calibration_artifact",
        "model_evaluation",
        "model_gate_decision",
    ]:
        if token not in combined:
            fail(f"missing Stage7 token {token}")
    coverage = load("reports/W2_STAGE7_DATA_COVERAGE.json")
    national = load("reports/W2_STAGE7_NATIONAL_MODEL_COMPARISON.json")
    club = load("reports/W2_STAGE7_CLUB_MODEL_COMPARISON.json")
    calibration = load("reports/W2_STAGE7_CALIBRATION.json")
    residual = load("archive/reports/W2_STAGE7_MARKET_RESIDUAL_RESEARCH.json")
    gate = load("archive/reports/W2_STAGE7_GATE4_DECISION.json")
    result = read("reports/W2_STAGE7_RESULT.md")
    if coverage["national_results"] != 1081:  # type: ignore[index]
        fail("national track must use 1081 results")
    if coverage["national_market_power_rows"] != 1074:  # type: ignore[index]
        fail("paired market set must use 1074 rows")
    if coverage["national_ou_subset_rows"] != 128:  # type: ignore[index]
        fail("national OU subset must use 128 rows")
    if coverage["club_results"] != 5270:  # type: ignore[index]
        fail("club track must use 5270 results")
    if coverage["feature_policy"] != "odds_market_bookmaker_line_fields_forbidden":  # type: ignore[index]
        fail("feature policy must forbid market fields")
    if national["market_comparison"]["same_test_rows_as_stage6"] is not True:  # type: ignore[index]
        fail("national comparison must use Stage6 test rows")
    expected_club_claim = "NO_MARKET_SUPERIORITY_CLAIM_NO_RELIABLE_HISTORICAL_MARKET_ODDS"
    if club.get("market_claim") != expected_club_claim:  # type: ignore[attr-defined]
        fail("club report must not claim market superiority")
    residual_is_research = (
        residual.get("research_only") is True  # type: ignore[attr-defined]
        and residual.get("not_edge_not_recommendation") is True  # type: ignore[attr-defined]
    )
    if not residual_is_research:
        fail("market residual must be research only")
    if gate["GATE_4_AH"] != "BLOCKED_FORWARD_ONLY":  # type: ignore[index]
        fail("AH gate must remain forward only")
    if gate["GATE_4_NATIONAL_1X2"] not in {"CLOSED", "PROVISIONAL_NOT_PROMOTED"}:  # type: ignore[index]
        fail("national Gate4 status invalid")
    if "RECOMMENDATION_OUTPUT=false" not in result or "CANDIDATE_OUTPUT=false" not in result:
        fail("Stage7 must not generate candidates or recommendations")
    if "runtime/model_artifacts/" not in read(".gitignore"):
        fail("model artifacts must be gitignored")
    if "W2_API_FOOTBALL_API_KEY" in json.dumps(coverage) + result:
        fail("API key environment name must not appear in reports")
    if not calibration["national"]["selection_policy"].startswith("validation_only"):  # type: ignore[index]
        fail("calibration must be validation selected")
    print("W2 Stage7 model check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
