#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "reports/W2_GATE3_MARKET_BASELINE_DECISION.json"

MANDATORY_REQUIREMENTS = {
    "G3-1-1X2_CONSENSUS_DEVIG_REPRODUCIBLE",
    "G3-2-AH_CONSENSUS_PRICING_SETTLEMENT",
    "G3-3-OU_CONSENSUS_DEVIG_REPRODUCIBLE",
    "G3-4-COMPLETE_OU_LADDER_FITTING_BACKTEST",
    "G3-5-STRICT_SPLIT_OR_WALK_FORWARD_EVIDENCE",
    "G3-6-DATA_SOURCE_AND_SNAPSHOT_SEMANTICS_CLEAR",
    "G3-7-REPRODUCIBLE_RESULTS",
    "G3-8-LEAKAGE_GUARDS",
    "G3-9-NO_RECOMMENDATION_OR_INDEPENDENT_ADVANTAGE_CLAIM",
}


def fail(message: str) -> None:
    print(f"W2 Gate3 market baseline check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_decision() -> dict[str, Any]:
    if not DECISION.is_file():
        fail(f"missing {DECISION.relative_to(ROOT)}")
    payload = json.loads(DECISION.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail("decision payload must be a JSON object")
    return payload


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def validate_common(payload: dict[str, Any]) -> None:
    require(payload.get("gate") == 3, "gate must be 3")
    require(payload.get("status") in {"PARTIAL", "BLOCKED", "CLOSED"}, "invalid Gate3 status")
    require(payload.get("repository_head_relation") == "current as of containing commit",
            "repository head relation missing")
    requirements = payload.get("requirements")
    require(isinstance(requirements, dict), "requirements must be an object")
    require(set(requirements) == MANDATORY_REQUIREMENTS, "mandatory requirement set mismatch")
    for requirement_id, requirement in requirements.items():
        require(requirement.get("status") in {"PASS", "PARTIAL", "BLOCKED", "NOT_APPLICABLE"},
                f"invalid status for {requirement_id}")
        require(requirement.get("evidence"), f"missing evidence for {requirement_id}")
        require("metrics" in requirement, f"missing metrics for {requirement_id}")
        require("limitations" in requirement, f"missing limitations for {requirement_id}")
        require("blocker_codes" in requirement, f"missing blocker codes for {requirement_id}")
    require(
        payload.get("recommendation_output") is False,
        "recommendation output must remain false",
    )
    require(payload.get("candidate") is False, "candidate must remain false")
    require(payload.get("formal_recommendation") is False,
            "formal recommendation must remain false")
    one_x_two = payload.get("one_x_two", {})
    require(
        set(one_x_two.get("devig_methods", []))
        == {"LOGARITHMIC", "POWER", "PROPORTIONAL", "SHIN"},
        "1X2 must report all four devig methods",
    )
    require(
        one_x_two.get("method_selection_policy")
        == "train_validation_only_test_final_report",
        "method selection must not use final test rows",
    )
    require(one_x_two.get("snapshot_semantics") == "UNKNOWN_PREMATCH_AGGREGATE",
            "1X2 snapshot semantics must be explicit")
    totals = payload.get("totals", {})
    summary = totals.get("summary", {})
    require(summary.get("sample_count") == 128, "OU ladder sample count must be 128")
    require(summary.get("fit_failures") == 0, "OU fit failures must be reported as zero")
    require(summary.get("residuals") is None, "OU residuals belong in fixture diagnostics report")
    require(summary.get("snapshot_semantics") == "CLOSING", "OU semantics must be CLOSING")
    ah = payload.get("asian_handicap", {})
    require(ah.get("historical_ah_status") == "FORWARD_ONLY",
            "historical AH must remain FORWARD_ONLY until real backtest exists")
    leakage = payload.get("leakage_audit", {})
    require(leakage.get("closing_odds_not_used_for_early_phase") is True,
            "closing odds early-phase guard missing")
    require(leakage.get("historical_ah_fabricated") is False,
            "historical AH must not be fabricated")


def validate_closure(payload: dict[str, Any]) -> None:
    validate_common(payload)
    require(payload.get("status") == "CLOSED", "closure mode requires Gate3 status CLOSED")
    require(payload.get("blockers") == [], "closure mode requires no blockers")
    requirements = payload["requirements"]
    not_pass = [
        requirement_id
        for requirement_id, requirement in requirements.items()
        if requirement.get("status") != "PASS"
    ]
    require(not not_pass, f"closure mode requires all mandatory requirements PASS: {not_pass}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("audit", "closure"), default="audit")
    args = parser.parse_args(argv)
    payload = load_decision()
    if args.mode == "closure":
        validate_closure(payload)
    else:
        validate_common(payload)
    print(f"W2 Gate3 market baseline check PASS ({args.mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
