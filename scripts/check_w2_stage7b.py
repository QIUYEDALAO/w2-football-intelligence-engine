#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "src/w2/models/challenger.py",
    "src/w2/infrastructure/persistence/challenger_models.py",
    "migrations/versions/0008_create_stage7b_challenger.py",
    "docs/adr/ADR-0009-national-challenger-and-forward-holdout.md",
    "docs/models/W2_CHALLENGER_POLICY_V1.md",
    "docs/models/W2_FORWARD_HOLDOUT_POLICY_V1.md",
    "archive/scripts/run_stage7b_challenger.py",
    "archive/scripts/lock_stage7b_forward_predictions.py",
    "reports/W2_STAGE7B_DATA_EXPANSION.json",
    "reports/W2_STAGE7B_CHALLENGER_COMPARISON.json",
    "reports/W2_STAGE7B_FROZEN_MODEL_MANIFEST.json",
    "reports/W2_STAGE7B_FORWARD_HOLDOUT_PROTOCOL.json",
    "reports/W2_STAGE7B_RESULT.md",
]


def fail(message: str) -> None:
    print(f"W2 Stage7B check FAIL: {message}", file=sys.stderr)
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
        "AuditSetFreeze",
        "ForwardPredictionLock",
        "REGULARIZED_MULTICLASS_LOGISTIC",
        "GRADIENT_BOOSTING",
        "ELO_POISSON_STACKING",
        "CONSTRAINED_ENSEMBLE",
        "challenger_model",
        "forward_holdout_run",
        "forward_prediction_lock",
        "forward_evaluation",
    ]:
        if token not in combined:
            fail(f"missing Stage7B token {token}")
    expansion = load("reports/W2_STAGE7B_DATA_EXPANSION.json")
    comparison = load("reports/W2_STAGE7B_CHALLENGER_COMPARISON.json")
    manifest = load("reports/W2_STAGE7B_FROZEN_MODEL_MANIFEST.json")
    protocol = load("reports/W2_STAGE7B_FORWARD_HOLDOUT_PROTOCOL.json")
    result = read("reports/W2_STAGE7B_RESULT.md")
    audit_set = manifest["audit_set"]  # type: ignore[index]
    if audit_set["fixture_count"] != 214:
        fail("Stage7/8 audit set must freeze 214 fixtures")
    if audit_set["status"] != "AUDIT_ONLY":
        fail("audit set must be AUDIT_ONLY")
    if comparison["audit_set_usage"] != "AUDIT_ONLY_NO_TUNING":  # type: ignore[index]
        fail("audit set must not be used for tuning")
    if comparison["no_candidate_or_recommendation"] is not True:  # type: ignore[index]
        fail("challenger comparison must not emit candidates or recommendations")
    if expansion["historical_odds_requested"] is not False:  # type: ignore[index]
        fail("Stage7B must not request historical odds")
    if expansion["quota_policy"]["requests_used"] > expansion["quota_policy"]["stage7b_max"]:  # type: ignore[index]
        fail("Stage7B API budget exceeded")
    if protocol["status"] not in {"NOT_READY", "SKIP", "WATCH"}:  # type: ignore[index]
        fail("forward holdout status invalid")
    if protocol["candidate_output"] or protocol["recommendation_output"]:  # type: ignore[index]
        fail("forward holdout must not emit candidate or recommendation")
    for token in [
        "GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING",
        "GATE_4_AH=BLOCKED_FORWARD_ONLY",
        "STAGE_9=BLOCKED",
        "CANDIDATE_OUTPUT=false",
        "RECOMMENDATION_OUTPUT=false",
        "PUSH_BLOCKED_NO_ORIGIN",
    ]:
        if token not in result:
            fail(f"missing status {token}")
    if "runtime/stage7b/" not in read(".gitignore"):
        fail("runtime/stage7b must be gitignored")
    print("W2 Stage7B check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
