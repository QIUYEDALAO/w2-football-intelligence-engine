from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/W2_STAGE9B_SHADOW_OPERATIONS.json"


def main() -> None:
    if not REPORT.exists():
        raise SystemExit("missing Stage9B shadow operations report")
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    if payload.get("formal_recommendation") is not False or payload.get("candidate") is not False:
        raise SystemExit("Stage9B attempted formal publication")
    if payload.get("forward", {}).get("lock_count") != 0:
        raise SystemExit("unexpected forward lock in local-only Stage9B")
    if payload.get("retrospective", {}).get("status") != "RETROSPECTIVE_REPLAY":
        raise SystemExit("retrospective replay not clearly separated")
    for decision in payload.get("decisions", []):
        if decision.get("phase") != "RETROSPECTIVE_REPLAY":
            raise SystemExit("forward/retrospective phase mix detected")
        if decision.get("public_decision") not in {"NOT_READY", "SKIP", "WATCH"}:
            raise SystemExit("invalid public shadow decision")
    print("W2 Stage9B check PASS")


if __name__ == "__main__":
    main()
