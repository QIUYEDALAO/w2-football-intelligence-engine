#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "reports/W2_STAGE7B_FORWARD_HOLDOUT_PROTOCOL.json"


def main() -> int:
    payload = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    if payload["status"] not in {"NOT_READY", "SKIP", "WATCH"}:
        raise SystemExit("invalid forward holdout status")
    if payload.get("candidate_output") or payload.get("recommendation_output"):
        raise SystemExit("forward lock cannot emit candidate or recommendation")
    print("W2 Stage7B forward prediction lock check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
