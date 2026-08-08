from __future__ import annotations

from datetime import UTC, datetime

from w2.ingestion.free_fixture_bridge import (
    FreeFixtureBridgeConfig,
    materialize_bridge_evidence,
    plan_fixture_discovery,
    plan_fixture_followups,
)
from w2.ingestion.raw_store import RawPayloadStore
from w2.matchday.intake_v2 import MatchdayCompetitionPolicy

NOW = datetime(2026, 8, 8, 5, 0, tzinfo=UTC)
ENABLED = FreeFixtureBridgeConfig(enabled=True)


def test_bridge_is_disabled_by_default_and_protects_free_reserve() -> None:
    assert plan_fixture_discovery(date_utc="2026-08-08", actual_calls_today=0)["status"] == (
        "DISABLED_BY_DEFAULT"
    )
    blocked = plan_fixture_discovery(
        date_utc="2026-08-08",
        actual_calls_today=60,
        config=ENABLED,
    )
    assert blocked["status"] == "FREE_DAILY_RESERVE_PROTECTED"
    assert blocked["planned_calls"] == 0


def test_discovery_cache_and_no_idle_followups_spend_zero_calls() -> None:
    discovery = plan_fixture_discovery(
        date_utc="2026-08-08",
        actual_calls_today=5,
        config=ENABLED,
    )
    cached = plan_fixture_discovery(
        date_utc="2026-08-08",
        actual_calls_today=5,
        cached_request_keys=frozenset({discovery["calls"][0].cache_key}),
        config=ENABLED,
    )
    idle = plan_fixture_followups(
        fixture_payload=_fixture_payload("100"),
        allowed_league_ids=frozenset({"113"}),
        due_fixture_ids=(),
        actual_calls_today=5,
        config=ENABLED,
    )
    assert cached["status"] == "DISCOVERY_CACHED_NO_CALL"
    assert idle["status"] == "NO_DUE_TARGET_FIXTURES_NO_IDLE_POLLING"
    assert cached["planned_calls"] == idle["planned_calls"] == 0


def test_followups_dedupe_fixture_ids_and_use_single_id_on_free() -> None:
    payload = _fixture_payload("100")
    payload["response"].append(payload["response"][0])
    plan = plan_fixture_followups(
        fixture_payload=payload,
        allowed_league_ids=frozenset({"113"}),
        due_fixture_ids=("100", "100"),
        actual_calls_today=5,
        enrichment_endpoints=("statistics",),
        config=ENABLED,
    )
    assert plan["status"] == "PLANNED"
    assert [(item.request.endpoint, item.request.params) for item in plan["calls"]] == [
        ("fixtures", {"id": "100"}),
        ("odds", {"fixture": "100"}),
        ("statistics", {"fixture": "100"}),
    ]


def test_provider_ids_batching_is_bounded_to_twenty_when_available() -> None:
    fixture_ids = tuple(str(index) for index in range(1, 22))
    payload = {
        "response": [
            _fixture_payload(fixture_id)["response"][0] for fixture_id in fixture_ids
        ]
    }
    plan = plan_fixture_followups(
        fixture_payload=payload,
        allowed_league_ids=frozenset({"113"}),
        due_fixture_ids=fixture_ids,
        actual_calls_today=0,
        cached_request_keys=frozenset(
            {
                f"matchday-intake:odds:unused-{fixture_id}"
                for fixture_id in fixture_ids
            }
        ),
        config=FreeFixtureBridgeConfig(enabled=True, provider_ids_batching=True),
    )
    detail_calls = [item for item in plan["calls"] if item.request.endpoint == "fixtures"]
    assert [len(item.fixture_ids) for item in detail_calls] == [20, 1]
    assert detail_calls[0].request.params["ids"].count("-") == 19


def test_bridge_materializes_existing_raw_capture_identity_and_market_contracts() -> None:
    store = RawPayloadStore()
    evidence = materialize_bridge_evidence(
        fixture_payload=_fixture_payload("100"),
        fixture_params={"date": "2026-08-08"},
        odds_payloads={"100": _odds_payload("100")},
        policies={"allsvenskan": _policy()},
        captured_at=NOW,
        source_revision="unit",
        raw_store=store,
    )
    assert evidence["raw_payload_count"] == 2
    assert {item["endpoint"] for item in evidence["endpoint_captures"]} == {
        "fixtures",
        "odds",
    }
    assert evidence["fixture_discovery"]["candidate_fixtures"][0]["schema_version"] == (
        "MatchdayFixtureIdentityV1"
    )
    assert {item["canonical_market"] for item in evidence["market_observations"]} == {
        "ASIAN_HANDICAP",
        "TOTALS",
    }
    assert evidence["normalization_rejections"] == []


def _policy() -> MatchdayCompetitionPolicy:
    return MatchdayCompetitionPolicy(
        competition_id="allsvenskan",
        enabled=True,
        provider="api_football",
        provider_league_id="113",
        season="2026",
        discovery_horizon_hours=48,
        fixture_status_allowlist=("NS",),
        checkpoints=(),
        endpoint_matrix={},
        odds_max_age_seconds=3600,
        lineup_requirement="OPTIONAL",
        request_caps={},
        provider_allowlist=("fixtures", "odds"),
        feature_enrichment_policy={},
    )


def _fixture_payload(fixture_id: str) -> dict[str, object]:
    return {
        "response": [
            {
                "fixture": {
                    "id": int(fixture_id),
                    "date": "2026-08-08T13:00:00+00:00",
                    "status": {"short": "NS"},
                },
                "league": {"id": 113, "season": 2026},
                "teams": {"home": {"id": 10}, "away": {"id": 20}},
            }
        ]
    }


def _odds_payload(fixture_id: str) -> dict[str, object]:
    return {
        "response": [
            {
                "fixture": {"id": int(fixture_id)},
                "bookmakers": [
                    {
                        "id": 4,
                        "name": "Pinnacle",
                        "bets": [
                            {
                                "id": 33,
                                "name": "Asian Handicap",
                                "values": [
                                    {"value": "Home -0.5", "odd": "1.91"},
                                    {"value": "Away +0.5", "odd": "1.95"},
                                ],
                            },
                            {
                                "id": 5,
                                "name": "Goals Over/Under",
                                "values": [
                                    {"value": "Over 2.5", "odd": "1.90"},
                                    {"value": "Under 2.5", "odd": "1.96"},
                                ],
                            },
                        ],
                    }
                ],
            }
        ]
    }
