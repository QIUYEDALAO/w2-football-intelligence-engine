from __future__ import annotations

import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
from w2.infrastructure.persistence.ingestion_models import (
    ProviderQuotaObservationModel,
    ProviderRequestLogModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayEndpointCaptureModel,
    MatchdayFixtureIdentityModel,
)
from w2.ingestion.authoritative_lineup import ValidatedAuthoritativeLineup
from w2.matchday.intake_v2 import CheckpointPlan, stable_hash

LINEUP_FIRST_SEEN_POLICY_VERSION = "w2.lineup_first_seen.v1"
LINEUP_FIRST_SEEN_SCHEMA_VERSION = "w2.lineup_first_seen_event.v1"
LINEUP_FIRST_SEEN_EVENT_ENDPOINT = "lineup_first_seen_event"
LINEUP_FIRST_SEEN_CHECKPOINT_PREFIX = "LINEUP_FIRST_SEEN_POLL_"
LINEUP_FIRST_SEEN_MAX_POLLS_PER_FIXTURE = 3
LINEUP_FIRST_SEEN_MAX_POLLS_PER_TICK = 10
LINEUP_FIRST_SEEN_DAILY_CALL_CAP = 1500
LINEUP_FIRST_SEEN_PROVIDER_RESERVE = 1500
LINEUP_FIRST_SEEN_EMPIRICAL_MIN_SAMPLE = 5
LINEUP_FIRST_SEEN_PLAN_GRACE = timedelta(minutes=10)


def lineup_first_seen_enabled() -> bool:
    return os.environ.get("W2_LINEUP_FIRST_SEEN_ENABLED", "false").lower() == "true"


@dataclass(frozen=True, kw_only=True)
class LineupPollCandidate:
    fixture_id: str
    competition_id: str
    season: str
    kickoff_at: datetime
    completed_poll_count: int
    existing_plan_count: int
    last_polled_at: datetime | None = None


def empirical_start_lead_minutes(observations: Sequence[int]) -> int | None:
    usable = sorted(max(int(value), 0) for value in observations)
    if len(usable) < LINEUP_FIRST_SEEN_EMPIRICAL_MIN_SAMPLE:
        return None
    return usable[max(math.ceil(len(usable) * 0.9) - 1, 0)]


def next_lineup_poll_at(
    *,
    now: datetime,
    candidate: LineupPollCandidate,
    observed_minutes_to_kickoff: Sequence[int],
) -> datetime | None:
    current = _utc(now)
    kickoff = _utc(candidate.kickoff_at)
    if (
        kickoff <= current
        or candidate.completed_poll_count >= LINEUP_FIRST_SEEN_MAX_POLLS_PER_FIXTURE
        or candidate.existing_plan_count >= LINEUP_FIRST_SEEN_MAX_POLLS_PER_FIXTURE
    ):
        return None
    if candidate.completed_poll_count == 0:
        observed_lead = empirical_start_lead_minutes(observed_minutes_to_kickoff)
        if observed_lead is None:
            return current
        target = kickoff - timedelta(minutes=observed_lead)
        return max(current, target)
    last = _utc(candidate.last_polled_at or current)
    remaining_polls = LINEUP_FIRST_SEEN_MAX_POLLS_PER_FIXTURE - candidate.completed_poll_count
    delay = max((kickoff - last) / (remaining_polls + 1), timedelta(minutes=1))
    return min(last + delay, kickoff - timedelta(seconds=1))


def first_seen_event_payload(
    *,
    fixture_id: str,
    competition_id: str,
    provider: str,
    provider_fixture_id: str,
    first_seen_at: datetime,
    kickoff_at: datetime,
    raw_sha256: str,
    validated: ValidatedAuthoritativeLineup,
    raw_response: object,
) -> dict[str, Any]:
    first_seen = _utc(first_seen_at)
    kickoff = _utc(kickoff_at)
    if first_seen >= kickoff:
        raise ValueError("POST_KICKOFF_LINEUP_REJECTED")
    raw_teams = {
        str((row.get("team") or {}).get("id") or row.get("team_id") or ""): row
        for row in raw_response
        if isinstance(row, Mapping)
    } if isinstance(raw_response, Sequence) and not isinstance(raw_response, (str, bytes)) else {}

    starting_xi = []
    bench = []
    formation = []
    coach = []
    for team in validated.teams:
        starting_xi.append(
            {
                "team_id": team.team_id,
                "players": [player.as_persistence_dict(starter=True) for player in team.starters],
            }
        )
        bench.append(
            {
                "team_id": team.team_id,
                "players": [
                    player.as_persistence_dict(starter=False) for player in team.substitutes
                ],
            }
        )
        formation.append({"team_id": team.team_id, "formation": team.formation})
        raw_coach = raw_teams.get(team.team_id, {}).get("coach")
        coach_value = raw_coach if isinstance(raw_coach, Mapping) else {}
        coach.append(
            {
                "team_id": team.team_id,
                "coach_id": str(coach_value.get("id") or "") or None,
                "coach_name": str(coach_value.get("name") or "") or None,
            }
        )
    return {
        "event_id": stable_hash(f"{provider}:{provider_fixture_id}:LINEUP_FIRST_SEEN"),
        "fixture_id": fixture_id,
        "competition_id": competition_id,
        "provider": provider,
        "provider_fixture_id": provider_fixture_id,
        "first_seen_at": first_seen,
        "kickoff_at": kickoff,
        "minutes_to_kickoff": max(int((kickoff - first_seen).total_seconds() // 60), 0),
        "raw_sha256": raw_sha256,
        "starting_xi": starting_xi,
        "bench": bench,
        "formation": formation,
        "coach": coach,
        "coverage_status": "COMPLETE_BOTH_TEAMS",
        "schema_version": LINEUP_FIRST_SEEN_SCHEMA_VERSION,
    }


class LineupFirstSeenRepository:
    def __init__(self, *, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine()

    def append_event(self, payload: Mapping[str, Any]) -> bool:
        event_id = str(payload["event_id"])
        first_seen_at = _utc(payload["first_seen_at"])
        stored = dict(payload)
        stored["first_seen_at"] = first_seen_at.isoformat().replace("+00:00", "Z")
        stored["kickoff_at"] = _utc(payload["kickoff_at"]).isoformat().replace(
            "+00:00", "Z"
        )
        with Session(self.engine) as session:
            existing = session.get(RawPayloadModel, event_id)
            if existing is not None:
                return False
            try:
                session.add(
                    RawPayloadModel(
                        sha256=event_id,
                        endpoint=LINEUP_FIRST_SEEN_EVENT_ENDPOINT,
                        captured_at=first_seen_at,
                        inserted_at=datetime.now(UTC),
                        storage_uri=f"db://raw_payload/{event_id}",
                        payload=stored,
                    )
                )
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                return False

    def minutes_to_kickoff_observations(self) -> list[int]:
        with Session(self.engine) as session:
            return [
                int(row.payload["minutes_to_kickoff"])
                for row in session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == LINEUP_FIRST_SEEN_EVENT_ENDPOINT)
                    .order_by(RawPayloadModel.captured_at)
                )
            ]

    def distribution_summary(self) -> dict[str, Any]:
        values = sorted(self.minutes_to_kickoff_observations())

        def percentile(fraction: float) -> int | None:
            if not values:
                return None
            return values[max(math.ceil(len(values) * fraction) - 1, 0)]

        return {
            "schema_version": "w2.lineup_first_seen_distribution.v1",
            "sample_count": len(values),
            "minimum": values[0] if values else None,
            "p50": percentile(0.5),
            "p90": percentile(0.9),
            "maximum": values[-1] if values else None,
            "adaptive_start_lead_minutes": empirical_start_lead_minutes(values),
            "adaptive_source": (
                "OBSERVED_P90"
                if len(values) >= LINEUP_FIRST_SEEN_EMPIRICAL_MIN_SAMPLE
                else "INSUFFICIENT_LOCAL_SAMPLE_NO_TIMING_CLAIM"
            ),
        }

    def daily_lineup_call_count(self, *, now: datetime) -> int:
        day_start = _utc(now).replace(hour=0, minute=0, second=0, microsecond=0)
        with Session(self.engine) as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(ProviderRequestLogModel)
                    .where(
                        ProviderRequestLogModel.provider == "api_football",
                        ProviderRequestLogModel.endpoint == "lineups",
                        ProviderRequestLogModel.live.is_(True),
                        ProviderRequestLogModel.requested_at >= day_start,
                    )
                )
                or 0
            )

    def quota_guard(self, *, now: datetime) -> dict[str, Any]:
        calls = self.daily_lineup_call_count(now=now)
        with Session(self.engine) as session:
            authority = session.scalar(
                select(ProviderQuotaObservationModel)
                .where(ProviderQuotaObservationModel.provider == "api_football")
                .order_by(ProviderQuotaObservationModel.observed_at.desc())
                .limit(1)
            )
        remaining = authority.daily_remaining if authority is not None else None
        blocker = (
            "LINEUP_FIRST_SEEN_DAILY_CALL_CAP_REACHED"
            if calls >= LINEUP_FIRST_SEEN_DAILY_CALL_CAP
            else "LINEUP_FIRST_SEEN_QUOTA_AUTHORITY_MISSING"
            if remaining is None
            else "LINEUP_FIRST_SEEN_PROVIDER_REMAINING_BELOW_RESERVE"
            if int(remaining) < LINEUP_FIRST_SEEN_PROVIDER_RESERVE
            else None
        )
        return {
            "allowed": blocker is None,
            "blocker": blocker,
            "lineup_calls_today": calls,
            "daily_call_cap": LINEUP_FIRST_SEEN_DAILY_CALL_CAP,
            "provider_remaining": int(remaining) if remaining is not None else None,
            "provider_reserve": LINEUP_FIRST_SEEN_PROVIDER_RESERVE,
        }

    def poll_candidates(self, *, now: datetime) -> list[LineupPollCandidate]:
        current = _utc(now)
        matchday_end = (current + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        with Session(self.engine) as session:
            identities = list(
                session.scalars(
                    select(MatchdayFixtureIdentityModel)
                    .where(
                        MatchdayFixtureIdentityModel.provider == "api_football",
                        MatchdayFixtureIdentityModel.fixture_status == "NS",
                        MatchdayFixtureIdentityModel.kickoff_utc > current,
                        MatchdayFixtureIdentityModel.kickoff_utc < matchday_end,
                    )
                    .order_by(MatchdayFixtureIdentityModel.kickoff_utc)
                )
            )
            seen = {
                str(row.payload.get("provider_fixture_id") or "")
                for row in session.scalars(
                    select(RawPayloadModel).where(
                        RawPayloadModel.endpoint == LINEUP_FIRST_SEEN_EVENT_ENDPOINT
                    )
                )
            }
            plans = list(
                session.scalars(
                    select(MatchdayCheckpointPlanModel).where(
                        MatchdayCheckpointPlanModel.policy_version
                        == LINEUP_FIRST_SEEN_POLICY_VERSION
                    )
                )
            )
            captures = list(
                session.scalars(
                    select(MatchdayEndpointCaptureModel).where(
                        MatchdayEndpointCaptureModel.endpoint == "lineups",
                        MatchdayEndpointCaptureModel.checkpoint.like(
                            f"%{LINEUP_FIRST_SEEN_CHECKPOINT_PREFIX}%"
                        ),
                    )
                )
            )
        output = []
        for identity in identities:
            if identity.provider_fixture_id in seen:
                continue
            aliases = {
                identity.fixture_id,
                identity.provider_fixture_id,
                f"api_football:{identity.provider_fixture_id}",
            }
            fixture_plans = [row for row in plans if row.fixture_id in aliases]
            if any(row.status in {"PLANNED", "DUE"} for row in fixture_plans):
                continue
            completed = sum(int(row.attempt_count or 0) > 0 for row in fixture_plans)
            polled_at = [
                _utc(row.provider_captured_at)
                for row in captures
                if row.fixture_id in aliases
            ]
            output.append(
                LineupPollCandidate(
                    fixture_id=identity.fixture_id,
                    competition_id=identity.competition_id,
                    season=identity.season,
                    kickoff_at=_utc(identity.kickoff_utc),
                    completed_poll_count=completed,
                    existing_plan_count=len(fixture_plans),
                    last_polled_at=max(polled_at, default=None),
                )
            )
        return output

    def build_due_plans(self, *, now: datetime) -> list[CheckpointPlan]:
        current = _utc(now)
        observed = self.minutes_to_kickoff_observations()
        plans = []
        for candidate in self.poll_candidates(now=current):
            scheduled = next_lineup_poll_at(
                now=current,
                candidate=candidate,
                observed_minutes_to_kickoff=observed,
            )
            if scheduled is None:
                continue
            window_end = min(scheduled + LINEUP_FIRST_SEEN_PLAN_GRACE, candidate.kickoff_at)
            plans.append(
                CheckpointPlan(
                    fixture_id=candidate.fixture_id,
                    competition_id=candidate.competition_id,
                    season=candidate.season,
                    checkpoint=(
                        LINEUP_FIRST_SEEN_CHECKPOINT_PREFIX
                        + str(candidate.existing_plan_count + 1)
                    ),
                    kickoff_utc=candidate.kickoff_at,
                    scheduled_at=scheduled,
                    window_start=scheduled,
                    window_end=window_end,
                    endpoints=("lineups",),
                    status="DUE" if scheduled <= current else "PLANNED",
                    blockers=(),
                    policy_version=LINEUP_FIRST_SEEN_POLICY_VERSION,
                )
            )
        return sorted(plans, key=lambda item: (item.scheduled_at, item.kickoff_utc))[
            :LINEUP_FIRST_SEEN_MAX_POLLS_PER_TICK
        ]


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
