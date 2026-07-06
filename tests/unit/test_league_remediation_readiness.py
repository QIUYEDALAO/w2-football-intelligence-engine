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
    assert payload["ready_for_provider_reaudit"] is False
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
    assert payload["ready_for_provider_reaudit"] is False
