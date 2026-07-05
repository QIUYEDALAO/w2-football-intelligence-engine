from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_w2_league_whitelist_audit import build_cli_payload, summarize_output_dir

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_w2_league_whitelist_audit.py"


def test_cli_default_dry_run_has_zero_provider_calls() -> None:
    payload = _run("--group", "national_leagues", "--dry-run", "--json")

    assert payload["status"] == "DRY_RUN_READY"
    assert payload["competition_count"] == 8
    assert payload["planned_provider_calls"] == 56
    assert payload["planned_provider_calls_by_endpoint"] == {
        "leagues": 8,
        "fixtures_future": 8,
        "fixtures_results": 8,
        "statistics": 8,
        "lineups": 8,
        "injuries": 8,
        "odds": 8,
        "squad_value": 0,
    }
    assert payload["provider_calls"] == 0
    assert payload["db_reads"] == 0
    assert payload["db_writes"] == 0


def test_single_league_dry_run_has_report_shape() -> None:
    payload = _run("--competition-id", "brasileirao_serie_a", "--dry-run", "--json")
    result = payload["results"][0]

    assert result["competition_id"] == "brasileirao_serie_a"
    assert result["enabled"] is False
    assert result["provider_calls"] == 0
    assert result["planned_provider_calls"] == 7
    assert result["planned_provider_calls_by_endpoint"]["fixtures_future"] == 1
    assert result["planned_provider_calls_by_endpoint"]["fixtures_results"] == 1
    assert {item["name"] for item in result["audit_items"]} == {
        "provider_mapping",
        "fixtures",
        "results",
        "xg",
        "lineups_injuries",
        "bookmaker_depth",
        "squad_value",
    }


def test_execute_provider_without_approval_fails_closed() -> None:
    payload = _run(
        "--competition-id",
        "brasileirao_serie_a",
        "--execute-provider-audit",
        "--json",
    )

    assert payload["status"] == "NEED_USER_APPROVAL"
    assert payload["message"] == "NEED_USER_APPROVAL: LEAGUE_WHITELIST_PROVIDER_AUDIT"
    assert payload["provider_calls"] == 0
    assert payload["results"][0]["actual_provider_calls"] == 0


def test_missing_api_key_with_approval_fails_closed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("W2_API_FOOTBALL_API_KEY", raising=False)

    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        execute_provider_audit=True,
        approved_provider_calls=True,
    )

    assert payload["status"] == "PROVIDER_KEY_MISSING"
    assert payload["provider_calls"] == 0
    assert payload["results"][0]["provider_calls"] == 0


def test_hard_cap_exceeded_returns_zero_provider_calls() -> None:
    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        execute_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=6,
    )

    assert payload["status"] == "BLOCKED_BY_HARD_CAP"
    assert payload["provider_calls"] == 0


def test_dry_run_does_not_sleep() -> None:
    def fail_sleep(_seconds: float) -> None:
        raise AssertionError("dry-run must not throttle")

    payload = build_cli_payload(
        group="national_leagues_in_season",
        sleeper=fail_sleep,
    )

    assert payload["status"] == "DRY_RUN_READY"
    assert payload["provider_calls"] == 0


def test_approved_provider_execution_with_key_fails_closed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")

    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        execute_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=20,
    )
    cli_payload = _run(
        "--competition-id",
        "brasileirao_serie_a",
        "--execute-provider-audit",
        "--approved-provider-calls",
        "--max-provider-calls",
        "20",
        "--json",
    )

    assert payload["status"] == "PROVIDER_EXECUTION_NOT_IMPLEMENTED_IN_OFFLINE_HARNESS"
    assert cli_payload["status"] == payload["status"]
    assert payload["provider_calls"] == 0
    assert cli_payload["provider_calls"] == 0
    assert payload["results"][0]["actual_provider_calls"] == 0
    assert payload["results"][0]["can_enable"] is False
    assert payload["results"][0]["overall_status"] == payload["status"]


def test_out_dir_writes_json_to_tmp_path(tmp_path: Path) -> None:
    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        out_dir=tmp_path,
    )

    report_path = Path(payload["report_paths"][0])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_path.name == "W2_WHITELIST_AUDIT_brasileirao_serie_a.json"
    assert report["competition_id"] == "brasileirao_serie_a"
    assert "evidence_fixture_ids" in report


def test_summarize_output_dir_is_read_only_and_marks_season_review(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("W2_API_FOOTBALL_API_KEY", raising=False)
    (tmp_path / "audit_ledger.json").write_text(
        json.dumps([{"endpoint": "leagues"}, {"endpoint": "fixtures"}]),
        encoding="utf-8",
    )
    (tmp_path / "summary.json").write_text(
        json.dumps(
            {
                "actual_provider_calls_total": 25,
                "stopped_reason": "PROVIDER_HTTP_429",
            }
        ),
        encoding="utf-8",
    )
    _write_summary_report(
        tmp_path,
        "brasileirao_serie_a",
        "FAIL",
        warnings=["AUDIT_SEASON_FALLBACK: configured=2026 audited=2024"],
    )
    _write_summary_report(
        tmp_path,
        "argentina_primera",
        "PROVIDER_HTTP_429",
        blockers=["PROVIDER_HTTP_429"],
    )

    payload = summarize_output_dir(tmp_path)

    assert payload["provider_calls"] == 0
    assert payload["db_reads"] == 0
    assert payload["db_writes"] == 0
    assert payload["actual_provider_calls_total"] == 25
    assert payload["completed_leagues"] == ["brasileirao_serie_a"]
    assert payload["partial_leagues"] == ["argentina_primera"]
    assert "mls" in payload["unstarted_leagues"]
    assert payload["provider_mapping_or_season_review_required"] is True
    assert payload["recommended_next_action"] == "WAIT_FOR_PROVIDER_COOLDOWN_THEN_RESUME"
    assert payload["per_league"]["brasileirao_serie_a"][
        "provider_mapping_or_season_review_required"
    ] is True


def test_stage14a_is_not_national_league_evidence() -> None:
    text = Path("config/competitions/README.md").read_text(encoding="utf-8")

    assert "Do not use `scripts/run_stage14a_league_audit.py` as evidence" in text
    assert "scripts/run_w2_league_whitelist_audit.py" in text


def test_no_enabled_flips_or_tracked_artifact_dirs() -> None:
    national = sorted(Path("config/competitions/national_leagues").glob("*.json"))

    assert national
    assert all('"enabled": false' in path.read_text(encoding="utf-8") for path in national)
    assert _tracked_count("runtime") == 0
    assert _tracked_count("reports") == 0
    assert _tracked_count(":(glob)**/dist/**") == 0
    assert _tracked_count(".learnings") == 0


def _run(*args: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _tracked_count(pattern: str) -> int:
    result = subprocess.run(
        ["git", "ls-files", pattern],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return len([line for line in result.stdout.splitlines() if line.strip()])


def _write_summary_report(
    tmp_path: Path,
    competition_id: str,
    status: str,
    *,
    blockers: list[str] | None = None,
    warnings: list[str] | None = None,
) -> None:
    (tmp_path / f"W2_WHITELIST_AUDIT_{competition_id}.json").write_text(
        json.dumps(
            {
                "competition_id": competition_id,
                "overall_status": status,
                "status": status,
                "can_enable": False,
                "actual_provider_calls": 13,
                "items": [{"name": "provider_mapping", "status": "FAIL"}],
                "blockers": blockers or [],
                "warnings": warnings or [],
            }
        ),
        encoding="utf-8",
    )
