from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "reports/W2_BASELIGHT_MCP_PROBE.json"
MANIFEST = ROOT / "reports/W2_GATE3_BASELIGHT_LIMITED_AH_EXTRACT_MANIFEST.json"
WALK_FORWARD = ROOT / "reports/W2_GATE3_BASELIGHT_AH_WALK_FORWARD.json"
DECISION = ROOT / "reports/W2_GATE3_MARKET_BASELINE_DECISION.json"
HANDOFF = ROOT / "reports/W2_CURRENT_HANDOFF.md"


def test_live_mcp_probe_passed_with_redacted_report() -> None:
    probe = json.loads(PROBE.read_text(encoding="utf-8"))

    assert probe["status"] == "PASS"
    assert probe["api_key_present"] is True
    assert probe["sql_tool_detected"] is True
    assert probe["sql_tool_name"] == "baselight_sdk_query_execute"
    assert probe["odds_limit_query_status"] == "PASS"
    assert probe["matches_limit_query_status"] == "PASS"
    assert probe["query_row_counts"]["match_betting_odds"] <= 5
    assert probe["query_row_counts"]["matches"] <= 5
    assert probe["no_secret_logged"] is True
    assert probe["no_full_data_download"] is True
    assert probe["candidate"] is False
    assert probe["formal_recommendation"] is False


def test_limited_extract_blocker_keeps_gate3_partial() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    walk_forward = json.loads(WALK_FORWARD.read_text(encoding="utf-8"))
    decision = json.loads(DECISION.read_text(encoding="utf-8"))
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert manifest["extraction_attempt_status"] == "BASELIGHT_LIMITED_AH_EXTRACT_QUERY_PENDING"
    assert manifest["sample_file_exists"] is False
    assert manifest["row_count"] == 0
    assert walk_forward["status"] == "INSUFFICIENT_SAMPLE"
    assert "BASELIGHT_LIMITED_AH_EXTRACT_QUERY_PENDING" in walk_forward["blockers"]
    assert decision["status"] == "PARTIAL"
    assert decision["baselight"]["limited_extract_status"] == (
        "BASELIGHT_LIMITED_AH_EXTRACT_QUERY_PENDING"
    )
    assert decision["baselight"]["ah_walk_forward_status"] == "INSUFFICIENT_SAMPLE"
    assert decision["baselight"]["sample_sha256"] is None
    assert "BASELIGHT_INTRADAY_TIMESTAMP_UNAVAILABLE" in decision["baselight"][
        "remaining_limitations"
    ]
    assert "PRECISE_PHASE_COVERAGE_UNAVAILABLE" in decision["baselight"][
        "remaining_limitations"
    ]
    assert "EXPORT_AND_RETENTION_POLICY_UNVERIFIED" in decision["baselight"][
        "remaining_limitations"
    ]
    assert "handoff_version: 28" in handoff
    assert "candidate=false" in handoff
    assert "formal_recommendation=false" in handoff
