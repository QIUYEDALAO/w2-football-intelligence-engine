from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.run_w2_league_whitelist_audit import build_cli_payload

from w2.competitions.league_whitelist_provider_audit import (
    AUDIT_PROVIDER_ENDPOINT_ALLOWLIST,
    IN_SEASON_NATIONAL_LEAGUES,
    ApiFootballLeagueAuditProvider,
    LocalProviderAuditLedger,
    ProviderAuditBudget,
    ProviderAuditStopped,
    _normalized_provider_key,
    evaluate_controlled_provider_league_audit,
)
from w2.competitions.registry import CompetitionRegistry


def test_provider_wrapper_respects_endpoint_allowlist() -> None:
    provider = _provider("brasileirao_serie_a", requester=FakeRequester())

    assert {"statistics", "injuries"}.issubset(AUDIT_PROVIDER_ENDPOINT_ALLOWLIST)
    try:
        provider._request("h2h", {}, league_id="71")  # noqa: SLF001
    except ProviderAuditStopped as exc:
        assert exc.status == "ENDPOINT_NOT_AUTHORIZED"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("h2h must not be authorized")


def test_cap_reached_stops_before_further_provider_calls() -> None:
    requester = FakeRequester()
    provider = _provider("brasileirao_serie_a", requester=requester, league_hard_cap=2)

    result = evaluate_controlled_provider_league_audit(
        _entry("brasileirao_serie_a"),
        environment="staging",
        provider=provider,
    )

    assert result.overall_status == "LEAGUE_PROVIDER_HARD_CAP_REACHED"
    assert len(requester.calls) == 2
    assert result.provider_calls == 2


def test_alternate_sample_is_used_at_most_once() -> None:
    requester = FakeRequester(empty_statistics_first=True)
    provider = _provider("brasileirao_serie_a", requester=requester)

    result = evaluate_controlled_provider_league_audit(
        _entry("brasileirao_serie_a"),
        environment="staging",
        provider=provider,
    )

    statistics_calls = [call for call in requester.calls if call[0] == "statistics"]
    assert len(statistics_calls) == 2
    assert {item.name: item.status.value for item in result.items}["xg"] == "PASS"


def test_429_quota_warning_stops_audit() -> None:
    requester = FakeRequester(status_by_endpoint={"leagues": 429})
    provider = _provider("brasileirao_serie_a", requester=requester)

    result = evaluate_controlled_provider_league_audit(
        _entry("brasileirao_serie_a"),
        environment="staging",
        provider=provider,
    )

    assert result.overall_status == "PROVIDER_HTTP_429"
    assert provider.ledger.records[0]["status_code"] == 429


def test_real_provider_audit_throttles_each_request(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    sleeps: list[float] = []
    requester = FakeRequester()

    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        real_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=13,
        request_interval_seconds=2.5,
        requester_factory=lambda _competition_id: requester,
        sleeper=sleeps.append,
    )

    assert payload["status"] == "PROVIDER_AUDIT_COMPLETED"
    assert sleeps
    assert sleeps == [2.5] * payload["provider_calls"]
    assert payload["provider_calls"] == len(requester.calls)


def test_429_summary_recommends_cooldown_and_stops_before_later_endpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    requester = FakeRequester(status_by_endpoint={"statistics": 429})

    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        real_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=13,
        out_dir=tmp_path,
        requester_factory=lambda _competition_id: requester,
    )

    endpoints = [endpoint for endpoint, _params in requester.calls]
    assert payload["status"] == "PROVIDER_AUDIT_STOPPED_EARLY"
    assert payload["stopped_early"] is True
    assert payload["stopped_reason"] == "PROVIDER_HTTP_429"
    assert payload["cooldown_recommended"] is True
    assert endpoints == ["leagues", "fixtures", "fixtures", "statistics"]
    summary = json.loads(Path(str(payload["summary_json"])).read_text(encoding="utf-8"))
    assert summary["cooldown_recommended"] is True
    assert summary["stopped_reason"] == "PROVIDER_HTTP_429"


def test_provider_payload_auth_error_stops_audit() -> None:
    requester = FakeRequester(error_by_endpoint={"leagues": {"to" + "ken": "invalid"}})
    provider = _provider("brasileirao_serie_a", requester=requester)

    result = evaluate_controlled_provider_league_audit(
        _entry("brasileirao_serie_a"),
        environment="staging",
        provider=provider,
    )

    assert result.overall_status == "PROVIDER_KEY_INVALID"
    assert provider.ledger.records[0]["error"] == "PROVIDER_KEY_INVALID"


def test_provider_plan_error_is_ledgered_without_immediate_stop() -> None:
    requester = FakeRequester(plan_restricted_seasons={"2026"})
    provider = _provider("brasileirao_serie_a", requester=requester)

    provider.get_league("71", "2026")

    assert provider.ledger.records[0]["error"] == "PROVIDER_PLAN_RESTRICTED"


def test_local_ledger_records_endpoint_and_call_counts() -> None:
    provider = _provider("brasileirao_serie_a", requester=FakeRequester())

    evaluate_controlled_provider_league_audit(
        _entry("brasileirao_serie_a"),
        environment="staging",
        provider=provider,
    )

    assert provider.ledger.records
    assert provider.ledger.records[0]["endpoint"] == "leagues"
    assert provider.ledger.records[-1]["provider_call_index"] == len(provider.ledger.records)
    assert all(
        "payload" not in record and "response" not in record
        for record in provider.ledger.records
    )


def test_national_leagues_in_season_scope_excludes_later_season_leagues() -> None:
    payload = build_cli_payload(group="national_leagues_in_season")
    ids = [result["competition_id"] for result in payload["results"]]

    assert tuple(ids) == IN_SEASON_NATIONAL_LEAGUES
    assert "eredivisie" not in ids
    assert "primeira_liga" not in ids


def test_argentina_requires_28_teams(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    requester = FakeRequester(team_count=27)

    payload = build_cli_payload(
        competition_id="argentina_primera",
        real_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=15,
        requester_factory=lambda _competition_id: requester,
    )

    result = payload["results"][0]
    assert result["can_enable"] is False
    assert "provider_mapping:FAIL" in result["blockers"]


def test_chinese_super_league_and_mls_warnings(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    china = build_cli_payload(
        competition_id="chinese_super_league",
        real_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=13,
        requester_factory=lambda _competition_id: FakeRequester(),
    )
    mls = build_cli_payload(
        competition_id="mls",
        real_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=13,
        requester_factory=lambda _competition_id: FakeRequester(),
    )

    assert any("INTEGRITY_GATE" in item for item in china["results"][0]["warnings"])
    assert any("WORLD_CUP_CALENDAR" in item for item in mls["results"][0]["warnings"])


def test_empty_configured_season_falls_back_for_coverage_probe(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    requester = FakeRequester(empty_seasons={"2026"})

    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        real_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=13,
        requester_factory=lambda _competition_id: requester,
    )

    result = payload["results"][0]
    statuses = {item["name"]: item["status"] for item in result["items"]}
    seasons = [
        params["season"]
        for endpoint, params in requester.calls
        if endpoint in {"leagues", "fixtures"}
    ]
    assert seasons[:3] == ["2026", "2026", "2026"]
    assert "2025" in seasons
    assert statuses["provider_mapping"] == "FAIL"
    assert statuses["fixtures"] == "PASS"
    assert statuses["results"] == "PASS"
    assert statuses["xg"] == "PASS"
    assert statuses["lineups_injuries"] == "PASS"
    assert statuses["bookmaker_depth"] == "PASS"
    assert result["can_enable"] is False
    assert any("AUDIT_SEASON_FALLBACK" in item for item in result["warnings"])
    assert result["actual_provider_calls"] <= 13


def test_provider_bookmaker_depth_requires_minimum_bookmakers(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    requester = FakeRequester(
        odds_payload=[
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
    )

    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        real_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=13,
        requester_factory=lambda _competition_id: requester,
    )

    item = _item(payload, "bookmaker_depth")
    assert item["status"] == "FAIL"
    assert item["observed_evidence"] == {
        "observed_ah_ou_market_names": ["asian handicap", "goals over/under"],
        "observed_bookmaker_count": 1,
        "observed_has_ah": True,
        "observed_has_line": True,
        "observed_has_ou": True,
    }
    assert payload["results"][0]["can_enable"] is False


def test_provider_bookmaker_depth_requires_line_presence(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    requester = FakeRequester(
        odds_payload=[
            {"bookmakers": [{"name": "BookA", "bets": [{"name": "Asian Handicap"}]}]},
            {"bookmakers": [{"name": "BookB", "bets": [{"name": "Goals Over/Under"}]}]},
            {"bookmakers": [{"name": "BookC", "bets": [{"name": "Goals Over/Under"}]}]},
        ]
    )

    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        real_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=13,
        requester_factory=lambda _competition_id: requester,
    )

    item = _item(payload, "bookmaker_depth")
    assert item["status"] == "FAIL"
    assert item["observed_evidence"] == {
        "observed_ah_ou_market_names": ["asian handicap", "goals over/under"],
        "observed_bookmaker_count": 3,
        "observed_has_ah": True,
        "observed_has_line": False,
        "observed_has_ou": True,
    }
    assert payload["results"][0]["can_enable"] is False


def test_provider_bookmaker_depth_passes_with_minimum_bookmakers_and_lines(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")

    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        real_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=13,
        requester_factory=lambda _competition_id: FakeRequester(),
    )

    item = _item(payload, "bookmaker_depth")
    assert item["status"] == "PASS"
    assert item["observed_evidence"] == {
        "observed_ah_ou_market_names": ["asian handicap", "goals over/under"],
        "observed_bookmaker_count": 3,
        "observed_has_ah": True,
        "observed_has_line": True,
        "observed_has_ou": True,
    }


def test_plan_restricted_seasons_are_recorded_and_fall_back_to_accessible_probe(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    requester = FakeRequester(plan_restricted_seasons={"2026", "2025"})

    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        real_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=13,
        requester_factory=lambda _competition_id: requester,
    )

    result = payload["results"][0]
    statuses = {item["name"]: item["status"] for item in result["items"]}
    seasons = [
        params["season"]
        for endpoint, params in requester.calls
        if endpoint in {"leagues", "fixtures"}
    ]
    assert seasons[:6] == ["2026", "2026", "2026", "2025", "2025", "2025"]
    assert "2024" in seasons
    assert statuses["provider_mapping"] == "FAIL"
    assert statuses["fixtures"] == "PASS"
    assert result["can_enable"] is False
    assert result["actual_provider_calls"] <= 13


def test_report_json_excludes_raw_provider_payload(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        real_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=13,
        out_dir=tmp_path,
        requester_factory=lambda _competition_id: FakeRequester(),
    )

    assert payload["output_dir"] == str(tmp_path)
    for path in [*payload["report_paths"], payload["audit_ledger_json"], payload["summary_json"]]:
        text = Path(str(path)).read_text(encoding="utf-8")
        assert "raw_payload" not in text
        assert "x-apisports-key" not in text
    assert payload["db_writes"] == 0
    assert payload["provider_calls"] == payload["local_ledger_records"]


def test_resume_from_out_dir_skips_completed_report(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    _write_resume_report(tmp_path, "brasileirao_serie_a", "FAIL")
    requesters: dict[str, FakeRequester] = {}

    payload = build_cli_payload(
        group="national_leagues_in_season",
        real_provider_audit=True,
        approved_provider_calls=True,
        daily_hard_cap=90,
        out_dir=tmp_path / "next",
        resume_from_out_dir=tmp_path,
        requester_factory=lambda competition_id: requesters.setdefault(
            competition_id,
            FakeRequester(),
        ),
    )

    assert payload["skipped_existing_reports"] == [
        str(tmp_path / "W2_WHITELIST_AUDIT_brasileirao_serie_a.json")
    ]
    assert "brasileirao_serie_a" not in requesters
    assert payload["results"][0]["competition_id"] == "argentina_primera"


def test_resume_from_out_dir_restarts_provider_stop_report(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy")
    _write_resume_report(tmp_path, "brasileirao_serie_a", "PROVIDER_HTTP_429")
    requesters: dict[str, FakeRequester] = {}

    payload = build_cli_payload(
        group="national_leagues_in_season",
        real_provider_audit=True,
        approved_provider_calls=True,
        daily_hard_cap=90,
        out_dir=tmp_path / "next",
        resume_from_out_dir=tmp_path,
        requester_factory=lambda competition_id: requesters.setdefault(
            competition_id,
            FakeRequester(),
        ),
    )

    assert payload["skipped_existing_reports"] == []
    assert requesters["brasileirao_serie_a"].calls
    assert payload["results"][0]["competition_id"] == "brasileirao_serie_a"


def test_invalid_provider_key_fails_closed_before_provider_call(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "dummy…")

    payload = build_cli_payload(
        competition_id="brasileirao_serie_a",
        real_provider_audit=True,
        approved_provider_calls=True,
        max_provider_calls=13,
    )

    assert payload["provider_calls"] == 0
    assert payload["local_ledger_records"] == 0
    assert payload["results"][0]["overall_status"] == "PROVIDER_KEY_INVALID"
    assert payload["results"][0]["can_enable"] is False


def test_provider_key_copy_paste_pollution_is_normalized(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", " W2_API_FOOTBALL_API_KEY='dummy-key'\n")

    assert _normalized_provider_key("W2_API_FOOTBALL_API_KEY") == "dummy-key"


def test_enabled_false_remains_after_real_provider_harness() -> None:
    national = sorted(Path("config/competitions/national_leagues").glob("*.json"))

    assert national
    assert all('"enabled": false' in path.read_text(encoding="utf-8") for path in national)


def _entry(competition_id: str):
    return CompetitionRegistry().entries()[competition_id]


def _provider(
    competition_id: str,
    *,
    requester: Any,
    league_hard_cap: int = 13,
) -> ApiFootballLeagueAuditProvider:
    return ApiFootballLeagueAuditProvider(
        competition_id=competition_id,
        league_hard_cap=league_hard_cap,
        budget=ProviderAuditBudget(daily_hard_cap=90),
        ledger=LocalProviderAuditLedger(),
        requester=requester,
        request_interval_seconds=0,
    )


def _item(payload: dict[str, Any], name: str) -> dict[str, Any]:
    return next(item for item in payload["results"][0]["items"] if item["name"] == name)


class FakeRequester:
    def __init__(
        self,
        *,
        empty_statistics_first: bool = False,
        empty_seasons: set[str] | None = None,
        plan_restricted_seasons: set[str] | None = None,
        error_by_endpoint: dict[str, dict[str, str]] | None = None,
        status_by_endpoint: dict[str, int] | None = None,
        team_count: int | None = None,
        odds_payload: list[dict[str, Any]] | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.empty_statistics_first = empty_statistics_first
        self.empty_seasons = empty_seasons or set()
        self.plan_restricted_seasons = plan_restricted_seasons or set()
        self.error_by_endpoint = error_by_endpoint or {}
        self.status_by_endpoint = status_by_endpoint or {}
        self.team_count = team_count
        self.odds_payload = odds_payload

    def __call__(
        self,
        endpoint: str,
        params: dict[str, str],
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        self.calls.append((endpoint, params))
        status = self.status_by_endpoint.get(endpoint, 200)
        return status, {"x-ratelimit-requests-remaining": "90"}, _payload(endpoint, params, self)


def _payload(endpoint: str, params: dict[str, str], requester: FakeRequester) -> dict[str, Any]:
    league_id = params.get("league") or params.get("id") or "71"
    profile = _profile_by_league_id(league_id)
    if endpoint in requester.error_by_endpoint:
        return {"errors": requester.error_by_endpoint[endpoint], "response": []}
    if params.get("season") in requester.plan_restricted_seasons:
        return {
            "errors": {"plan": "Free plans do not have access to this season."},
            "response": [],
        }
    if params.get("season") in requester.empty_seasons:
        return {"response": []}
    if endpoint == "leagues":
        return {
            "response": [
                {
                    "league": {"id": int(league_id), "name": profile["name"]},
                    "country": {"name": profile["country"]},
                    "seasons": [{"year": 2026}],
                    "team_count": requester.team_count or profile["expected_team_count"],
                }
            ]
        }
    if endpoint == "fixtures" and params.get("status") == "FT":
        return {
            "response": [
                {"fixture": {"id": "fixture-result-1"}, "goals": {"home": 1, "away": 0}}
            ]
        }
    if endpoint == "fixtures":
        return {
            "response": [
                {"fixture": {"id": "fixture-future-1"}},
                {"fixture": {"id": "fixture-future-2"}},
            ]
        }
    if endpoint == "statistics":
        if requester.empty_statistics_first and params.get("fixture") == "fixture-future-1":
            return {"response": []}
        return {"response": [{"team": {"id": 1}, "statistics": [{"type": "xg", "value": "1.2"}]}]}
    if endpoint == "lineups":
        return {"response": [{"team": {"id": 1}, "startXI": []}]}
    if endpoint == "injuries":
        return {"response": []}
    if endpoint == "odds":
        if requester.odds_payload is not None:
            return {"response": requester.odds_payload}
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
                        }
                    ]
                }
            ]
        }
    return {"response": []}


def _profile_by_league_id(league_id: str) -> dict[str, Any]:
    for path in Path("config/competitions/national_leagues").glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if str(payload["provider_mapping"]["api_football_league_id"]) == str(league_id):
            return payload
    raise AssertionError(f"unknown league id {league_id}")


def _write_resume_report(tmp_path: Path, competition_id: str, status: str) -> None:
    path = tmp_path / f"W2_WHITELIST_AUDIT_{competition_id}.json"
    path.write_text(
        json.dumps(
            {
                "competition_id": competition_id,
                "overall_status": status,
                "status": status,
                "can_enable": False,
                "actual_provider_calls": 0,
                "items": [],
                "blockers": [status] if status.startswith("PROVIDER_") else [],
                "warnings": [],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
