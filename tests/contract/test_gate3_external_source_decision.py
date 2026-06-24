from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQ = ROOT / "docs/data/W2_HISTORICAL_MARKET_SOURCE_REQUIREMENTS_V1.md"
COMPARISON = ROOT / "reports/W2_GATE3_EXTERNAL_SOURCE_COMPARISON.json"
DECISION = ROOT / "reports/W2_GATE3_MARKET_BASELINE_DECISION.json"
HANDOFF = ROOT / "reports/W2_CURRENT_HANDOFF.md"
ROADMAP = ROOT / "docs/W2_MASTER_ROADMAP.md"
SAMPLE = ROOT / "tests/fixtures/gate3_external_source/the_odds_api_schema_fixture.json"


def test_requirements_include_all_gate3_must_fields() -> None:
    text = REQ.read_text(encoding="utf-8")
    for field in [
        "provider",
        "provider_fixture_id",
        "competition",
        "season",
        "kickoff_utc",
        "bookmaker",
        "ASIAN_HANDICAP",
        "TOTALS",
        "captured_at",
        "settlement_semantics",
        "source_license",
        "source_payload_hash",
    ]:
        assert field in text
    for section in ["## MUST", "## SHOULD", "## OPTIONAL", "## DISQUALIFYING"]:
        assert section in text
    assert "Closing-only" in text


def test_comparison_provider_entries_have_requirement_results() -> None:
    payload = json.loads(COMPARISON.read_text(encoding="utf-8"))
    assert payload["candidate"] is False
    assert payload["formal_recommendation"] is False
    assert payload["decision"]["requires_user_approval"] is True
    assert payload["decision"]["acquisition_authorized"] is False
    assert payload["providers"]
    for provider in payload["providers"]:
        assert provider["provider_name"]
        assert provider["official_documentation_sources"]
        assert provider["requirement_results"]
        assert provider["overall_recommendation"] in {
            "TRIAL_CANDIDATE_REQUIRES_APPROVAL",
            "REFERENCE_ONLY",
            "NOT_RECOMMENDED_FOR_GATE3",
            "FORWARD_ONLY_SUPPLEMENT",
        }


def test_failed_must_or_unknown_license_is_not_approved() -> None:
    payload = json.loads(COMPARISON.read_text(encoding="utf-8"))
    for provider in payload["providers"]:
        must_results = provider["requirement_results"]["MUST"]
        has_must_fail = any(value["status"] == "FAIL" for value in must_results.values())
        unknown_license = must_results["source_license"]["status"] in {"UNKNOWN", "FAIL"}
        if has_must_fail or unknown_license:
            assert provider["approved_for_gate3"] is False
            assert provider["commercial_use_status"] != "APPROVED"


def test_public_sample_status_and_probe_do_not_create_dataset() -> None:
    payload = json.loads(COMPARISON.read_text(encoding="utf-8"))
    for provider in payload["providers"]:
        if provider["public_sample_availability"] == "PUBLIC_SAMPLE_UNAVAILABLE":
            assert provider["schema_probe_status"] != "VERIFIED"
    probe = subprocess.run(
        [
            sys.executable,
            "scripts/probe_w2_historical_market_source.py",
            "--provider",
            "the_odds_api",
            "--sample",
            str(SAMPLE),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
    result = json.loads(probe.stdout)
    assert result["schema_mappable"] is True
    assert result["formal_dataset_created"] is False
    assert result["candidate"] is False
    assert result["formal_recommendation"] is False
    assert "source_license" in result["missing_contract_fields"]
    assert result["result_settlement_available"] is False


def test_purchase_contact_contract_and_gate3_are_not_authorized() -> None:
    comparison = json.loads(COMPARISON.read_text(encoding="utf-8"))
    decision = json.loads(DECISION.read_text(encoding="utf-8"))
    handoff = HANDOFF.read_text(encoding="utf-8")
    roadmap = ROADMAP.read_text(encoding="utf-8")

    assert comparison["decision"]["status"] == "DECISION_REQUIRED"
    assert comparison["decision"]["purchase_authorized"] is False
    assert comparison["decision"]["provider_contact_authorized"] is False
    assert comparison["decision"]["contract_acceptance_authorized"] is False
    assert decision["status"] == "PARTIAL"
    assert decision["external_source_decision_status"] == "FORWARD_ONLY_ACCUMULATION_SELECTED"
    assert decision["acquisition_not_authorized"] is True
    assert decision["user_decision_required"] is False
    assert "handoff_version: 38" in handoff
    assert "gate3_acquisition_authorized: false" in handoff
    assert "roadmap_version: 1" in roadmap
    assert "candidate: false" in handoff
    assert "formal_recommendation: false" in handoff
