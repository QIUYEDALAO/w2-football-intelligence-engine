from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "reports/W2_BASELIGHT_MCP_PROBE.json"
HANDOFF = ROOT / "reports/W2_CURRENT_HANDOFF.md"


def test_baselight_mcp_probe_report_is_desensitized() -> None:
    probe = json.loads(PROBE.read_text(encoding="utf-8"))

    assert probe["schema_version"] == "W2_BASELIGHT_MCP_PROBE_V1"
    assert probe["mcp_endpoint"] == "https://api.baselight.app/mcp"
    assert probe["status"] in {
        "BASELIGHT_API_KEY_REQUIRED",
        "LIVE_FLAG_REQUIRED",
        "SQL_TOOL_NOT_DETECTED",
        "PASS",
    }
    assert isinstance(probe["api_key_present"], bool)
    assert probe["no_full_data_download"] is True
    assert probe["no_secret_logged"] is True
    assert probe["candidate"] is False
    assert probe["formal_recommendation"] is False
    assert "query_row_counts" in probe


def test_handoff_records_mcp_probe_without_closing_gate3() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert "handoff_version: 42" in handoff
    assert "gate3_baselight_mcp_probe_path: reports/W2_BASELIGHT_MCP_PROBE.json" in handoff
    assert "gate3_baselight_api_key_required: true" in handoff
    assert "gate3_baselight_full_extract_status: NOT_STARTED" in handoff
    assert "Gate3 remains `PARTIAL`" in handoff
    assert "candidate=false" in handoff
    assert "formal_recommendation=false" in handoff
