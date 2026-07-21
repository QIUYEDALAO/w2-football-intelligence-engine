from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.features.team_factors import TeamMatchHistory
from w2.features.xg_materialization import FINISHED_STATUS, TeamXgMatch, parse_team_xg_matches
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamMatchHistoryModel,
    CanonicalTeamModel,
    ProviderTeamIdentityCrosswalkModel,
    TeamRatingSnapshotModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayEndpointCaptureModel,
    MatchdayFixtureIdentityModel,
)
from w2.ingestion.future_refresh import (
    response_count,
    sanitize_params,
    sha256_payload,
)
from w2.matchday.intake_v2 import endpoint_capture_contract, stable_hash
from w2.providers.api_football import ApiFootballClient, LiveApiFootballResponse
from w2.ratings.elo import rating_from_history

PROVIDER = "api_football"
PROVIDER_PRIMARY_READY = "PROVIDER_PRIMARY_READY"
MODEL_VERSION = "internal_elo_v1"


class FactorModelRemediationError(RuntimeError):
    pass


@dataclass(frozen=True, kw_only=True)
class FactorModelRemediationConfig:
    competition_id: str = "allsvenskan"
    provider_league_id: str = "113"
    season: str = "2026"
    recent_match_count: int = 5
    min_rating_matches: int = 2
    request_budget: int = 100
    source_revision: str = "LOCAL_UNDEPLOYED"
    output_dir: Path = Path("docs/operations/factor_model_remediation")
    smoke_fixture_ids: tuple[str, ...] = ("1494224", "1494218")


@dataclass(frozen=True, kw_only=True)
class ProviderAuditEntry:
    endpoint: str
    params: dict[str, str]
    status_code: int
    elapsed_ms: int
    captured_at_utc: str
    requested_at_utc: str | None
    payload_sha256: str
    capture_id: str
    response_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "params": self.params,
            "status_code": self.status_code,
            "elapsed_ms": self.elapsed_ms,
            "captured_at_utc": self.captured_at_utc,
            "requested_at_utc": self.requested_at_utc,
            "payload_sha256": self.payload_sha256,
            "capture_id": self.capture_id,
            "response_count": self.response_count,
        }


@dataclass(frozen=True, kw_only=True)
class RemediationResult:
    generated_at_utc: datetime
    competition_id: str
    season: str
    canonical_team_count: int
    provider_crosswalk_count: int
    fixture_identity_ready_count: int
    canonical_history_rows: int
    canonical_history_fixtures: int
    rating_snapshot_count: int
    xg_match_rows: int
    xg_status: str
    h2h_rows: int
    provider_call_count: int
    blockers: list[str] = field(default_factory=list)
    provider_audit: list[ProviderAuditEntry] = field(default_factory=list)
    smoke_fixture_readiness: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "W2FactorModelRemediationResultV1",
            "generated_at_utc": iso_z(self.generated_at_utc),
            "competition_id": self.competition_id,
            "season": self.season,
            "canonical_team_count": self.canonical_team_count,
            "provider_crosswalk_count": self.provider_crosswalk_count,
            "fixture_identity_ready_count": self.fixture_identity_ready_count,
            "canonical_history_rows": self.canonical_history_rows,
            "canonical_history_fixtures": self.canonical_history_fixtures,
            "rating_snapshot_count": self.rating_snapshot_count,
            "xg_match_rows": self.xg_match_rows,
            "xg_status": self.xg_status,
            "h2h_rows": self.h2h_rows,
            "provider_call_count": self.provider_call_count,
            "blockers": self.blockers,
            "provider_audit": [entry.as_dict() for entry in self.provider_audit],
            "smoke_fixture_readiness": self.smoke_fixture_readiness,
            "formal_ah": False,
            "formal_ou": False,
            "recommendation_lock": False,
            "production_recommendation": False,
            "final_state": "MANUAL_APPROVAL_REQUIRED",
        }


class FactorModelRemediationService:
    def __init__(
        self,
        *,
        engine: Engine | None = None,
        client: ApiFootballClient | None = None,
        config: FactorModelRemediationConfig | None = None,
        now: datetime | None = None,
    ) -> None:
        self.engine = engine or create_engine()
        self.config = config or FactorModelRemediationConfig()
        self.now = normalize_utc(now or datetime.now(UTC))
        self.client = client or ApiFootballClient(
            allow_live=True,
            allowed_live_endpoints=frozenset(
                {"fixtures", "statistics", "h2h", "lineups", "status"}
            ),
        )
        self._provider_audit: list[ProviderAuditEntry] = []

    def seed_provider_primary_identity(self) -> dict[str, int]:
        with Session(self.engine) as session:
            fixtures = self._target_fixtures(session)
            if not fixtures:
                return {
                    "canonical_team_count": 0,
                    "provider_crosswalk_count": 0,
                    "fixture_identity_ready_count": 0,
                }
            team_rows = provider_teams_from_fixtures(fixtures)
            canonical_count = 0
            crosswalk_count = 0
            for team in team_rows:
                canonical = canonical_team_payload(
                    provider_team_id=team["provider_team_id"],
                    display_name=team["display_name"],
                    country=team["country"],
                    created_at=self.now,
                )
                try:
                    with session.begin_nested():
                        session.add(CanonicalTeamModel(**canonical))
                        session.flush()
                    canonical_count += 1
                except IntegrityError:
                    existing_team = session.get(CanonicalTeamModel, canonical["w2_team_id"])
                    if (
                        existing_team is None
                        or existing_team.identity_hash != canonical["identity_hash"]
                    ):
                        raise FactorModelRemediationError(
                            "CANONICAL_TEAM_IDENTITY_CONFLICT"
                        ) from None
                crosswalk = provider_crosswalk_payload(
                    provider_team_id=team["provider_team_id"],
                    w2_team_id=canonical["w2_team_id"],
                    competition_id=self.config.competition_id,
                    season=self.config.season,
                    evidence_hashes=team["evidence_hashes"],
                    valid_from=self.now,
                )
                try:
                    with session.begin_nested():
                        session.add(ProviderTeamIdentityCrosswalkModel(**crosswalk))
                        session.flush()
                    crosswalk_count += 1
                except IntegrityError:
                    existing_crosswalk = session.get(
                        ProviderTeamIdentityCrosswalkModel,
                        crosswalk["id"],
                    )
                    if (
                        existing_crosswalk is None
                        or existing_crosswalk.identity_hash != crosswalk["identity_hash"]
                    ):
                        raise FactorModelRemediationError(
                            "PROVIDER_TEAM_CROSSWALK_CONFLICT"
                        ) from None
            mapping = {
                item["provider_team_id"]: stable_w2_team_id(item["provider_team_id"])
                for item in team_rows
            }
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
                fixture.identity_hash = stable_hash(
                    {
                        "fixture_id": fixture.fixture_id,
                        "provider": fixture.provider,
                        "provider_fixture_id": fixture.provider_fixture_id,
                        "home_w2_team_id": home,
                        "away_w2_team_id": away,
                        "status": PROVIDER_PRIMARY_READY,
                    }
                )
                ready += 1
            session.commit()
        return {
            "canonical_team_count": canonical_count,
            "provider_crosswalk_count": crosswalk_count,
            "fixture_identity_ready_count": ready,
        }

    def run_controlled_provider_capture(self, *, live: bool) -> RemediationResult:
        seed = self.seed_provider_primary_identity()
        blockers: list[str] = []
        xg_rows = 0
        h2h_rows = 0
        if live:
            team_ids = self._provider_team_ids()
            historical_fixtures: dict[str, dict[str, Any]] = {}
            fixture_capture_ids: dict[str, str] = {}
            for team_id in team_ids:
                if self.provider_call_count >= self.config.request_budget:
                    blockers.append("PROVIDER_CALL_BUDGET_EXHAUSTED")
                    break
                response = self._request(
                    "fixtures",
                    {
                        "team": team_id,
                        "league": self.config.provider_league_id,
                        "season": self.config.season,
                        "last": str(self.config.recent_match_count),
                    },
                )
                if response.status_code >= 400:
                    blockers.append(f"HISTORICAL_FIXTURES_HTTP_{response.status_code}:{team_id}")
                    continue
                capture_id = self._persist_capture(response, fixture_id=None)
                for item in finished_fixture_items(response.payload, now=self.now):
                    provider_fixture_id = provider_fixture_id_from_item(item)
                    if not provider_fixture_id:
                        continue
                    historical_fixtures[provider_fixture_id] = item
                    fixture_capture_ids[provider_fixture_id] = capture_id
            if historical_fixtures:
                self._upsert_history_fixtures(
                    historical_fixtures,
                    fixture_capture_ids=fixture_capture_ids,
                )
                xg_rows, xg_blockers = self._probe_xg(historical_fixtures)
                blockers.extend(xg_blockers)
            else:
                blockers.append("HISTORICAL_FIXTURE_SAMPLE_EMPTY")
            h2h_rows, h2h_blockers = self._capture_smoke_h2h()
            blockers.extend(h2h_blockers)
        if seed["fixture_identity_ready_count"] == 0:
            blockers.append("MATCHDAY_FIXTURE_IDENTITIES_EMPTY_OR_UNAVAILABLE")
        rating_rows = self.materialize_ratings()
        snapshot = self._snapshot(
            seed=seed,
            blockers=blockers,
            xg_rows=xg_rows,
            h2h_rows=h2h_rows,
            rating_rows=rating_rows,
        )
        return snapshot

    def materialize_ratings(self) -> int:
        count = 0
        with Session(self.engine) as session:
            team_ids = [
                row[0]
                for row in session.execute(
                    select(CanonicalTeamModel.w2_team_id).order_by(CanonicalTeamModel.w2_team_id)
                )
            ]
            for team_id in team_ids:
                rows = list(
                    session.scalars(
                        select(CanonicalTeamMatchHistoryModel)
                        .where(CanonicalTeamMatchHistoryModel.team_w2_id == team_id)
                        .order_by(CanonicalTeamMatchHistoryModel.kickoff_utc)
                    )
                )
                history = [
                    TeamMatchHistory(
                        team_id=row.team_w2_id,
                        opponent_id=row.opponent_w2_id,
                        kickoff_at=normalize_utc(row.kickoff_utc),
                        goals_for=row.goals_for,
                        goals_against=row.goals_against,
                        source="canonical_team_match_history",
                        source_group="team_fixture_history",
                        is_independent_signal=True,
                        collection_status="READY",
                        result_identity_hash=row.result_identity_hash,
                    )
                    for row in rows
                ]
                rating = rating_from_history(
                    team_id=team_id,
                    history=history,
                    as_of=self.now,
                    min_matches=self.config.min_rating_matches,
                )
                if rating is None:
                    continue
                source_hashes = [row.history_hash for row in rows]
                payload = {
                    "w2_team_id": team_id,
                    "observed_at": iso_z(rating.observed_at),
                    "model_version": MODEL_VERSION,
                    "elo": round(rating.elo, 6),
                    "attack_strength": round(rating.attack_strength, 6),
                    "defence_strength": round(rating.defence_strength, 6),
                    "form_index": round(rating.form_index, 6),
                    "source_history_hashes": source_hashes,
                }
                rating_hash = stable_hash(payload)
                model = TeamRatingSnapshotModel(
                    rating_id=f"{team_id}:{MODEL_VERSION}:{rating_hash[:16]}",
                    w2_team_id=team_id,
                    observed_at=normalize_utc(rating.observed_at),
                    model_version=MODEL_VERSION,
                    elo=float(payload["elo"]),
                    attack_strength=float(payload["attack_strength"]),
                    defence_strength=float(payload["defence_strength"]),
                    form_index=float(payload["form_index"]),
                    source=MODEL_VERSION,
                    source_history_hashes=source_hashes,
                    rating_hash=rating_hash,
                    payload=payload,
                )
                try:
                    with session.begin_nested():
                        session.add(model)
                        session.flush()
                    count += 1
                except IntegrityError:
                    existing = session.get(TeamRatingSnapshotModel, model.rating_id)
                    if existing is None or existing.rating_hash != rating_hash:
                        raise FactorModelRemediationError("TEAM_RATING_SNAPSHOT_CONFLICT") from None
            session.commit()
        return count

    @property
    def provider_call_count(self) -> int:
        return len(self._provider_audit)

    def team_identity_authority_payload(self) -> dict[str, Any]:
        with Session(self.engine) as session:
            teams = list(
                session.scalars(
                    select(CanonicalTeamModel).order_by(CanonicalTeamModel.w2_team_id)
                )
            )
            crosswalks = list(
                session.scalars(
                    select(ProviderTeamIdentityCrosswalkModel).order_by(
                        ProviderTeamIdentityCrosswalkModel.provider,
                        ProviderTeamIdentityCrosswalkModel.provider_team_id,
                    )
                )
            )
            fixtures = list(
                session.scalars(
                    select(MatchdayFixtureIdentityModel)
                    .where(
                        MatchdayFixtureIdentityModel.competition_id
                        == self.config.competition_id
                    )
                    .order_by(MatchdayFixtureIdentityModel.provider_fixture_id)
                )
            )
        payload = {
            "schema_version": "AllsvenskanTeamIdentityAuthorityV1",
            "generated_at_utc": iso_z(self.now),
            "competition_id": self.config.competition_id,
            "season": self.config.season,
            "authority_status": (
                PROVIDER_PRIMARY_READY
                if crosswalks and all(
                    row.identity_status == PROVIDER_PRIMARY_READY for row in crosswalks
                )
                else "DATA_DEPENDENCY_MISSING"
            ),
            "scope_note": (
                "Provider-primary identity is valid for API-Football matchday analysis "
                "only; it is not a reviewed Football-Data or Transfermarkt crosswalk."
            ),
            "canonical_teams": [
                {
                    "w2_team_id": team.w2_team_id,
                    "display_name": team.display_name,
                    "country": team.country,
                    "active_status": team.active_status,
                    "identity_hash": team.identity_hash,
                }
                for team in teams
            ],
            "provider_crosswalks": [
                {
                    "provider": row.provider,
                    "provider_team_id": row.provider_team_id,
                    "w2_team_id": row.w2_team_id,
                    "competition_id": row.competition_id,
                    "season": row.season,
                    "identity_status": row.identity_status,
                    "identity_hash": row.identity_hash,
                    "evidence_hash_count": len(row.evidence_hashes or []),
                }
                for row in crosswalks
            ],
            "fixture_identity_projection": [
                {
                    "provider_fixture_id": fixture.provider_fixture_id,
                    "fixture_id": fixture.fixture_id,
                    "team_identity_status": fixture.team_identity_status,
                    "home_w2_team_id": fixture.home_w2_team_id,
                    "away_w2_team_id": fixture.away_w2_team_id,
                }
                for fixture in fixtures
            ],
            "formal_ah": False,
            "formal_ou": False,
            "recommendation_lock": False,
            "production_recommendation": False,
        }
        payload["authority_hash"] = stable_hash(payload)
        return payload

    def _request(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        if self.provider_call_count >= self.config.request_budget:
            raise FactorModelRemediationError("PROVIDER_CALL_BUDGET_EXHAUSTED")
        response = self.client.request_live(endpoint, params)
        return response

    def _persist_capture(
        self,
        response: LiveApiFootballResponse,
        *,
        fixture_id: str | None,
    ) -> str:
        payload_hash = sha256_payload(response.payload)
        captured_at = normalize_utc(response.captured_at)
        requested_at = (
            normalize_utc(response.requested_at)
            if response.requested_at is not None
            else captured_at
        )
        capture = endpoint_capture_contract(
            checkpoint="CONTROLLED_FACTOR_MODEL_REMEDIATION",
            endpoint=response.endpoint,
            params=response.params,
            requested_at=requested_at,
            provider_captured_at=captured_at,
            status_code=response.status_code,
            elapsed_ms=response.elapsed_ms,
            payload=response.payload,
            fixture_id=fixture_id,
            competition_id=self.config.competition_id,
            attempt=1,
            quota_values={
                key: value
                for key, value in response.headers.items()
                if key.lower().startswith(("x-ratelimit", "x-requests"))
            },
            provider_event_time=None,
        )
        with Session(self.engine) as session:
            existing = session.get(MatchdayEndpointCaptureModel, capture["capture_id"])
            if existing is None:
                session.add(
                    MatchdayEndpointCaptureModel(
                        capture_id=str(capture["capture_id"]),
                        fixture_id=fixture_id,
                        competition_id=self.config.competition_id,
                        checkpoint="CONTROLLED_FACTOR_MODEL_REMEDIATION",
                        endpoint=response.endpoint,
                        sanitized_params=sanitize_params(response.params),
                        params_hash=str(capture["params_hash"]),
                        request_task_key=str(capture["request_task_key"]),
                        attempt=1,
                        requested_at=requested_at,
                        provider_captured_at=captured_at,
                        status_code=response.status_code,
                        elapsed_ms=response.elapsed_ms,
                        response_count=response_count(response.payload),
                        quota_values=dict(capture["quota_values"]),
                        raw_payload_sha256=payload_hash,
                        provider_event_time=None,
                        capture_status=str(capture["capture_status"]),
                        error_code=capture["error_code"],
                    )
                )
            session.commit()
        from w2.matchday.repository import MatchdayRuntimeRepository

        MatchdayRuntimeRepository(engine=self.engine).save_raw_payload(
            sha256=payload_hash,
            endpoint=response.endpoint,
            captured_at=captured_at,
            payload=response.payload,
        )
        self._provider_audit.append(
            ProviderAuditEntry(
                endpoint=response.endpoint,
                params=sanitize_params(response.params),
                status_code=response.status_code,
                elapsed_ms=response.elapsed_ms,
                captured_at_utc=iso_z(captured_at),
                requested_at_utc=iso_z(requested_at),
                payload_sha256=payload_hash,
                capture_id=str(capture["capture_id"]),
                response_count=response_count(response.payload),
            )
        )
        return str(capture["capture_id"])

    def _upsert_history_fixtures(
        self,
        fixtures: dict[str, dict[str, Any]],
        *,
        fixture_capture_ids: dict[str, str],
    ) -> int:
        count = 0
        mapping = self._provider_to_w2_mapping()
        with Session(self.engine) as session:
            for provider_fixture_id, item in sorted(fixtures.items()):
                rows = history_rows_from_fixture(
                    item,
                    competition_id=self.config.competition_id,
                    season=self.config.season,
                    source_raw_hash=stable_hash(item),
                    endpoint_capture_id=fixture_capture_ids.get(provider_fixture_id),
                    captured_at=self.now,
                    provider_to_w2=mapping,
                )
                for payload in rows:
                    model = CanonicalTeamMatchHistoryModel(**payload)
                    try:
                        with session.begin_nested():
                            session.add(model)
                            session.flush()
                        count += 1
                    except IntegrityError:
                        existing = session.get(
                            CanonicalTeamMatchHistoryModel,
                            model.history_id,
                        )
                        if existing is None or existing.history_hash != model.history_hash:
                            raise FactorModelRemediationError("MATCH_HISTORY_CONFLICT") from None
            session.commit()
        return count

    def _probe_xg(self, fixtures: dict[str, dict[str, Any]]) -> tuple[int, list[str]]:
        blockers: list[str] = []
        xg_rows: list[TeamXgMatch] = []
        for provider_fixture_id, item in sorted(fixtures.items()):
            if self.provider_call_count >= self.config.request_budget:
                blockers.append("PROVIDER_CALL_BUDGET_EXHAUSTED")
                break
            response = self._request("statistics", {"fixture": provider_fixture_id})
            if response.status_code >= 400:
                blockers.append(f"STATISTICS_HTTP_{response.status_code}:{provider_fixture_id}")
                continue
            self._persist_capture(response, fixture_id=provider_fixture_id)
            xg_rows.extend(
                parse_team_xg_matches(
                    fixture_payload=item,
                    statistics_payload=response.payload,
                    captured_at=response.captured_at,
                    raw_payload_sha256=sha256_payload(response.payload),
                )
            )
        if not xg_rows:
            blockers.append("PROVIDER_XG_FIELD_UNAVAILABLE_FOR_ALLSVENSKAN")
            return 0, blockers
        from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository

        repo = FutureRefreshDbRepository(engine=self.engine)
        return repo.upsert_team_xg_matches(
            [
                {
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
                for row in xg_rows
            ]
        ), blockers

    def _capture_smoke_h2h(self) -> tuple[int, list[str]]:
        blockers: list[str] = []
        rows = 0
        with Session(self.engine) as session:
            fixtures = list(
                session.scalars(
                    select(MatchdayFixtureIdentityModel)
                    .where(
                        MatchdayFixtureIdentityModel.provider_fixture_id.in_(
                            self.config.smoke_fixture_ids
                        ),
                        MatchdayFixtureIdentityModel.competition_id == self.config.competition_id,
                    )
                    .order_by(MatchdayFixtureIdentityModel.provider_fixture_id)
                )
            )
        for fixture in fixtures:
            if self.provider_call_count >= self.config.request_budget:
                blockers.append("PROVIDER_CALL_BUDGET_EXHAUSTED")
                break
            response = self._request(
                "h2h",
                {
                    "h2h": f"{fixture.home_provider_team_id}-{fixture.away_provider_team_id}",
                    "last": "5",
                },
            )
            if response.status_code >= 400:
                blockers.append(f"H2H_HTTP_{response.status_code}:{fixture.provider_fixture_id}")
                continue
            capture_id = self._persist_capture(response, fixture_id=fixture.provider_fixture_id)
            h2h_items = {
                provider_fixture_id_from_item(item): item
                for item in finished_fixture_items(response.payload, now=self.now)
                if provider_fixture_id_from_item(item)
            }
            h2h_capture_ids = {
                provider_fixture_id: capture_id for provider_fixture_id in h2h_items
            }
            rows += self._upsert_history_fixtures(
                h2h_items,
                fixture_capture_ids=h2h_capture_ids,
            )
        return rows, blockers

    def _snapshot(
        self,
        *,
        seed: dict[str, int],
        blockers: list[str],
        xg_rows: int,
        h2h_rows: int,
        rating_rows: int,
    ) -> RemediationResult:
        with Session(self.engine) as session:
            history_rows = (
                session.scalar(select(func.count()).select_from(CanonicalTeamMatchHistoryModel))
                or 0
            )
            fixture_count = (
                session.scalar(
                    select(func.count(func.distinct(CanonicalTeamMatchHistoryModel.provider_fixture_id)))
                )
                or 0
            )
            readiness = self._smoke_readiness(session)
        if xg_rows > 0:
            xg_status = "READY"
        elif self.provider_call_count == 0:
            xg_status = "NOT_PROBED_PROVIDER_CALLS_DISABLED"
        else:
            xg_status = "PROVIDER_XG_FIELD_UNAVAILABLE_FOR_ALLSVENSKAN"
        return RemediationResult(
            generated_at_utc=self.now,
            competition_id=self.config.competition_id,
            season=self.config.season,
            canonical_team_count=seed["canonical_team_count"],
            provider_crosswalk_count=seed["provider_crosswalk_count"],
            fixture_identity_ready_count=seed["fixture_identity_ready_count"],
            canonical_history_rows=int(history_rows),
            canonical_history_fixtures=int(fixture_count),
            rating_snapshot_count=rating_rows,
            xg_match_rows=xg_rows,
            xg_status=xg_status,
            h2h_rows=h2h_rows,
            provider_call_count=self.provider_call_count,
            blockers=sorted(set(blockers)),
            provider_audit=self._provider_audit,
            smoke_fixture_readiness=readiness,
        )

    def _target_fixtures(self, session: Session) -> list[MatchdayFixtureIdentityModel]:
        query: Select[tuple[MatchdayFixtureIdentityModel]] = (
            select(MatchdayFixtureIdentityModel)
            .where(
                MatchdayFixtureIdentityModel.provider == PROVIDER,
                MatchdayFixtureIdentityModel.competition_id == self.config.competition_id,
                MatchdayFixtureIdentityModel.season == self.config.season,
            )
            .order_by(MatchdayFixtureIdentityModel.kickoff_utc)
        )
        return list(session.scalars(query))

    def _provider_team_ids(self) -> list[str]:
        with Session(self.engine) as session:
            fixtures = self._target_fixtures(session)
        ids = {
            team_id
            for fixture in fixtures
            for team_id in (fixture.home_provider_team_id, fixture.away_provider_team_id)
        }
        return sorted(ids, key=lambda value: int(value) if value.isdigit() else value)

    def _provider_to_w2_mapping(self) -> dict[str, str]:
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(ProviderTeamIdentityCrosswalkModel)
                    .where(
                        ProviderTeamIdentityCrosswalkModel.provider == PROVIDER,
                        ProviderTeamIdentityCrosswalkModel.competition_id
                        == self.config.competition_id,
                        ProviderTeamIdentityCrosswalkModel.season == self.config.season,
                        ProviderTeamIdentityCrosswalkModel.identity_status
                        == PROVIDER_PRIMARY_READY,
                    )
                    .order_by(ProviderTeamIdentityCrosswalkModel.provider_team_id)
                )
            )
        return {row.provider_team_id: row.w2_team_id for row in rows}

    def _smoke_readiness(self, session: Session) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for fixture in session.scalars(
            select(MatchdayFixtureIdentityModel)
            .where(MatchdayFixtureIdentityModel.provider_fixture_id.in_(self.config.smoke_fixture_ids))
            .order_by(MatchdayFixtureIdentityModel.provider_fixture_id)
        ):
            home_history = (
                session.scalar(
                    select(func.count())
                    .select_from(CanonicalTeamMatchHistoryModel)
                    .where(CanonicalTeamMatchHistoryModel.team_w2_id == fixture.home_w2_team_id)
                )
                or 0
            )
            away_history = (
                session.scalar(
                    select(func.count())
                    .select_from(CanonicalTeamMatchHistoryModel)
                    .where(CanonicalTeamMatchHistoryModel.team_w2_id == fixture.away_w2_team_id)
                )
                or 0
            )
            home_rating = (
                session.scalar(
                    select(func.count())
                    .select_from(TeamRatingSnapshotModel)
                    .where(TeamRatingSnapshotModel.w2_team_id == fixture.home_w2_team_id)
                )
                or 0
            )
            away_rating = (
                session.scalar(
                    select(func.count())
                    .select_from(TeamRatingSnapshotModel)
                    .where(TeamRatingSnapshotModel.w2_team_id == fixture.away_w2_team_id)
                )
                or 0
            )
            output.append(
                {
                    "provider_fixture_id": fixture.provider_fixture_id,
                    "fixture_id": fixture.fixture_id,
                    "team_identity_status": fixture.team_identity_status,
                    "home_history_rows": int(home_history),
                    "away_history_rows": int(away_history),
                    "home_rating_ready": bool(home_rating),
                    "away_rating_ready": bool(away_rating),
                }
            )
        return output


def provider_teams_from_fixtures(
    fixtures: list[MatchdayFixtureIdentityModel],
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for fixture in fixtures:
        payload = fixture.payload if isinstance(fixture.payload, dict) else {}
        teams = payload.get("teams") if isinstance(payload.get("teams"), dict) else {}
        for side, provider_id in (
            ("home", fixture.home_provider_team_id),
            ("away", fixture.away_provider_team_id),
        ):
            team_payload = teams.get(side) if isinstance(teams, dict) else None
            display_name = (
                str(team_payload.get("name"))
                if isinstance(team_payload, dict) and team_payload.get("name")
                else provider_id
            )
            current = by_id.setdefault(
                provider_id,
                {
                    "provider_team_id": provider_id,
                    "display_name": display_name,
                    "country": "Sweden",
                    "evidence_hashes": set(),
                },
            )
            current["evidence_hashes"].add(fixture.identity_hash)
    return [
        {
            **item,
            "evidence_hashes": sorted(item["evidence_hashes"]),
        }
        for item in sorted(by_id.values(), key=lambda row: row["provider_team_id"])
    ]


def stable_w2_team_id(provider_team_id: str) -> str:
    return f"w2:team:api_football:{provider_team_id}"


def canonical_team_payload(
    *,
    provider_team_id: str,
    display_name: str,
    country: str | None,
    created_at: datetime,
) -> dict[str, Any]:
    w2_team_id = stable_w2_team_id(provider_team_id)
    payload = {
        "schema_version": "CanonicalTeamV1",
        "w2_team_id": w2_team_id,
        "display_name": display_name,
        "country": country,
        "active_status": "ACTIVE",
        "provider_primary_identity": {
            "provider": PROVIDER,
            "provider_team_id": provider_team_id,
        },
    }
    return {
        "w2_team_id": w2_team_id,
        "display_name": display_name,
        "country": country,
        "active_status": "ACTIVE",
        "created_at": normalize_utc(created_at),
        "identity_hash": stable_hash(payload),
        "payload": payload,
    }


def provider_crosswalk_payload(
    *,
    provider_team_id: str,
    w2_team_id: str,
    competition_id: str,
    season: str,
    evidence_hashes: list[str],
    valid_from: datetime,
) -> dict[str, Any]:
    payload = {
        "schema_version": "ProviderTeamIdentityCrosswalkV1",
        "provider": PROVIDER,
        "provider_team_id": provider_team_id,
        "w2_team_id": w2_team_id,
        "competition_id": competition_id,
        "season": season,
        "valid_from": iso_z(valid_from),
        "identity_status": PROVIDER_PRIMARY_READY,
        "evidence_hashes": evidence_hashes,
        "scope_note": "Provider-primary W2 identity; not a Football-Data or Transfermarkt match.",
    }
    identity_hash = stable_hash(payload)
    return {
        "id": f"{PROVIDER}:{provider_team_id}:{competition_id}:{season}",
        "provider": PROVIDER,
        "provider_team_id": provider_team_id,
        "w2_team_id": w2_team_id,
        "competition_id": competition_id,
        "season": season,
        "valid_from": normalize_utc(valid_from),
        "valid_to": None,
        "identity_status": PROVIDER_PRIMARY_READY,
        "evidence_hashes": evidence_hashes,
        "identity_hash": identity_hash,
    }


def finished_fixture_items(payload: dict[str, Any], *, now: datetime) -> list[dict[str, Any]]:
    response = payload.get("response")
    if not isinstance(response, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in response:
        if not isinstance(item, dict):
            continue
        fixture = dict_or_empty(item.get("fixture"))
        status = dict_or_empty(fixture.get("status"))
        kickoff = parse_utc(fixture.get("date"))
        if status.get("short") in FINISHED_STATUS and kickoff is not None and kickoff < now:
            rows.append(item)
    return rows


def history_rows_from_fixture(
    item: dict[str, Any],
    *,
    competition_id: str,
    season: str,
    source_raw_hash: str,
    endpoint_capture_id: str | None,
    captured_at: datetime,
    provider_to_w2: dict[str, str],
) -> list[dict[str, Any]]:
    fixture = dict_or_empty(item.get("fixture"))
    teams = dict_or_empty(item.get("teams"))
    goals = dict_or_empty(item.get("goals"))
    provider_fixture_id = str(fixture.get("id") or "")
    kickoff = parse_utc(fixture.get("date"))
    status = dict_or_empty(fixture.get("status"))
    home = dict_or_empty(teams.get("home"))
    away = dict_or_empty(teams.get("away"))
    home_provider_id = str(home.get("id") or "")
    away_provider_id = str(away.get("id") or "")
    if not provider_fixture_id or kickoff is None or not home_provider_id or not away_provider_id:
        return []
    home_w2 = provider_to_w2.get(home_provider_id)
    away_w2 = provider_to_w2.get(away_provider_id)
    if home_w2 is None or away_w2 is None:
        return []
    home_goals = int_or_zero(goals.get("home"))
    away_goals = int_or_zero(goals.get("away"))
    rows = []
    for side, team_provider_id, opponent_provider_id, team_w2, opponent_w2, gf, ga in (
        ("HOME", home_provider_id, away_provider_id, home_w2, away_w2, home_goals, away_goals),
        ("AWAY", away_provider_id, home_provider_id, away_w2, home_w2, away_goals, home_goals),
    ):
        result_identity = stable_hash(
            {
                "provider_fixture_id": provider_fixture_id,
                "team_provider_id": team_provider_id,
                "opponent_provider_id": opponent_provider_id,
                "goals_for": gf,
                "goals_against": ga,
                "status": status.get("short"),
            }
        )
        payload = {
            "fixture_id": f"{PROVIDER}:{provider_fixture_id}",
            "provider": PROVIDER,
            "provider_fixture_id": provider_fixture_id,
            "competition_id": competition_id,
            "season": season,
            "kickoff_utc": iso_z(kickoff),
            "fixture_status": str(status.get("short") or ""),
            "team_side": side,
            "team_provider_id": team_provider_id,
            "opponent_provider_id": opponent_provider_id,
            "team_w2_id": team_w2,
            "opponent_w2_id": opponent_w2,
            "goals_for": gf,
            "goals_against": ga,
            "result_identity_hash": result_identity,
            "source_raw_hash": source_raw_hash,
            "endpoint_capture_id": endpoint_capture_id,
            "captured_at": iso_z(captured_at),
        }
        nested_payload = {"schema_version": "CanonicalTeamMatchHistoryV1", **payload}
        history_hash = stable_hash(payload)
        rows.append(
            {
                **payload,
                "history_id": f"{PROVIDER}:{provider_fixture_id}:{team_w2}",
                "kickoff_utc": kickoff,
                "captured_at": normalize_utc(captured_at),
                "history_hash": history_hash,
                "payload": nested_payload,
            }
        )
    return rows


def write_remediation_artifacts(result: RemediationResult, *, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = result.as_dict()
    (output_dir / "W2_FACTOR_MODEL_REMEDIATION_RESULT_V1.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "W2_FACTOR_MODEL_REMEDIATION_RESULT_V1.md").write_text(
        markdown_summary(payload),
        encoding="utf-8",
    )


def write_team_identity_authority_artifacts(
    authority_payload: dict[str, Any],
    *,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "ALLSVENSKAN_TEAM_IDENTITY_AUTHORITY_V1.json").write_text(
        json.dumps(authority_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Allsvenskan Team Identity Authority V1",
        "",
        f"- generated_at_utc: `{authority_payload['generated_at_utc']}`",
        f"- competition_id: `{authority_payload['competition_id']}`",
        f"- season: `{authority_payload['season']}`",
        f"- authority_status: `{authority_payload['authority_status']}`",
        f"- canonical_team_count: `{len(authority_payload['canonical_teams'])}`",
        f"- provider_crosswalk_count: `{len(authority_payload['provider_crosswalks'])}`",
        f"- fixture_projection_count: `{len(authority_payload['fixture_identity_projection'])}`",
        f"- authority_hash: `{authority_payload['authority_hash']}`",
        "",
        "## Scope",
        "",
        f"- {authority_payload['scope_note']}",
        "- formal_ah: `false`",
        "- formal_ou: `false`",
        "- recommendation_lock: `false`",
        "- production_recommendation: `false`",
    ]
    (output_dir / "ALLSVENSKAN_TEAM_IDENTITY_AUTHORITY_V1.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def markdown_summary(payload: dict[str, Any]) -> str:
    lines = [
        "# W2 Factor Model Remediation Result V1",
        "",
        f"- generated_at_utc: `{payload['generated_at_utc']}`",
        f"- competition_id: `{payload['competition_id']}`",
        f"- season: `{payload['season']}`",
        f"- canonical_team_count: `{payload['canonical_team_count']}`",
        f"- provider_crosswalk_count: `{payload['provider_crosswalk_count']}`",
        f"- fixture_identity_ready_count: `{payload['fixture_identity_ready_count']}`",
        f"- canonical_history_rows: `{payload['canonical_history_rows']}`",
        f"- canonical_history_fixtures: `{payload['canonical_history_fixtures']}`",
        f"- rating_snapshot_count: `{payload['rating_snapshot_count']}`",
        f"- xg_match_rows: `{payload['xg_match_rows']}`",
        f"- xg_status: `{payload['xg_status']}`",
        f"- h2h_rows: `{payload['h2h_rows']}`",
        f"- provider_call_count: `{payload['provider_call_count']}`",
        f"- final_state: `{payload['final_state']}`",
        "",
        "## Blockers",
        "",
    ]
    blockers = payload.get("blockers") or []
    lines.extend(f"- `{blocker}`" for blocker in blockers)
    if not blockers:
        lines.append("- none")
    lines.extend(["", "## Smoke Fixture Readiness", ""])
    for row in payload.get("smoke_fixture_readiness") or []:
        lines.append(
            "- "
            f"`{row['provider_fixture_id']}` identity=`{row['team_identity_status']}` "
            f"history=`{row['home_history_rows']}/{row['away_history_rows']}` "
            f"ratings=`{row['home_rating_ready']}/{row['away_rating_ready']}`"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- formal_ah: `false`",
            "- formal_ou: `false`",
            "- recommendation_lock: `false`",
            "- production_recommendation: `false`",
            (
                "- Raw provider payloads are persisted only through endpoint "
                "capture/raw-payload storage."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def normalize_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def iso_z(value: datetime) -> str:
    return normalize_utc(value).isoformat().replace("+00:00", "Z")


def int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def provider_fixture_id_from_item(item: dict[str, Any]) -> str:
    fixture = dict_or_empty(item.get("fixture"))
    return str(fixture.get("id") or "")


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
