from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.future_refresh_models import (
    ExpectedMatchFixtureMaterializationModel,
    ExpectedMatchFixtureObservationModel,
    RawPayloadModel,
)
from w2.prematch.expected_match_denominator import materialize_saved_fixture_observations


def add_expected_match_fixture_materialization(
    session: Session,
    raw: RawPayloadModel,
    *,
    materialized_at: datetime,
) -> tuple[int, int]:
    """Materialize one saved fixture raw in the same transaction as its source."""
    if raw.inserted_at is None:
        session.add(
            ExpectedMatchFixtureMaterializationModel(
                raw_payload_sha256=raw.sha256,
                source_captured_at=raw.captured_at,
                source_inserted_at=None,
                materialized_at=materialized_at.astimezone(UTC),
                status="REJECTED",
                observation_count=0,
                rejection_count=1,
                rejection_samples=[{"reason": "SOURCE_INSERTED_AT_UNAVAILABLE"}],
            )
        )
        return 0, 1
    observations, rejected = materialize_saved_fixture_observations(
        raw_payload_sha256=raw.sha256,
        raw_captured_at=_db_utc(raw.captured_at),
        raw_inserted_at=_db_utc(raw.inserted_at),
        payload=raw.payload,
        materialized_at=materialized_at,
    )
    added = 0
    for observation in observations:
        existing = session.scalar(
            select(ExpectedMatchFixtureObservationModel).where(
                ExpectedMatchFixtureObservationModel.provider
                == observation["provider"],
                ExpectedMatchFixtureObservationModel.provider_fixture_id
                == observation["provider_fixture_id"],
            )
        )
        if existing is not None and (
            existing.provider_league_id,
            existing.season,
            existing.home_provider_team_id,
            existing.away_provider_team_id,
        ) != (
            observation["provider_league_id"],
            observation["season"],
            observation["home_provider_team_id"],
            observation["away_provider_team_id"],
        ):
            rejected.append(
                {
                    "reason": "CANONICAL_PROVIDER_FIXTURE_IDENTITY_CONFLICT",
                    "sample": str(observation["provider_fixture_id"]),
                }
            )
            continue
        session.add(ExpectedMatchFixtureObservationModel(**observation))
        added += 1
    status = (
        "COMPLETE"
        if not rejected
        else "COMPLETE_WITH_REJECTIONS"
        if added
        else "REJECTED"
    )
    session.add(
        ExpectedMatchFixtureMaterializationModel(
            raw_payload_sha256=raw.sha256,
            source_captured_at=raw.captured_at,
            source_inserted_at=raw.inserted_at,
            materialized_at=materialized_at,
            status=status,
            observation_count=added,
            rejection_count=len(rejected),
            rejection_samples=rejected[:20],
        )
    )
    return added, len(rejected)


def _db_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
