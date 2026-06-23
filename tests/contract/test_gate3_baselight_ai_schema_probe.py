from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "reports/W2_GATE3_BASELIGHT_AI_SCHEMA_PROBE.json"
DECISION = ROOT / "reports/W2_GATE3_MARKET_BASELINE_DECISION.json"
HANDOFF = ROOT / "reports/W2_CURRENT_HANDOFF.md"


def test_baselight_ai_schema_probe_is_conditional_candidate() -> None:
    probe = json.loads(PROBE.read_text(encoding="utf-8"))
    decision = json.loads(DECISION.read_text(encoding="utf-8"))

    assert probe["dataset"] == "@blt.ultimate_soccer_dataset"
    assert probe["odds_table"] == "match_betting_odds"
    assert probe["match_result_table"] == "matches"
    assert probe["baselight_status"] == "CONDITIONAL_GATE3_CANDIDATE"
    assert decision["baselight"]["status"] == "CONDITIONAL_GATE3_CANDIDATE"
    assert probe["asian_handicap"]["settled_fixture_count"] >= 500
    assert decision["baselight"]["settled_ah_fixture_count"] == 10858


def test_baselight_limitations_keep_gate3_partial() -> None:
    probe = json.loads(PROBE.read_text(encoding="utf-8"))
    decision = json.loads(DECISION.read_text(encoding="utf-8"))
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert probe["collected_at"]["observed_precision"] == "DATE_ONLY"
    assert decision["status"] == "PARTIAL"
    assert probe["candidate"] is False
    assert probe["formal_recommendation"] is False
    assert decision["candidate"] is False
    assert decision["formal_recommendation"] is False
    assert "BASELIGHT_INTRADAY_TIMESTAMP_UNAVAILABLE" in decision["baselight"][
        "remaining_limitations"
    ]
    assert "PRECISE_PHASE_COVERAGE_UNAVAILABLE" in decision["baselight"][
        "remaining_limitations"
    ]
    assert (
        decision["baselight"]["license_status"]
        == "DATASET_CC_BY_4_0_PLATFORM_EXPORT_UNVERIFIED"
    )
    assert "handoff_version: 26" in handoff
    assert "STAGE7I_LIFECYCLE_COLLECTOR_INACTIVE" in handoff

