from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.ingestion.future_refresh import (
    FutureFixtureRefreshService,
    FutureRefreshConfig,
    FutureRefreshError,
    RefreshSingletonLock,
    canonical_market,
    config_from_policy,
    deterministic_task_key,
    load_refresh_policy,
    observations_from_odds_payload,
    parse_line,
    run_future_refresh_task,
)
from w2.providers.api_football import LiveApiFootballResponse

NOW = datetime(2026, 6, 23, 10, 0, tzinfo=UTC)


class FakeApiFootballClient:
    def __init__(
        self,
        *,
        remaining: int = 7000,
        status_code: int = 200,
        burst_remaining: int | None = None,
        daily_header: str = "x-ratelimit-requests-remaining",
        include_status_daily_payload: bool = True,
    ) -> None:
        self.remaining = remaining
        self.status_code = status_code
        self.burst_remaining = burst_remaining
        self.daily_header = daily_header
        self.include_status_daily_payload = include_status_daily_payload
        self.calls: list[tuple[str, dict[str, str]]] = []

    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        self.calls.append((endpoint, params))
        payload = self.payload(endpoint, params)
        headers = {self.daily_header: str(self.remaining)}
        if self.burst_remaining is not None:
            headers["x-ratelimit-remaining"] = str(self.burst_remaining)
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=self.status_code,
            elapsed_ms=7,
            payload=payload,
            headers=headers,
            captured_at=NOW,
        )

    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint == "status":
            if not self.include_status_daily_payload:
                return {"response": {"requests": {}}}
            return {"response": {"requests": {"remaining": self.remaining}}}
        if endpoint == "fixtures":
            return {
                "response": [
                    {
                        "fixture": {
                            "id": 1489404,
                            "date": "2026-06-23T17:00:00+00:00",
                            "status": {"short": "NS"},
                            "venue": {"name": "Test Venue"},
                        },
                        "league": {"id": 1, "name": "World Cup", "round": "Group K"},
                        "teams": {
                            "home": {"id": 10, "name": "Team A"},
                            "away": {"id": 20, "name": "Team B"},
                        },
                    },
                    {
                        "fixture": {
                            "id": 1480000,
                            "date": "2026-06-22T17:00:00+00:00",
                            "status": {"short": "NS"},
                        },
                        "league": {"id": 1, "name": "World Cup"},
                        "teams": {"home": {"id": 1}, "away": {"id": 2}},
                    },
                ]
            }
        if endpoint == "odds":
            return {
                "response": [
                    {
                        "fixture": {"id": int(params["fixture"])},
                        "bookmakers": [
                            {
                                "id": 1,
                                "name": "Book A",
                                "bets": [
                                    {
                                        "id": 1,
                                        "name": "Match Winner",
                                        "values": [
                                            {"value": "Home", "odd": "1.80"},
                                            {"value": "Draw", "odd": "3.70"},
                                        ],
                                    }
                                ],
                            },
                            {
                                "id": 2,
                                "name": "Book B",
                                "bets": [
                                    {
                                        "id": 1,
                                        "name": "Match Winner",
                                        "values": [{"value": "Home", "odd": "1.82"}],
                                    }
                                ],
                            },
                        ],
                    }
                ]
            }
        if endpoint == "statistics":
            return {
                "response": [
                    {
                        "team": {"id": 10},
                        "statistics": [{"type": "expected_goals", "value": "1.5"}],
                    },
                    {
                        "team": {"id": 20},
                        "statistics": [{"type": "expected_goals", "value": "0.8"}],
                    },
                ]
            }
        if endpoint == "lineups":
            return {
                "response": [
                    {"team": {"id": 10}, "startXI": [{} for _ in range(11)], "substitutes": []},
                    {"team": {"id": 20}, "startXI": [{} for _ in range(11)], "substitutes": [{}]},
                ]
            }
        if endpoint == "injuries":
            return {"response": []}
        raise AssertionError(endpoint)


def test_canonical_market_keeps_only_full_time_asian_handicap_in_ah_pool() -> None:
    assert canonical_market("Asian Handicap") == "ASIAN_HANDICAP"
    assert canonical_market("Handicap") == "ASIAN_HANDICAP"
    assert canonical_market("Asian Handicap First Half") == "ASIAN_HANDICAP_FIRST_HALF"
    assert canonical_market("Asian Handicap (2nd Half)") == "ASIAN_HANDICAP_(2ND_HALF)"
    assert canonical_market("Corners Asian Handicap") == "CORNERS_ASIAN_HANDICAP"
    assert canonical_market("Yellow Asian Handicap") == "YELLOW_ASIAN_HANDICAP"


def test_parse_line_preserves_asian_split_quarter_lines() -> None:
    assert parse_line("Over 2/2.5") == "2.25"
    assert parse_line("Under 2 - 2.5") == "2.25"
    assert parse_line("Home -0/0.5") == "-0.25"
    assert parse_line("Away +0.5/1") == "0.75"
    assert parse_line("Over 2.5") == "2.5"


def test_odds_payload_does_not_put_half_or_card_handicap_into_full_time_ah_pool() -> None:
    payload = {
        "response": [
            {
                "fixture": {"id": 1489404},
                "bookmakers": [
                    {
                        "id": 1,
                        "name": "Book A",
                        "bets": [
                            {
                                "id": 4,
                                "name": "Asian Handicap",
                                "values": [
                                    {"value": "Home -1.25", "odd": "1.91"},
                                    {"value": "Away +1.25", "odd": "1.97"},
                                ],
                            },
                            {
                                "id": 5,
                                "name": "Asian Handicap First Half",
                                "values": [
                                    {"value": "Home -0.5", "odd": "1.88"},
                                    {"value": "Away +0.5", "odd": "2.00"},
                                ],
                            },
                            {
                                "id": 6,
                                "name": "Cards Asian Handicap",
                                "values": [
                                    {"value": "Home -1.5", "odd": "1.90"},
                                    {"value": "Away +1.5", "odd": "1.98"},
                                ],
                            },
                        ],
                    }
                ],
            }
        ]
    }
    response = LiveApiFootballResponse(
        endpoint="odds",
        params={"fixture": "1489404"},
        status_code=200,
        elapsed_ms=7,
        payload=payload,
        headers={},
        captured_at=NOW,
    )

    rows = observations_from_odds_payload(
        fixture_id="1489404",
        payload=payload,
        response=response,
        source_revision="test",
        raw_payload_sha256="payload",
    )

    full_time_ah_rows = [row for row in rows if row["canonical_market"] == "ASIAN_HANDICAP"]
    assert {row["raw_market_label"] for row in full_time_ah_rows} == {"Asian Handicap"}
    assert {row["line"] for row in full_time_ah_rows} == {"-1.25", "+1.25"}
    assert {
        row["canonical_market"]
        for row in rows
        if row["raw_market_label"] != "Asian Handicap"
    } == {"ASIAN_HANDICAP_FIRST_HALF", "CARDS_ASIAN_HANDICAP"}


def test_odds_payload_records_split_totals_line_as_quarter_line() -> None:
    payload = {
        "response": [
            {
                "fixture": {"id": 1489404},
                "bookmakers": [
                    {
                        "id": 1,
                        "name": "Book A",
                        "bets": [
                            {
                                "id": 5,
                                "name": "Goals Over/Under",
                                "values": [
                                    {"value": "Over 2/2.5", "odd": "2.03"},
                                    {"value": "Under 2/2.5", "odd": "1.85"},
                                ],
                            },
                        ],
                    },
                ],
            },
        ],
    }
    response = LiveApiFootballResponse(
        endpoint="odds",
        params={"fixture": "1489404"},
        status_code=200,
        elapsed_ms=7,
        payload=payload,
        headers={},
        captured_at=NOW,
    )

    rows = observations_from_odds_payload(
        fixture_id="1489404",
        payload=payload,
        response=response,
        source_revision="test",
        raw_payload_sha256="payload",
    )

    totals_rows = [row for row in rows if row["canonical_market"] == "TOTALS"]
    assert {row["line"] for row in totals_rows} == {"2.25"}
    assert {row["decimal_odds"] for row in totals_rows} == {"2.03", "1.85"}


class ManyFutureFixturesClient(FakeApiFootballClient):
    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint != "fixtures":
            return super().payload(endpoint, params)
        return {
            "response": [
                {
                    "fixture": {
                        "id": 1489400 + index,
                        "date": f"2026-06-23T{11 + index:02d}:00:00+00:00",
                        "status": {"short": "NS"},
                    },
                    "league": {"id": 1, "name": "World Cup", "round": "Group K"},
                    "teams": {
                        "home": {"id": 100 + index, "name": f"Team H {index}"},
                        "away": {"id": 200 + index, "name": f"Team A {index}"},
                    },
                }
                for index in range(12)
            ]
        }


class EmptyLineupsClient(FakeApiFootballClient):
    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint == "lineups":
            return {"response": []}
        return super().payload(endpoint, params)


class NineFutureFixturesClient(FakeApiFootballClient):
    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint != "fixtures":
            return super().payload(endpoint, params)
        return {
            "response": [
                {
                    "fixture": {
                        "id": 1489400 + index,
                        "date": f"2026-06-23T{11 + index:02d}:00:00+00:00",
                        "status": {"short": "NS"},
                    },
                    "league": {"id": 1, "name": "World Cup", "round": "Group K"},
                    "teams": {
                        "home": {"id": 100 + index, "name": f"Team H {index}"},
                        "away": {"id": 200 + index, "name": f"Team A {index}"},
                    },
                }
                for index in range(9)
            ]
        }


def test_future_fixture_refresh_writes_idempotent_read_model(tmp_path: Path) -> None:
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(runtime_root=tmp_path, quota_reserve=1500, persistence="file")
    service = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    )

    first = service.run()
    second = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert first.fixture_count == 1
    assert first.mapping_count == 1
    assert first.market_snapshot_count == 1
    assert second.fixture_count == 1
    assert (tmp_path / "read_model/fixtures.json").is_file()
    assert (tmp_path / "read_model/provider_mappings.json").is_file()
    assert (tmp_path / "read_model/market_snapshots.json").is_file()
    assert len(list((tmp_path / "raw").glob("fixtures_*.json"))) == 1
    assert len(list((tmp_path / "raw").glob("odds_*.json"))) == 1
    assert first.ledger_appended_count == 3
    assert second.ledger_appended_count == 0
    ledger_lines = (tmp_path / "ledger/market_observations.jsonl").read_text().splitlines()
    assert len(ledger_lines) == 3


def test_future_refresh_saves_lineups_raw_before_materialization_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_projection(**_kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("materialization exploded")

    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "status,fixtures,odds,lineups")
    monkeypatch.setattr(
        "w2.ingestion.future_refresh.project_ledger_to_read_model",
        fail_projection,
    )
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        persistence="file",
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("lineups",),
        feature_enrichment_request_budget=1,
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))

    assert result.status == "PARTIAL_FAILED"
    assert result.error_code == "RuntimeError"
    assert list((tmp_path / "raw").glob("lineups_1489404_*.json"))
    assert audit["status"] == "PARTIAL_FAILED"
    assert audit["error_code"] == "RuntimeError"
    assert audit["raw_payload_written_count"] >= 3
    assert any(
        item["endpoint"] == "lineups" and item["raw_payload_persisted"] is True
        for item in audit["requests"]
    )


def test_future_refresh_lineups_empty_diagnostic(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "status,fixtures,odds,lineups")
    client = EmptyLineupsClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        persistence="file",
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("lineups",),
        feature_enrichment_request_budget=1,
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))

    assert result.blockers == []
    assert any(
        item["endpoint"] == "lineups"
        and item["response_count"] == 0
        and item["diagnostic_code"] == "PROVIDER_LINEUPS_EMPTY"
        for item in audit["requests"]
    )


def test_future_refresh_lineups_materialization_missing_diagnostic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "status,fixtures,odds,lineups")
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        persistence="file",
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("lineups",),
        feature_enrichment_request_budget=1,
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))

    assert result.blockers == []
    assert any(
        item["endpoint"] == "lineups"
        and item["response_count"] > 0
        and item["diagnostic_code"] == "LINEUPS_MATERIALIZATION_MISSING"
        for item in audit["requests"]
    )


def test_future_refresh_batches_lineups_without_disallowed_endpoints(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "status,fixtures,odds,lineups")
    monkeypatch.setenv("W2_PROVIDER_REFRESH_BATCH_SIZE", "3")
    client = NineFutureFixturesClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        persistence="file",
        max_fixture_candidates=9,
        max_odds_requests=0,
        request_budget=20,
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("lineups", "statistics", "injuries"),
        feature_enrichment_request_budget=9,
        provider_refresh_batch_size=3,
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))

    endpoints = [endpoint for endpoint, _params in client.calls]
    assert endpoints.count("lineups") == 9
    assert "statistics" not in endpoints
    assert "injuries" not in endpoints
    assert "h2h" not in endpoints
    assert result.feature_enrichment_payload_count == 9
    assert audit["feature_enrichment_batch_count"] == 3
    assert len(list((tmp_path / "raw").glob("lineups_*.json"))) == 9


def test_future_fixture_refresh_preserves_core_tasks_when_reserve_locked(
    tmp_path: Path,
) -> None:
    client = FakeApiFootballClient(remaining=1499)
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        quota_reserve=1500,
        persistence="file",
        feature_enrichment_enabled=True,
        feature_enrichment_request_budget=3,
        feature_enrichment_endpoints=("statistics", "lineups", "injuries"),
    )
    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert result.blockers == []
    assert result.fixture_count == 1
    assert result.market_snapshot_count == 1
    assert ("odds", {"fixture": "1489404"}) in client.calls
    assert ("lineups", {"fixture": "1489404"}) in client.calls
    assert all(endpoint != "statistics" for endpoint, _ in client.calls)
    assert all(endpoint != "injuries" for endpoint, _ in client.calls)
    assert (tmp_path / "future_refresh_audit.json").is_file()


def test_future_refresh_requests_odds_for_all_fixture_candidates(tmp_path: Path) -> None:
    client = ManyFutureFixturesClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        max_fixture_candidates=12,
        max_odds_requests=12,
        request_budget=30,
        persistence="file",
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))
    odds_calls = [params["fixture"] for endpoint, params in client.calls if endpoint == "odds"]

    assert result.fixture_count == 12
    assert odds_calls == [str(1489400 + index) for index in range(12)]
    assert audit["odds_request_fixture_ids"] == odds_calls
    assert audit["odds_request_attempt_count"] == 12
    assert audit["odds_request_limit"] == 12
    assert audit["odds_request_coverage_ratio"] == 1.0


def test_future_refresh_daily_quota_is_not_burst_quota(tmp_path: Path) -> None:
    client = FakeApiFootballClient(remaining=6774, burst_remaining=299)
    config = FutureRefreshConfig(runtime_root=tmp_path, quota_reserve=1500, persistence="file")

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert result.blockers == []
    assert result.remaining_quota == 6774


def test_future_refresh_burst_only_is_daily_unknown(tmp_path: Path) -> None:
    client = FakeApiFootballClient(
        remaining=299,
        daily_header="x-ratelimit-remaining",
        include_status_daily_payload=False,
    )
    config = FutureRefreshConfig(runtime_root=tmp_path, quota_reserve=1500, persistence="file")

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert result.blockers == ["DAILY_QUOTA_UNKNOWN"]


def test_future_refresh_blocks_when_header_remaining_below_preflight_minimum(
    tmp_path: Path,
) -> None:
    client = FakeApiFootballClient(remaining=49)
    config = FutureRefreshConfig(runtime_root=tmp_path, quota_reserve=20, persistence="file")

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))

    assert result.blockers == ["PROVIDER_HEADER_REMAINING_BELOW_MINIMUM"]
    assert client.calls == [("status", {})]
    assert audit["request_count"] == 1
    assert audit["requests"][0]["daily_remaining"] == 49
    assert audit["requests"][0]["daily_limit"] is None


def test_future_fixture_refresh_request_budget(tmp_path: Path) -> None:
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(runtime_root=tmp_path, request_budget=1, persistence="file")
    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert result.blockers == ["REQUEST_BUDGET_EXHAUSTED"]
    assert len(client.calls) == 1


def test_future_refresh_controlled_feature_enrichment_uses_budget_and_audit(
    tmp_path: Path,
) -> None:
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        quota_reserve=1500,
        persistence="file",
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("statistics", "lineups", "injuries"),
        feature_enrichment_request_budget=2,
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = (tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8")

    assert result.blockers == []
    assert result.feature_enrichment_payload_count == 1
    assert ("statistics", {"fixture": "1489404"}) not in client.calls
    assert ("lineups", {"fixture": "1489404"}) in client.calls
    assert ("injuries", {"fixture": "1489404"}) not in client.calls
    assert list((tmp_path / "raw").glob("lineups_*.json"))
    assert "ENDPOINT_NOT_AUTHORIZED:statistics" in audit
    assert "ENDPOINT_NOT_AUTHORIZED:injuries" in audit
    assert '"candidate": false' in audit
    assert '"formal_recommendation": false' in audit


def test_future_refresh_endpoint_allowlist_skips_unauthorized_enrichment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "status,fixtures,odds,lineups")
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        quota_reserve=1500,
        persistence="file",
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("statistics", "lineups", "injuries"),
        feature_enrichment_request_budget=3,
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))

    assert result.blockers == []
    assert result.request_count == 4
    assert [endpoint for endpoint, _params in client.calls] == [
        "status",
        "fixtures",
        "odds",
        "lineups",
    ]
    assert result.feature_enrichment_payload_count == 1
    assert any(
        item["error_code"] == "ENDPOINT_NOT_AUTHORIZED:statistics"
        for item in audit["requests"]
    )
    assert any(
        item["error_code"] == "ENDPOINT_NOT_AUTHORIZED:injuries"
        for item in audit["requests"]
    )


def test_future_refresh_tick_hard_cap_blocks_before_provider_call(tmp_path: Path) -> None:
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        persistence="file",
        max_fixture_candidates=31,
        max_odds_requests=31,
        request_budget=40,
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))

    assert result.status == "BLOCKED"
    assert result.blockers == ["PROVIDER_REFRESH_BUDGET_TOO_HIGH"]
    assert result.request_count == 0
    assert client.calls == []
    assert audit["request_count"] == 0
    assert audit["requests"][0]["projected_calls"] == 33


def test_future_refresh_projected_calls_ignore_disallowed_enrichment(tmp_path: Path) -> None:
    client = ManyFutureFixturesClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        persistence="file",
        max_fixture_candidates=5,
        max_odds_requests=5,
        request_budget=30,
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("statistics", "lineups", "injuries"),
        feature_enrichment_request_budget=15,
    )

    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert result.blockers == []
    assert result.request_count == 12
    assert result.feature_enrichment_payload_count == 5
    assert all(endpoint != "statistics" for endpoint, _params in client.calls)
    assert all(endpoint != "injuries" for endpoint, _params in client.calls)
    assert len([endpoint for endpoint, _params in client.calls if endpoint == "lineups"]) == 5


def test_future_refresh_records_401_without_retry(tmp_path: Path) -> None:
    client = FakeApiFootballClient(status_code=401)
    config = FutureRefreshConfig(runtime_root=tmp_path, persistence="file")
    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = (tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8")

    assert result.blockers == ["PROVIDER_HTTP_401"]
    assert len(client.calls) == 1
    assert "PROVIDER_HTTP_401" in audit


def test_future_refresh_records_429_without_tight_retry(tmp_path: Path) -> None:
    client = FakeApiFootballClient(status_code=429)
    config = FutureRefreshConfig(runtime_root=tmp_path, persistence="file")
    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = (tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8")

    assert result.blockers == ["PROVIDER_HTTP_429"]
    assert len(client.calls) == 1
    assert "PROVIDER_HTTP_429" in audit


def test_future_refresh_caps_configured_provider_retries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("W2_PROVIDER_HTTP_MAX_ATTEMPTS", "999")
    client = FakeApiFootballClient(status_code=429)
    result = FutureFixtureRefreshService(
        client=client,
        config=FutureRefreshConfig(runtime_root=tmp_path, persistence="file"),
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert result.blockers == ["PROVIDER_HTTP_429"]
    assert result.request_count == 3
    assert len(client.calls) == 3


def test_future_refresh_daily_hard_cap_blocks_before_provider_call(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("W2_PROVIDER_REFRESH_TICK_HARD_CAP", "100")
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        persistence="file",
        daily_hard_cap=7500,
        daily_reserve=1500,
        actual_provider_calls_today=6000,
        max_odds_requests=20,
        feature_enrichment_enabled=True,
        feature_enrichment_request_budget=9,
    )
    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()
    audit = json.loads((tmp_path / "future_refresh_audit.json").read_text(encoding="utf-8"))

    assert result.status == "BLOCKED"
    assert result.blockers == ["PROVIDER_RESERVE_PROTECTED"]
    assert result.request_count == 0
    assert client.calls == []
    assert audit["request_count"] == 0
    assert audit["requests"][0]["error_code"] == "PROVIDER_RESERVE_PROTECTED"


def test_future_refresh_w2_budget_scope_ignores_provider_header_usage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("W2_PROVIDER_REFRESH_TICK_HARD_CAP", "100")
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(
        runtime_root=tmp_path,
        persistence="file",
        daily_hard_cap=100,
        daily_reserve=20,
        daily_usage_scope="w2_ledger",
        actual_provider_calls_today=70,
        max_odds_requests=5,
        feature_enrichment_enabled=True,
        feature_enrichment_request_budget=3,
    )
    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert result.status != "BLOCKED"
    assert "PROVIDER_RESERVE_PROTECTED" not in result.blockers


def test_future_refresh_policy_allows_only_registered_competitions(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        """
        {
          "competitions": [
            {
              "competition_id": "world_cup_2026",
              "provider_league_id": "1",
              "season": "2026",
              "horizon_days": 14,
              "scheduler_interval_seconds": 900,
              "quota_reserve": 1500,
              "request_budget": 40,
              "max_fixture_candidates": 20,
              "max_odds_requests": 20,
              "market_freshness_seconds": 3600,
              "enabled": true
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    policy = load_refresh_policy(competition_id="world_cup_2026", policy_path=policy_path)
    config = config_from_policy(
        competition_id="world_cup_2026",
        runtime_root=tmp_path / "runtime",
        policy_path=policy_path,
    )

    assert policy.provider_league_id == "1"
    assert config.season == "2026"
    assert config.max_odds_requests == 20
    try:
        load_refresh_policy(competition_id="premier_league", policy_path=policy_path)
    except FutureRefreshError as exc:
        assert str(exc) == "COMPETITION_NOT_ENABLED:premier_league"
    else:  # pragma: no cover
        raise AssertionError("unregistered policy unexpectedly loaded")


def test_world_cup_future_refresh_policy_uses_zero_trickle_backfill_budget() -> None:
    config = config_from_policy(competition_id="world_cup_2026")

    assert config.daily_hard_cap == 120
    assert config.daily_reserve == 0
    assert config.request_budget == 30
    assert config.checkpoint_mode == "world_cup_three_checkpoint"
    assert config.trickle_backfill_daily_budget == 0


def test_future_refresh_file_lock_prevents_duplicate_owner(tmp_path: Path) -> None:
    first = RefreshSingletonLock(
        key="future-refresh:world_cup_2026:2026:bucket",
        owner="owner-a",
        runtime_root=tmp_path,
        ttl_seconds=60,
    )
    second = RefreshSingletonLock(
        key="future-refresh:world_cup_2026:2026:bucket",
        owner="owner-b",
        runtime_root=tmp_path,
        ttl_seconds=60,
    )

    assert first.acquire(now=NOW)
    assert not second.acquire(now=NOW)
    assert first.release()


def test_future_refresh_task_writes_audit_and_blocks_duplicate_bucket(tmp_path: Path) -> None:
    key = deterministic_task_key(
        competition_id="world_cup_2026",
        season="2026",
        now=NOW,
        interval_seconds=900,
    )
    existing = RefreshSingletonLock(
        key=key,
        owner="existing",
        runtime_root=tmp_path,
        ttl_seconds=60,
    )
    assert existing.acquire(now=NOW)

    audit = run_future_refresh_task(
        task_id="task-1",
        key=key,
        owner="new-owner",
        queued_at=NOW,
        runtime_root=tmp_path,
        client=FakeApiFootballClient(),
        now=NOW,
        persistence="file",
    )

    assert audit.status == "ALREADY_RUNNING"
    assert (tmp_path / "task_audit/task-1.json").is_file()
    assert existing.release()


def test_future_refresh_error_type_is_runtime_error() -> None:
    assert issubclass(FutureRefreshError, RuntimeError)
