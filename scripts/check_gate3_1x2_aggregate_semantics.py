#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "reports" / "W2_GATE3_MARKET_BASELINE_DECISION.json"
DOC = ROOT / "docs" / "markets" / "W2_1X2_AGGREGATE_SEMANTICS_V1.md"


def fail(message: str) -> None:
    print(f"W2 Gate3 1X2 aggregate semantics check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def load_decision() -> dict[str, Any]:
    payload = json.loads(DECISION.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail("decision report must be a JSON object")
    return cast(dict[str, Any], payload)


def main() -> int:
    decision = load_decision()
    text = DOC.read_text(encoding="utf-8")
    one_x_two = decision.get("one_x_two", {})
    blockers = set(decision.get("blockers", []))

    require(
        one_x_two.get("snapshot_semantics") == "UNKNOWN_PREMATCH_AGGREGATE",
        "1X2 semantics changed unexpectedly",
    )
    require(decision.get("candidate") is False, "candidate flag must be false")
    require(
        decision.get("formal_recommendation") is False,
        "formal recommendation flag must be false",
    )
    require("UNKNOWN_PREMATCH_AGGREGATE" in text, "doc must define UNKNOWN_PREMATCH_AGGREGATE")
    require("Forbidden use:" in text and "as-of samples" in text, "doc must forbid as-of use")
    require(
        "This limitation is source-specific" in text,
        "doc must scope the limitation to the aggregate source",
    )
    require(
        "UNKNOWN_PREMATCH_AGGREGATE_LIMITS_AS_OF_CLAIMS" in blockers
        or "UNKNOWN_PREMATCH_AGGREGATE_NOT_AS_OF" in blockers,
        "Gate3 must retain a 1X2 aggregate-as-of blocker while evidence is aggregate-only",
    )
    require(decision.get("status") == "PARTIAL", "aggregate-only 1X2 must not close Gate3")
    print("W2 Gate3 1X2 aggregate semantics check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
