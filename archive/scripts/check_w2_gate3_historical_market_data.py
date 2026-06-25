#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "archive" / "reports"
INVENTORY = REPORTS / "W2_GATE3_HISTORICAL_MARKET_SOURCE_INVENTORY.json"
PHASE_COVERAGE = REPORTS / "W2_GATE3_PHASE_COVERAGE.json"
AH_WALK_FORWARD = REPORTS / "W2_GATE3_AH_WALK_FORWARD.json"
DECISION = REPORTS / "W2_GATE3_MARKET_BASELINE_DECISION.json"


def fail(message: str) -> None:
    print(f"W2 Gate3 historical market data check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        fail(f"missing {path.relative_to(ROOT)}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail(f"{path.name} must contain a JSON object")
    return payload


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def validate_common() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    inventory = load(INVENTORY)
    phase = load(PHASE_COVERAGE)
    ah = load(AH_WALK_FORWARD)
    decision = load(DECISION)
    require(inventory.get("candidate") is False, "inventory candidate flag must be false")
    require(
        inventory.get("formal_recommendation") is False,
        "inventory formal recommendation flag must be false",
    )
    require(phase.get("candidate") is False, "phase coverage candidate flag must be false")
    require(
        phase.get("formal_recommendation") is False,
        "phase coverage formal recommendation flag must be false",
    )
    require(ah.get("candidate") is False, "AH candidate flag must be false")
    require(ah.get("formal_recommendation") is False, "AH formal recommendation flag must be false")
    sha_re = re.compile(r"^[0-9a-f]{64}$")
    for source in inventory.get("sources", []):
        require(sha_re.match(source.get("sha256", "")) is not None, "source hash must be SHA256")
        require(
            source.get("snapshot_semantics")
            in {"CAPTURED_AT", "CLOSING", "UNKNOWN_PREMATCH_AGGREGATE", "INVALID_OR_UNUSABLE"},
            "invalid source snapshot semantics",
        )
        if source.get("snapshot_semantics") == "CAPTURED_AT":
            require(source.get("captured_at_field") is not None, "captured-at source missing field")
    phases = phase.get("phases", {})
    for required_phase in ("T-24h", "T-1h", "T-30m", "T-10m", "Closing"):
        require(required_phase in phases, f"missing phase {required_phase}")
    require(
        phase.get("excluded_closing_leakage_count", 0) == 0,
        "closing leakage into early phases must be zero",
    )
    baselight_resolved = set(
        decision.get("baselight", {}).get("resolved_by_baselight_limited_backtest", [])
    )
    if (
        ah.get("status") == "NO_USABLE_INTERNAL_HISTORICAL_AH_DATA"
        and "HISTORICAL_AH_BASELINE_BACKTEST_MISSING" not in baselight_resolved
    ):
        require(
            "HISTORICAL_AH_BASELINE_BACKTEST_MISSING" in decision.get("blockers", []),
            "AH no-data status must keep historical AH blocker",
        )
    return inventory, phase, ah, decision


def validate_closure() -> None:
    _, phase, ah, decision = validate_common()
    require(decision.get("status") == "CLOSED", "closure requires Gate3 CLOSED")
    require(decision.get("blockers") == [], "closure requires no Gate3 blockers")
    require(ah.get("status") == "READY", "closure requires AH walk-forward READY")
    require(phase.get("status") == "CAPTURED_AT_AVAILABLE", "closure requires captured-at coverage")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("audit", "closure"), default="audit")
    args = parser.parse_args(argv)
    if args.mode == "closure":
        validate_closure()
    else:
        validate_common()
    print(f"W2 Gate3 historical market data check PASS ({args.mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
