from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from w2.strategy.shadow import (
    SHADOW_STRATEGY_VERSION,
    ShadowStrategyEngine,
    ShadowStrategyLedger,
    manifest_payload,
    stable_sha256,
    write_json,
)
from w2.strategy.shadow_demo import demo_inputs

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def run_replay() -> dict[str, Any]:
    engine = ShadowStrategyEngine()
    ledger = ShadowStrategyLedger()
    decisions = []
    locks = []
    for item in demo_inputs():
        decision = engine.evaluate(item)
        lock = ledger.lock(decision)
        repeated = ledger.lock(decision)
        assert repeated.decision_hash == lock.decision_hash
        decisions.append(decision.as_dict())
        locks.append(
            {
                "fixture_id": lock.fixture_id,
                "phase": lock.phase,
                "strategy_version": lock.strategy_version,
                "decision_hash": lock.decision_hash,
                "locked_at": lock.locked_at.isoformat().replace("+00:00", "Z"),
            }
        )
    manifest = manifest_payload(ROOT)
    manifest_hash = stable_sha256(manifest)
    return {
        "run_id": "stage9a-offline-shadow-replay",
        "strategy_version": SHADOW_STRATEGY_VERSION,
        "manifest": manifest,
        "manifest_sha256": manifest_hash,
        "mode": "OFFLINE_REPLAY",
        "network": "DISABLED",
        "formal_recommendation": False,
        "candidate": False,
        "decisions": decisions,
        "locks": locks,
        "events": ledger.events,
        "threshold_sensitivity": {
            "status": "RESEARCH_ONLY_NOT_PROMOTED",
            "tested_penalties": ["0.025", "0.035", "0.050"],
        },
    }


def main() -> None:
    replay = run_replay()
    grades: dict[str, int] = {}
    hard_gates: dict[str, int] = {}
    for decision in replay["decisions"]:
        grades[decision["published_grade"]] = grades.get(decision["published_grade"], 0) + 1
        if decision["primary"]:
            for reason in decision["primary"]["hard_gate_reasons"]:
                hard_gates[reason] = hard_gates.get(reason, 0) + 1
        for reason in decision["skip_reasons"]:
            hard_gates[reason] = hard_gates.get(reason, 0) + 1

    write_json(REPORTS / "W2_STAGE9A_SHADOW_REPLAY.json", replay)
    write_json(
        REPORTS / "W2_STAGE9A_GRADE_DISTRIBUTION.json",
        {"strategy_version": SHADOW_STRATEGY_VERSION, "grades": grades},
    )
    write_json(
        REPORTS / "W2_STAGE9A_HARD_GATE_AUDIT.json",
        {"strategy_version": SHADOW_STRATEGY_VERSION, "reason_counts": hard_gates},
    )
    result = (
        "# W2 Stage 9A Result\n\n"
        "STAGE_9A=COMPLETED_LOCAL\n\n"
        "SHADOW_STRATEGY=READY_LOCAL_STAGING\n\n"
        "GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING\n\n"
        "GATE_5_STRATEGY=NOT_STARTED\n\n"
        "FORMAL_RECOMMENDATION=false\n\n"
        "CANDIDATE=false\n\n"
        "SERVER_DEPLOYMENT=NOT_PERFORMED\n"
    )
    (REPORTS / "W2_STAGE9A_RESULT.md").write_text(result, encoding="utf-8")
    print(json.dumps({"status": "PASS", "decisions": len(replay["decisions"])}, sort_keys=True))


if __name__ == "__main__":
    main()
