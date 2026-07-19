from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from w2.domain.enums import DataStatus, DecisionReasonCode, DecisionTier
from w2.matchday.orchestrator import build_matchday_dry_run

NOW = datetime(2026, 7, 5, 0, 0, tzinfo=UTC)
KICKOFF = NOW + timedelta(hours=25)


def _payload(
    *,
    environment: str = "staging",
    fixtures: list[dict[str, object]],
) -> dict[str, object]:
    return build_matchday_dry_run(
        football_day=date(2026, 7, 5),
        environment=environment,
        as_of=NOW,
        fixtures=fixtures,
        provider_allowed_endpoints=("status", "fixtures", "odds", "lineups", "statistics"),
    )


def test_empty_day_returns_no_fixtures_without_side_effects() -> None:
    payload = _payload(fixtures=[])

    assert payload["status"] == "NO_FIXTURES"
    assert payload["fixture_count"] == 0
    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["would_enqueue"] is False
    assert payload["environment_policy"]["lock_policy"]["name"] == "staging_B"  # type: ignore[index]
    assert payload["dashboard_would_generate"] == {"would_generate": False, "card_count": 0}


def test_one_fixture_without_market_is_blocked_market_unavailable() -> None:
    payload = _payload(fixtures=[{"fixture_id": "fixture-1", "kickoff_utc": KICKOFF}])
    fixture = payload["fixtures"][0]  # type: ignore[index]

    assert fixture["data_status"] == DataStatus.BLOCKED.value
    assert fixture["reason_code"] == DecisionReasonCode.MARKET_UNAVAILABLE.value
    assert fixture["decision_tier"] == DecisionTier.NOT_READY.value
    assert fixture["provider_calls"] == 0
    assert fixture["db_writes"] == 0


def test_market_line_odds_returns_decision_and_refresh_plan() -> None:
    payload = _payload(
        fixtures=[
            {
                "fixture_id": "fixture-1",
                "kickoff_utc": KICKOFF,
                "home_team": "Home",
                "away_team": "Away",
                "market": "ASIAN_HANDICAP",
                "line": "-0.25",
                "odds": "1.95",
            }
        ],
    )
    fixture = payload["fixtures"][0]  # type: ignore[index]
    refresh = payload["refresh_plan_summary"]  # type: ignore[assignment]
    labels = {tick["label"] for tick in refresh["ticks"]}  # type: ignore[index]

    assert fixture["data_status"] == DataStatus.READY.value
    assert fixture["decision_tier"] == DecisionTier.NOT_READY.value
    assert fixture["decision_contract"]["pick"] is None  # type: ignore[index]
    assert fixture["decision_contract"]["outcome_tracked"] is False  # type: ignore[index]
    assert {"T_24H", "T_3H", "T_90M", "T_30M", "T_15M"}.issubset(labels)
    assert refresh["endpoint_allowlist"] == ["status", "fixtures", "odds", "lineups"]  # type: ignore[index]
    assert refresh["skipped_endpoints"] == ["statistics"]  # type: ignore[index]
    assert payload["next_refresh_tick"] is not None
    assert payload["environment_policy"]["disclaimer"]  # type: ignore[index]


def test_production_missing_quote_provenance_is_not_ready() -> None:
    payload = _payload(
        environment="production",
        fixtures=[
            {
                "fixture_id": "fixture-1",
                "kickoff_utc": KICKOFF,
                "market": "ASIAN_HANDICAP",
                "line": "-0.25",
                "odds": "1.95",
                "lineups_available": True,
                "xg_available": True,
                "ratings_available": True,
                "team_value_available": True,
            }
        ],
    )
    fixture = payload["fixtures"][0]  # type: ignore[index]

    assert fixture["decision_tier"] == DecisionTier.NOT_READY.value
    assert fixture["decision_contract"]["pick"] is None  # type: ignore[index]
    assert fixture["decision_contract"]["outcome_tracked"] is False  # type: ignore[index]
    assert fixture["lock_eligible"] is False
    assert payload["environment_policy"]["lock_policy"]["name"] == "production_B"  # type: ignore[index]


def test_staging_missing_quote_provenance_does_not_create_lock_candidate() -> None:
    payload = _payload(
        fixtures=[
            {
                "fixture_id": "fixture-1",
                "kickoff_utc": KICKOFF,
                "market": "ASIAN_HANDICAP",
                "line": "-0.25",
                "odds": "1.95",
                "recommendation_id": "rec-1",
                "lineups_available": True,
                "xg_available": True,
                "ratings_available": True,
                "team_value_available": True,
            }
        ],
    )

    fixture = payload["fixtures"][0]  # type: ignore[index]

    assert fixture["decision_tier"] == DecisionTier.NOT_READY.value
    assert fixture["decision_contract"]["pick"] is None  # type: ignore[index]
    assert fixture["decision_contract"]["outcome_tracked"] is False  # type: ignore[index]
    assert fixture["lock_eligible"] is False
    assert payload["lock_candidates"] == []
    assert payload["would_write_lock"] is False


def test_settlement_dry_run_placeholder_and_provider_usage_are_side_effect_free() -> None:
    payload = _payload(fixtures=[{"fixture_id": "fixture-1", "kickoff_utc": KICKOFF}])

    assert payload["settlement_dry_run"] == {
        "would_run": False,
        "reason": "not implemented in dry-run skeleton",
        "db_writes": 0,
    }
    assert payload["provider_usage_plan"]["provider_calls"] == 0  # type: ignore[index]
    assert payload["provider_usage_plan"]["would_enqueue"] is False  # type: ignore[index]
    assert payload["would_write_settlement"] is False
