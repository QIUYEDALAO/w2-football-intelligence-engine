from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, and_, desc, func, or_, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from w2.config import Settings
from w2.domain.canonical_serialization import (
    HashDomain,
    SerializerVersion,
    canonical_sha256,
)
from w2.features.xg_materialization import statistics_xg_by_team
from w2.identity import CanonicalIdentityRepository
from w2.identity.canonical_identity_repository import (
    PROVIDER_PRIMARY_READY,
    canonical_team_payload,
    provider_crosswalk_payload,
)
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamMatchHistoryModel,
    CanonicalTeamModel,
    ProviderTeamIdentityCrosswalkModel,
    TeamRatingSnapshotModel,
)
from w2.infrastructure.persistence.future_refresh_models import (
    ExpectedMatchFixtureMaterializationModel,
    ExpectedMatchFixtureObservationModel,
    FreePlanFixtureScopeObservationModel,
    FutureRefreshCheckpointAuditModel,
    FutureRefreshRunAuditModel,
    FutureRefreshTaskAuditModel,
    RawFixtureScopeMembershipModel,
    RawPayloadModel,
    RawStatisticsRetentionModel,
    TeamXgMatchModel,
    TeamXgRollingSnapshotModel,
)
from w2.infrastructure.persistence.ingestion_models import (
    ProviderQuotaObservationModel,
    ProviderRequestLogModel,
    QuotaUsageModel,
)
from w2.infrastructure.persistence.league_models import LeagueProfileModel, LeagueSeasonModel
from w2.infrastructure.persistence.market_projection_view import current_market_projection
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayEndpointCaptureModel,
    MatchdayFixtureIdentityModel,
    MatchdayMarketObservationModel,
)
from w2.infrastructure.persistence.model_forecast_models import (
    ModelForecastCaptureModel,
    ModelForecastOutcomeModel,
    canonical_model_forecast_fixture_id_sql,
    model_forecast_fixture_aliases,
)
from w2.infrastructure.persistence.models import (
    LineupSourceSnapshotModel,
    PlayerIdentityMappingModel,
    PlayerValuationObservationModel,
    StructuredLineupPlayerModel,
    StructuredLineupSnapshotModel,
    TeamLineupBaselineModel,
    TransfermarktPlayerReferenceModel,
    uuid_str,
)
from w2.ingestion.authoritative_lineup import (
    AuthoritativeLineupError,
    validate_authoritative_lineup,
)
from w2.ingestion.expected_match_materialization import (
    add_expected_match_fixture_materialization,
)
from w2.ingestion.raw_fixture_scope import (
    RAW_FIXTURE_SCOPE_POLICY_VERSION,
    RawFixtureScope,
    raw_fixture_scope_membership_contract,
)
from w2.lineups.intelligence import (
    build_team_baseline,
    build_team_rotation_prior,
    derive_lineup_change_features,
    lineup_requirement,
)
from w2.prematch.expected_match_denominator import (
    classify_expected_match_rows,
)
from w2.prematch.lifecycle import LineupConfirmedEvent
from w2.providers.control import provider_quota_authority_max_age_seconds

QUOTA_USAGE_LEDGER_DIVERGENCE_THRESHOLD = 5


class FutureRefreshPersistenceError(RuntimeError):
    pass


SCOPED_OBSERVATION_ROWS_PER_MARKET = 128
ROUND3_EVIDENCE_ROWS_PER_FIXTURE = 4096
ROUND3_ACTIVE_WHITELIST_SIZE = 13


def parse_db_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value:
        raise FutureRefreshPersistenceError("INVALID_DATETIME")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _fixture_aliases(fixture_id: str) -> tuple[str, ...]:
    return model_forecast_fixture_aliases(fixture_id)


def _round3_active_whitelist(rows: list[tuple[str, Any]]) -> set[str]:
    competition_ids = {
        str(competition_id)
        for competition_id, payload in rows
        if isinstance(payload, dict)
        and payload.get("scope_group") in {"top_five", "national_leagues"}
    }
    return competition_ids if len(competition_ids) == ROUND3_ACTIVE_WHITELIST_SIZE else set()


def _fixture_identity_candidates(
    session: Session,
    fixture_id: str,
) -> list[MatchdayFixtureIdentityModel]:
    aliases = _fixture_aliases(fixture_id)
    if not aliases:
        return []
    bare_aliases = [alias.removeprefix("api_football:") for alias in aliases]
    return list(
        session.scalars(
            select(MatchdayFixtureIdentityModel)
            .where(
                (MatchdayFixtureIdentityModel.fixture_id.in_(aliases))
                | (MatchdayFixtureIdentityModel.provider_fixture_id.in_(bare_aliases))
            )
            .order_by(MatchdayFixtureIdentityModel.captured_at.desc())
            .limit(2)
        )
    )


def _canonical_lineup_identity_hash(
    *,
    fixture_id: str,
    home_team_external_id: str,
    home_sorted_starter_ids: list[str],
    away_team_external_id: str,
    away_sorted_starter_ids: list[str],
) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "fixture_id": fixture_id,
                "home_team_external_id": home_team_external_id,
                "home_sorted_starter_ids": home_sorted_starter_ids,
                "away_team_external_id": away_team_external_id,
                "away_sorted_starter_ids": away_sorted_starter_ids,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _provider_teams_from_fixtures(
    fixtures: list[MatchdayFixtureIdentityModel],
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for fixture in fixtures:
        payload = fixture.payload if isinstance(fixture.payload, dict) else {}
        league = payload.get("league")
        country = (
            str(league.get("country") or "").strip() or None if isinstance(league, dict) else None
        )
        teams = payload.get("teams") if isinstance(payload.get("teams"), dict) else {}
        for side, provider_team_id in (
            ("home", fixture.home_provider_team_id),
            ("away", fixture.away_provider_team_id),
        ):
            team = teams.get(side) if isinstance(teams, dict) else None
            display_name = (
                str(team.get("name"))
                if isinstance(team, dict) and team.get("name")
                else provider_team_id
            )
            current = by_id.setdefault(
                provider_team_id,
                {
                    "provider_team_id": provider_team_id,
                    "display_name": display_name,
                    "country": country,
                    "evidence_hashes": [],
                },
            )
            if fixture.identity_hash not in current["evidence_hashes"]:
                current["evidence_hashes"].append(fixture.identity_hash)
    return [
        {**item, "evidence_hashes": sorted(item["evidence_hashes"])}
        for item in sorted(by_id.values(), key=lambda row: str(row["provider_team_id"]))
    ]


def _fixture_identity_semantic_hash(row: MatchdayFixtureIdentityModel) -> str:
    payload = {
        "schema_version": "MatchdayFixtureIdentitySemanticHashV1",
        "fixture_id": row.fixture_id,
        "provider": row.provider,
        "provider_fixture_id": row.provider_fixture_id,
        "competition_id": row.competition_id,
        "provider_league_id": row.provider_league_id,
        "season": row.season,
        "kickoff_utc": iso_z(parse_db_datetime(row.kickoff_utc)),
        "fixture_status": row.fixture_status,
        "home_provider_team_id": row.home_provider_team_id,
        "away_provider_team_id": row.away_provider_team_id,
        "home_w2_team_id": row.home_w2_team_id,
        "away_w2_team_id": row.away_w2_team_id,
        "team_identity_status": row.team_identity_status,
    }
    return canonical_sha256(
        payload,
        domain=HashDomain.FUTURE_REFRESH_FIXTURE_IDENTITY,
        version=SerializerVersion.LEGACY_V1,
    )


def _provider_identity_seed_result(
    canonical: int = 0,
    crosswalk: int = 0,
    ready: int = 0,
) -> dict[str, int]:
    return {
        "canonical_team_count": canonical,
        "provider_crosswalk_count": crosswalk,
        "fixture_identity_ready_count": ready,
    }


def iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _enabled_provider_league_id(league: LeagueSeasonModel | None) -> str | None:
    if league is None or not isinstance(league.payload, dict):
        return None
    if league.payload.get("enabled") is not True:
        return None
    mapping = league.payload.get("provider_mapping")
    mapping = mapping if isinstance(mapping, dict) else {}
    provider_league_id = str(
        league.payload.get("provider_league_id")
        or mapping.get("league_id")
        or mapping.get("api_football_league_id")
        or ""
    )
    return provider_league_id or None


def _expected_match_fail_closed(team_id: str, reason: str) -> dict[str, Any]:
    return {
        "status": "UNAVAILABLE_FAIL_CLOSED",
        "reason": reason,
        "team_id": team_id,
        "expected_match_count": None,
        "canonical_fixture_ids": [],
        "rows": [],
        "high_confidence_allowed": False,
    }


def _expected_match_observation_dict(
    row: ExpectedMatchFixtureObservationModel,
) -> dict[str, Any]:
    return {
        "observation_hash": row.observation_hash,
        "provider": row.provider,
        "provider_fixture_id": row.provider_fixture_id,
        "canonical_fixture_id": row.canonical_fixture_id,
        "provider_league_id": row.provider_league_id,
        "season": row.season,
        "kickoff_at": iso_z(row.kickoff_at),
        "home_provider_team_id": row.home_provider_team_id,
        "away_provider_team_id": row.away_provider_team_id,
        "fixture_status": row.fixture_status,
        "home_goals": row.home_goals,
        "away_goals": row.away_goals,
        "raw_payload_sha256": row.raw_payload_sha256,
        "captured_at": iso_z(row.captured_at),
        "source_inserted_at": iso_z(row.source_inserted_at),
    }


class DatabaseRawPayloadObjectStore:
    def __init__(self, session: Session) -> None:
        self.session = session

    def put(
        self,
        *,
        sha256: str,
        endpoint: str,
        captured_at: datetime,
        payload: dict[str, Any],
    ) -> str:
        storage_uri = f"db://raw_payload/{sha256}"
        inserted_at = datetime.now(UTC)
        raw = RawPayloadModel(
            sha256=sha256,
            endpoint=endpoint,
            captured_at=captured_at,
            inserted_at=inserted_at,
            storage_uri=storage_uri,
            payload=payload,
        )
        self.session.add(raw)
        if endpoint == "statistics":
            self.session.add(
                RawStatisticsRetentionModel(
                    raw_payload_sha256=sha256,
                    retained_at=datetime.now(UTC),
                )
            )
        elif endpoint == "fixtures":
            add_expected_match_fixture_materialization(
                self.session,
                raw,
                materialized_at=inserted_at,
            )
        return storage_uri

    def get(self, sha256: str) -> dict[str, Any] | None:
        row = self.session.get(RawPayloadModel, sha256)
        return dict(row.payload) if row is not None else None


class FutureRefreshDbRepository:
    def __init__(self, *, engine: Engine | None = None, settings: Settings | None = None) -> None:
        self.engine = engine or create_engine(settings)

    @staticmethod
    def _free_plan_fixture_scope_state_from_rows(
        rows: list[FreePlanFixtureScopeObservationModel],
    ) -> dict[str, Any]:
        if not rows:
            return {"observed": False, "restriction": None, "consecutive_count": 0}
        consecutive = []
        for row in rows:
            if not row.restricted:
                break
            consecutive.append(row)
        restriction = None
        if len(consecutive) >= 3:
            newest = consecutive[0]
            oldest = consecutive[-1]
            restriction = {
                "sample_count": len(consecutive),
                "observed_at_utc": f"{iso_z(oldest.observed_at)}/{iso_z(newest.observed_at)}",
                "payload_sha256": newest.payload_sha256,
                "provider_error": newest.provider_error,
                "evidence_source": "runtime_observations",
            }
        return {
            "observed": True,
            "restriction": restriction,
            "consecutive_count": len(consecutive),
        }

    def free_plan_fixture_scope_state(
        self,
        *,
        league_id: str,
        season: str,
    ) -> dict[str, Any]:
        try:
            with Session(self.engine) as session:
                rows = list(
                    session.scalars(
                        select(FreePlanFixtureScopeObservationModel)
                        .where(
                            FreePlanFixtureScopeObservationModel.provider == "api_football",
                            FreePlanFixtureScopeObservationModel.league_id == str(league_id),
                            FreePlanFixtureScopeObservationModel.season == str(season),
                        )
                        .order_by(FreePlanFixtureScopeObservationModel.observed_at.desc())
                    )
                )
        except Exception as exc:
            raise FutureRefreshPersistenceError(
                "FREE_PLAN_FIXTURE_SCOPE_OBSERVATION_READ_FAILED"
            ) from exc
        return self._free_plan_fixture_scope_state_from_rows(rows)

    def latest_provider_quota_authority(self) -> dict[str, Any]:
        try:
            with Session(self.engine) as session:
                row = session.scalar(
                    select(ProviderQuotaObservationModel)
                    .where(ProviderQuotaObservationModel.provider == "api_football")
                    .order_by(ProviderQuotaObservationModel.observed_at.desc())
                    .limit(1)
                )
        except Exception as exc:
            raise FutureRefreshPersistenceError("PROVIDER_QUOTA_AUTHORITY_READ_FAILED") from exc
        if row is None:
            return {}
        return {
            "observed_at": iso_z(row.observed_at),
            "daily_limit": row.daily_limit,
            "daily_remaining": row.daily_remaining,
            "burst_limit": row.burst_limit,
            "burst_remaining": row.burst_remaining,
        }

    def record_free_plan_fixture_scope_observation(
        self,
        *,
        league_id: str,
        season: str,
        restricted: bool,
        observed_at: datetime,
        payload_sha256: str,
        provider_error: str | None,
    ) -> dict[str, Any]:
        with Session(self.engine) as session:
            try:
                row = FreePlanFixtureScopeObservationModel(
                    id=uuid_str(),
                    provider="api_football",
                    league_id=str(league_id),
                    season=str(season),
                    restricted=bool(restricted),
                    observed_at=parse_db_datetime(observed_at),
                    payload_sha256=str(payload_sha256),
                    provider_error=str(provider_error) if provider_error else None,
                )
                session.add(row)
                session.commit()
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError(
                    "FREE_PLAN_FIXTURE_SCOPE_OBSERVATION_WRITE_FAILED"
                ) from exc
        current = self.free_plan_fixture_scope_state(
            league_id=str(league_id),
            season=str(season),
        )
        return {
            **current,
            "newly_confirmed": int(current["consecutive_count"]) == 3,
        }

    def seed_provider_primary_identity(
        self,
        *,
        competition_id: str,
        season: str,
        now: datetime,
    ) -> dict[str, int]:
        """Expand the canonical identity pool from already-persisted fixtures.

        This is a database-only operation. It never calls the Provider and does
        not grant reviewed Chinese-label authority.
        """
        normalized_now = parse_db_datetime(now)
        with Session(self.engine) as session:
            fixtures = list(
                session.scalars(
                    select(MatchdayFixtureIdentityModel)
                    .where(
                        MatchdayFixtureIdentityModel.provider == "api_football",
                        MatchdayFixtureIdentityModel.competition_id == competition_id,
                        MatchdayFixtureIdentityModel.season == season,
                    )
                    .order_by(MatchdayFixtureIdentityModel.kickoff_utc)
                )
            )
            if not fixtures:
                return _provider_identity_seed_result()
            canonical_count = 0
            crosswalk_count = 0
            for team in _provider_teams_from_fixtures(fixtures):
                provider_team_id = str(team["provider_team_id"])
                canonical = canonical_team_payload(
                    provider_team_id=provider_team_id,
                    display_name=str(team["display_name"]),
                    country=str(team["country"]) if team["country"] else None,
                    created_at=normalized_now,
                )
                existing_team = session.get(CanonicalTeamModel, str(canonical["w2_team_id"]))
                if existing_team is None:
                    try:
                        with session.begin_nested():
                            session.add(CanonicalTeamModel(**canonical))
                            session.flush()
                        canonical_count += 1
                    except IntegrityError:
                        pass
                    existing_team = session.get(CanonicalTeamModel, str(canonical["w2_team_id"]))
                if existing_team is None or (
                    existing_team.identity_hash != canonical["identity_hash"]
                ):
                    raise FutureRefreshPersistenceError("CANONICAL_TEAM_IDENTITY_CONFLICT")
                crosswalk = provider_crosswalk_payload(
                    provider_team_id=provider_team_id,
                    w2_team_id=str(canonical["w2_team_id"]),
                    competition_id=competition_id,
                    season=season,
                    evidence_hashes=list(team["evidence_hashes"]),
                    valid_from=normalized_now,
                )
                existing_crosswalk = session.get(
                    ProviderTeamIdentityCrosswalkModel, str(crosswalk["id"])
                )
                if existing_crosswalk is None:
                    try:
                        with session.begin_nested():
                            session.add(ProviderTeamIdentityCrosswalkModel(**crosswalk))
                            session.flush()
                        crosswalk_count += 1
                    except IntegrityError:
                        pass
                    existing_crosswalk = session.get(
                        ProviderTeamIdentityCrosswalkModel, str(crosswalk["id"])
                    )
                if existing_crosswalk is None or (
                    existing_crosswalk.provider != "api_football"
                    or existing_crosswalk.provider_team_id != provider_team_id
                    or existing_crosswalk.w2_team_id != canonical["w2_team_id"]
                    or existing_crosswalk.competition_id != competition_id
                    or existing_crosswalk.season != season
                    or existing_crosswalk.identity_status != PROVIDER_PRIMARY_READY
                ):
                    raise FutureRefreshPersistenceError("PROVIDER_TEAM_CROSSWALK_CONFLICT")
            mapping = CanonicalIdentityRepository.provider_team_mapping_in_session(
                session,
                provider="api_football",
                competition=competition_id,
                season=season,
                as_of=normalized_now,
            )
            ready = 0
            for fixture in fixtures:
                home = mapping.get(fixture.home_provider_team_id)
                away = mapping.get(fixture.away_provider_team_id)
                if home is None or away is None:
                    fixture.team_identity_status = "DATA_DEPENDENCY_MISSING"
                    continue
                fixture.home_w2_team_id = home
                fixture.away_w2_team_id = away
                fixture.team_identity_status = PROVIDER_PRIMARY_READY
                fixture.identity_hash = _fixture_identity_semantic_hash(fixture)
                ready += 1
            session.commit()
        return _provider_identity_seed_result(canonical_count, crosswalk_count, ready)

    def save_raw_payload(
        self,
        *,
        sha256: str,
        endpoint: str,
        captured_at: datetime,
        payload: dict[str, Any],
        fixture_scope: RawFixtureScope | str | None = None,
        request_identity: str | None = None,
        scope_policy_version: str = RAW_FIXTURE_SCOPE_POLICY_VERSION,
    ) -> str:
        with Session(self.engine) as session:
            store = DatabaseRawPayloadObjectStore(session)
            try:
                existing = session.get(RawPayloadModel, sha256)
                storage_uri = (
                    existing.storage_uri
                    if existing is not None
                    else store.put(
                        sha256=sha256,
                        endpoint=endpoint,
                        captured_at=captured_at,
                        payload=payload,
                    )
                )
                memberships = self._raw_fixture_scope_memberships(
                    raw_payload_sha256=sha256,
                    endpoint=endpoint,
                    payload=payload,
                    fixture_scope=fixture_scope,
                    request_identity=request_identity,
                    classified_at=datetime.now(UTC),
                    scope_policy_version=scope_policy_version,
                )
                for membership in memberships:
                    persisted = session.get(
                        RawFixtureScopeMembershipModel,
                        str(membership["membership_hash"]),
                    )
                    if persisted is None:
                        session.add(RawFixtureScopeMembershipModel(**membership))
                    elif not self._raw_fixture_scope_membership_matches(
                        persisted,
                        membership,
                    ):
                        raise FutureRefreshPersistenceError(
                            "RAW_FIXTURE_SCOPE_MEMBERSHIP_CONFLICT"
                        )
                session.commit()
                return storage_uri
            except IntegrityError:
                session.rollback()
                existing = session.get(RawPayloadModel, sha256)
                if existing is None:
                    raise FutureRefreshPersistenceError("RAW_PAYLOAD_CONFLICT") from None
                if not self._raw_fixture_scope_memberships_are_persisted(
                    session,
                    raw_payload_sha256=sha256,
                    endpoint=endpoint,
                    payload=payload,
                    fixture_scope=fixture_scope,
                    request_identity=request_identity,
                    scope_policy_version=scope_policy_version,
                ):
                    raise FutureRefreshPersistenceError(
                        "RAW_FIXTURE_SCOPE_MEMBERSHIP_CONFLICT"
                    ) from None
                return existing.storage_uri
            except FutureRefreshPersistenceError:
                session.rollback()
                raise
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("RAW_PAYLOAD_WRITE_FAILED") from exc

    def materialize_saved_expected_match_fixtures(
        self,
        *,
        as_of: datetime,
        limit: int = 256,
    ) -> dict[str, Any]:
        """Backfill a bounded batch from persisted fixture raw; never calls a provider."""
        before = parse_db_datetime(as_of)
        bounded_limit = max(0, min(int(limit), 2048))
        if bounded_limit == 0:
            return {
                "raw_payloads": 0,
                "observations": 0,
                "rejections": 0,
                "provider_calls": 0,
            }
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(RawPayloadModel)
                    .outerjoin(
                        ExpectedMatchFixtureMaterializationModel,
                        ExpectedMatchFixtureMaterializationModel.raw_payload_sha256
                        == RawPayloadModel.sha256,
                    )
                    .where(
                        RawPayloadModel.endpoint == "fixtures",
                        RawPayloadModel.captured_at <= before,
                        func.coalesce(
                            RawPayloadModel.inserted_at,
                            RawPayloadModel.captured_at,
                        )
                        <= before,
                        ExpectedMatchFixtureMaterializationModel.raw_payload_sha256.is_(
                            None
                        ),
                    )
                    .order_by(RawPayloadModel.captured_at, RawPayloadModel.sha256)
                    .limit(bounded_limit)
                )
            )
            observations = 0
            rejections = 0
            try:
                materialized_at = datetime.now(UTC)
                for row in rows:
                    added, rejected = add_expected_match_fixture_materialization(
                        session,
                        row,
                        materialized_at=materialized_at,
                    )
                    observations += added
                    rejections += rejected
                session.commit()
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError(
                    "EXPECTED_MATCH_MATERIALIZATION_WRITE_FAILED"
                ) from exc
        return {
            "raw_payloads": len(rows),
            "observations": observations,
            "rejections": rejections,
            "provider_calls": 0,
        }

    def expected_match_denominators_for_teams(
        self,
        team_ids: list[str],
        *,
        before: datetime,
        competition_id: str,
        season: str,
        limit_per_team: int = 20,
    ) -> list[dict[str, Any]]:
        """Read the enabled saved-raw denominator at one arbitrary PIT instant."""
        ids = [str(team_id) for team_id in dict.fromkeys(team_ids) if str(team_id)]
        bounded_limit = max(0, min(int(limit_per_team), 20))
        if not ids or len(ids) > 2 or bounded_limit == 0:
            return []
        as_of = parse_db_datetime(before)
        with Session(self.engine) as session:
            league = session.scalar(
                select(LeagueSeasonModel).where(
                    LeagueSeasonModel.competition_id == competition_id,
                    LeagueSeasonModel.season == season,
                )
            )
            provider_league_id = _enabled_provider_league_id(league)
            if provider_league_id is None:
                return [
                    _expected_match_fail_closed(team_id, "COMPETITION_NOT_ENABLED")
                    for team_id in ids
                ]
            latest = (
                select(
                    ExpectedMatchFixtureObservationModel.observation_hash.label(
                        "observation_hash"
                    ),
                    func.row_number()
                    .over(
                        partition_by=(
                            ExpectedMatchFixtureObservationModel.provider,
                            ExpectedMatchFixtureObservationModel.provider_fixture_id,
                        ),
                        order_by=(
                            ExpectedMatchFixtureObservationModel.captured_at.desc(),
                            ExpectedMatchFixtureObservationModel.source_inserted_at.desc(),
                            ExpectedMatchFixtureObservationModel.observation_hash.desc(),
                        ),
                    )
                    .label("rank"),
                )
                .where(
                    ExpectedMatchFixtureObservationModel.provider == "api_football",
                    ExpectedMatchFixtureObservationModel.provider_league_id
                    == provider_league_id,
                    ExpectedMatchFixtureObservationModel.captured_at <= as_of,
                    ExpectedMatchFixtureObservationModel.source_inserted_at <= as_of,
                )
                .subquery()
            )
            results = []
            for team_id in ids:
                rows = list(
                    session.scalars(
                        select(ExpectedMatchFixtureObservationModel)
                        .join(
                            latest,
                            ExpectedMatchFixtureObservationModel.observation_hash
                            == latest.c.observation_hash,
                        )
                        .where(
                            latest.c.rank == 1,
                            ExpectedMatchFixtureObservationModel.kickoff_at < as_of,
                            or_(
                                ExpectedMatchFixtureObservationModel.home_provider_team_id
                                == team_id,
                                ExpectedMatchFixtureObservationModel.away_provider_team_id
                                == team_id,
                            ),
                        )
                        .order_by(
                            ExpectedMatchFixtureObservationModel.kickoff_at.desc(),
                            ExpectedMatchFixtureObservationModel.provider_fixture_id.desc(),
                        )
                        .limit(bounded_limit * 4)
                    )
                )
                results.append(
                    classify_expected_match_rows(
                        [_expected_match_observation_dict(row) for row in rows],
                        team_id=team_id,
                        limit=bounded_limit,
                    )
                )
        return results

    @staticmethod
    def _raw_fixture_scope_membership_payload(
        row: RawFixtureScopeMembershipModel,
    ) -> dict[str, Any]:
        return {
            "membership_hash": row.membership_hash,
            "raw_payload_sha256": row.raw_payload_sha256,
            "provider_fixture_id": row.provider_fixture_id,
            "scope_policy_version": row.scope_policy_version,
            "source_scope": row.source_scope,
            "request_identity": row.request_identity,
            "classified_at": row.classified_at,
            "provider_league_id": row.provider_league_id,
            "kickoff_utc": iso_z(row.kickoff_utc) if row.kickoff_utc is not None else None,
        }

    @classmethod
    def _raw_fixture_scope_membership_matches(
        cls,
        row: RawFixtureScopeMembershipModel,
        expected: dict[str, Any],
    ) -> bool:
        persisted = cls._raw_fixture_scope_membership_payload(row)
        return all(
            persisted[key] == expected[key]
            for key in (
                "membership_hash",
                "raw_payload_sha256",
                "provider_fixture_id",
                "scope_policy_version",
                "source_scope",
                "request_identity",
                "provider_league_id",
            )
        ) and persisted["kickoff_utc"] == (
            iso_z(expected["kickoff_utc"])
            if expected.get("kickoff_utc") is not None
            else None
        )

    @staticmethod
    def _raw_fixture_scope_memberships(
        *,
        raw_payload_sha256: str,
        endpoint: str,
        payload: dict[str, Any],
        fixture_scope: RawFixtureScope | str | None,
        request_identity: str | None,
        classified_at: datetime,
        scope_policy_version: str,
    ) -> list[dict[str, Any]]:
        if fixture_scope is None:
            return []
        if endpoint != "fixtures" or not request_identity:
            raise FutureRefreshPersistenceError("RAW_FIXTURE_SCOPE_CONTEXT_INVALID")
        response = payload.get("response")
        if not isinstance(response, list):
            return []
        memberships: list[dict[str, Any]] = []
        for item in response:
            fixture = item.get("fixture") if isinstance(item, dict) else None
            provider_fixture_id = (
                str(fixture.get("id") or "") if isinstance(fixture, dict) else ""
            )
            if not provider_fixture_id:
                continue
            assert isinstance(fixture, dict)
            league = item.get("league") if isinstance(item, dict) else None
            provider_league_id = (
                str(league.get("id") or "") if isinstance(league, dict) else ""
            )
            try:
                kickoff_utc = parse_db_datetime(fixture.get("date"))
            except FutureRefreshPersistenceError:
                kickoff_utc = None
            memberships.append(
                raw_fixture_scope_membership_contract(
                    raw_payload_sha256=raw_payload_sha256,
                    provider_fixture_id=provider_fixture_id,
                    source_scope=fixture_scope,
                    request_identity=request_identity,
                    classified_at=classified_at,
                    provider_league_id=provider_league_id or None,
                    kickoff_utc=kickoff_utc,
                    scope_policy_version=scope_policy_version,
                )
            )
        return memberships

    def _raw_fixture_scope_memberships_are_persisted(
        self,
        session: Session,
        *,
        raw_payload_sha256: str,
        endpoint: str,
        payload: dict[str, Any],
        fixture_scope: RawFixtureScope | str | None,
        request_identity: str | None,
        scope_policy_version: str,
    ) -> bool:
        expected = self._raw_fixture_scope_memberships(
            raw_payload_sha256=raw_payload_sha256,
            endpoint=endpoint,
            payload=payload,
            fixture_scope=fixture_scope,
            request_identity=request_identity,
            classified_at=datetime.now(UTC),
            scope_policy_version=scope_policy_version,
        )
        for item in expected:
            row = session.get(RawFixtureScopeMembershipModel, str(item["membership_hash"]))
            if row is None:
                return False
            if not self._raw_fixture_scope_membership_matches(row, item):
                return False
        return True

    def save_lineup_snapshots(
        self,
        *,
        fixture_id: str,
        captured_at: datetime,
        raw_sha256: str,
        payload: dict[str, Any],
        materialize_baselines: bool = True,
        kickoff_at: datetime | None = None,
        source_capture_id: str | None = None,
        expected_team_ids: tuple[str, str] | None = None,
    ) -> int:
        with Session(self.engine) as identity_session:
            identities = _fixture_identity_candidates(identity_session, fixture_id)
        if len(identities) > 1:
            raise FutureRefreshPersistenceError("LINEUP_FIXTURE_IDENTITY_CONFLICT")
        if identities:
            identity = identities[0]
            expected_team_ids = (
                identity.home_provider_team_id,
                identity.away_provider_team_id,
            )
            kickoff_at = kickoff_at or parse_db_datetime(identity.kickoff_utc)
        response = payload.get("response")
        try:
            validated = validate_authoritative_lineup(
                response,
                expected_team_ids=expected_team_ids,
                captured_at=captured_at,
                kickoff_utc=kickoff_at,
            )
        except AuthoritativeLineupError as exc:
            raise FutureRefreshPersistenceError(exc.code) from exc
        snapshots: list[tuple[StructuredLineupSnapshotModel, list[dict[str, Any]]]] = []
        for team in validated.teams:
            starters = [player.as_persistence_dict(starter=True) for player in team.starters]
            substitutes = [player.as_persistence_dict(starter=False) for player in team.substitutes]
            starter_ids = [player.player_id for player in team.starters]
            lineup_identity_hash = hashlib.sha256(
                json.dumps(
                    {
                        "fixture_id": str(fixture_id),
                        "team_external_id": team.team_id,
                        "starters": sorted(starter_ids),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            snapshots.append(
                (
                    StructuredLineupSnapshotModel(
                        fixture_id=fixture_id,
                        team_external_id=team.team_id,
                        team_name=team.team_name,
                        formation=team.formation,
                        captured_at=captured_at,
                        confirmed=True,
                        authoritative_status="COMPLETE",
                        raw_sha256=raw_sha256,
                        lineup_identity_hash=lineup_identity_hash,
                        source_capture_id=source_capture_id,
                        schema_version="w2.structured_lineup.v2",
                    ),
                    [*starters, *substitutes],
                )
            )
        expected = self._lineup_replay_spec(snapshots)
        with Session(self.engine) as session:
            if self._lineup_replay_is_exact(session, expected):
                materialized = 0
            else:
                try:
                    for snapshot, players in snapshots:
                        session.add(snapshot)
                        session.flush()
                        for player in players:
                            session.add(
                                StructuredLineupPlayerModel(
                                    lineup_snapshot_id=snapshot.id,
                                    mapping_status="MISSING",
                                    **player,
                                )
                            )
                    session.commit()
                    materialized = len(snapshots)
                except IntegrityError:
                    session.rollback()
                    if not self._lineup_replay_is_exact(session, expected):
                        raise FutureRefreshPersistenceError(
                            "LINEUP_MATERIALIZATION_CONFLICT"
                        ) from None
                    materialized = 0
                except Exception as exc:
                    session.rollback()
                    raise FutureRefreshPersistenceError(
                        f"LINEUP_MATERIALIZATION_FAILED:{exc.__class__.__name__}"
                    ) from exc
        self.materialize_player_identity_mappings(fixture_id=fixture_id, as_of=captured_at)
        if materialize_baselines:
            self.materialize_team_lineup_baselines(limit=4096)
        return materialized

    @staticmethod
    def _lineup_replay_spec(
        snapshots: list[tuple[StructuredLineupSnapshotModel, list[dict[str, Any]]]],
    ) -> list[dict[str, Any]]:
        return sorted(
            (
                {
                    "fixture_id": snapshot.fixture_id,
                    "team_external_id": snapshot.team_external_id,
                    "team_name": snapshot.team_name,
                    "formation": snapshot.formation,
                    "captured_at": iso_z(snapshot.captured_at),
                    "confirmed": snapshot.confirmed,
                    "authoritative_status": snapshot.authoritative_status,
                    "raw_sha256": snapshot.raw_sha256,
                    "lineup_identity_hash": snapshot.lineup_identity_hash,
                    "source_capture_id": snapshot.source_capture_id,
                    "schema_version": snapshot.schema_version,
                    "players": sorted(
                        (dict(player) for player in players),
                        key=lambda player: (
                            str(player["api_football_player_id"]),
                            bool(player["starter"]),
                        ),
                    ),
                }
                for snapshot, players in snapshots
            ),
            key=lambda snapshot: str(snapshot["team_external_id"]),
        )

    def _lineup_replay_is_exact(
        self,
        session: Session,
        expected: list[dict[str, Any]],
    ) -> bool:
        fixture_id = str(expected[0]["fixture_id"])
        captured_at = str(expected[0]["captured_at"])
        snapshots = [
            row
            for row in session.scalars(
                select(StructuredLineupSnapshotModel).where(
                    StructuredLineupSnapshotModel.fixture_id == fixture_id
                )
            )
            if iso_z(row.captured_at) == captured_at
        ]
        if not snapshots:
            return False
        actual: list[dict[str, Any]] = []
        for snapshot in snapshots:
            players = list(
                session.scalars(
                    select(StructuredLineupPlayerModel).where(
                        StructuredLineupPlayerModel.lineup_snapshot_id == snapshot.id
                    )
                )
            )
            actual.append(
                {
                    "fixture_id": snapshot.fixture_id,
                    "team_external_id": snapshot.team_external_id,
                    "team_name": snapshot.team_name,
                    "formation": snapshot.formation,
                    "captured_at": iso_z(snapshot.captured_at),
                    "confirmed": snapshot.confirmed,
                    "authoritative_status": snapshot.authoritative_status,
                    "raw_sha256": snapshot.raw_sha256,
                    "lineup_identity_hash": snapshot.lineup_identity_hash,
                    "source_capture_id": snapshot.source_capture_id,
                    "schema_version": snapshot.schema_version,
                    "players": sorted(
                        (
                            {
                                "api_football_player_id": player.api_football_player_id,
                                "player_name": player.player_name,
                                "starter": player.starter,
                                "shirt_number": player.shirt_number,
                                "provider_position": player.provider_position,
                                "grid": player.grid,
                                "captain": player.captain,
                            }
                            for player in players
                        ),
                        key=lambda player: (
                            str(player["api_football_player_id"]),
                            bool(player["starter"]),
                        ),
                    ),
                }
            )
        actual.sort(key=lambda snapshot: str(snapshot["team_external_id"]))
        if actual != expected:
            raise FutureRefreshPersistenceError("LINEUP_MATERIALIZATION_CONFLICT")
        return True

    def confirmed_lineup_business_identity(self, *, fixture_id: str) -> str | None:
        """Return the latest complete capture's canonical XI identity."""
        with Session(self.engine) as session:
            events = self._canonical_lineup_events_in_session(session, fixture_id=fixture_id)
        return events[-1].lineup_input_hash if events else None

    def canonical_lineup_confirmed_event(
        self,
        fixture_id: str,
    ) -> LineupConfirmedEvent | None:
        with Session(self.engine) as session:
            events = self._canonical_lineup_events_in_session(session, fixture_id=fixture_id)
        hashes = {event.lineup_input_hash for event in events}
        if len(hashes) > 1:
            raise FutureRefreshPersistenceError("LINEUP_CONFIRMATION_CONFLICT")
        return events[0] if events else None

    def _canonical_lineup_events_in_session(
        self,
        session: Session,
        *,
        fixture_id: str,
    ) -> list[LineupConfirmedEvent]:
        identity = self._exact_fixture_identity_in_session(session, fixture_id=fixture_id)
        aliases = {
            alias
            for value in (fixture_id, identity.fixture_id, identity.provider_fixture_id)
            for alias in _fixture_aliases(value)
        }
        snapshots = list(
            session.scalars(
                select(StructuredLineupSnapshotModel)
                .where(StructuredLineupSnapshotModel.fixture_id.in_(aliases))
                .order_by(
                    StructuredLineupSnapshotModel.captured_at,
                    StructuredLineupSnapshotModel.id,
                )
            )
        )
        if not snapshots:
            return []
        captures = list(
            session.scalars(
                select(MatchdayEndpointCaptureModel).where(
                    MatchdayEndpointCaptureModel.endpoint == "lineups",
                    MatchdayEndpointCaptureModel.raw_payload_sha256.in_(
                        {snapshot.raw_sha256 for snapshot in snapshots}
                    ),
                )
            )
        )
        grouped: dict[
            tuple[str, str, datetime],
            list[StructuredLineupSnapshotModel],
        ] = {}
        for snapshot in snapshots:
            captured_at = parse_db_datetime(snapshot.captured_at)
            source_capture_id = str(snapshot.source_capture_id or "")
            if not source_capture_id:
                matches = [
                    capture
                    for capture in captures
                    if capture.fixture_id is not None
                    and aliases.intersection(_fixture_aliases(capture.fixture_id))
                    and capture.raw_payload_sha256 == snapshot.raw_sha256
                    and parse_db_datetime(capture.provider_captured_at) == captured_at
                ]
                if len(matches) != 1:
                    continue
                source_capture_id = matches[0].capture_id
            grouped.setdefault(
                (source_capture_id, snapshot.raw_sha256, captured_at),
                [],
            ).append(snapshot)

        snapshot_ids = [snapshot.id for rows in grouped.values() for snapshot in rows]
        starter_ids: dict[str, list[str]] = {}
        if snapshot_ids:
            for player in session.scalars(
                select(StructuredLineupPlayerModel).where(
                    StructuredLineupPlayerModel.lineup_snapshot_id.in_(snapshot_ids),
                    StructuredLineupPlayerModel.starter.is_(True),
                )
            ):
                starter_ids.setdefault(player.lineup_snapshot_id, []).append(
                    player.api_football_player_id
                )

        events: list[LineupConfirmedEvent] = []
        kickoff = parse_db_datetime(identity.kickoff_utc)
        canonical_fixture_id = identity.provider_fixture_id
        for (source_capture_id, raw_sha256, captured_at), rows in grouped.items():
            by_team = {row.team_external_id: row for row in rows}
            if (
                len(rows) != 2
                or len(by_team) != 2
                or any(
                    not row.confirmed
                    or row.authoritative_status != "COMPLETE"
                    or not row.lineup_identity_hash
                    for row in rows
                )
            ):
                continue
            home = by_team.get(identity.home_provider_team_id)
            away = by_team.get(identity.away_provider_team_id)
            if home is None or away is None:
                continue
            home_starters = sorted(starter_ids.get(home.id, []))
            away_starters = sorted(starter_ids.get(away.id, []))
            try:
                validate_authoritative_lineup(
                    [
                        {
                            "team_id": home.team_external_id,
                            "team_name": home.team_name,
                            "starters": [{"player_id": player_id} for player_id in home_starters],
                        },
                        {
                            "team_id": away.team_external_id,
                            "team_name": away.team_name,
                            "starters": [{"player_id": player_id} for player_id in away_starters],
                        },
                    ],
                    expected_team_ids=(
                        identity.home_provider_team_id,
                        identity.away_provider_team_id,
                    ),
                    captured_at=captured_at,
                    kickoff_utc=kickoff,
                )
            except AuthoritativeLineupError:
                continue
            events.append(
                LineupConfirmedEvent(
                    fixture_id=canonical_fixture_id,
                    competition_id=identity.competition_id,
                    season=identity.season,
                    captured_at=captured_at,
                    lineup_input_hash=_canonical_lineup_identity_hash(
                        fixture_id=canonical_fixture_id,
                        home_team_external_id=identity.home_provider_team_id,
                        home_sorted_starter_ids=home_starters,
                        away_team_external_id=identity.away_provider_team_id,
                        away_sorted_starter_ids=away_starters,
                    ),
                    home_starters=11,
                    away_starters=11,
                    home_lineup_identity_hash=str(home.lineup_identity_hash),
                    away_lineup_identity_hash=str(away.lineup_identity_hash),
                    source_capture_id=source_capture_id,
                    raw_sha256=raw_sha256,
                )
            )
        return sorted(
            events,
            key=lambda event: (
                event.captured_at,
                event.source_capture_id,
                event.lineup_input_hash,
            ),
        )

    @staticmethod
    def _exact_fixture_identity_in_session(
        session: Session,
        *,
        fixture_id: str,
    ) -> MatchdayFixtureIdentityModel:
        rows = _fixture_identity_candidates(session, fixture_id)
        if not rows:
            raise FutureRefreshPersistenceError("LINEUP_FIXTURE_IDENTITY_MISSING")
        if len(rows) != 1:
            raise FutureRefreshPersistenceError("LINEUP_FIXTURE_IDENTITY_CONFLICT")
        return rows[0]

    def materialize_player_identity_mappings(
        self,
        *,
        fixture_id: str,
        as_of: datetime,
    ) -> int:
        """Project reviewed canonical mappings onto the saved lineup."""
        if as_of.tzinfo is None:
            raise FutureRefreshPersistenceError("PLAYER_IDENTITY_AS_OF_TIMEZONE_INVALID")
        payload = self.fixture_payload(str(fixture_id))
        fixture = payload.get("fixture", {}) if isinstance(payload, dict) else {}
        league = payload.get("league", {}) if isinstance(payload, dict) else {}
        season = str(league.get("season") or "")
        try:
            kickoff = parse_db_datetime(fixture.get("date"))
        except FutureRefreshPersistenceError:
            kickoff = None
        with Session(self.engine) as session:
            snapshots = session.scalars(
                select(StructuredLineupSnapshotModel)
                .where(
                    StructuredLineupSnapshotModel.fixture_id == fixture_id,
                    StructuredLineupSnapshotModel.captured_at <= as_of,
                )
                .order_by(StructuredLineupSnapshotModel.captured_at.desc())
            ).all()
            latest: dict[str, StructuredLineupSnapshotModel] = {}
            for snapshot in snapshots:
                latest.setdefault(snapshot.team_external_id, snapshot)
            changed = 0
            for snapshot in latest.values():
                authority = (
                    CanonicalIdentityRepository.reviewed_team_authority_in_session(
                        session,
                        provider="api_football",
                        provider_team_id=snapshot.team_external_id,
                        season=season,
                        as_of=kickoff,
                    )
                    if kickoff is not None
                    else None
                )
                team_w2_id = authority.w2_team_id if authority else None
                if snapshot.team_w2_id != team_w2_id:
                    snapshot.team_w2_id = team_w2_id
                    changed += 1
                players = session.scalars(
                    select(StructuredLineupPlayerModel).where(
                        StructuredLineupPlayerModel.lineup_snapshot_id == snapshot.id
                    )
                ).all()
                for player in players:
                    mapping = (
                        CanonicalIdentityRepository.player_mapping_in_session(
                            session,
                            api_football_player_id=player.api_football_player_id,
                            w2_team_id=authority.w2_team_id,
                            competition=authority.competition_id,
                            season=season,
                            as_of=kickoff,
                        )
                        if authority and kickoff is not None
                        else None
                    )
                    values = (
                        mapping.id if mapping else None,
                        mapping.canonical_player_id if mapping else None,
                        mapping.transfermarkt_player_id if mapping else None,
                        mapping.mapping_status if mapping else "MISSING",
                    )
                    current = (
                        player.identity_mapping_id,
                        player.canonical_player_id,
                        player.valuation_source_player_id,
                        player.mapping_status,
                    )
                    if current != values:
                        (
                            player.identity_mapping_id,
                            player.canonical_player_id,
                            player.valuation_source_player_id,
                            player.mapping_status,
                        ) = values
                        changed += 1
            session.commit()
            return changed

    def player_identity_join_evidence(
        self,
        *,
        fixture_id: str,
        as_of: datetime,
    ) -> dict[str, Any]:
        """Read-only join proof backed by the canonical identity repository."""
        payload = self.fixture_payload(str(fixture_id))
        fixture = payload.get("fixture", {}) if isinstance(payload, dict) else {}
        league = payload.get("league", {}) if isinstance(payload, dict) else {}
        season = str(league.get("season") or "")
        try:
            kickoff = parse_db_datetime(fixture.get("date"))
        except FutureRefreshPersistenceError:
            kickoff = None
        with Session(self.engine) as session:
            snapshots = session.scalars(
                select(StructuredLineupSnapshotModel)
                .where(
                    StructuredLineupSnapshotModel.fixture_id == str(fixture_id),
                    StructuredLineupSnapshotModel.captured_at <= as_of,
                )
                .order_by(StructuredLineupSnapshotModel.captured_at.desc())
            ).all()
            latest: dict[str, StructuredLineupSnapshotModel] = {}
            for snapshot in snapshots:
                latest.setdefault(snapshot.team_external_id, snapshot)
            rows: list[dict[str, Any]] = []
            starters = 0
            for snapshot in latest.values():
                authority = (
                    CanonicalIdentityRepository.reviewed_team_authority_in_session(
                        session,
                        provider="api_football",
                        provider_team_id=snapshot.team_external_id,
                        season=season,
                        as_of=kickoff,
                    )
                    if kickoff is not None
                    else None
                )
                players = session.scalars(
                    select(StructuredLineupPlayerModel)
                    .where(
                        StructuredLineupPlayerModel.lineup_snapshot_id == snapshot.id,
                        StructuredLineupPlayerModel.starter.is_(True),
                    )
                    .order_by(StructuredLineupPlayerModel.api_football_player_id)
                ).all()
                starters += len(players)
                for player in players:
                    mapping = (
                        CanonicalIdentityRepository.player_mapping_in_session(
                            session,
                            api_football_player_id=player.api_football_player_id,
                            w2_team_id=authority.w2_team_id,
                            competition=authority.competition_id,
                            season=season,
                            as_of=kickoff,
                        )
                        if authority and kickoff is not None
                        else None
                    )
                    if mapping is None:
                        continue
                    rows.append(
                        {
                            "api_football_player_id": player.api_football_player_id,
                            "api_football_team_id": snapshot.team_external_id,
                            "canonical_team_id": mapping.evidence["canonical_team_id"],
                            "canonical_player_id": mapping.canonical_player_id,
                            "transfermarkt_player_id": mapping.transfermarkt_player_id,
                            "identity_hash": mapping.identity_hash,
                        }
                    )
            ordered_rows = sorted(
                rows,
                key=lambda row: (
                    row["api_football_team_id"],
                    row["api_football_player_id"],
                ),
            )
            provider_ids = {row["api_football_player_id"] for row in rows}
            canonical_ids = {row["canonical_player_id"] for row in rows}
            metrics = {
                "CONFIRMED_SNAPSHOTS": sum(row.confirmed for row in latest.values()),
                "CONFIRMED_STARTERS": starters,
                "UNIQUE_PROVIDER_PLAYERS": len(provider_ids),
                "UNIQUE_CANONICAL_PLAYERS": len(canonical_ids),
                "REVIEWED_MAPPINGS": len(rows),
                "MISSING_OR_INVALID": starters - len(rows),
                "DUPLICATE_CANONICAL": len(rows) - len(canonical_ids),
            }
            passed = metrics == {
                "CONFIRMED_SNAPSHOTS": 2,
                "CONFIRMED_STARTERS": 22,
                "UNIQUE_PROVIDER_PLAYERS": 22,
                "UNIQUE_CANONICAL_PLAYERS": 22,
                "REVIEWED_MAPPINGS": 22,
                "MISSING_OR_INVALID": 0,
                "DUPLICATE_CANONICAL": 0,
            }
            business_hash = hashlib.sha256(
                json.dumps(
                    ordered_rows,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            return {
                "schema_version": "w2.player_identity_join_evidence.v3",
                "fixture_id": str(fixture_id),
                "kickoff_utc": iso_z(kickoff) if kickoff is not None else None,
                "status": "PASS" if passed else "INCOMPLETE",
                "metrics": metrics,
                "rows": ordered_rows,
                "business_hash": business_hash,
                "provider_calls": 0,
                "db_writes": 0,
            }

    def lineup_gate_evidence(
        self,
        *,
        fixture_id: str,
        as_of: datetime,
    ) -> dict[str, Any]:
        payload = self.fixture_payload(str(fixture_id))
        fixture = payload.get("fixture", {}) if isinstance(payload, dict) else {}
        league = payload.get("league", {}) if isinstance(payload, dict) else {}
        season = str(league.get("season") or "")
        try:
            kickoff = parse_db_datetime(fixture.get("date"))
        except FutureRefreshPersistenceError:
            kickoff = None
        with Session(self.engine) as session:
            snapshots = session.scalars(
                select(StructuredLineupSnapshotModel)
                .where(
                    StructuredLineupSnapshotModel.fixture_id == fixture_id,
                    StructuredLineupSnapshotModel.captured_at <= as_of,
                )
                .order_by(StructuredLineupSnapshotModel.captured_at.desc())
            ).all()
            latest_by_team: dict[str, StructuredLineupSnapshotModel] = {}
            for snapshot in snapshots:
                latest_by_team.setdefault(snapshot.team_external_id, snapshot)
            selected = list(latest_by_team.values())
            if len(selected) != 2:
                return {
                    "status": "INCOMPLETE",
                    "confirmed": False,
                    "team_count": len(selected),
                    "starter_counts": [],
                    "uniquely_mapped_starters": 0,
                    "valued_starters": 0,
                    "formation_count": sum(bool(row.formation) for row in selected),
                    "blockers": ["LINEUP_SNAPSHOT_INCOMPLETE"],
                }
            rotation_priors = self._rotation_priors_in_session(
                session,
                team_external_ids=[snapshot.team_external_id for snapshot in selected],
                competition_external_id=str(league.get("id") or ""),
                season=season,
                as_of=kickoff or as_of,
            )
            if any(not snapshot.lineup_identity_hash for snapshot in selected):
                return {
                    "status": "INCOMPLETE",
                    "confirmed": False,
                    "team_count": len(selected),
                    "starter_counts": [],
                    "uniquely_mapped_starters": 0,
                    "valued_starters": 0,
                    "formation_count": sum(bool(row.formation) for row in selected),
                    "blockers": ["LINEUP_IDENTITY_HASH_MISSING"],
                    "rotation_priors": rotation_priors,
                    "schema_version": "w2.lineup_gate_evidence.v1",
                }
            starter_counts: list[int] = []
            mappings: list[PlayerIdentityMappingModel] = []
            valued_starter_api_ids: set[str] = set()
            baseline_hashes: list[str] = []
            change_features: list[dict[str, Any]] = []
            evidence_blockers: list[str] = []
            for snapshot in selected:
                players = session.scalars(
                    select(StructuredLineupPlayerModel).where(
                        StructuredLineupPlayerModel.lineup_snapshot_id == snapshot.id
                    )
                ).all()
                starters = [player for player in players if player.starter]
                substitutes = [player for player in players if not player.starter]
                starter_counts.append(len(starters))
                baseline = session.scalar(
                    select(TeamLineupBaselineModel)
                    .where(
                        TeamLineupBaselineModel.team_external_id == snapshot.team_external_id,
                        TeamLineupBaselineModel.as_of_time <= snapshot.captured_at,
                    )
                    .order_by(TeamLineupBaselineModel.as_of_time.desc())
                    .limit(1)
                )
                baseline_players = (
                    [
                        player
                        for player in baseline.payload.get("players", [])
                        if isinstance(player, dict)
                    ]
                    if baseline is not None
                    else []
                )
                all_api_ids = {
                    player.api_football_player_id for player in [*starters, *substitutes]
                } | {str(player.get("player_id") or "") for player in baseline_players}
                authority = (
                    CanonicalIdentityRepository.reviewed_team_authority_in_session(
                        session,
                        provider="api_football",
                        provider_team_id=snapshot.team_external_id,
                        season=season,
                        as_of=kickoff,
                    )
                    if kickoff is not None
                    else None
                )
                newest_mapping: dict[str, PlayerIdentityMappingModel] = {}
                if authority is not None and kickoff is not None:
                    for api_id in all_api_ids:
                        mapping = CanonicalIdentityRepository.player_mapping_in_session(
                            session,
                            api_football_player_id=api_id,
                            w2_team_id=authority.w2_team_id,
                            competition=authority.competition_id,
                            season=season,
                            as_of=kickoff,
                        )
                        if mapping is not None:
                            newest_mapping[api_id] = mapping
                starter_api_ids = {player.api_football_player_id for player in starters}
                mappings.extend(
                    mapping
                    for api_id, mapping in newest_mapping.items()
                    if api_id in starter_api_ids
                )
                transfermarkt_ids = {
                    str(mapping.transfermarkt_player_id)
                    for mapping in newest_mapping.values()
                    if mapping.transfermarkt_player_id
                }
                valuation_rows = session.scalars(
                    select(PlayerValuationObservationModel)
                    .where(
                        PlayerValuationObservationModel.transfermarkt_player_id.in_(
                            transfermarkt_ids
                        ),
                        PlayerValuationObservationModel.observed_at <= snapshot.captured_at,
                    )
                    .order_by(PlayerValuationObservationModel.observed_at.desc())
                ).all()
                newest_valuation: dict[str, PlayerValuationObservationModel] = {}
                for valuation in valuation_rows:
                    newest_valuation.setdefault(valuation.transfermarkt_player_id, valuation)

                def enriched_player(
                    api_id: str,
                    *,
                    position: str | None,
                    captain: bool = False,
                    original: dict[str, Any] | None = None,
                    mapping_lookup: dict[str, PlayerIdentityMappingModel] = newest_mapping,
                    valuation_lookup: dict[str, PlayerValuationObservationModel] = newest_valuation,
                    starter_ids: set[str] = starter_api_ids,
                ) -> dict[str, Any]:
                    result = dict(original or {})
                    mapping = mapping_lookup.get(api_id)
                    valuation = (
                        valuation_lookup.get(str(mapping.transfermarkt_player_id))
                        if mapping is not None and mapping.transfermarkt_player_id
                        else None
                    )
                    result.update(
                        player_id=api_id,
                        position=position,
                        captain=captain,
                        canonical_player_id=(mapping.canonical_player_id if mapping else None),
                        mapping_status=(mapping.mapping_status if mapping else "MISSING"),
                        valuation_source_player_id=(
                            mapping.transfermarkt_player_id if mapping else None
                        ),
                        market_value_eur=(
                            float(valuation.market_value_eur) if valuation is not None else None
                        ),
                        valuation_observed_at=(
                            valuation.observed_at if valuation is not None else None
                        ),
                        valuation_source=(valuation.source if valuation is not None else None),
                        valuation_source_artifact_hash=(
                            valuation.source_sha256 if valuation is not None else None
                        ),
                    )
                    if api_id in starter_ids and valuation is not None:
                        valued_starter_api_ids.add(api_id)
                    return result

                if baseline is None:
                    evidence_blockers.append("LINEUP_BASELINE_MISSING")
                    change_features.append(
                        {
                            "team_external_id": snapshot.team_external_id,
                            "status": "INCOMPLETE",
                            "blockers": ["LINEUP_BASELINE_MISSING"],
                        }
                    )
                else:
                    baseline_hashes.append(baseline.artifact_hash)
                    enriched_baseline = {
                        **baseline.payload,
                        "players": [
                            enriched_player(
                                str(player.get("player_id") or ""),
                                position=str(player.get("usual_position") or "") or None,
                                original=player,
                            )
                            for player in baseline_players
                        ],
                    }
                    features = derive_lineup_change_features(
                        baseline=enriched_baseline,
                        starters=[
                            enriched_player(
                                player.api_football_player_id,
                                position=player.provider_position,
                                captain=player.captain,
                            )
                            for player in starters
                        ],
                        substitutes=[
                            enriched_player(
                                player.api_football_player_id,
                                position=player.provider_position,
                                captain=player.captain,
                            )
                            for player in substitutes
                        ],
                        formation=snapshot.formation,
                    )
                    change_features.append(
                        {
                            "team_external_id": snapshot.team_external_id,
                            **asdict(features),
                            "blockers": list(features.blockers),
                            "baseline_artifact_hash": baseline.artifact_hash,
                        }
                    )
                    evidence_blockers.extend(features.blockers)
            if len({snapshot.captured_at for snapshot in selected}) != 1:
                evidence_blockers.append("LINEUP_SNAPSHOT_TIME_MISMATCH")
            if len(mappings) != 22:
                evidence_blockers.append("PLAYER_IDENTITY_MAPPING_INCOMPLETE")
            if len(valued_starter_api_ids) != 22:
                evidence_blockers.append("PLAYER_VALUATION_INCOMPLETE")
            return {
                "status": "COMPLETE"
                if starter_counts == [11, 11]
                and len(mappings) == 22
                and len(valued_starter_api_ids) == 22
                else "INCOMPLETE",
                "confirmed": all(snapshot.confirmed for snapshot in selected),
                "team_count": 2,
                "starter_counts": starter_counts,
                "uniquely_mapped_starters": len(mappings),
                "valued_starters": len(valued_starter_api_ids),
                "formation_count": sum(bool(snapshot.formation) for snapshot in selected),
                "captured_at": max(snapshot.captured_at for snapshot in selected).isoformat(),
                "raw_sha256": sorted({snapshot.raw_sha256 for snapshot in selected}),
                "baseline_artifact_hashes": sorted(set(baseline_hashes)),
                "lineup_change_features": change_features,
                "rotation_priors": rotation_priors,
                "blockers": sorted(set(evidence_blockers)),
                "schema_version": "w2.lineup_gate_evidence.v1",
            }

    def _rotation_priors_in_session(
        self,
        session: Session,
        *,
        team_external_ids: list[str],
        competition_external_id: str,
        season: str,
        as_of: datetime,
    ) -> list[dict[str, Any]]:
        identities = list(
            session.scalars(
                select(MatchdayFixtureIdentityModel)
                .where(
                    MatchdayFixtureIdentityModel.provider_league_id == competition_external_id,
                    MatchdayFixtureIdentityModel.season == season,
                    MatchdayFixtureIdentityModel.kickoff_utc < as_of,
                )
                .order_by(MatchdayFixtureIdentityModel.kickoff_utc.desc())
                .limit(256)
            )
        )
        history_aliases = {
            alias
            for identity in identities
            for value in (identity.fixture_id, identity.provider_fixture_id)
            for alias in _fixture_aliases(value)
        }
        snapshots = (
            list(
                session.scalars(
                    select(StructuredLineupSnapshotModel)
                    .where(
                        StructuredLineupSnapshotModel.fixture_id.in_(history_aliases),
                        StructuredLineupSnapshotModel.team_external_id.in_(team_external_ids),
                        StructuredLineupSnapshotModel.confirmed.is_(True),
                        StructuredLineupSnapshotModel.captured_at < as_of,
                    )
                    .order_by(
                        StructuredLineupSnapshotModel.captured_at.desc(),
                        StructuredLineupSnapshotModel.id,
                    )
                    .limit(256)
                )
            )
            if history_aliases
            else []
        )
        if not snapshots or not identities:
            return [
                build_team_rotation_prior(
                    [],
                    team_external_id=team_id,
                    as_of=as_of,
                )
                for team_id in sorted(set(team_external_ids))
            ]
        kickoff_by_fixture: dict[str, datetime] = {}
        for identity in identities:
            for alias in _fixture_aliases(identity.fixture_id):
                kickoff_by_fixture.setdefault(alias, identity.kickoff_utc)
            for alias in _fixture_aliases(identity.provider_fixture_id):
                kickoff_by_fixture.setdefault(alias, identity.kickoff_utc)
        snapshot_ids = [snapshot.id for snapshot in snapshots]
        players = list(
            session.scalars(
                select(StructuredLineupPlayerModel).where(
                    StructuredLineupPlayerModel.lineup_snapshot_id.in_(snapshot_ids),
                    StructuredLineupPlayerModel.starter.is_(True),
                )
            )
        )
        starters_by_snapshot: dict[str, list[dict[str, str]]] = {}
        for player in players:
            starters_by_snapshot.setdefault(player.lineup_snapshot_id, []).append(
                {"player_id": player.api_football_player_id}
            )
        rows = [
            {
                "fixture_id": snapshot.fixture_id,
                "team_external_id": snapshot.team_external_id,
                "kickoff_at": kickoff_by_fixture.get(snapshot.fixture_id),
                "captured_at": snapshot.captured_at,
                "confirmed": snapshot.confirmed,
                "starters": starters_by_snapshot.get(snapshot.id, []),
                "lineup_identity_hash": snapshot.lineup_identity_hash,
            }
            for snapshot in snapshots
        ]
        return [
            build_team_rotation_prior(
                rows,
                team_external_id=team_id,
                as_of=as_of,
            )
            for team_id in sorted(set(team_external_ids))
        ]

    def lineup_attribution_evidence_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Read bounded pre-kickoff lineup evidence for finished fixtures in one session."""
        requested = list(dict.fromkeys(str(value) for value in fixture_ids if value))
        if not requested or len(requested) > 512:
            return {}
        aliases = {alias for fixture_id in requested for alias in _fixture_aliases(fixture_id)}
        bare = {alias.removeprefix("api_football:") for alias in aliases}
        with Session(self.engine) as session:
            identities = list(
                session.scalars(
                    select(MatchdayFixtureIdentityModel)
                    .where(
                        (MatchdayFixtureIdentityModel.fixture_id.in_(aliases))
                        | (MatchdayFixtureIdentityModel.provider_fixture_id.in_(bare))
                    )
                    .order_by(MatchdayFixtureIdentityModel.captured_at.desc())
                )
            )
            selected_identity: dict[str, MatchdayFixtureIdentityModel | None] = {}
            identity_conflicts: set[str] = set()
            for fixture_id in requested:
                requested_aliases = set(_fixture_aliases(fixture_id))
                matches = [
                    identity
                    for identity in identities
                    if requested_aliases
                    & {
                        *_fixture_aliases(identity.fixture_id),
                        *_fixture_aliases(identity.provider_fixture_id),
                    }
                ]
                hashes = {identity.identity_hash for identity in matches}
                if len(hashes) > 1:
                    identity_conflicts.add(fixture_id)
                    selected_identity[fixture_id] = None
                else:
                    selected_identity[fixture_id] = matches[0] if matches else None
            snapshots = list(
                session.scalars(
                    select(StructuredLineupSnapshotModel)
                    .where(
                        StructuredLineupSnapshotModel.fixture_id.in_(aliases),
                        StructuredLineupSnapshotModel.confirmed.is_(True),
                    )
                    .order_by(StructuredLineupSnapshotModel.captured_at.desc())
                )
            )
            snapshot_by_fixture_team: dict[tuple[str, str], StructuredLineupSnapshotModel] = {}
            for requested_id, target_identity in selected_identity.items():
                if target_identity is None:
                    continue
                for snapshot in snapshots:
                    if snapshot.captured_at >= target_identity.kickoff_utc or not any(
                        alias in _fixture_aliases(snapshot.fixture_id)
                        for alias in _fixture_aliases(requested_id)
                    ):
                        continue
                    snapshot_by_fixture_team.setdefault(
                        (requested_id, snapshot.team_external_id),
                        snapshot,
                    )
            selected_snapshots = list(snapshot_by_fixture_team.values())
            players = (
                list(
                    session.scalars(
                        select(StructuredLineupPlayerModel).where(
                            StructuredLineupPlayerModel.lineup_snapshot_id.in_(
                                [snapshot.id for snapshot in selected_snapshots]
                            ),
                            StructuredLineupPlayerModel.starter.is_(True),
                        )
                    )
                )
                if selected_snapshots
                else []
            )
            starters_by_snapshot: dict[str, list[str]] = {}
            for player in players:
                starters_by_snapshot.setdefault(
                    player.lineup_snapshot_id,
                    [],
                ).append(player.api_football_player_id)
            baseline_conditions = []
            for (fixture_id, team_id), snapshot in snapshot_by_fixture_team.items():
                identity = selected_identity[fixture_id]
                if identity is None:
                    continue
                baseline_conditions.append(
                    and_(
                        TeamLineupBaselineModel.team_external_id == team_id,
                        TeamLineupBaselineModel.competition_external_id
                        == identity.provider_league_id,
                        TeamLineupBaselineModel.season == identity.season,
                        TeamLineupBaselineModel.as_of_time <= snapshot.captured_at,
                    )
                )
            baselines = (
                list(
                    session.scalars(
                        select(TeamLineupBaselineModel)
                        .where(or_(*baseline_conditions))
                        .order_by(TeamLineupBaselineModel.as_of_time.desc())
                    )
                )
                if baseline_conditions
                else []
            )
            result: dict[str, dict[str, Any]] = {}
            for fixture_id in requested:
                target_identity = selected_identity[fixture_id]
                if fixture_id in identity_conflicts:
                    result[fixture_id] = {
                        "status": "INCOMPLETE",
                        "fixture_id": fixture_id,
                        "home": None,
                        "away": None,
                        "blockers": ["FIXTURE_ID_ALIAS_CONFLICT"],
                    }
                    continue
                if target_identity is None:
                    result[fixture_id] = {
                        "status": "INCOMPLETE",
                        "blockers": ["FIXTURE_IDENTITY_MISSING"],
                    }
                    continue
                team_order = (
                    target_identity.home_provider_team_id,
                    target_identity.away_provider_team_id,
                )
                priors = {
                    item["team_external_id"]: item
                    for item in self._rotation_priors_in_session(
                        session,
                        team_external_ids=list(team_order),
                        competition_external_id=target_identity.provider_league_id,
                        season=target_identity.season,
                        as_of=target_identity.kickoff_utc,
                    )
                }
                teams: list[dict[str, Any]] = []
                blockers: list[str] = []
                for team_id in team_order:
                    target_snapshot = snapshot_by_fixture_team.get((fixture_id, team_id))
                    if target_snapshot is None:
                        blockers.append(f"{team_id}:LINEUP_SNAPSHOT_MISSING")
                        teams.append(
                            {
                                "team_external_id": team_id,
                                "starter_continuity": None,
                                "rotation_prior": priors.get(team_id),
                            }
                        )
                        continue
                    starter_ids = set(starters_by_snapshot.get(target_snapshot.id, []))
                    baseline = next(
                        (
                            row
                            for row in baselines
                            if row.team_external_id == team_id
                            and row.competition_external_id == target_identity.provider_league_id
                            and row.season == target_identity.season
                            and row.as_of_time <= target_snapshot.captured_at
                        ),
                        None,
                    )
                    regular = {
                        str(player.get("player_id") or "")
                        for player in (
                            baseline.payload.get("players", []) if baseline is not None else []
                        )
                        if isinstance(player, Mapping)
                        and float(player.get("starter_weight") or 0.0) >= 3.0
                    }
                    continuity = (
                        len(regular & starter_ids) / max(len(regular), 1)
                        if baseline is not None and len(starter_ids) == 11 and len(regular) > 0
                        else None
                    )
                    if continuity is None:
                        blockers.append(f"{team_id}:LINEUP_BASELINE_INCOMPLETE")
                    teams.append(
                        {
                            "team_external_id": team_id,
                            "starter_continuity": (
                                round(continuity, 12) if continuity is not None else None
                            ),
                            "rotation_prior": priors.get(team_id),
                            "lineup_identity_hash": target_snapshot.lineup_identity_hash,
                            "baseline_artifact_hash": (
                                baseline.artifact_hash if baseline is not None else None
                            ),
                        }
                    )
                payload = {
                    "status": "READY" if not blockers else "INCOMPLETE",
                    "fixture_id": fixture_id,
                    "kickoff_utc": iso_z(target_identity.kickoff_utc),
                    "lineup_requirement": lineup_requirement(target_identity.competition_id),
                    "home": teams[0],
                    "away": teams[1],
                    "blockers": sorted(blockers),
                }
                result[fixture_id] = {
                    **payload,
                    "input_hash": hashlib.sha256(
                        json.dumps(
                            payload,
                            sort_keys=True,
                            separators=(",", ":"),
                            default=str,
                        ).encode()
                    ).hexdigest(),
                }
            return result

    def import_transfermarkt_player_snapshot(
        self,
        *,
        source_url: str,
        source_sha256: str,
        observed_at: datetime,
        rows: list[dict[str, Any]],
    ) -> int:
        with Session(self.engine) as session:
            try:
                session.add(
                    LineupSourceSnapshotModel(
                        source="TRANSFERMARKT_DATASET",
                        source_revision=source_sha256,
                        schema_version="w2.transfermarkt_players.v1",
                        object_uri=source_url,
                        sha256=source_sha256,
                        observed_at=observed_at,
                        ingested_at=datetime.now(UTC),
                    )
                )
                for row in rows:
                    session.add(TransfermarktPlayerReferenceModel(**row))
                    value = row.get("market_value_eur")
                    if value is not None:
                        session.add(
                            PlayerValuationObservationModel(
                                transfermarkt_player_id=row["transfermarkt_player_id"],
                                observed_at=observed_at,
                                market_value_eur=value,
                                source="TRANSFERMARKT_DATASET",
                                source_sha256=source_sha256,
                                schema_version="w2.transfermarkt_player_value.v1",
                            )
                        )
                session.commit()
                return len(rows)
            except IntegrityError:
                session.rollback()
                source_exists = session.scalar(
                    select(func.count(LineupSourceSnapshotModel.id)).where(
                        LineupSourceSnapshotModel.sha256 == source_sha256
                    )
                )
                if source_exists:
                    return 0
                raise FutureRefreshPersistenceError("TRANSFERMARKT_IMPORT_CONFLICT") from None
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("TRANSFERMARKT_IMPORT_FAILED") from exc

    def structured_lineup_fixture_ids(self) -> list[str]:
        with Session(self.engine) as session:
            return list(
                session.scalars(select(StructuredLineupSnapshotModel.fixture_id).distinct()).all()
            )

    def stored_lineup_materialization_candidates(
        self,
        *,
        limit: int = 512,
    ) -> list[dict[str, Any]]:
        """Return bounded, saved lineup payloads for an explicit offline materializer.

        This is an administrative migration reader, not a public-request fallback.
        Fixture identity must come from the parameters saved with the original
        provider response; rows without that identity are excluded fail closed.
        """
        bounded_limit = max(0, min(int(limit), 4096))
        if bounded_limit == 0:
            return []
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == "lineups")
                    .order_by(RawPayloadModel.captured_at, RawPayloadModel.sha256)
                    .limit(bounded_limit)
                )
            )
        candidates: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row.payload)
            parameters = payload.get("parameters")
            fixture_id = (
                str(parameters.get("fixture") or "") if isinstance(parameters, dict) else ""
            )
            if not fixture_id:
                continue
            candidates.append(
                {
                    "fixture_id": fixture_id,
                    "captured_at": parse_db_datetime(row.captured_at),
                    "raw_sha256": row.sha256,
                    "payload": payload,
                }
            )
        return candidates

    def materialize_stored_lineup_payloads(self, *, limit: int = 512) -> dict[str, int]:
        """Idempotently materialize already-saved lineup payloads without a provider call."""
        candidates = self.stored_lineup_materialization_candidates(limit=limit)
        materialized_snapshots = 0
        skipped_incomplete = 0
        for candidate in candidates:
            try:
                materialized_snapshots += self.save_lineup_snapshots(
                    **candidate,
                    materialize_baselines=False,
                )
            except FutureRefreshPersistenceError as exc:
                if str(exc) in {"LINEUP_RESPONSE_INVALID", "LINEUP_TEAMS_INCOMPLETE"}:
                    skipped_incomplete += 1
                    continue
                raise
        return {
            "candidate_payload_count": len(candidates),
            "materialized_snapshot_count": materialized_snapshots,
            "skipped_incomplete_count": skipped_incomplete,
            "provider_calls": 0,
        }

    def materialize_team_lineup_baselines(self, *, limit: int = 512) -> dict[str, int]:
        """Build deterministic, as-of-safe baselines from structured saved lineups."""
        bounded_limit = max(0, min(int(limit), 4096))
        if bounded_limit == 0:
            return {
                "baseline_candidate_count": 0,
                "materialized_baseline_count": 0,
                "skipped_fixture_metadata_count": 0,
                "provider_calls": 0,
            }
        fixture_payloads = self.fixture_payloads()
        fixture_metadata: dict[str, dict[str, Any]] = {}
        for payload in fixture_payloads:
            fixture = payload.get("fixture")
            league = payload.get("league")
            if not isinstance(fixture, dict) or not isinstance(league, dict):
                continue
            fixture_id = str(fixture.get("id") or "")
            kickoff = fixture.get("date")
            if not fixture_id or not kickoff:
                continue
            fixture_metadata[fixture_id] = {
                "kickoff_at": parse_db_datetime(kickoff),
                "competition_external_id": str(league.get("id") or "unknown"),
                "season": str(league.get("season") or "unknown"),
            }
        with Session(self.engine) as session:
            snapshots = list(
                session.scalars(
                    select(StructuredLineupSnapshotModel)
                    .order_by(
                        StructuredLineupSnapshotModel.captured_at,
                        StructuredLineupSnapshotModel.fixture_id,
                        StructuredLineupSnapshotModel.team_external_id,
                    )
                    .limit(bounded_limit)
                )
            )
            rows: list[dict[str, Any]] = []
            for snapshot in snapshots:
                metadata = fixture_metadata.get(snapshot.fixture_id)
                if metadata is None:
                    continue
                starters = list(
                    session.scalars(
                        select(StructuredLineupPlayerModel).where(
                            StructuredLineupPlayerModel.lineup_snapshot_id == snapshot.id,
                            StructuredLineupPlayerModel.starter.is_(True),
                        )
                    )
                )
                rows.append(
                    {
                        "fixture_id": snapshot.fixture_id,
                        "team_external_id": snapshot.team_external_id,
                        "kickoff_at": metadata["kickoff_at"],
                        "captured_at": parse_db_datetime(snapshot.captured_at),
                        "formation": snapshot.formation,
                        "raw_sha256": snapshot.raw_sha256,
                        "competition_external_id": metadata["competition_external_id"],
                        "season": metadata["season"],
                        "starters": [
                            {
                                "player_id": player.api_football_player_id,
                                "position": player.provider_position,
                            }
                            for player in starters
                        ],
                    }
                )
            materialized = 0
            for target in rows:
                history_by_fixture: dict[str, dict[str, Any]] = {}
                for row in rows:
                    if (
                        row["team_external_id"] != target["team_external_id"]
                        or row["kickoff_at"] >= target["captured_at"]
                        or row["captured_at"] > target["captured_at"]
                    ):
                        continue
                    current = history_by_fixture.get(str(row["fixture_id"]))
                    if current is None or row["captured_at"] > current["captured_at"]:
                        history_by_fixture[str(row["fixture_id"])] = row
                history_rows = list(history_by_fixture.values())
                baseline = build_team_baseline(
                    history_rows,
                    team_external_id=str(target["team_external_id"]),
                    as_of=parse_db_datetime(target["captured_at"]),
                )
                selected_ids = set(baseline["input_fixture_ids"])
                input_rows = [
                    row
                    for row in history_rows
                    if row["team_external_id"] == target["team_external_id"]
                    and row["fixture_id"] in selected_ids
                ]
                input_manifest = {
                    "team_external_id": target["team_external_id"],
                    "as_of": parse_db_datetime(target["captured_at"]).isoformat(),
                    "input_fixture_ids": list(baseline["input_fixture_ids"]),
                    "input_raw_sha256": sorted({str(row["raw_sha256"]) for row in input_rows}),
                    "schema_version": "w2.lineup_baseline.input.v1",
                }
                existing = session.scalar(
                    select(TeamLineupBaselineModel).where(
                        TeamLineupBaselineModel.team_external_id == target["team_external_id"],
                        TeamLineupBaselineModel.competition_external_id
                        == target["competition_external_id"],
                        TeamLineupBaselineModel.season == target["season"],
                        TeamLineupBaselineModel.as_of_time == target["captured_at"],
                    )
                )
                if existing is not None:
                    if existing.artifact_hash != baseline["artifact_hash"]:
                        raise FutureRefreshPersistenceError("LINEUP_BASELINE_CONFLICT")
                    continue
                session.add(
                    TeamLineupBaselineModel(
                        team_external_id=str(target["team_external_id"]),
                        competition_external_id=str(target["competition_external_id"]),
                        season=str(target["season"]),
                        as_of_time=parse_db_datetime(target["captured_at"]),
                        match_count=int(baseline["match_count"]),
                        payload=baseline,
                        input_manifest=input_manifest,
                        artifact_hash=str(baseline["artifact_hash"]),
                        schema_version="w2.lineup_baseline.v1",
                    )
                )
                materialized += 1
            session.commit()
        return {
            "baseline_candidate_count": len(rows),
            "materialized_baseline_count": materialized,
            "skipped_fixture_metadata_count": len(snapshots) - len(rows),
            "provider_calls": 0,
        }

    def latest_market_observations(self) -> list[dict[str, Any]]:
        return self._canonical_market_observations_for_fixtures(None)

    def latest_market_observations_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> list[dict[str, Any]]:
        ids = [fixture_id for fixture_id in dict.fromkeys(fixture_ids) if fixture_id]
        if not ids or len(ids) > 64:
            return []
        return self._canonical_market_observations_for_fixtures(ids)

    def market_observation_timeline_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Read bounded canonical odds history without using the current projection."""
        ids = [fixture_id for fixture_id in dict.fromkeys(fixture_ids) if fixture_id]
        if not ids or len(ids) > 64:
            return []
        canonical_ids = {
            value if value.startswith("api_football:") else f"api_football:{value}" for value in ids
        }
        ranked = (
            select(
                MatchdayMarketObservationModel.observation_id.label("observation_id"),
                func.row_number()
                .over(
                    partition_by=(
                        MatchdayMarketObservationModel.fixture_id,
                        MatchdayMarketObservationModel.canonical_market,
                    ),
                    order_by=(
                        MatchdayMarketObservationModel.captured_at.desc(),
                        MatchdayMarketObservationModel.observation_id.desc(),
                    ),
                )
                .label("row_number"),
            )
            .where(
                MatchdayMarketObservationModel.fixture_id.in_(canonical_ids),
                MatchdayMarketObservationModel.canonical_market.in_(("ASIAN_HANDICAP", "TOTALS")),
            )
            .subquery()
        )
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(MatchdayMarketObservationModel)
                    .join(
                        ranked,
                        MatchdayMarketObservationModel.observation_id == ranked.c.observation_id,
                    )
                    .where(ranked.c.row_number <= SCOPED_OBSERVATION_ROWS_PER_MARKET)
                    .order_by(
                        MatchdayMarketObservationModel.captured_at,
                        MatchdayMarketObservationModel.observation_id,
                    )
                )
            )
        return [
            {
                "observation_id": row.observation_id,
                "fixture_id": row.fixture_id.removeprefix("api_football:"),
                "provider": row.provider,
                "bookmaker_id": row.bookmaker_id,
                "canonical_market": row.canonical_market,
                "canonical_selection": row.canonical_selection,
                "selection": row.canonical_selection,
                "line": row.line,
                "decimal_odds": row.decimal_odds,
                "captured_at": iso_z(row.captured_at),
                "live": row.live,
                "suspended": row.suspended,
                "capture_id": row.capture_id,
                "raw_payload_sha256": row.raw_payload_sha256,
                "source_revision": row.source_revision,
            }
            for row in rows
        ]

    def round3_market_evidence_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Read real market history and its complete persisted lineage."""
        ids = [fixture_id for fixture_id in dict.fromkeys(fixture_ids) if fixture_id]
        if not ids or len(ids) > 64:
            return []
        canonical_ids = {
            value if value.startswith("api_football:") else f"api_football:{value}" for value in ids
        }
        observation_raw = aliased(RawPayloadModel)
        capture_raw = aliased(RawPayloadModel)
        identity_raw = aliased(RawPayloadModel)
        ranked = (
            select(
                MatchdayMarketObservationModel.observation_id.label("observation_id"),
                func.row_number()
                .over(
                    partition_by=MatchdayMarketObservationModel.fixture_id,
                    order_by=(
                        MatchdayMarketObservationModel.captured_at.desc(),
                        MatchdayMarketObservationModel.observation_id.desc(),
                    ),
                )
                .label("row_number"),
            )
            .where(MatchdayMarketObservationModel.fixture_id.in_(canonical_ids))
            .subquery()
        )
        try:
            with Session(self.engine) as session:
                active_whitelist = _round3_active_whitelist(
                    [
                        (str(competition_id), payload)
                        for competition_id, payload in session.execute(
                            select(
                                LeagueProfileModel.competition_id,
                                LeagueProfileModel.payload,
                            )
                        )
                    ]
                )
                rows = session.execute(
                    select(
                        MatchdayMarketObservationModel,
                        MatchdayEndpointCaptureModel,
                        MatchdayFixtureIdentityModel,
                        observation_raw.sha256,
                        observation_raw.storage_uri,
                        observation_raw.payload["synthetic"].as_boolean(),
                        observation_raw.payload["test_only"].as_boolean(),
                        capture_raw.sha256,
                        identity_raw.sha256,
                    )
                    .join(
                        ranked,
                        MatchdayMarketObservationModel.observation_id == ranked.c.observation_id,
                    )
                    .outerjoin(
                        MatchdayEndpointCaptureModel,
                        MatchdayEndpointCaptureModel.capture_id
                        == MatchdayMarketObservationModel.capture_id,
                    )
                    .outerjoin(
                        MatchdayFixtureIdentityModel,
                        MatchdayFixtureIdentityModel.fixture_id
                        == MatchdayMarketObservationModel.fixture_id,
                    )
                    .outerjoin(
                        observation_raw,
                        observation_raw.sha256 == MatchdayMarketObservationModel.raw_payload_sha256,
                    )
                    .outerjoin(
                        capture_raw,
                        capture_raw.sha256 == MatchdayEndpointCaptureModel.raw_payload_sha256,
                    )
                    .outerjoin(
                        identity_raw,
                        identity_raw.sha256 == MatchdayFixtureIdentityModel.raw_payload_sha256,
                    )
                    .where(ranked.c.row_number <= ROUND3_EVIDENCE_ROWS_PER_FIXTURE)
                    .order_by(
                        MatchdayMarketObservationModel.fixture_id,
                        MatchdayMarketObservationModel.captured_at,
                        MatchdayMarketObservationModel.observation_id,
                    )
                ).all()
        except Exception as exc:
            raise FutureRefreshPersistenceError("ROUND3_MARKET_EVIDENCE_QUERY_FAILED") from exc
        evidence = []
        for (
            observation,
            capture,
            identity,
            raw_sha,
            raw_uri,
            raw_synthetic,
            raw_test_only,
            capture_sha,
            identity_sha,
        ) in rows:
            evidence.append(
                {
                    "observation_id": observation.observation_id,
                    "fixture_id": observation.fixture_id,
                    "provider_fixture_id": observation.provider_fixture_id,
                    "competition_id": observation.competition_id,
                    "provider": observation.provider,
                    "bookmaker_id": observation.bookmaker_id,
                    "bookmaker_name": observation.bookmaker_name,
                    "capture_id": observation.capture_id,
                    "capture_checkpoint": capture.checkpoint if capture else None,
                    "raw_market_label": observation.raw_market_label,
                    "canonical_market": observation.canonical_market,
                    "canonical_selection": observation.canonical_selection,
                    "line": observation.line,
                    "decimal_odds": observation.decimal_odds,
                    "suspended": observation.suspended,
                    "live": observation.live,
                    "provider_updated_at": observation.provider_updated_at or None,
                    "captured_at": iso_z(observation.captured_at),
                    "raw_payload_sha256": observation.raw_payload_sha256,
                    "source_revision": observation.source_revision,
                    "raw_storage_uri": raw_uri,
                    "synthetic": raw_synthetic is True or raw_test_only is True,
                    "raw_lineage_present": bool(raw_sha),
                    "capture_lineage_present": bool(capture and capture_sha),
                    "fixture_identity_present": bool(identity and identity_sha),
                    "runtime_whitelist_member": observation.competition_id in active_whitelist,
                    "capture_identity_conflict": bool(
                        capture
                        and (
                            capture.capture_id != observation.capture_id
                            or capture.fixture_id not in _fixture_aliases(observation.fixture_id)
                            or capture.competition_id != observation.competition_id
                            or capture.raw_payload_sha256 != observation.raw_payload_sha256
                            or capture.endpoint != "odds"
                        )
                    ),
                    "identity_conflict": bool(
                        identity
                        and (
                            identity.fixture_id != observation.fixture_id
                            or identity.provider_fixture_id != observation.provider_fixture_id
                            or identity.competition_id != observation.competition_id
                            or identity.provider != observation.provider
                        )
                    ),
                }
            )
        return evidence

    def matchday_fixture_identity(self, fixture_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            rows = _fixture_identity_candidates(session, fixture_id)
        if not rows:
            return None
        identities = {row.identity_hash for row in rows if row.identity_hash}
        if len(identities) > 1:
            return {
                "status": "FIXTURE_ID_ALIAS_CONFLICT",
                "fixture_id": fixture_id,
                "matched_fixture_ids": [row.fixture_id for row in rows],
                "matched_identity_hashes": sorted(identities),
            }
        row = rows[0]
        return {
            "status": row.team_identity_status,
            "fixture_id": row.fixture_id,
            "provider": row.provider,
            "provider_fixture_id": row.provider_fixture_id,
            "competition_id": row.competition_id,
            "season": row.season,
            "kickoff_utc": iso_z(row.kickoff_utc),
            "home_provider_team_id": row.home_provider_team_id,
            "away_provider_team_id": row.away_provider_team_id,
            "home_w2_team_id": row.home_w2_team_id,
            "away_w2_team_id": row.away_w2_team_id,
            "identity_hash": row.identity_hash,
            "raw_payload_sha256": row.raw_payload_sha256,
            "endpoint_capture_id": row.endpoint_capture_id,
        }

    def canonical_match_history_for_teams(
        self,
        team_ids: list[str],
        *,
        before: datetime,
        limit_per_team: int = 20,
    ) -> list[dict[str, Any]]:
        ids = [team_id for team_id in dict.fromkeys(team_ids) if team_id]
        if not ids or len(ids) > 8:
            return []
        ranked = (
            select(
                CanonicalTeamMatchHistoryModel.history_id.label("history_id"),
                func.row_number()
                .over(
                    partition_by=CanonicalTeamMatchHistoryModel.team_w2_id,
                    order_by=CanonicalTeamMatchHistoryModel.kickoff_utc.desc(),
                )
                .label("rank"),
            )
            .where(
                CanonicalTeamMatchHistoryModel.team_w2_id.in_(ids),
                CanonicalTeamMatchHistoryModel.kickoff_utc < before,
            )
            .subquery()
        )
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(CanonicalTeamMatchHistoryModel)
                    .join(
                        ranked,
                        CanonicalTeamMatchHistoryModel.history_id == ranked.c.history_id,
                    )
                    .where(ranked.c.rank <= limit_per_team)
                    .order_by(
                        CanonicalTeamMatchHistoryModel.team_w2_id,
                        CanonicalTeamMatchHistoryModel.kickoff_utc,
                    )
                )
            )
        return [self._canonical_match_history_dict(row) for row in rows]

    def team_rating_snapshots_for_w2_teams(
        self,
        team_ids: list[str],
        *,
        before: datetime,
    ) -> list[dict[str, Any]]:
        ids = [team_id for team_id in dict.fromkeys(team_ids) if team_id]
        if not ids or len(ids) > 8:
            return []
        ranked = (
            select(
                TeamRatingSnapshotModel.rating_id.label("rating_id"),
                func.row_number()
                .over(
                    partition_by=TeamRatingSnapshotModel.w2_team_id,
                    order_by=TeamRatingSnapshotModel.observed_at.desc(),
                )
                .label("rank"),
            )
            .where(
                TeamRatingSnapshotModel.w2_team_id.in_(ids),
                TeamRatingSnapshotModel.observed_at < before,
            )
            .subquery()
        )
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(TeamRatingSnapshotModel)
                    .join(ranked, TeamRatingSnapshotModel.rating_id == ranked.c.rating_id)
                    .where(ranked.c.rank == 1)
                    .order_by(TeamRatingSnapshotModel.w2_team_id)
                )
            )
        return [self._team_rating_snapshot_dict(row) for row in rows]

    def team_xg_rolling_snapshots_for_w2_teams(
        self,
        team_ids: list[str],
        *,
        before: datetime,
        competition_id: str,
        season: str,
    ) -> list[dict[str, Any]]:
        ids = [team_id for team_id in dict.fromkeys(team_ids) if team_id]
        if not ids or len(ids) > 2:
            return []
        with Session(self.engine) as session:
            crosswalk_rows = list(
                session.scalars(
                    select(ProviderTeamIdentityCrosswalkModel).where(
                        ProviderTeamIdentityCrosswalkModel.w2_team_id.in_(ids),
                        ProviderTeamIdentityCrosswalkModel.competition_id == competition_id,
                        ProviderTeamIdentityCrosswalkModel.season == season,
                        ProviderTeamIdentityCrosswalkModel.provider == "api_football",
                        ProviderTeamIdentityCrosswalkModel.identity_status.in_(
                            ("PROVIDER_PRIMARY_READY", "READY")
                        ),
                    )
                )
            )
        provider_to_w2 = {row.provider_team_id: row.w2_team_id for row in crosswalk_rows}
        if not provider_to_w2:
            return []
        provider_rows = self.team_xg_rolling_snapshots_for_teams(
            list(provider_to_w2),
            before=before,
        )
        projected: list[dict[str, Any]] = []
        for row in provider_rows:
            provider_team_id = str(row.get("team_id") or "")
            w2_team_id = provider_to_w2.get(provider_team_id)
            if not w2_team_id:
                continue
            projected.append(
                {
                    **row,
                    "team_id": w2_team_id,
                    "provider_team_id": provider_team_id,
                    "identity_projection": "PROVIDER_TEAM_ID_TO_W2_TEAM_ID",
                    "identity_projection_status": "READY",
                }
            )
        return projected

    def provider_team_mapping(
        self,
        *,
        provider: str,
        competition_id: str,
        season: str,
        as_of: datetime,
    ) -> dict[str, str]:
        with Session(self.engine) as session:
            return CanonicalIdentityRepository.provider_team_mapping_in_session(
                session,
                provider=provider,
                competition=competition_id,
                season=season,
                as_of=as_of,
            )

    def team_xg_matches_for_w2_teams(
        self,
        team_ids: list[str],
        *,
        before: datetime,
        limit_per_team: int = 20,
    ) -> list[dict[str, Any]]:
        ids = [team_id for team_id in dict.fromkeys(team_ids) if team_id]
        if not ids or len(ids) > 8:
            return []
        with Session(self.engine) as session:
            crosswalk_rows = list(
                session.scalars(
                    select(ProviderTeamIdentityCrosswalkModel).where(
                        ProviderTeamIdentityCrosswalkModel.w2_team_id.in_(ids),
                        ProviderTeamIdentityCrosswalkModel.provider == "api_football",
                        ProviderTeamIdentityCrosswalkModel.identity_status.in_(
                            ("PROVIDER_PRIMARY_READY", "READY")
                        ),
                    )
                )
            )
        provider_to_w2 = {row.provider_team_id: row.w2_team_id for row in crosswalk_rows}
        if not provider_to_w2:
            return []
        rows = self.team_xg_matches_for_teams(
            list(provider_to_w2),
            before=before,
            limit_per_team=limit_per_team,
        )
        projected: list[dict[str, Any]] = []
        for row in rows:
            provider_team_id = str(row.get("team_id") or "")
            w2_team_id = provider_to_w2.get(provider_team_id)
            if not w2_team_id:
                continue
            projected.append(
                {
                    **row,
                    "team_id": w2_team_id,
                    "provider_team_id": provider_team_id,
                    "identity_projection": "PROVIDER_TEAM_ID_TO_W2_TEAM_ID",
                    "identity_projection_status": "READY",
                }
            )
        return projected

    def _projection_observations(
        self,
        *,
        canonical_fixture_ids: set[str] | None = None,
        canonical_markets: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        """Read the current-market projection from its only authority.

        `current_market_projection` is a view over the canonical history that
        keeps the latest non-suspended, non-live quote per fixture, market,
        bookmaker, selection and line. Nothing is recomputed here.

        The order is total: `line` and `observation_id` complete the sort so a
        caller that bounds rows per market always keeps the same rows. The
        previous in-memory projection sorted only to `canonical_selection`,
        which left rows differing by `line` in an arbitrary order.
        """
        projection = current_market_projection
        query = select(projection)
        if canonical_fixture_ids is not None:
            query = query.where(projection.c.fixture_id.in_(canonical_fixture_ids))
        if canonical_markets is not None:
            query = query.where(projection.c.canonical_market.in_(canonical_markets))
        query = query.order_by(
            projection.c.provider,
            projection.c.projection_fixture_id,
            projection.c.canonical_market,
            projection.c.bookmaker_id,
            projection.c.canonical_selection,
            projection.c.line,
            projection.c.observation_id,
        )
        with Session(self.engine) as session:
            rows = list(session.execute(query).mappings())
        return [self._projection_row_dict(row) for row in rows]

    @staticmethod
    def _projection_row_dict(row: RowMapping) -> dict[str, Any]:
        return {
            "observation_id": row["observation_id"],
            "fixture_id": row["projection_fixture_id"],
            "provider": row["provider"],
            "bookmaker_id": row["bookmaker_id"],
            "bookmaker_name": row["bookmaker_name"],
            "capture_id": row["capture_id"],
            "provider_bet_id": row["provider_bet_id"],
            "raw_market_label": row["raw_market_label"],
            "canonical_market": row["canonical_market"],
            "selection": row["canonical_selection"],
            "line": row["line"],
            "decimal_odds": row["decimal_odds"],
            "suspended": row["suspended"],
            "live": row["live"],
            "provider_last_update": row["provider_updated_at"],
            "captured_at": iso_z(row["captured_at"]),
            "ingested_at": iso_z(row["ingested_at"]),
            "raw_payload_sha256": row["raw_payload_sha256"],
            "source_revision": row["source_revision"],
            "candidate": False,
            "formal_recommendation": False,
        }

    def _canonical_market_observations_for_fixtures(
        self,
        fixture_ids: list[str] | None,
    ) -> list[dict[str, Any]]:
        if fixture_ids is None:
            return self._projection_observations()

        canonical_ids = {
            fixture_id if fixture_id.startswith("api_football:") else f"api_football:{fixture_id}"
            for fixture_id in fixture_ids
        }
        latest_rows = self._projection_observations(
            canonical_fixture_ids=canonical_ids,
            canonical_markets=("ASIAN_HANDICAP", "TOTALS"),
        )

        # Grouped by provider as well: fixture ids are only unique within a
        # provider, so grouping on the bare id would let two providers share one
        # bound and truncate each other's quotes.
        bounded: list[dict[str, Any]] = []
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in latest_rows:
            group_key = (
                str(row["provider"]),
                str(row["fixture_id"]),
                str(row["canonical_market"]),
            )
            grouped.setdefault(group_key, []).append(row)
        for group_key in sorted(grouped):
            bounded.extend(grouped[group_key][:SCOPED_OBSERVATION_ROWS_PER_MARKET])
        return bounded

    def fixture_payloads(self, *, provider_league_id: str | None = None) -> list[dict[str, Any]]:
        fixtures: dict[str, dict[str, Any]] = {}
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == "fixtures")
                    .order_by(RawPayloadModel.captured_at)
                )
            )
        for row in rows:
            response = row.payload.get("response")
            if not isinstance(response, list):
                continue
            for item in response:
                if not isinstance(item, dict):
                    continue
                if provider_league_id is not None:
                    league_id = str(item.get("league", {}).get("id") or "")
                    if league_id != provider_league_id:
                        continue
                fixture_id = str(item.get("fixture", {}).get("id"))
                if fixture_id and fixture_id != "None":
                    fixtures[fixture_id] = item
        return sorted(fixtures.values(), key=lambda item: item.get("fixture", {}).get("date", ""))

    def live_fixture_payloads(
        self,
        *,
        provider_league_id: str | None,
        kickoff_from: datetime,
        kickoff_to: datetime,
        scope_policy_version: str = RAW_FIXTURE_SCOPE_POLICY_VERSION,
    ) -> list[dict[str, Any]]:
        """Reserved scoped reader; the active planner still uses fixture_payloads()."""
        return self._fixture_payloads_for_scope(
            source_scope=RawFixtureScope.LIVE_DISCOVERY,
            provider_league_id=provider_league_id,
            kickoff_from=kickoff_from,
            kickoff_to=kickoff_to,
            scope_policy_version=scope_policy_version,
        )

    def historical_fixture_payloads(
        self,
        *,
        kickoff_from: datetime,
        kickoff_to: datetime,
        provider_league_id: str | None = None,
        scope_policy_version: str = RAW_FIXTURE_SCOPE_POLICY_VERSION,
    ) -> list[dict[str, Any]]:
        """Reserved scoped reader; Gate 1 history is selected by kickoff time."""
        return self._fixture_payloads_for_scope(
            source_scope=RawFixtureScope.HISTORICAL_TRAINING,
            provider_league_id=provider_league_id,
            kickoff_from=kickoff_from,
            kickoff_to=kickoff_to,
            scope_policy_version=scope_policy_version,
        )

    def _fixture_payloads_for_scope(
        self,
        *,
        source_scope: RawFixtureScope,
        provider_league_id: str | None,
        kickoff_from: datetime,
        kickoff_to: datetime,
        scope_policy_version: str,
    ) -> list[dict[str, Any]]:
        start = parse_db_datetime(kickoff_from)
        end = parse_db_datetime(kickoff_to)
        if end < start:
            raise FutureRefreshPersistenceError("FIXTURE_SCOPE_HORIZON_INVALID")
        scope_filters = [
            RawPayloadModel.endpoint == "fixtures",
            RawFixtureScopeMembershipModel.source_scope == source_scope.value,
            RawFixtureScopeMembershipModel.scope_policy_version == scope_policy_version,
            RawFixtureScopeMembershipModel.kickoff_utc >= start,
            RawFixtureScopeMembershipModel.kickoff_utc <= end,
        ]
        if provider_league_id is not None:
            scope_filters.append(
                RawFixtureScopeMembershipModel.provider_league_id == provider_league_id
            )
        with Session(self.engine) as session:
            rows = list(
                session.execute(
                    select(RawPayloadModel, RawFixtureScopeMembershipModel)
                    .join(
                        RawFixtureScopeMembershipModel,
                        RawFixtureScopeMembershipModel.raw_payload_sha256
                        == RawPayloadModel.sha256,
                    )
                    .where(*scope_filters)
                    .order_by(RawPayloadModel.captured_at)
                )
            )
        fixtures: dict[str, dict[str, Any]] = {}
        for raw, membership in rows:
            response = raw.payload.get("response")
            if not isinstance(response, list):
                continue
            for item in response:
                fixture = item.get("fixture") if isinstance(item, dict) else None
                if not isinstance(fixture, dict):
                    continue
                fixture_id = str(fixture.get("id") or "")
                if fixture_id != membership.provider_fixture_id:
                    continue
                league = item.get("league")
                league_id = str(league.get("id") or "") if isinstance(league, dict) else ""
                if provider_league_id is not None and league_id != provider_league_id:
                    continue
                try:
                    kickoff = parse_db_datetime(fixture.get("date"))
                except FutureRefreshPersistenceError:
                    continue
                if start <= kickoff <= end:
                    fixtures[fixture_id] = item
                break
        return sorted(fixtures.values(), key=lambda item: item.get("fixture", {}).get("date", ""))

    def fixture_payload(self, fixture_id: str, *, payload_limit: int = 32) -> dict[str, Any] | None:
        """Find one fixture without scanning the complete raw-payload history."""
        bounded_limit = max(0, min(int(payload_limit), 128))
        if not fixture_id or bounded_limit == 0:
            return None
        identity = self.matchday_fixture_identity(fixture_id)
        if (
            identity is not None
            and str(identity.get("status") or "") != "FIXTURE_ID_ALIAS_CONFLICT"
        ):
            identity_id = str(identity.get("fixture_id") or "")
            with Session(self.engine) as session:
                identity_row = session.scalar(
                    select(MatchdayFixtureIdentityModel).where(
                        MatchdayFixtureIdentityModel.fixture_id == identity_id
                    )
                )
            if identity_row is not None and isinstance(identity_row.payload, dict):
                return identity_row.payload
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == "fixtures")
                    .order_by(RawPayloadModel.captured_at.desc())
                    .limit(bounded_limit)
                )
            )
        for row in rows:
            response = row.payload.get("response")
            if not isinstance(response, list):
                continue
            for item in response[:256]:
                if not isinstance(item, dict):
                    continue
                if str(item.get("fixture", {}).get("id") or "") == fixture_id:
                    return item
        return None

    def fixture_payloads_bounded(
        self,
        *,
        payload_limit: int = 32,
        item_limit: int = 512,
    ) -> list[dict[str, Any]]:
        bounded_payloads = max(0, min(int(payload_limit), 128))
        bounded_items = max(0, min(int(item_limit), 1024))
        if bounded_payloads == 0 or bounded_items == 0:
            return []
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == "fixtures")
                    .order_by(RawPayloadModel.captured_at.desc())
                    .limit(bounded_payloads)
                )
            )
            identity_rows = list(
                session.scalars(
                    select(MatchdayFixtureIdentityModel)
                    .order_by(MatchdayFixtureIdentityModel.captured_at.desc())
                    .limit(bounded_items)
                )
            )
        fixtures: dict[str, dict[str, Any]] = {}
        for identity in identity_rows:
            payload = identity.payload
            fixture_id = (
                str(payload.get("fixture", {}).get("id") or "") if isinstance(payload, dict) else ""
            )
            if fixture_id:
                fixtures[fixture_id] = payload
        for row in rows:
            response = row.payload.get("response")
            if not isinstance(response, list):
                continue
            for item in response[:bounded_items]:
                if not isinstance(item, dict):
                    continue
                fixture_id = str(item.get("fixture", {}).get("id") or "")
                if fixture_id and fixture_id not in fixtures:
                    fixtures[fixture_id] = item
                if len(fixtures) >= bounded_items:
                    return sorted(
                        fixtures.values(),
                        key=lambda value: value.get("fixture", {}).get("date", ""),
                    )
        return sorted(
            fixtures.values(),
            key=lambda value: value.get("fixture", {}).get("date", ""),
        )

    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == endpoint)
                    .order_by(RawPayloadModel.captured_at)
                )
            )
        return [
            {
                "sha256": row.sha256,
                "endpoint": row.endpoint,
                "captured_at": iso_z(row.captured_at),
                "payload": dict(row.payload),
            }
            for row in rows
        ]

    def raw_payload_count(self, endpoint: str) -> int:
        with Session(self.engine) as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == endpoint)
                )
                or 0
            )

    def raw_payload_exists(self, *, sha256: str, endpoint: str) -> bool:
        with Session(self.engine) as session:
            return bool(
                session.scalar(
                    select(func.count())
                    .select_from(RawPayloadModel)
                    .where(
                        RawPayloadModel.sha256 == sha256,
                        RawPayloadModel.endpoint == endpoint,
                    )
                )
            )

    def raw_statistics_fixture_ids(self) -> set[str]:
        """Return only fixtures with complete, numeric two-sided xG evidence."""
        fixture_ids: set[str] = set()
        with Session(self.engine) as session:
            rows = session.execute(
                select(RawPayloadModel.payload)
                .where(RawPayloadModel.endpoint == "statistics")
                .execution_options(yield_per=256)
            )
            for (payload,) in rows:
                parameters = payload.get("parameters") if isinstance(payload, dict) else None
                fixture_id = (
                    str(parameters.get("fixture") or "")
                    if isinstance(parameters, dict)
                    else ""
                )
                if fixture_id and len(statistics_xg_by_team(payload)) == 2:
                    fixture_ids.add(fixture_id)
        return fixture_ids

    def provider_live_request_count_since(self, *, endpoint: str, since: datetime) -> int:
        with Session(self.engine) as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(ProviderRequestLogModel)
                    .where(
                        ProviderRequestLogModel.provider == "api_football",
                        ProviderRequestLogModel.endpoint == endpoint,
                        ProviderRequestLogModel.live.is_(True),
                        ProviderRequestLogModel.requested_at >= parse_db_datetime(since),
                    )
                )
                or 0
            )

    def raw_payloads_for_scope(
        self,
        endpoint: str,
        *,
        fixture_id: str | None = None,
        team_ids: list[str] | None = None,
        limit: int = 32,
    ) -> list[dict[str, Any]]:
        """Return a bounded set of raw payloads relevant to one public request."""
        bounded_limit = max(0, min(int(limit), 128))
        if bounded_limit == 0 or (fixture_id is None and not team_ids):
            return []
        wanted_teams = {str(team_id) for team_id in team_ids or [] if str(team_id)}
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.endpoint == endpoint)
                    .order_by(RawPayloadModel.captured_at.desc())
                    .limit(bounded_limit)
                )
            )
        scoped: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row.payload)
            parameters = payload.get("parameters")
            parameters = parameters if isinstance(parameters, dict) else {}
            parameter_fixture = str(parameters.get("fixture") or "")
            parameter_team = str(parameters.get("team") or "")
            parameter_h2h = {
                value
                for value in str(parameters.get("h2h") or "").replace("-", "_").split("_")
                if value
            }
            fixture_match = fixture_id is not None and parameter_fixture == fixture_id
            team_match = bool(wanted_teams) and (
                parameter_team in wanted_teams or wanted_teams <= parameter_h2h
            )
            if not fixture_match and not team_match:
                continue
            scoped.append(
                {
                    "sha256": row.sha256,
                    "endpoint": row.endpoint,
                    "captured_at": iso_z(row.captured_at),
                    "payload": payload,
                }
            )
        return scoped

    def upsert_team_xg_matches(self, matches: list[dict[str, Any]]) -> int:
        upserted = 0
        with Session(self.engine) as session:
            try:
                for row in matches:
                    row_id = str(row["id"])
                    existing = session.get(TeamXgMatchModel, row_id)
                    if existing is not None:
                        existing_evidence = (
                            existing.fixture_id,
                            existing.team_id,
                            existing.opponent_team_id,
                            parse_db_datetime(existing.kickoff_at),
                            existing.xg_for,
                            existing.xg_against,
                            existing.goals_for,
                            existing.goals_against,
                            existing.source_system,
                        )
                        incoming_evidence = (
                            str(row["fixture_id"]),
                            str(row["team_id"]),
                            str(row["opponent_team_id"]),
                            parse_db_datetime(row["kickoff_at"]),
                            float(row["xg_for"]),
                            float(row["xg_against"]),
                            int(row["goals_for"]),
                            int(row["goals_against"]),
                            str(row["source_system"]),
                        )
                        if existing_evidence != incoming_evidence:
                            raise ValueError(f"TEAM_XG_MATCH_IMMUTABLE_CONFLICT:{row_id}")
                        continue
                    session.add(
                        TeamXgMatchModel(
                            id=row_id,
                            fixture_id=str(row["fixture_id"]),
                            team_id=str(row["team_id"]),
                            opponent_team_id=str(row["opponent_team_id"]),
                            kickoff_at=parse_db_datetime(row["kickoff_at"]),
                            captured_at=parse_db_datetime(row["captured_at"]),
                            xg_for=float(row["xg_for"]),
                            xg_against=float(row["xg_against"]),
                            goals_for=int(row["goals_for"]),
                            goals_against=int(row["goals_against"]),
                            raw_payload_sha256=str(row["raw_payload_sha256"]),
                            source_system=str(row["source_system"]),
                            candidate=False,
                            formal_recommendation=False,
                        )
                    )
                    upserted += 1
                session.commit()
            except ValueError as exc:
                session.rollback()
                raise FutureRefreshPersistenceError(str(exc)) from exc
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("TEAM_XG_MATCH_WRITE_FAILED") from exc
        return upserted

    def team_xg_matches(self) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(TeamXgMatchModel).order_by(
                        TeamXgMatchModel.team_id,
                        TeamXgMatchModel.kickoff_at,
                    )
                )
            )
        return [self._team_xg_match_dict(row) for row in rows]

    def team_xg_matches_for_teams(
        self,
        team_ids: list[str],
        *,
        before: datetime,
        limit_per_team: int = 20,
    ) -> list[dict[str, Any]]:
        ids = [team_id for team_id in dict.fromkeys(team_ids) if team_id]
        bounded_limit = max(0, min(int(limit_per_team), 50))
        if not ids or bounded_limit == 0:
            return []
        ranked = (
            select(
                TeamXgMatchModel.id.label("id"),
                func.row_number()
                .over(
                    partition_by=TeamXgMatchModel.team_id,
                    order_by=TeamXgMatchModel.kickoff_at.desc(),
                )
                .label("rank"),
            )
            .where(
                TeamXgMatchModel.team_id.in_(ids),
                TeamXgMatchModel.kickoff_at < before,
            )
            .subquery()
        )
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(TeamXgMatchModel)
                    .join(ranked, TeamXgMatchModel.id == ranked.c.id)
                    .where(ranked.c.rank <= bounded_limit)
                    .order_by(TeamXgMatchModel.team_id, TeamXgMatchModel.kickoff_at)
                )
            )
        return [self._team_xg_match_dict(row) for row in rows]

    @staticmethod
    def _team_xg_match_dict(row: TeamXgMatchModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "fixture_id": row.fixture_id,
            "team_id": row.team_id,
            "opponent_team_id": row.opponent_team_id,
            "kickoff_at": iso_z(row.kickoff_at),
            "captured_at": iso_z(row.captured_at),
            "xg_for": row.xg_for,
            "xg_against": row.xg_against,
            "goals_for": row.goals_for,
            "goals_against": row.goals_against,
            "raw_payload_sha256": row.raw_payload_sha256,
            "source_system": row.source_system,
            "candidate": False,
            "formal_recommendation": False,
        }

    def upsert_team_xg_rolling_snapshots(self, snapshots: list[dict[str, Any]]) -> int:
        upserted = 0
        with Session(self.engine) as session:
            for row in snapshots:
                session.merge(
                    TeamXgRollingSnapshotModel(
                        snapshot_id=str(row["snapshot_id"]),
                        team_id=str(row["team_id"]),
                        as_of_fixture_id=str(row["as_of_fixture_id"]),
                        as_of_time=parse_db_datetime(row["as_of_time"]),
                        match_count=int(row["match_count"]),
                        rolling_xg_for=float(row["rolling_xg_for"]),
                        rolling_xg_against=float(row["rolling_xg_against"]),
                        rolling_goals_for=float(row["rolling_goals_for"]),
                        rolling_goals_against=float(row["rolling_goals_against"]),
                        regression_index=float(row["regression_index"]),
                        source_system=str(row["source_system"]),
                        candidate=False,
                        formal_recommendation=False,
                    )
                )
                upserted += 1
            try:
                session.commit()
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("TEAM_XG_SNAPSHOT_WRITE_FAILED") from exc
        return upserted

    def team_xg_rolling_snapshots(
        self,
        *,
        fixture_id: str | None = None,
        team_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            query = select(TeamXgRollingSnapshotModel)
            if fixture_id is not None:
                query = query.where(TeamXgRollingSnapshotModel.as_of_fixture_id == fixture_id)
            if team_id is not None:
                query = query.where(TeamXgRollingSnapshotModel.team_id == team_id)
            rows = list(
                session.scalars(
                    query.order_by(
                        TeamXgRollingSnapshotModel.team_id,
                        TeamXgRollingSnapshotModel.as_of_time,
                    )
                )
            )
        return [self._team_xg_rolling_snapshot_dict(row) for row in rows]

    def team_xg_rolling_snapshots_for_teams(
        self,
        team_ids: list[str],
        *,
        before: datetime,
    ) -> list[dict[str, Any]]:
        ids = [team_id for team_id in dict.fromkeys(team_ids) if team_id]
        if not ids or len(ids) > 2:
            return []
        ranked = (
            select(
                TeamXgRollingSnapshotModel.snapshot_id.label("snapshot_id"),
                func.row_number()
                .over(
                    partition_by=TeamXgRollingSnapshotModel.team_id,
                    order_by=TeamXgRollingSnapshotModel.as_of_time.desc(),
                )
                .label("rank"),
            )
            .where(
                TeamXgRollingSnapshotModel.team_id.in_(ids),
                TeamXgRollingSnapshotModel.as_of_time < before,
            )
            .subquery()
        )
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(TeamXgRollingSnapshotModel)
                    .join(
                        ranked,
                        TeamXgRollingSnapshotModel.snapshot_id == ranked.c.snapshot_id,
                    )
                    .where(ranked.c.rank == 1)
                    .order_by(TeamXgRollingSnapshotModel.team_id)
                    .limit(2)
                )
            )
        return [self._team_xg_rolling_snapshot_dict(row) for row in rows]

    @staticmethod
    def _team_xg_rolling_snapshot_dict(
        row: TeamXgRollingSnapshotModel,
    ) -> dict[str, Any]:
        return {
            "snapshot_id": row.snapshot_id,
            "team_id": row.team_id,
            "as_of_fixture_id": row.as_of_fixture_id,
            "as_of_time": iso_z(row.as_of_time),
            "match_count": row.match_count,
            "rolling_xg_for": row.rolling_xg_for,
            "rolling_xg_against": row.rolling_xg_against,
            "rolling_goals_for": row.rolling_goals_for,
            "rolling_goals_against": row.rolling_goals_against,
            "regression_index": row.regression_index,
            "source_system": row.source_system,
            "candidate": False,
            "formal_recommendation": False,
        }

    @staticmethod
    def _canonical_match_history_dict(row: CanonicalTeamMatchHistoryModel) -> dict[str, Any]:
        return {
            "history_id": row.history_id,
            "fixture_id": row.fixture_id,
            "provider": row.provider,
            "provider_fixture_id": row.provider_fixture_id,
            "competition_id": row.competition_id,
            "season": row.season,
            "kickoff_utc": iso_z(row.kickoff_utc),
            "fixture_status": row.fixture_status,
            "team_side": row.team_side,
            "team_provider_id": row.team_provider_id,
            "opponent_provider_id": row.opponent_provider_id,
            "team_w2_id": row.team_w2_id,
            "opponent_w2_id": row.opponent_w2_id,
            "goals_for": row.goals_for,
            "goals_against": row.goals_against,
            "result_identity_hash": row.result_identity_hash,
            "source_raw_hash": row.source_raw_hash,
            "endpoint_capture_id": row.endpoint_capture_id,
            "captured_at": iso_z(row.captured_at),
            "history_hash": row.history_hash,
        }

    @staticmethod
    def _team_rating_snapshot_dict(row: TeamRatingSnapshotModel) -> dict[str, Any]:
        return {
            "rating_id": row.rating_id,
            "w2_team_id": row.w2_team_id,
            "observed_at": iso_z(row.observed_at),
            "model_version": row.model_version,
            "elo": row.elo,
            "attack_strength": row.attack_strength,
            "defence_strength": row.defence_strength,
            "form_index": row.form_index,
            "source": row.source,
            "source_history_hashes": row.source_history_hashes,
            "rating_hash": row.rating_hash,
        }

    def market_snapshots(self) -> list[dict[str, Any]]:
        observations = self.latest_market_observations()
        return self._market_snapshots_from_observations(observations)

    def market_snapshots_for_fixture(self, fixture_id: str) -> list[dict[str, Any]]:
        observations = self.latest_market_observations_for_fixtures([fixture_id])
        return self._market_snapshots_from_observations(observations)

    def _market_snapshots_from_observations(
        self,
        observations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        by_fixture: dict[str, list[dict[str, Any]]] = {}
        for row in observations:
            by_fixture.setdefault(str(row["fixture_id"]), []).append(row)
        snapshots: list[dict[str, Any]] = []
        for fixture_id, rows in sorted(by_fixture.items()):
            captured_at = max(str(row["captured_at"]) for row in rows)
            bookmakers = {str(row["bookmaker_id"]) for row in rows if row.get("bookmaker_id")}
            markets = {str(row["canonical_market"]) for row in rows}
            snapshots.append(
                {
                    "fixture_id": fixture_id,
                    "captured_at": captured_at,
                    "captured_at_utc": captured_at,
                    "snapshot_semantics": "CAPTURED_AT",
                    "bookmaker_count": len(bookmakers),
                    "quality": "READY" if rows else "MARKET_NOT_COMPARABLE",
                    "source": "matchday_market_observations",
                    "market_coverage": {market: True for market in sorted(markets)},
                    "candidate": False,
                    "formal_recommendation": False,
                }
            )
        return snapshots

    def provider_status(self) -> dict[str, Any]:
        with Session(self.engine) as session:
            row = session.scalar(
                select(FutureRefreshRunAuditModel).order_by(
                    desc(FutureRefreshRunAuditModel.generated_at)
                )
            )
        if row is None:
            return {}
        last_success = next(
            (
                item
                for item in reversed(row.requests)
                if isinstance(item, dict) and item.get("status_code") == 200
            ),
            {},
        )
        return {
            "provider": "api_football",
            "status": "READY" if not row.blockers else "DEGRADED",
            "remaining_quota": row.remaining_quota,
            "credential_status": "PRESENT",
            "last_request_status": (
                row.requests[-1].get("status_code")
                if row.requests and isinstance(row.requests[-1], dict)
                else None
            ),
            "last_successful_refresh_at": last_success.get("captured_at_utc"),
            "blockers": row.blockers,
        }

    def write_task_audit(self, audit: dict[str, Any]) -> None:
        with Session(self.engine) as session:
            try:
                session.merge(
                    FutureRefreshTaskAuditModel(
                        task_id=str(audit["task_id"]),
                        key=str(audit["key"]),
                        owner=str(audit["owner"]),
                        queued_at=parse_db_datetime(audit["queued_at"]),
                        started_at=parse_db_datetime(audit["started_at"]),
                        finished_at=parse_db_datetime(audit["finished_at"]),
                        status=str(audit["status"]),
                        result=dict(audit["result"]),
                        gate_a_authorization_id=(
                            str(audit["gate_a_authorization_id"])
                            if audit.get("gate_a_authorization_id") is not None
                            else None
                        ),
                        gate_a_lease_epoch=(
                            int(audit["gate_a_lease_epoch"])
                            if audit.get("gate_a_lease_epoch") is not None
                            else None
                        ),
                    )
                )
                session.commit()
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("TASK_AUDIT_WRITE_FAILED") from exc

    def task_key_exists(self, key: str) -> bool:
        with Session(self.engine) as session:
            row = session.scalar(
                select(FutureRefreshTaskAuditModel.task_id)
                .where(
                    FutureRefreshTaskAuditModel.key == key,
                    FutureRefreshTaskAuditModel.status == "COMPLETED",
                )
                .limit(1)
            )
        return row is not None

    def market_refresh_status_for_fixtures(
        self,
        fixture_ids: list[str],
        *,
        now: datetime | None = None,
    ) -> dict[str, str | None]:
        ids = [fixture_id for fixture_id in dict.fromkeys(fixture_ids) if fixture_id]
        if not ids or len(ids) > 64:
            return {"odds_last_confirmed_at": None, "next_refresh_tick": None}
        reference = parse_db_datetime(now or datetime.now(UTC))
        canonical_ids = {
            fixture_id if fixture_id.startswith("api_football:") else f"api_football:{fixture_id}"
            for fixture_id in ids
        }
        with Session(self.engine) as session:
            odds_last_confirmed_at = session.scalar(
                select(func.max(MatchdayMarketObservationModel.captured_at)).where(
                    MatchdayMarketObservationModel.fixture_id.in_(canonical_ids),
                    MatchdayMarketObservationModel.live.is_(False),
                )
            )
            next_refresh_tick = session.scalar(
                select(func.min(MatchdayCheckpointPlanModel.scheduled_at)).where(
                    MatchdayCheckpointPlanModel.fixture_id.in_(canonical_ids),
                    MatchdayCheckpointPlanModel.status.in_(("PLANNED", "DUE")),
                    MatchdayCheckpointPlanModel.scheduled_at >= reference,
                )
            )
        return {
            "odds_last_confirmed_at": (
                iso_z(odds_last_confirmed_at) if odds_last_confirmed_at is not None else None
            ),
            "next_refresh_tick": (
                iso_z(next_refresh_tick) if next_refresh_tick is not None else None
            ),
        }

    def next_market_refresh_by_fixture(
        self,
        fixture_ids: list[str],
        *,
        now: datetime | None = None,
    ) -> dict[str, str]:
        ids = [fixture_id for fixture_id in dict.fromkeys(fixture_ids) if fixture_id]
        if not ids or len(ids) > 64:
            return {}
        reference = parse_db_datetime(now or datetime.now(UTC))
        canonical_by_requested = {
            fixture_id: (
                fixture_id
                if fixture_id.startswith("api_football:")
                else f"api_football:{fixture_id}"
            )
            for fixture_id in ids
        }
        with Session(self.engine) as session:
            rows = session.execute(
                select(
                    MatchdayCheckpointPlanModel.fixture_id,
                    func.min(MatchdayCheckpointPlanModel.scheduled_at),
                )
                .where(
                    MatchdayCheckpointPlanModel.fixture_id.in_(canonical_by_requested.values()),
                    MatchdayCheckpointPlanModel.status.in_(("PLANNED", "DUE")),
                    MatchdayCheckpointPlanModel.scheduled_at >= reference,
                    MatchdayCheckpointPlanModel.test_only.is_(False),
                    MatchdayCheckpointPlanModel.namespace.is_(None),
                )
                .group_by(MatchdayCheckpointPlanModel.fixture_id)
            ).all()
        by_canonical = {str(fixture_id): iso_z(due_at) for fixture_id, due_at in rows}
        return {
            requested: by_canonical[canonical]
            for requested, canonical in canonical_by_requested.items()
            if canonical in by_canonical
        }

    def write_checkpoint_audit(
        self,
        *,
        fixture_id: str,
        checkpoint: str,
        as_of: datetime,
        calls_used: int,
        status: str,
        details: dict[str, Any],
    ) -> int:
        with Session(self.engine) as session:
            try:
                audit = FutureRefreshCheckpointAuditModel(
                    fixture_id=str(fixture_id),
                    checkpoint=str(checkpoint),
                    as_of=parse_db_datetime(as_of),
                    calls_used=int(calls_used),
                    status=str(status),
                    details=dict(details),
                )
                session.add(audit)
                session.commit()
                return int(audit.id)
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("CHECKPOINT_AUDIT_WRITE_FAILED") from exc

    def write_run_audit(self, payload: dict[str, Any]) -> None:
        with Session(self.engine) as session:
            try:
                session.add(
                    FutureRefreshRunAuditModel(
                        generated_at=parse_db_datetime(payload["generated_at_utc"]),
                        competition_id=str(payload["competition_id"]),
                        request_count=int(payload["request_count"]),
                        remaining_quota=payload["remaining_quota"],
                        fixture_count=int(payload["fixture_count"]),
                        mapping_count=int(payload["mapping_count"]),
                        market_snapshot_count=int(payload["market_snapshot_count"]),
                        ledger_appended_count=int(payload["ledger_appended_count"]),
                        selected_market_fixture_ids=list(payload["selected_market_fixture_ids"]),
                        blockers=list(payload["blockers"]),
                        requests=list(payload["requests"]),
                        candidate=False,
                        formal_recommendation=False,
                    )
                )
                session.commit()
            except Exception as exc:
                session.rollback()
                raise FutureRefreshPersistenceError("RUN_AUDIT_WRITE_FAILED") from exc

    def request_count_evidence_since(
        self,
        since: datetime,
        *,
        include_quota_usage: bool = True,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        since_utc = parse_db_datetime(since)
        day_start = since_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        try:
            with Session(self.engine) as session:
                future_refresh_requests = session.scalar(
                    select(
                        func.coalesce(func.sum(FutureRefreshRunAuditModel.request_count), 0)
                    ).where(FutureRefreshRunAuditModel.generated_at >= since_utc)
                )
                provider_request_logs = session.scalar(
                    select(func.count())
                    .select_from(ProviderRequestLogModel)
                    .where(
                        ProviderRequestLogModel.provider == "api_football",
                        ProviderRequestLogModel.requested_at >= since_utc,
                    )
                )
                dispatched_requests = session.scalar(
                    select(func.count())
                    .select_from(ProviderRequestLogModel)
                    .where(
                        ProviderRequestLogModel.provider == "api_football",
                        ProviderRequestLogModel.live.is_(True),
                        ProviderRequestLogModel.requested_at >= since_utc,
                    )
                )
                latest_quota = (
                    session.scalar(
                        select(QuotaUsageModel)
                        .where(
                            QuotaUsageModel.provider == "api_football",
                            QuotaUsageModel.window_start >= day_start,
                            QuotaUsageModel.window_start < day_end,
                        )
                        .order_by(
                            QuotaUsageModel.observed_at.desc(),
                            QuotaUsageModel.used.desc(),
                        )
                        .limit(1)
                    )
                    if include_quota_usage
                    else None
                )
        except Exception as exc:
            raise FutureRefreshPersistenceError("REQUEST_COUNT_READ_FAILED") from exc
        quota_usage_count = int(latest_quota.used) if latest_quota is not None else 0
        quota_observed_at = latest_quota.observed_at if latest_quota is not None else None
        run_audit_count = int(future_refresh_requests or 0)
        provider_ledger_count = int(provider_request_logs or 0)
        dispatched_count = int(dispatched_requests or 0)
        attempt_count = max(run_audit_count, provider_ledger_count)
        reference = parse_db_datetime(as_of or datetime.now(UTC))
        observed = parse_db_datetime(quota_observed_at) if quota_observed_at else None
        age_seconds = max(int((reference - observed).total_seconds()), 0) if observed else None
        max_age_seconds = provider_quota_authority_max_age_seconds()
        authority_ready = bool(
            include_quota_usage
            and observed is not None
            and age_seconds is not None
            and age_seconds <= max_age_seconds
        )
        try:
            if observed is not None:
                with Session(self.engine) as session:
                    dispatched_since_authority = int(
                        session.scalar(
                            select(func.count())
                            .select_from(ProviderRequestLogModel)
                            .where(
                                ProviderRequestLogModel.provider == "api_football",
                                ProviderRequestLogModel.live.is_(True),
                                ProviderRequestLogModel.requested_at > observed,
                                ProviderRequestLogModel.requested_at >= since_utc,
                            )
                        )
                        or 0
                    )
            else:
                dispatched_since_authority = dispatched_count
        except Exception as exc:
            raise FutureRefreshPersistenceError("REQUEST_COUNT_READ_FAILED") from exc
        known_count = (
            quota_usage_count
            if authority_ready
            else quota_usage_count + dispatched_since_authority
        )
        delta = attempt_count - quota_usage_count
        return {
            "known_count": known_count,
            "quota_usage_count": quota_usage_count,
            "run_audit_count": run_audit_count,
            "provider_ledger_count": provider_ledger_count,
            "billable_from_provider": quota_usage_count if observed is not None else None,
            "provider_daily_limit": int(latest_quota.limit) if latest_quota else None,
            "provider_daily_remaining": (
                max(int(latest_quota.limit) - int(latest_quota.used), 0)
                if latest_quota
                else None
            ),
            "local_ledger_count": provider_ledger_count,
            "last_authority_at": iso_z(observed) if observed else None,
            "authority_age_seconds": age_seconds,
            "dispatched_count": dispatched_count,
            "dispatched_since_authority_count": dispatched_since_authority,
            "attempt_count": attempt_count,
            "quota_authority_status": "AUTHORITATIVE" if authority_ready else "DEGRADED",
            "quota_authority_degraded": not authority_ready,
            "quota_degradation_classification": (
                None if authority_ready else "EXPECTED_DEGRADED"
            ),
            "quota_authority_observed_at": iso_z(observed) if observed else None,
            "quota_authority_age_seconds": age_seconds,
            "quota_authority_max_age_seconds": max_age_seconds,
            "quota_usage_ledger_delta": delta,
            "quota_usage_ledger_divergence": (
                observed is not None
                and abs(delta) > QUOTA_USAGE_LEDGER_DIVERGENCE_THRESHOLD
            ),
        }

    def request_count_since(
        self,
        since: datetime,
        *,
        include_quota_usage: bool = True,
        as_of: datetime | None = None,
    ) -> int:
        return int(
            self.request_count_evidence_since(
                since,
                include_quota_usage=include_quota_usage,
                as_of=as_of,
            )["known_count"]
        )

    def successful_request_count_since(self, since: datetime) -> int:
        since_utc = parse_db_datetime(since)
        try:
            with Session(self.engine) as session:
                return int(
                    session.scalar(
                        select(func.count())
                        .select_from(ProviderRequestLogModel)
                        .where(
                            ProviderRequestLogModel.provider == "api_football",
                            ProviderRequestLogModel.live.is_(True),
                            ProviderRequestLogModel.requested_at >= since_utc,
                            ProviderRequestLogModel.status_code >= 200,
                            ProviderRequestLogModel.status_code < 300,
                        )
                    )
                    or 0
                )
        except Exception as exc:
            raise FutureRefreshPersistenceError("SUCCESSFUL_REQUEST_COUNT_READ_FAILED") from exc

    def provider_request_count_since(self, since: datetime) -> int:
        since_utc = parse_db_datetime(since)
        try:
            with Session(self.engine) as session:
                return int(
                    session.scalar(
                        select(func.count())
                        .select_from(ProviderRequestLogModel)
                        .where(
                            ProviderRequestLogModel.provider == "api_football",
                            ProviderRequestLogModel.requested_at >= since_utc,
                        )
                    )
                    or 0
                )
        except Exception as exc:
            raise FutureRefreshPersistenceError("PROVIDER_REQUEST_COUNT_READ_FAILED") from exc

    def postmatch_result_request_count_since(self, since: datetime) -> int:
        since_utc = parse_db_datetime(since)
        try:
            with Session(self.engine) as session:
                results = list(
                    session.scalars(
                        select(FutureRefreshTaskAuditModel.result).where(
                            FutureRefreshTaskAuditModel.started_at >= since_utc
                        )
                    )
                )
        except Exception as exc:
            raise FutureRefreshPersistenceError("RESULT_REQUEST_COUNT_READ_FAILED") from exc
        total = 0
        for result in results:
            checkpoints = result.get("refresh_checkpoints") if isinstance(result, dict) else None
            if not isinstance(checkpoints, list) or not checkpoints:
                continue
            if all(
                isinstance(item, dict) and item.get("checkpoint") == "POSTMATCH_RESULT"
                for item in checkpoints
            ):
                total += max(int(result.get("request_count") or 0), 0)
        return total

    def postmatch_result_successful_request_count_since(self, since: datetime) -> int:
        since_utc = parse_db_datetime(since)
        try:
            with Session(self.engine) as session:
                results = list(
                    session.scalars(
                        select(FutureRefreshTaskAuditModel.result).where(
                            FutureRefreshTaskAuditModel.started_at >= since_utc
                        )
                    )
                )
        except Exception as exc:
            raise FutureRefreshPersistenceError("RESULT_SUCCESS_COUNT_READ_FAILED") from exc
        total = 0
        for result in results:
            checkpoints = result.get("refresh_checkpoints") if isinstance(result, dict) else None
            requests = result.get("requests") if isinstance(result, dict) else None
            if (
                not isinstance(checkpoints, list)
                or not checkpoints
                or not isinstance(requests, list)
            ):
                continue
            if all(
                isinstance(item, dict) and item.get("checkpoint") == "POSTMATCH_RESULT"
                for item in checkpoints
            ):
                total += sum(
                    isinstance(item, dict)
                    and isinstance(item.get("status_code"), int)
                    and 200 <= int(item["status_code"]) < 300
                    for item in requests
                )
        return total

    def unsettled_model_forecast_postmatch_count(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        exclude_fixture_ids: tuple[str, ...] = (),
    ) -> int:
        start = parse_db_datetime(window_start)
        end = parse_db_datetime(window_end)
        excluded = {
            fixture_id.removeprefix("api_football:")
            for fixture_id in exclude_fixture_ids
            if fixture_id
        }
        query = (
            select(func.count(func.distinct(ModelForecastCaptureModel.fixture_id)))
            .select_from(ModelForecastCaptureModel)
            .join(
                MatchdayCheckpointPlanModel,
                canonical_model_forecast_fixture_id_sql(
                    MatchdayCheckpointPlanModel.fixture_id
                )
                == canonical_model_forecast_fixture_id_sql(
                    ModelForecastCaptureModel.fixture_id
                ),
            )
            .outerjoin(
                ModelForecastOutcomeModel,
                ModelForecastOutcomeModel.capture_identity_hash
                == ModelForecastCaptureModel.capture_identity_hash,
            )
            .where(
                ModelForecastOutcomeModel.capture_identity_hash.is_(None),
                MatchdayCheckpointPlanModel.checkpoint == "POSTMATCH_RESULT",
                MatchdayCheckpointPlanModel.status.in_(("PLANNED", "DUE")),
                MatchdayCheckpointPlanModel.window_start < end,
                MatchdayCheckpointPlanModel.window_end >= start,
            )
        )
        if excluded:
            query = query.where(ModelForecastCaptureModel.fixture_id.not_in(excluded))
        try:
            with Session(self.engine) as session:
                return int(session.scalar(query) or 0)
        except Exception as exc:
            raise FutureRefreshPersistenceError(
                "RESULT_CAPTURE_RESERVATION_READ_FAILED"
            ) from exc

    def provider_quota_snapshot(self, day_start: datetime) -> dict[str, Any]:
        start = parse_db_datetime(day_start).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        try:
            with Session(self.engine) as session:
                rows = list(
                    session.scalars(
                        select(QuotaUsageModel).where(
                            QuotaUsageModel.provider == "api_football",
                            QuotaUsageModel.window_start >= start,
                            QuotaUsageModel.window_start < end,
                        )
                    )
                )
        except Exception as exc:
            raise FutureRefreshPersistenceError("QUOTA_SNAPSHOT_READ_FAILED") from exc
        if not rows:
            return {
                "daily_limit": None,
                "used": None,
                "remaining": None,
                "observed_at": None,
                "burst_limit": None,
                "burst_remaining": None,
                "burst_observed_at": None,
            }
        burst_rows = [
            row
            for row in rows
            if row.burst_limit is not None and row.burst_remaining is not None
        ]
        burst_row = max(
            burst_rows,
            key=lambda row: (parse_db_datetime(row.observed_at), int(row.used)),
            default=None,
        )
        daily_row = max(
            rows,
            key=lambda row: (parse_db_datetime(row.observed_at), int(row.used)),
        )
        return {
            "daily_limit": int(daily_row.limit),
            "used": int(daily_row.used),
            "remaining": max(int(daily_row.limit) - int(daily_row.used), 0),
            "observed_at": iso_z(parse_db_datetime(daily_row.observed_at)),
            "burst_limit": (
                int(burst_row.burst_limit)
                if burst_row is not None and burst_row.burst_limit is not None
                else None
            ),
            "burst_remaining": (
                int(burst_row.burst_remaining)
                if burst_row is not None and burst_row.burst_remaining is not None
                else None
            ),
            "burst_observed_at": (
                iso_z(parse_db_datetime(burst_row.observed_at))
                if burst_row is not None
                else None
            ),
        }
