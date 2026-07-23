from __future__ import annotations

import json
from pathlib import Path

from w2.infrastructure import persistence as _persistence
from w2.infrastructure.database import Base

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

REQUIRED_TABLES = {
    "shadow_strategy_run",
    "shadow_strategy_lock",
    "shadow_strategy_evaluation",
}

REQUIRED_REPORTS = {
    "W2_STAGE9A_SHADOW_REPLAY.json",
    "W2_STAGE9A_GRADE_DISTRIBUTION.json",
    "W2_STAGE9A_HARD_GATE_AUDIT.json",
    "W2_STAGE9A_RESULT.md",
}


def load_json(name: str) -> dict[str, object]:
    path = REPORTS / name
    if not path.exists():
        raise SystemExit(f"missing report: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    if _persistence.ShadowStrategyRunModel is None:
        raise SystemExit("shadow strategy persistence import failed")
    missing_tables = REQUIRED_TABLES.difference(Base.metadata.tables)
    if missing_tables:
        raise SystemExit(f"missing shadow tables: {sorted(missing_tables)}")
    for name in REQUIRED_REPORTS:
        if not (REPORTS / name).exists():
            raise SystemExit(f"missing report: {name}")
    replay = load_json("W2_STAGE9A_SHADOW_REPLAY.json")
    if replay.get("formal_recommendation") is not False or replay.get("candidate") is not False:
        raise SystemExit("shadow replay attempted formal publication")
    decisions = replay.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise SystemExit("shadow replay has no fixture decisions")
    for decision in decisions:
        if not isinstance(decision, dict):
            raise SystemExit("invalid shadow decision")
        if decision.get("public_decision") not in {"NOT_READY", "SKIP", "WATCH"}:
            raise SystemExit("invalid public decision")
        if decision.get("formal_recommendation") or decision.get("candidate"):
            raise SystemExit("forbidden publication flag")
        if decision.get("published_grade") in {"A", "B"}:
            raise SystemExit("Gate4 grade cap was not applied")
        if "most_likely_outcome" not in decision:
            raise SystemExit("missing every-fixture judgment")
    print("W2 Stage 9A shadow strategy check PASS")


if __name__ == "__main__":
    main()
