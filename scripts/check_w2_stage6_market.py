#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "src/w2/markets/consensus.py",
    "src/w2/markets/devig.py",
    "src/w2/markets/poisson.py",
    "src/w2/markets/movement.py",
    "src/w2/markets/quality.py",
    "src/w2/infrastructure/persistence/market_models.py",
    "migrations/versions/0005_create_stage6_market_baseline.py",
    "docs/adr/ADR-0006-market-baseline.md",
    "docs/models/W2_MARKET_BASELINE_V1.md",
    "docs/markets/W2_DEVIG_METHODS_V1.md",
    "docs/markets/W2_MARKET_MOVEMENT_FEATURES_V1.md",
    "scripts/run_stage6_market_backtest.py",
]
REPORT_ARTIFACTS = [
    "reports/W2_STAGE6_1X2_BACKTEST.json",
    "reports/W2_STAGE6_OU_BACKTEST.json",
    "reports/W2_STAGE6_MARKET_QUALITY.json",
    "reports/W2_STAGE6_RESULT.md",
]


def fail(message: str) -> None:
    print(f"W2 Stage6 market check FAIL: {message}", file=sys.stderr)
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
        "MarketConsensusBuilder",
        "PROPORTIONAL",
        "SHIN",
        "POWER",
        "LOGARITHMIC",
        "fit_total_goals_mu",
        "DixonColesBaseline",
        "MarketQualityAssessor",
        "MovementFeatureBuilder",
        "CALIBRATION_REQUIRED",
        "FORWARD_ONLY",
        "market_consensus",
        "market_baseline_run",
        "market_fit_diagnostic",
    ]:
        if token not in combined:
            fail(f"missing Stage6 token {token}")
    if all((ROOT / path).is_file() for path in REPORT_ARTIFACTS):
        one_x_two = load("reports/W2_STAGE6_1X2_BACKTEST.json")
        ou = load("reports/W2_STAGE6_OU_BACKTEST.json")
        quality = load("reports/W2_STAGE6_MARKET_QUALITY.json")
        result = read("reports/W2_STAGE6_RESULT.md")
        if one_x_two["sample_count"] < 1000:  # type: ignore[index]
            fail("1X2 backtest must use Stage5B national sample")
        if one_x_two["snapshot_semantics"] != "UNKNOWN_PREMATCH_AGGREGATE":  # type: ignore[index]
            fail("1X2 semantics must stay UNKNOWN_PREMATCH_AGGREGATE")
        methods = set(one_x_two["methods"])  # type: ignore[index]
        if methods != {"PROPORTIONAL", "SHIN", "POWER", "LOGARITHMIC"}:
            fail("all four devig methods must be reported")
        if one_x_two["method_selection_policy"] != "train_validation_only_test_final_report":  # type: ignore[index]
            fail("method selection must not use test")
        if ou["summary"]["sample_count"] != 128:  # type: ignore[index]
            fail("OU backtest must use the 128-row W1 closing subset")
        if ou["summary"]["fit_failures"] != 0:  # type: ignore[index]
            fail("OU ladder fit should not fail on W1 subset")
        dc = ou["dixon_coles_market_baseline"]  # type: ignore[index]
        for key in [
            "one_x_two_log_loss",
            "ou_log_score",
            "btts_log_score",
            "exact_score_log_score",
        ]:
            if key not in dc:
                fail(f"missing Dixon-Coles metric {key}")
        if quality.get("historical_ah_status") != "FORWARD_ONLY":  # type: ignore[attr-defined]
            fail("historical AH must remain FORWARD_ONLY")
        if quality.get("recommendation_output") is not False:  # type: ignore[attr-defined]
            fail("Stage6 must not generate recommendations")
        for token in [
            "STAGE_6=COMPLETED",
            "RECOMMENDATION_OUTPUT=false",
            "NETWORK_USED=false",
            "API_QUOTA_USED=0",
            "PUSH_BLOCKED_NO_ORIGIN",
        ]:
            if token not in result:
                fail(f"missing final status {token}")
    print("W2 Stage6 market check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
