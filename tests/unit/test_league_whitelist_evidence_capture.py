from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.run_w2_league_whitelist_audit import build_cli_payload
from scripts.summarize_w2_league_audit_diagnosis import build_diagnosis


def test_provider_audit_report_captures_sanitized_observed_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")

    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        real_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=13,
        out_dir=tmp_path,
        requester_factory=lambda _competition_id: EvidenceRequester(),
    )

    report = json.loads(Path(payload["report_paths"][0]).read_text(encoding="utf-8"))
    items = {item["name"]: item for item in report["items"]}

    assert items["provider_mapping"]["status"] == "PASS"
    assert items["provider_mapping"]["observed_evidence"] == {
        "observed_provider_league_id": "71",
        "observed_provider_league_name": "Observed Brasileirao",
        "observed_provider_country": "Observed Country",
        "observed_provider_season": "2026",
        "observed_provider_team_count": 18,
        "expected_provider_league_id": "71",
        "expected_provider_league_name": "Serie A",
        "expected_provider_country": "Brazil",
        "expected_provider_season": "2026",
        "expected_provider_team_count": 20,
        "advisory_mismatches": ["name", "country", "team_count"],
    }
    assert items["fixtures"]["status"] == "FAIL"
    assert items["fixtures"]["observed_evidence"] == {
        "observed_fixture_query_params": {"league": "71", "next": "5", "season": "2026"},
        "observed_fixture_response_count": 0,
    }
    assert items["bookmaker_depth"]["status"] == "FAIL"
    assert items["bookmaker_depth"]["observed_evidence"] == {
        "observed_ah_ou_market_names": ["asian handicap"],
        "observed_bookmaker_count": 1,
        "observed_has_ah": True,
        "observed_has_line": True,
        "observed_has_ou": False,
    }
    assert report["can_enable"] is False


def test_provider_audit_report_keeps_bookmaker_depth_evidence_when_depth_is_too_low(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")

    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        real_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=13,
        out_dir=tmp_path,
        requester_factory=lambda _competition_id: EvidenceRequester(
            odds_response=[
                {
                    "bookmakers": [
                        {
                            "name": "BookA",
                            "bets": [
                                {"name": "Asian Handicap", "values": [{"value": "Home -0.25"}]},
                                {"name": "Goals Over/Under", "values": [{"value": "Over 2.5"}]},
                            ],
                        }
                    ]
                }
            ]
        ),
    )

    report = json.loads(Path(payload["report_paths"][0]).read_text(encoding="utf-8"))
    items = {item["name"]: item for item in report["items"]}

    assert items["bookmaker_depth"]["status"] == "FAIL"
    assert items["bookmaker_depth"]["observed_evidence"] == {
        "observed_ah_ou_market_names": ["asian handicap", "goals over/under"],
        "observed_bookmaker_count": 1,
        "observed_has_ah": True,
        "observed_has_line": True,
        "observed_has_ou": True,
    }
    assert payload["provider_calls"] == len(payload["results"][0]["items"])
    assert report["can_enable"] is False


def test_report_json_excludes_raw_payload_headers_body_and_key(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")

    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        real_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=13,
        out_dir=tmp_path,
        requester_factory=lambda _competition_id: EvidenceRequester(),
    )

    for path in [*payload["report_paths"], payload["audit_ledger_json"], payload["summary_json"]]:
        text = Path(str(path)).read_text(encoding="utf-8").lower()
        assert "raw_payload" not in text
        assert "request_headers" not in text
        assert '"headers"' not in text
        assert '"body"' not in text
        assert "x-apisports-key" not in text


def test_diagnosis_evidence_gap_false_when_report_has_observed_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    build_cli_payload(
        competition_id="brasileirao_serie_a",
        real_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=13,
        out_dir=tmp_path,
        requester_factory=lambda _competition_id: EvidenceRequester(),
    )

    payload = build_diagnosis(audit_dirs=[tmp_path])

    assert payload["diagnosis"]["insufficient_diagnostic_evidence"] is False
    assert payload["diagnosis"]["missing_observed_fields"] == []
    assert payload["provider_calls"] == 0
    assert payload["db_reads"] == 0
    assert payload["db_writes"] == 0


class EvidenceRequester:
    def __init__(self, odds_response: list[dict[str, Any]] | None = None) -> None:
        self.odds_response = odds_response

    def __call__(
        self,
        endpoint: str,
        params: dict[str, str],
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        if endpoint == "leagues":
            return 200, {}, {
                "response": [
                    {
                        "league": {"id": 71, "name": "Observed Brasileirao"},
                        "country": {"name": "Observed Country"},
                        "seasons": [{"year": 2026}],
                        "team_count": 18,
                    }
                ]
            }
        if endpoint == "fixtures" and params.get("status") == "FT":
            return 200, {}, {
                "response": [
                    {"fixture": {"id": "fixture-result-1"}, "goals": {"home": 1, "away": 0}}
                ]
            }
        if endpoint == "fixtures":
            return 200, {}, {"response": []}
        if endpoint == "statistics":
            return 200, {}, {
                "response": [
                    {"team": {"id": 1}, "statistics": [{"type": "xg", "value": "1.2"}]}
                ]
            }
        if endpoint == "lineups":
            return 200, {}, {"response": [{"team": {"id": 1}, "startXI": []}]}
        if endpoint == "injuries":
            return 200, {}, {"response": []}
        if endpoint == "odds":
            if self.odds_response is not None:
                return 200, {}, {"response": self.odds_response}
            return 200, {}, {
                "response": [
                    {
                        "bookmakers": [
                            {
                                "name": "BookA",
                                "bets": [
                                    {
                                        "name": "Asian Handicap",
                                        "values": [{"value": "Home -0.25"}],
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        return 200, {}, {"response": []}
