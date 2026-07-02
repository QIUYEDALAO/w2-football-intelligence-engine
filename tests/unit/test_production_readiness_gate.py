from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from w2.operations.production_readiness import build_production_readiness_report


def test_production_readiness_passes_with_complete_read_only_rehearsal() -> None:
    report = build_production_readiness_report(
        dashboard=_dashboard_payload(formal=True),
        report_text="W2 report\nas-of：01:00\n状态：正式推荐",
        report_summary=_report_summary(),
        audit_manifest=_audit_manifest(),
        settlement_summary=_settlement_summary(inspected_locks=1, candidates=1),
        expected_sha="sha",
    )

    assert report["status"] == "PASS"
    assert report["provider_calls"] == 0
    assert report["db_writes"] == 0
    assert report["production_deploy"] is False
    assert report["blockers"] == []


def test_production_readiness_blocks_invalid_formal_and_forbidden_report_copy() -> None:
    payload = _dashboard_payload(formal=True)
    match = payload["all"][0]
    match["recommendation"]["selection"] = "UNKNOWN"

    report = build_production_readiness_report(
        dashboard=payload,
        report_text="方向未识别",
        report_summary=_report_summary(),
        audit_manifest=_audit_manifest(),
        settlement_summary=_settlement_summary(inspected_locks=1, candidates=1),
        expected_sha="sha",
    )

    assert report["status"] == "BLOCKED"
    codes = {item["code"] for item in report["blockers"]}
    assert "VALID_FORMAL_PAYLOADS" in codes
    assert "REPORT_COPY_SAFE" in codes


def test_production_readiness_warns_when_no_lock_or_settlement_candidate() -> None:
    report = build_production_readiness_report(
        dashboard=_dashboard_payload(formal=False),
        report_text="W2 report\nas-of：01:00\n状态：观察",
        report_summary=_report_summary(),
        audit_manifest=_audit_manifest(),
        settlement_summary=_settlement_summary(inspected_locks=0, candidates=0),
        expected_sha="sha",
    )

    assert report["status"] == "WARN_ONLY"
    codes = {item["code"] for item in report["warnings"]}
    assert "NO_DB_LOCK_SNAPSHOTS_FOR_REHEARSAL" in codes
    assert "NO_SETTLEMENT_CANDIDATES_FOR_REHEARSAL" in codes


def test_production_readiness_cli_input_skip_db_reports_blocked_without_writes(
    tmp_path: Path,
) -> None:
    payload_path = tmp_path / "dashboard.json"
    payload_path.write_text(json.dumps(_dashboard_payload(formal=False)), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/check_w2_production_readiness.py",
            "--input",
            str(payload_path),
            "--skip-db",
            "--expected-sha",
            "sha",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert any(
        item["code"] == "SETTLEMENT_DRY_RUN_NOT_EXECUTED"
        for item in payload["blockers"]
    )


def _dashboard_payload(*, formal: bool) -> dict[str, object]:
    recommendation = (
        {
            "tier": "FORMAL",
            "market": "ASIAN_HANDICAP",
            "selection": "HOME_AH",
            "line": "-0.5",
            "odds": "1.91",
            "expected_value": "0.12",
        }
        if formal
        else None
    )
    return {
        "generated_at": "2026-07-01T01:00:00Z",
        "selected_football_day": "2026-07-01",
        "all": [
            {
                "fixture_id": "fixture-1",
                "home_team_name": "Home",
                "away_team_name": "Away",
                "formal_recommendation": formal,
                "recommendation": recommendation,
                "pricing_shadow": {"beats_market": False},
            }
        ],
    }


def _report_summary() -> dict[str, object]:
    return {
        "status": "PASS",
        "health": {"version_sha": "sha"},
        "quota_summary": {
            "provider_calls": 0,
            "network_quota_required": False,
            "status": "NOT_REQUIRED_READ_ONLY_REPORT",
        },
    }


def _audit_manifest() -> dict[str, object]:
    return {
        "status": "PASS",
        "read_only": True,
        "provider_calls": 0,
        "db_writes": 0,
    }


def _settlement_summary(*, inspected_locks: int, candidates: int) -> dict[str, object]:
    return {
        "status": "PASS",
        "dry_run": True,
        "write_db": False,
        "provider_calls": 0,
        "db_writes": 0,
        "counts": {
            "inspected_locks": inspected_locks,
            "candidate_settlements": candidates,
        },
    }
