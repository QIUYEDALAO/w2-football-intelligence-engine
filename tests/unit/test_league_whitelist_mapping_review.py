from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.summarize_w2_league_audit_diagnosis import build_diagnosis

LEAGUES = (
    "brasileirao_serie_a",
    "argentina_primera",
    "mls",
    "chinese_super_league",
    "allsvenskan",
    "eliteserien",
)


def test_combined_diagnosis_from_two_dirs(tmp_path: Path) -> None:
    first = tmp_path / "first"
    resume = tmp_path / "resume"
    _write_summary(first, 25)
    _write_summary(resume, 65)
    _write_report(first, "brasileirao_serie_a")
    _write_report(first, "argentina_primera", status="PROVIDER_HTTP_429")
    for league_id in LEAGUES[1:]:
        _write_report(resume, league_id)

    payload = build_diagnosis(audit_dirs=[first, resume])

    assert payload["status"] == "PASS"
    assert payload["competition_count"] == 6
    assert payload["completed_leagues"] == list(LEAGUES)
    assert payload["missing_leagues"] == []
    assert payload["provider_calls_total"] == 90
    assert payload["provider_calls"] == 0
    assert payload["db_reads"] == 0
    assert payload["db_writes"] == 0
    assert all(value is False for value in payload["can_enable_by_league"].values())
    assert payload["diagnosis"] == {
        "provider_mapping_review_required": True,
        "season_review_required": True,
        "bookmaker_coverage_review_required": True,
        "squad_value_mapping_required": True,
        "fixture_query_review_required": True,
        "insufficient_diagnostic_evidence": True,
        "missing_observed_fields": [
            "observed_provider_league_id",
            "observed_provider_league_name",
            "observed_provider_country",
            "observed_provider_season",
            "observed_provider_team_count",
            "observed_fixture_query_params",
            "observed_fixture_response_count",
            "observed_bookmaker_count",
            "observed_ah_ou_market_names",
            "observed_has_ah",
            "observed_has_ou",
            "observed_has_line",
        ],
    }
    assert "Do not rerun provider today; daily cap already reached." in payload[
        "recommended_next_actions"
    ]
    assert any(
        "Do not guess profile changes" in action
        for action in payload["recommended_next_actions"]
    )


def test_sufficient_observed_fields_clear_diagnostic_evidence_gap(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    _write_summary(audit_dir, 90)
    for league_id in LEAGUES:
        _write_report(audit_dir, league_id, extra=_observed_fields())

    payload = build_diagnosis(audit_dirs=[audit_dir])

    assert payload["diagnosis"]["insufficient_diagnostic_evidence"] is False
    assert payload["diagnosis"]["missing_observed_fields"] == []
    assert any(
        "update profile mapping from observed values only after reviewer approval" in action
        for action in payload["recommended_next_actions"]
    )


def test_missing_audit_dir_fails(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="AUDIT_OUTPUT_DIR_MISSING"):
        build_diagnosis(audit_dirs=[tmp_path / "missing"])


def test_raw_payload_fields_are_blocked(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    _write_summary(audit_dir, 1)
    _write_report(audit_dir, "brasileirao_serie_a", extra={"raw_payload": {"unsafe": True}})

    with pytest.raises(SystemExit, match="RAW_PAYLOAD_FIELD_NOT_ALLOWED"):
        build_diagnosis(audit_dirs=[audit_dir])


def test_out_file_can_write_to_tmp_path(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    _write_summary(audit_dir, 13)
    _write_report(audit_dir, "brasileirao_serie_a")
    out_file = tmp_path / "diagnosis.json"

    payload = build_diagnosis(audit_dirs=[audit_dir], out_file=out_file)

    assert payload["out_file"] == str(out_file)
    written = json.loads(out_file.read_text(encoding="utf-8"))
    assert written["provider_calls"] == 0


def test_out_file_to_non_tmp_path_is_blocked(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    _write_summary(audit_dir, 13)
    _write_report(audit_dir, "brasileirao_serie_a")

    with pytest.raises(SystemExit, match="OUT_FILE_MUST_BE_UNDER_TMP"):
        build_diagnosis(audit_dirs=[audit_dir], out_file=Path("diagnosis.json"))


def _write_summary(audit_dir: Path, calls: int) -> None:
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "summary.json").write_text(
        json.dumps({"actual_provider_calls_total": calls}),
        encoding="utf-8",
    )


def _write_report(
    audit_dir: Path,
    competition_id: str,
    *,
    status: str = "FAIL",
    extra: dict[str, object] | None = None,
) -> None:
    audit_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "competition_id": competition_id,
        "overall_status": status,
        "status": status,
        "can_enable": False,
        "actual_provider_calls": 13,
        "items": [
            {"name": "provider_mapping", "status": "FAIL"},
            {"name": "fixtures", "status": "FAIL"},
            {"name": "results", "status": "PASS"},
            {"name": "xg", "status": "PASS"},
            {"name": "lineups_injuries", "status": "PASS"},
            {"name": "bookmaker_depth", "status": "FAIL"},
            {"name": "squad_value", "status": "CANNOT_VERIFY"},
        ],
        "blockers": [
            "provider_mapping:FAIL",
            "fixtures:FAIL",
            "bookmaker_depth:FAIL",
            "squad_value:CANNOT_VERIFY",
        ],
        "warnings": ["AUDIT_SEASON_FALLBACK: configured=2026 audited=2024"],
    }
    if extra:
        payload.update(extra)
    (audit_dir / f"W2_WHITELIST_AUDIT_{competition_id}.json").write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )


def _observed_fields() -> dict[str, object]:
    return {
        "observed_provider_league_id": "71",
        "observed_provider_league_name": "Example League",
        "observed_provider_country": "Example Country",
        "observed_provider_season": "2024",
        "observed_provider_team_count": 20,
        "observed_fixture_query_params": {"league": "71", "season": "2024"},
        "observed_fixture_response_count": 3,
        "observed_bookmaker_count": 2,
        "observed_ah_ou_market_names": ["Asian Handicap", "Goals Over/Under"],
        "observed_has_ah": True,
        "observed_has_ou": True,
        "observed_has_line": True,
    }
