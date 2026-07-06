from __future__ import annotations

import json
import subprocess
import sys

from scripts.check_w2_league_remediation_readiness import build_readiness_payload


def test_remediation_readiness_reports_no_provider_or_db_calls() -> None:
    payload = build_readiness_payload()

    assert payload["profile_validation_status"] == "NEEDS_PROVIDER_EVIDENCE"
    assert payload["fixture_query_status"] == "FIXTURES_QUERY_REVIEW_REQUIRED"
    assert payload["odds_market_mapping_status"] == "PASS"
    assert payload["squad_value_source_status"] == "SQUAD_VALUE_SOURCE_MISSING"
    assert payload["ready_for_evidence_reaudit"] is True
    assert payload["ready_for_enablement_audit"] is False
    assert payload["ready_for_provider_reaudit"] is True
    assert payload["next_provider_audit_mode"] == "EVIDENCE_ONLY"
    assert payload["evidence_reaudit_blockers"] == []
    assert payload["enablement_blockers"] == [
        "NEEDS_PROVIDER_EVIDENCE",
        "SQUAD_VALUE_SOURCE_MISSING",
        "SEVEN_ITEM_AUDIT_NOT_PASSING",
    ]
    assert payload["evidence_only_audit_can_enable"] is False
    assert payload["provider_calls"] == 0
    assert payload["db_reads"] == 0
    assert payload["db_writes"] == 0
    assert payload["enabled_true"] is False


def test_remediation_readiness_cli_json_is_read_only() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/check_w2_league_remediation_readiness.py",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["provider_calls"] == 0
    assert payload["db_reads"] == 0
    assert payload["db_writes"] == 0
    assert payload["ready_for_evidence_reaudit"] is True
    assert payload["ready_for_enablement_audit"] is False
    assert payload["next_provider_audit_mode"] == "EVIDENCE_ONLY"


def test_squad_value_missing_blocks_enablement_only() -> None:
    payload = build_readiness_payload()

    assert payload["ready_for_evidence_reaudit"] is True
    assert "SQUAD_VALUE_SOURCE_MISSING" not in payload["evidence_reaudit_blockers"]
    assert "SQUAD_VALUE_SOURCE_MISSING" in payload["enablement_blockers"]
    assert payload["ready_for_enablement_audit"] is False


def test_provider_preflight_blockers_stop_evidence_reaudit() -> None:
    payload = build_readiness_payload(
        provider_key_header_safe=False,
        provider_quota_available=False,
        provider_hard_cap_valid=False,
    )

    assert payload["ready_for_evidence_reaudit"] is False
    assert payload["next_provider_audit_mode"] == "NOT_READY"
    assert payload["evidence_reaudit_blockers"] == [
        "PROVIDER_KEY_MISSING_OR_INVALID",
        "PROVIDER_QUOTA_MISSING",
        "PROVIDER_HARD_CAP_INVALID",
    ]
    assert payload["provider_calls"] == 0
    assert payload["db_reads"] == 0
    assert payload["db_writes"] == 0


def test_enabled_true_blocks_evidence_reaudit_and_enablement() -> None:
    payload = build_readiness_payload(enabled_national_leagues_override=["mls"])

    assert payload["enabled_true"] is True
    assert payload["ready_for_evidence_reaudit"] is False
    assert "ENABLED_TRUE_NOT_ALLOWED" in payload["evidence_reaudit_blockers"]
    assert "ENABLED_TRUE_NOT_ALLOWED" in payload["enablement_blockers"]
    assert payload["provider_calls"] == 0
