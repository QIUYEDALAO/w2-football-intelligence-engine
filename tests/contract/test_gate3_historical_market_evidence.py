from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "reports/W2_GATE3_HISTORICAL_MARKET_SOURCE_INVENTORY.json"
PHASE = ROOT / "reports/W2_GATE3_PHASE_COVERAGE.json"
AH = ROOT / "reports/W2_GATE3_AH_WALK_FORWARD.json"
DECISION = ROOT / "reports/W2_GATE3_MARKET_BASELINE_DECISION.json"
HANDOFF = ROOT / "reports/W2_CURRENT_HANDOFF.md"
ROADMAP = ROOT / "docs/W2_MASTER_ROADMAP.md"


def test_source_inventory_records_internal_market_assets() -> None:
    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))

    assert payload["source_count"] > 0
    assert payload["candidate"] is False
    assert payload["formal_recommendation"] is False
    semantics = {source["snapshot_semantics"] for source in payload["sources"]}
    assert "CAPTURED_AT" in semantics
    assert "CLOSING" in semantics
    for source in payload["sources"]:
        assert len(source["sha256"]) == 64
        assert source["snapshot_semantics"] in {
            "CAPTURED_AT",
            "CLOSING",
            "UNKNOWN_PREMATCH_AGGREGATE",
            "INVALID_OR_UNUSABLE",
        }


def test_phase_coverage_keeps_closing_out_of_early_phases() -> None:
    payload = json.loads(PHASE.read_text(encoding="utf-8"))

    assert payload["status"] == "CAPTURED_AT_AVAILABLE"
    assert payload["excluded_closing_leakage_count"] == 0
    assert (
        payload["phases"]["Closing"]["observation_count"]
        >= payload["phases"]["T-10m"]["observation_count"]
    )
    assert payload["candidate"] is False
    assert payload["formal_recommendation"] is False


def test_ah_walk_forward_truthfully_reports_no_usable_internal_data() -> None:
    payload = json.loads(AH.read_text(encoding="utf-8"))
    decision = json.loads(DECISION.read_text(encoding="utf-8"))

    assert payload["status"] == "NO_USABLE_INTERNAL_HISTORICAL_AH_DATA"
    assert payload["sample_count"] == 0
    assert payload["fixture_count"] == 0
    assert "HISTORICAL_AH_BASELINE_BACKTEST_MISSING" in decision["blockers"]
    assert "AH_WALK_FORWARD_EVIDENCE_MISSING" in decision["blockers"]


def test_historical_checker_audit_passes_and_closure_fails() -> None:
    audit = subprocess.run(
        [sys.executable, "scripts/check_w2_gate3_historical_market_data.py", "--mode", "audit"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    closure = subprocess.run(
        [sys.executable, "scripts/check_w2_gate3_historical_market_data.py", "--mode", "closure"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert audit.returncode == 0
    assert closure.returncode != 0
    assert "closure requires Gate3 CLOSED" in closure.stderr


def test_handoff_and_master_roadmap_boundaries_are_preserved() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")
    roadmap = ROADMAP.read_text(encoding="utf-8")

    assert "handoff_version: 29" in handoff
    assert "gate3_historical_source_inventory_path:" in handoff
    assert "gate3_external_source_decision_path:" in handoff
    assert "candidate: false" in handoff
    assert "formal_recommendation: false" in handoff
    assert "roadmap_version: 1" in roadmap
    assert "status: ACTIVE" in roadmap
