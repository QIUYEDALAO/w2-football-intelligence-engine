#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "src/w2/backtest/replay.py",
    "migrations/versions/0007_create_stage8_replay.py",
    "docs/adr/ADR-0008-event-driven-backtest.md",
    "docs/backtest/W2_REPLAY_ENGINE_V1.md",
    "docs/backtest/W2_EVALUATION_POLICY_V1.md",
    "docs/backtest/W2_ABLATION_POLICY_V1.md",
    "scripts/run_stage8_replay.py",
]
REPORT_ARTIFACTS = [
    "reports/W2_STAGE8_REPLAY_SUMMARY.json",
    "reports/W2_STAGE8_MODEL_COMPARISON.json",
    "reports/W2_STAGE8_ABLATION.json",
    "reports/W2_STAGE8_RESULT.md",
]


def fail(message: str) -> None:
    print(f"W2 Stage8 replay check FAIL: {message}", file=sys.stderr)
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
        "ReplayClock",
        "ReplayEvent",
        "EventOrderingPolicy",
        "AsOfDataRepository",
        "FeatureBuildStep",
        "ModelLoadStep",
        "PredictionStep",
        "EvaluationStep",
        "ReplayCheckpoint",
        "ReplayLedger",
        "ReplayManifest",
        "chronological_holdout",
        "rolling_window",
        "expanding_window",
        "walk_forward",
        "season_based_future_test",
        "nested_walk_forward",
    ]:
        if token not in combined:
            fail(f"missing Stage8 token {token}")
    if all((ROOT / path).is_file() for path in REPORT_ARTIFACTS):
        summary = load("reports/W2_STAGE8_REPLAY_SUMMARY.json")
        comparison = load("reports/W2_STAGE8_MODEL_COMPARISON.json")
        ablation = load("reports/W2_STAGE8_ABLATION.json")
        result = read("reports/W2_STAGE8_RESULT.md")
        if summary["fixture_count"] != 214:  # type: ignore[index]
            fail("Stage8 replay must use the paired Stage7/Stage6 fixture set")
        if summary["checkpoint_resume_matches_full_run"] is not True:  # type: ignore[index]
            fail("checkpoint resume must match full run")
        if summary["idempotent_replay"] is not True:  # type: ignore[index]
            fail("replay must be idempotent")
        if summary["future_leakage"] is not False or summary["fixture_split_leakage"] is not False:  # type: ignore[index]
            fail("leakage guards must pass")
        expected_models = {
            "uniform",
            "elo",
            "simple_poisson",
            "stage6_power_market",
            "stage6_dixon_coles_market",
            "stage7_best_independent",
            "stage7_calibrated_independent",
            "residual_blend_research_only",
        }
        if set(comparison["models"]) != expected_models:  # type: ignore[index]
            fail("model comparison set is incomplete")
        if comparison["ah"]["HISTORICAL_AH"] != "FORWARD_ONLY":  # type: ignore[index]
            fail("historical AH must stay forward-only")
        if set(ablation["runs"]) != {  # type: ignore[index]
            "remove_elo",
            "remove_rolling_form",
            "remove_rest_days",
            "remove_match_importance",
            "remove_neutral_site_adjustment",
            "remove_calibration",
            "remove_market_residual_layer",
        }:
            fail("ablation set incomplete")
        gate_path = ROOT / "archive/reports/W2_STAGE8_GATE4_AUDIT.json"
        if gate_path.is_file():
            gate = load("archive/reports/W2_STAGE8_GATE4_AUDIT.json")
            if gate["GATE_4_NATIONAL_1X2"] != "PROVISIONAL_NOT_PROMOTED":  # type: ignore[index]
                fail("Gate4 national must not be promoted")
            if gate["GATE_4_AH"] != "BLOCKED_FORWARD_ONLY":  # type: ignore[index]
                fail("Gate4 AH must remain blocked")
            for decision in gate["replay_decisions"]:  # type: ignore[index]
                if decision not in {"NOT_READY", "SKIP", "WATCH"}:
                    fail("invalid replay decision")
        if "CANDIDATE_OUTPUT=false" not in result or "RECOMMENDATION_OUTPUT=false" not in result:
            fail("Stage8 must not generate candidates or recommendations")
    if "runtime/replay/" not in read(".gitignore"):
        fail("runtime/replay must be gitignored")
    print("W2 Stage8 replay check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
