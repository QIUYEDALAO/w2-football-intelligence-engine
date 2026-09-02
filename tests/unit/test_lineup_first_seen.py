from __future__ import annotations

from datetime import UTC, datetime, timedelta

from apps.scheduler import main as scheduler_main
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.ingestion_models import ProviderQuotaObservationModel
from w2.infrastructure.persistence.matchday_intake_models import (
    LineupFirstSeenEventModel,
    MatchdayFixtureIdentityModel,
)
from w2.ingestion.authoritative_lineup import validate_authoritative_lineup
from w2.ingestion.lineup_first_seen import (
    LINEUP_FIRST_SEEN_POLICY_VERSION,
    LineupFirstSeenRepository,
    LineupPollCandidate,
    empirical_start_lead_minutes,
    first_seen_event_payload,
    next_lineup_poll_at,
)

NOW = datetime(2026, 9, 2, 10, tzinfo=UTC)


def _team(team_id: int, offset: int) -> dict[str, object]:
    return {
        "team": {"id": team_id, "name": f"Team {team_id}"},
        "coach": {"id": team_id + 1000, "name": f"Coach {team_id}"},
        "formation": "4-3-3",
        "startXI": [
            {"player": {"id": offset + index, "name": f"P{offset + index}"}}
            for index in range(11)
        ],
        "substitutes": [
            {"player": {"id": offset + 100 + index, "name": f"B{offset + index}"}}
            for index in range(7)
        ],
    }


def _identity(index: int, *, kickoff: datetime) -> MatchdayFixtureIdentityModel:
    fixture_id = str(9000 + index)
    return MatchdayFixtureIdentityModel(
        fixture_id=f"api_football:{fixture_id}",
        provider="api_football",
        provider_fixture_id=fixture_id,
        competition_id="premier_league",
        provider_league_id="39",
        season="2026",
        kickoff_utc=kickoff,
        fixture_status="NS",
        home_provider_team_id="10",
        away_provider_team_id="20",
        home_w2_team_id=None,
        away_w2_team_id=None,
        team_identity_status="PROVIDER_PRIMARY_READY",
        raw_payload_sha256=f"{index:064d}",
        endpoint_capture_id=None,
        captured_at=NOW - timedelta(hours=1),
        identity_hash=f"identity-{index}",
        payload={},
    )


def _event(*, first_seen_at: datetime = NOW) -> dict[str, object]:
    kickoff = NOW + timedelta(minutes=47)
    response = [_team(10, 100), _team(20, 200)]
    validated = validate_authoritative_lineup(
        response,
        expected_team_ids=("10", "20"),
        captured_at=first_seen_at,
        kickoff_utc=kickoff,
    )
    return first_seen_event_payload(
        fixture_id="api_football:9001",
        competition_id="premier_league",
        provider="api_football",
        provider_fixture_id="9001",
        first_seen_at=first_seen_at,
        kickoff_at=kickoff,
        raw_sha256="a" * 64,
        validated=validated,
        raw_response=response,
    )


def test_first_seen_event_contains_complete_timing_and_lineup_evidence() -> None:
    event = _event()

    assert event["minutes_to_kickoff"] == 47
    assert event["coverage_status"] == "COMPLETE_BOTH_TEAMS"
    assert [len(row["players"]) for row in event["starting_xi"]] == [11, 11]  # type: ignore[index]
    assert [len(row["players"]) for row in event["bench"]] == [7, 7]  # type: ignore[index]
    assert event["formation"] == [
        {"team_id": "10", "formation": "4-3-3"},
        {"team_id": "20", "formation": "4-3-3"},
    ]
    assert event["coach"] == [
        {"team_id": "10", "coach_id": "1010", "coach_name": "Coach 10"},
        {"team_id": "20", "coach_id": "1020", "coach_name": "Coach 20"},
    ]


def test_first_seen_event_is_first_write_wins() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = LineupFirstSeenRepository(engine=engine)
    first = _event()
    replay = {**first, "first_seen_at": NOW + timedelta(minutes=1), "raw_sha256": "b" * 64}

    assert repository.append_event(first) is True
    assert repository.append_event(replay) is False

    with Session(engine) as session:
        row = session.scalar(select(LineupFirstSeenEventModel))
    assert row is not None
    assert row.first_seen_at.replace(tzinfo=UTC) == NOW
    assert row.raw_sha256 == "a" * 64


def test_adaptive_polling_uses_observed_distribution_and_backs_off() -> None:
    assert empirical_start_lead_minutes([]) == 120
    assert empirical_start_lead_minutes([20, 30, 40, 50, 60]) == 60
    kickoff = NOW + timedelta(hours=2)

    first = next_lineup_poll_at(
        now=NOW,
        candidate=LineupPollCandidate(
            fixture_id="fixture",
            competition_id="premier_league",
            season="2026",
            kickoff_at=kickoff,
            completed_poll_count=0,
            existing_plan_count=0,
        ),
        observed_minutes_to_kickoff=[20, 30, 40, 50, 60],
    )
    retry = next_lineup_poll_at(
        now=kickoff - timedelta(minutes=60),
        candidate=LineupPollCandidate(
            fixture_id="fixture",
            competition_id="premier_league",
            season="2026",
            kickoff_at=kickoff,
            completed_poll_count=1,
            existing_plan_count=1,
            last_polled_at=kickoff - timedelta(minutes=60),
        ),
        observed_minutes_to_kickoff=[20, 30, 40, 50, 60],
    )

    assert first == kickoff - timedelta(minutes=60)
    assert retry == kickoff - timedelta(minutes=40)


def test_polling_never_creates_more_than_three_plans_per_fixture() -> None:
    assert (
        next_lineup_poll_at(
            now=NOW,
            candidate=LineupPollCandidate(
                fixture_id="fixture",
                competition_id="premier_league",
                season="2026",
                kickoff_at=NOW + timedelta(hours=2),
                completed_poll_count=2,
                existing_plan_count=3,
            ),
            observed_minutes_to_kickoff=[],
        )
        is None
    )


def test_plan_generation_caps_matchday_peak_without_fixed_timing_claim() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(_identity(index, kickoff=NOW + timedelta(hours=2)) for index in range(12))
        session.commit()

    plans = LineupFirstSeenRepository(engine=engine).build_due_plans(now=NOW)

    assert len(plans) == 10
    assert all(plan.policy_version == LINEUP_FIRST_SEEN_POLICY_VERSION for plan in plans)
    assert all(plan.endpoints == ("lineups",) for plan in plans)
    assert all(plan.scheduled_at == NOW for plan in plans)


def test_quota_guard_stops_below_1500_but_allows_exact_reserve(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = LineupFirstSeenRepository(engine=engine)
    monkeypatch.setattr(repository, "daily_lineup_call_count", lambda **_kwargs: 0)

    def observe(remaining: int, suffix: str, *, seconds: int) -> None:
        with Session(engine) as session:
            session.add(
                ProviderQuotaObservationModel(
                    provider="api_football",
                    endpoint="lineups",
                    request_hash=suffix * 64,
                    observed_at=NOW + timedelta(seconds=seconds),
                    daily_limit=7500,
                    daily_remaining=remaining,
                    burst_limit=300,
                    burst_remaining=299,
                )
            )
            session.commit()

    observe(1500, "a", seconds=1)
    assert repository.quota_guard(now=NOW)["allowed"] is True
    observe(1499, "b", seconds=2)
    guard = repository.quota_guard(now=NOW)
    assert guard["allowed"] is False
    assert guard["blocker"] == "LINEUP_FIRST_SEEN_PROVIDER_REMAINING_BELOW_RESERVE"


def test_scheduler_flag_off_is_fail_closed(monkeypatch) -> None:
    monkeypatch.delenv("W2_LINEUP_FIRST_SEEN_ENABLED", raising=False)
    result = scheduler_main.generate_lineup_first_seen_plans(NOW)
    assert result == {"status": "DISABLED", "generated_plan_count": 0, "provider_calls": 0}


def test_scheduler_requires_quota_authority_and_respects_reserve(monkeypatch) -> None:
    monkeypatch.setenv("W2_LINEUP_FIRST_SEEN_ENABLED", "true")

    class FakeRepository:
        def __init__(self) -> None:
            self.build_called = False

        def quota_guard(self, *, now: datetime) -> dict[str, object]:
            return {
                "allowed": False,
                "blocker": "LINEUP_FIRST_SEEN_QUOTA_AUTHORITY_MISSING",
                "provider_remaining": None,
            }

        def build_due_plans(self, *, now: datetime) -> list[object]:
            self.build_called = True
            return []

    fake = FakeRepository()
    monkeypatch.setattr("w2.ingestion.lineup_first_seen.LineupFirstSeenRepository", lambda: fake)
    result = scheduler_main.generate_lineup_first_seen_plans(NOW)
    assert result["status"] == "LINEUP_FIRST_SEEN_QUOTA_AUTHORITY_MISSING"
    assert result["generated_plan_count"] == 0


def test_scheduler_generates_plans_at_exact_reserve(monkeypatch) -> None:
    monkeypatch.setenv("W2_LINEUP_FIRST_SEEN_ENABLED", "true")

    class FakeRepository:
        def quota_guard(self, *, now: datetime) -> dict[str, object]:
            return {"allowed": True, "provider_remaining": 1500}

        def build_due_plans(self, *, now: datetime) -> list[object]:
            return []

    monkeypatch.setattr("w2.ingestion.lineup_first_seen.LineupFirstSeenRepository", FakeRepository)
    result = scheduler_main.generate_lineup_first_seen_plans(NOW)
    assert result["status"] == "PLANS_GENERATED"
    assert result["generated_plan_count"] == 0
