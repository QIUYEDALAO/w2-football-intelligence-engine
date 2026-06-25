from __future__ import annotations

import json
from pathlib import Path

from w2.strategy.operations import gate5_preflight
from w2.strategy.shadow import write_json

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def load(name: str) -> dict[str, object]:
    path = ROOT / name
    if not path.exists():
        raise SystemExit(f"missing {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    replay = load("reports/W2_STAGE9B_SHADOW_OPERATIONS.json")
    comparison = load("reports/W2_STAGE12B_W1_W2_COMPARISON.json")
    policy = load("config/policies/gate5_shadow_acceptance.v1.json")
    preflight = gate5_preflight(replay=replay, comparison=comparison, acceptance_policy=policy)
    if preflight.get("closed") is not False:
        raise SystemExit("Gate5 must not be CLOSED in preflight")
    if preflight.get("gate5_result") not in {
        "PROVISIONAL_BLOCKED_GATE4",
        "PROVISIONAL_FORWARD_SAMPLE_PENDING",
        "PROVISIONAL_TECHNICAL_GAPS",
        "READY_FOR_GATE5_REVIEW",
    }:
        raise SystemExit("invalid Gate5 preflight result")
    write_json(REPORTS / "W2_GATE5_PREFLIGHT.json", preflight)
    print("W2 Gate5 preflight check PASS")


if __name__ == "__main__":
    main()
