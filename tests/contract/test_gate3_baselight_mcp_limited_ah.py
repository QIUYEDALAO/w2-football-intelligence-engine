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


def test_limited_extract_pass_keeps_gate3_partial_with_date_only_limits() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    walk_forward = json.loads(WALK_FORWARD.read_text(encoding="utf-8"))
    decision = json.loads(DECISION.read_text(encoding="utf-8"))
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert manifest["extraction_attempt_status"] == "ODDS_DATE_WINDOW_SAMPLE_READY"
    assert manifest["extraction_method"] == "ODDS_DATE_WINDOW_THEN_MATCHES_METADATA_NO_JOIN"
    assert manifest["micro_batch_v3_status"] == "ODDS_DATE_WINDOW_SAMPLE_READY"
    assert manifest["sample_file_exists"] is True
    assert manifest["row_count"] == 72082
    assert manifest["fixture_count"] >= 500
    assert manifest["bookmaker_count"] >= 5
    assert manifest["line_bucket_count"] >= 8
    assert manifest["competition_count"] >= 5
    assert walk_forward["status"] == "PASS_LIMITED_WALK_FORWARD"
    assert walk_forward["fold_count"] >= 5
    assert not walk_forward["blockers"]
    assert decision["status"] == "PARTIAL"
    assert decision["baselight"]["limited_extract_status"] == "ODDS_DATE_WINDOW_SAMPLE_READY"
    assert decision["baselight"]["ah_walk_forward_status"] == "PASS_LIMITED_WALK_FORWARD"
    assert decision["baselight"]["extraction_method"] == (
        "ODDS_DATE_WINDOW_THEN_MATCHES_METADATA_NO_JOIN"
    )
    assert decision["baselight"]["micro_batch_v3_status"] == "PASS_LIMITED_WALK_FORWARD"
    assert decision["baselight"]["sample_sha256"] == (
        "eb493d9f67e7ac672d40a37ecb14efb615b307f8bb5152429338d9c27158831b"
    )
    assert "HISTORICAL_AH_BASELINE_BACKTEST_MISSING" in decision["baselight"][
        "resolved_by_baselight_limited_backtest"
    ]
    assert "AH_WALK_FORWARD_EVIDENCE_MISSING" in decision["baselight"][
        "resolved_by_baselight_limited_backtest"
    ]
    assert "BASELIGHT_INTRADAY_TIMESTAMP_UNAVAILABLE" in decision["baselight"][
        "remaining_limitations"
    ]
    assert "PRECISE_PHASE_COVERAGE_UNAVAILABLE" in decision["baselight"][
        "remaining_limitations"
    ]
    assert "EXPORT_AND_RETENTION_POLICY_UNVERIFIED" in decision["baselight"][
        "remaining_limitations"
    ]
    assert "CLOSING_ONLY_OU_LIMITS_PHASE_CLAIMS" in decision["baselight"][
        "remaining_limitations"
    ]
    assert "UNKNOWN_PREMATCH_AGGREGATE_LIMITS_AS_OF_CLAIMS" in decision["baselight"][
        "remaining_limitations"
    ]
    assert "handoff_version: 36" in handoff
    assert "candidate=false" in handoff
    assert "formal_recommendation=false" in handoff
