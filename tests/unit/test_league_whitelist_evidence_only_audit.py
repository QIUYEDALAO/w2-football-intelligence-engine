from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.run_w2_league_whitelist_audit import build_cli_payload
from scripts.summarize_w2_league_audit_diagnosis import build_diagnosis


def test_evidence_only_real_path_uses_only_mapping_fixture_and_odds_endpoints(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    requester = EvidenceRequester()

    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        real_provider_audit=True,
        approved_provider_calls=True,
        audit_mode="evidence-only",
        max_provider_calls=4,
        requester_factory=lambda _competition_id: requester,
    )

    result = payload["results"][0]
    endpoints = [endpoint for endpoint, _params in requester.calls]
    assert payload["audit_mode"] == "EVIDENCE_ONLY"
    assert payload["endpoint_allowlist"] == ["leagues", "fixtures", "odds"]
    assert payload["planned_provider_calls"] == 4
    assert payload["planned_provider_calls_by_endpoint"] == {
        "leagues": 1,
        "fixtures_future": 1,
        "fixtures_results": 1,
        "odds": 1,
    }
    assert endpoints == ["leagues", "fixtures", "fixtures", "odds"]
    assert not {"statistics", "lineups", "injuries"} & set(endpoints)
    assert payload["provider_calls"] == 4
    assert result["audit_mode"] == "EVIDENCE_ONLY"
    assert result["overall_status"] == "EVIDENCE_ONLY"
    assert result["can_enable"] is False
    assert result["enablement_evaluated"] is False
    assert result["evidence_only"] is True
    assert {item["name"] for item in result["items"]} == {
        "provider_mapping",
        "fixtures",
        "bookmaker_depth",
    }


def test_evidence_only_report_keeps_sanitized_observed_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")

    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        real_provider_audit=True,
        approved_provider_calls=True,
        audit_mode="evidence-only",
        out_dir=tmp_path,
        max_provider_calls=4,
        requester_factory=lambda _competition_id: EvidenceRequester(),
    )

    report_path = Path(payload["report_paths"][0])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    text = report_path.read_text(encoding="utf-8")
    observed = {
        field
        for item in report["items"]
        for field in item.get("observed_evidence", {})
    }
    assert report["audit_mode"] == "EVIDENCE_ONLY"
    assert report["endpoint_allowlist"] == ["leagues", "fixtures", "odds"]
    assert "raw_payload" not in text
    assert "x-apisports-key" not in text
    assert {
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
    }.issubset(observed)


def test_evidence_only_dry_run_has_zero_provider_calls_and_no_sleep() -> None:
    def fail_sleep(_seconds: float) -> None:
        raise AssertionError("dry-run must not sleep")

    payload = build_cli_payload(
        group="all_whitelist_competitions",
        audit_mode="evidence-only",
        sleeper=fail_sleep,
    )

    assert payload["status"] == "DRY_RUN_READY"
    assert payload["competition_count"] == 13
    assert payload["audit_mode"] == "EVIDENCE_ONLY"
    assert payload["endpoint_allowlist"] == ["leagues", "fixtures", "odds"]
    assert payload["planned_provider_calls"] == 52
    assert payload["provider_calls"] == 0
    assert payload["db_reads"] == 0
    assert payload["db_writes"] == 0


def test_evidence_only_diagnosis_does_not_require_enablement_only_items(
    tmp_path: Path,
) -> None:
    _write_evidence_only_report(tmp_path)

    payload = build_diagnosis(audit_dirs=[tmp_path])

    diagnosis = payload["diagnosis"]
    assert diagnosis["provider_mapping_review_required"] is True
    assert diagnosis["fixture_query_review_required"] is True
    assert diagnosis["bookmaker_coverage_review_required"] is True
    assert diagnosis["squad_value_mapping_required"] is False
    assert diagnosis["insufficient_diagnostic_evidence"] is False
    assert diagnosis["missing_observed_fields"] == []
    assert payload["provider_calls"] == 0
    assert payload["db_reads"] == 0
    assert payload["db_writes"] == 0


class EvidenceRequester:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(
        self,
        endpoint: str,
        params: dict[str, str],
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        self.calls.append((endpoint, params))
        return 200, {"x-ratelimit-requests-remaining": "90"}, _payload(endpoint)


def _payload(endpoint: str) -> dict[str, Any]:
    if endpoint == "leagues":
        return {
            "response": [
                {
                    "league": {"id": 71, "name": "Serie A"},
                    "country": {"name": "Brazil"},
                    "seasons": [{"year": 2026}],
                    "team_count": 20,
                }
            ]
        }
    if endpoint == "fixtures":
        return {
            "response": [
                {"fixture": {"id": "fixture-future-1"}, "goals": {"home": None, "away": None}},
            ]
        }
    if endpoint == "odds":
        return {
            "response": [
                {
                    "bookmakers": [
                        {
                            "name": "BookA",
                            "bets": [
                                {"name": "Asian Handicap", "values": [{"value": "Home -0.25"}]},
                            ],
                        },
                        {
                            "name": "BookB",
                            "bets": [
                                {"name": "Asian Handicap", "values": [{"value": "Away +0.25"}]},
                            ],
                        },
                        {
                            "name": "BookC",
                            "bets": [
                                {"name": "Goals Over/Under", "values": [{"value": "Over 2.5"}]},
                            ],
                        },
                    ]
                }
            ]
        }
    return {"response": []}


def _write_evidence_only_report(tmp_path: Path) -> None:
    report = {
        "competition_id": "brasileirao_serie_a",
        "audit_mode": "EVIDENCE_ONLY",
        "overall_status": "EVIDENCE_ONLY",
        "status": "EVIDENCE_ONLY",
        "can_enable": False,
        "items": [
            {
                "name": "provider_mapping",
                "status": "FAIL",
                "message": "provider mapping mismatch",
                "evidence_fixture_ids": [],
                "observed_evidence": {
                    "observed_provider_league_id": "71",
                    "observed_provider_league_name": "Serie A",
                    "observed_provider_country": "Brazil",
                    "observed_provider_season": "2026",
                    "observed_provider_team_count": 20,
                },
            },
            {
                "name": "fixtures",
                "status": "FAIL",
                "message": "FIXTURES_QUERY_REVIEW_REQUIRED",
                "evidence_fixture_ids": [],
                "observed_evidence": {
                    "observed_fixture_query_params": {
                        "future": {"league": "71", "season": "2026", "next": "5"}
                    },
                    "observed_fixture_response_count": 0,
                },
            },
            {
                "name": "bookmaker_depth",
                "status": "FAIL",
                "message": "bookmaker depth missing",
                "evidence_fixture_ids": [],
                "observed_evidence": {
                    "observed_bookmaker_count": 0,
                    "observed_ah_ou_market_names": ["asian handicap"],
                    "observed_has_ah": False,
                    "observed_has_ou": False,
                    "observed_has_line": False,
                },
            },
        ],
        "blockers": [
            "provider_mapping:FAIL",
            "fixtures:FAIL",
            "bookmaker_depth:FAIL",
        ],
        "warnings": [],
        "actual_provider_calls": 4,
    }
    (tmp_path / "W2_WHITELIST_AUDIT_brasileirao_serie_a.json").write_text(
        json.dumps(report, ensure_ascii=False),
        encoding="utf-8",
    )
