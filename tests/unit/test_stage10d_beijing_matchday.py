from __future__ import annotations

from datetime import UTC, date, datetime

from w2.api import repository
from w2.matchday.coverage import MISSING_REASONS, MatchdayCoverageReconciler
from w2.matchday.timezone import (
    BeijingOperationalDayPolicy,
    FixtureOperationalDateResolver,
    next_36_hours_window,
)


def test_beijing_operational_day_crosses_utc_date() -> None:
    policy = BeijingOperationalDayPolicy()
    window = policy.window_for_date(date(2026, 6, 23))
    assert window.start_utc == datetime(2026, 6, 22, 16, tzinfo=UTC)
    assert window.end_utc == datetime(2026, 6, 23, 16, tzinfo=UTC)
    assert policy.provider_utc_dates_for_window(window) == ["2026-06-22", "2026-06-23"]


def test_beijing_window_left_closed_right_open() -> None:
    window = BeijingOperationalDayPolicy().window_for_date(date(2026, 6, 23))
    assert window.contains(datetime(2026, 6, 22, 16, tzinfo=UTC))
    assert not window.contains(datetime(2026, 6, 23, 16, tzinfo=UTC))


def test_operational_date_beijing_conversion() -> None:
    resolver = FixtureOperationalDateResolver()
    annotation = resolver.annotate(datetime(2026, 6, 22, 17, tzinfo=UTC))
    assert annotation["kickoff_beijing"] == "2026-06-23T01:00:00+08:00"
    assert annotation["operational_date_beijing"] == "2026-06-23"


def test_same_fixture_unique_reason_and_missing_distribution() -> None:
    window = BeijingOperationalDayPolicy().window_for_date(date(2026, 6, 23))
    audit = MatchdayCoverageReconciler().reconcile(
        window=window,
        authoritative_fixtures=[
            {
                "fixture_id": "a",
                "competition": "World Cup",
                "kickoff_utc": "2026-06-22T17:00:00Z",
            },
            {
                "fixture_id": "a",
                "competition": "World Cup",
                "kickoff_utc": "2026-06-22T17:00:00Z",
            },
            {
                "fixture_id": "b",
                "competition": "World Cup",
                "kickoff_utc": "2026-06-22T18:00:00Z",
            },
        ],
        cards=[{"fixture": {"fixture_id": "a"}}],
        read_model_fixtures=[{"fixture_id": "a"}],
        displayed_fixtures=[{"fixture_id": "a"}],
        now_utc=datetime(2026, 6, 22, 15, tzinfo=UTC),
    )
    reasons = {row["fixture_id"]: row["reason"] for row in audit["fixtures"]}
    assert reasons["a"] in MISSING_REASONS
    assert audit["reason_distribution"]["DUPLICATE_FIXTURE"] == 1
    assert audit["reason_distribution"]["READ_MODEL_PROJECTION_MISSING"] == 1
    assert audit["read_model_count"] == audit["displayed_count"]


def test_matchday_service_filters_by_beijing_date() -> None:
    cards = [
        {
            "fixture": {
                "fixture_id": "in",
                "competition_id": "1",
                "competition_name": "World Cup",
                "kickoff_utc": "2026-06-22T17:00:00+00:00",
                "status": "NS",
                "home_team_id": "h",
                "home_team_name": "Home",
                "away_team_id": "a",
                "away_team_name": "Away",
                "data_health": "READY",
            },
            "card": {"action": "WATCH", "published_grade": "C"},
            "temporal": {},
            "integrity": {"integrity_status": "PASS"},
            "market_ranking": [],
        },
        {
            "fixture": {
                "fixture_id": "out",
                "competition_id": "1",
                "competition_name": "World Cup",
                "kickoff_utc": "2026-06-23T16:00:00+00:00",
                "status": "NS",
                "home_team_id": "h",
                "home_team_name": "Home",
                "away_team_id": "a",
                "away_team_name": "Away",
                "data_health": "READY",
            },
            "card": {"action": "WATCH", "published_grade": "C"},
            "temporal": {},
            "integrity": {"integrity_status": "PASS"},
            "market_ranking": [],
        },
    ]

    class Repo(repository.ReadModelRepository):
        def matchday_cards(self):  # type: ignore[no-untyped-def]
            return cards

    result = repository.ReadModelService(Repo()).matchday(target_date="2026-06-23")
    assert result["total"] == 1
    assert result["items"][0]["fixture_id"] == "in"
    assert result["items"][0]["operational_date_beijing"] == "2026-06-23"


def test_next_36_hours_independent_window() -> None:
    start, end = next_36_hours_window(datetime(2026, 6, 22, 12, tzinfo=UTC))
    assert start == datetime(2026, 6, 22, 12, tzinfo=UTC)
    assert end == datetime(2026, 6, 24, 0, tzinfo=UTC)
