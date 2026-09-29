"""F6 H2H 采集管线：新 fixture 进评估前自动补该场交锋（幂等防重复）。

复用 remediation.py 的 canonical 写入路径（history_rows_from_fixture + endpoint capture），
把 h2h 交锋写入 canonical_team_match_history，让 F6 builder 无需改动即可读到。
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import HashDomain
from w2.factor_model.remediation import (
    finished_fixture_items,
    history_rows_from_fixture,
)
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamMatchHistoryModel,
    ProviderTeamIdentityCrosswalkModel,
)
from w2.infrastructure.persistence.league_models import LeagueSeasonModel
from w2.infrastructure.persistence.matchday_intake_models import MatchdayEndpointCaptureModel
from w2.ingestion.future_refresh import response_count, sanitize_params, sha256_payload
from w2.matchday.intake_v2 import endpoint_capture_contract, stable_hash
from w2.matchday.repository import MatchdayRuntimeRepository
from w2.providers.api_football import ApiFootballClient

PROVIDER = "api_football"
CHECKPOINT = "F6_H2H_AUTO_CAPTURE"


def _crosswalk(session: Session) -> dict[str, str]:
    rows = session.scalars(
        select(ProviderTeamIdentityCrosswalkModel).where(
            ProviderTeamIdentityCrosswalkModel.provider == PROVIDER,
            ProviderTeamIdentityCrosswalkModel.identity_status == "PROVIDER_PRIMARY_READY",
        )
    ).all()
    mapping: dict[str, set[str]] = {}
    for row in rows:
        mapping.setdefault(row.provider_team_id, set()).add(row.w2_team_id)
    return {pid: next(iter(w2s)) for pid, w2s in mapping.items() if len(w2s) == 1}


def _league_mapping(session: Session) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in session.scalars(select(LeagueSeasonModel)):
        payload = row.payload or {}
        lid = str(payload.get("provider_league_id") or "").strip()
        if lid:
            mapping.setdefault(lid, row.competition_id)
    return mapping


def _persist_capture(
    session: Session, response, *, fixture_id: str | None, competition_id: str
) -> str:
    payload_hash = sha256_payload(response.payload, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)
    captured_at = response.captured_at.astimezone(UTC)
    requested_at = (response.requested_at or captured_at).astimezone(UTC)
    capture = endpoint_capture_contract(
        checkpoint=CHECKPOINT,
        endpoint=response.endpoint,
        params=response.params,
        requested_at=requested_at,
        provider_captured_at=captured_at,
        status_code=response.status_code,
        elapsed_ms=response.elapsed_ms,
        payload=response.payload,
        fixture_id=fixture_id,
        competition_id=competition_id,
        attempt=1,
        quota_values={
            k: v
            for k, v in response.headers.items()
            if k.lower().startswith(("x-ratelimit", "x-requests"))
        },
        provider_event_time=None,
    )
    existing = session.get(MatchdayEndpointCaptureModel, capture["capture_id"])
    if existing is None:
        session.add(
            MatchdayEndpointCaptureModel(
                capture_id=str(capture["capture_id"]),
                fixture_id=fixture_id,
                competition_id=competition_id,
                checkpoint=CHECKPOINT,
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
    MatchdayRuntimeRepository(engine=session.bind).save_raw_payload(
        sha256=payload_hash,
        endpoint=response.endpoint,
        captured_at=captured_at,
        payload=response.payload,
    )
    return str(capture["capture_id"])


def _freeze_h2h_history_row(session: Session, payload: dict) -> bool:
    """One immutable source identity; retry compares every frozen business field."""
    def same(existing):
        for field, expected in payload.items():
            actual = getattr(existing, field)
            if isinstance(expected, datetime) and isinstance(actual, datetime):
                expected, actual = (value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC) for value in (expected,actual))
            if actual != expected:
                raise RuntimeError(f"F6_HISTORY_FIELD_CONFLICT:{field}")
    existing = session.get(CanonicalTeamMatchHistoryModel, payload["history_id"])
    if existing is not None:
        same(existing)
        return False
    try:
        with session.begin_nested():
            session.add(CanonicalTeamMatchHistoryModel(**payload))
            session.flush()
        return True
    except IntegrityError:
        existing = session.get(CanonicalTeamMatchHistoryModel, payload["history_id"])
        if existing is None:
            raise
        same(existing)
        return False


def capture_h2h_for_pair(
    *,
    home_provider_team_id: str,
    away_provider_team_id: str,
    competition_id: str,
    season: str,
    client: ApiFootballClient | None = None,
) -> int:
    """对一场比赛采集其交锋历史，返回本次新增的 canonical 行数（幂等）。"""
    engine = create_engine()
    provider = client or ApiFootballClient(
        allow_live=True, allowed_live_endpoints=frozenset({"h2h"})
    )
    response = provider.request_live(
        "h2h", {"h2h": f"{home_provider_team_id}-{away_provider_team_id}", "last": "10"}
    )
    if response.status_code >= 400:
        raise RuntimeError("F6_H2H_CAPTURE_FAILED")
    now = datetime.now(UTC)
    inserted = 0
    with Session(engine) as session:
        mapping = _crosswalk(session)
        league_to_comp = _league_mapping(session)
        capture_id = _persist_capture(
            session,
            response,
            fixture_id=None,
            competition_id=competition_id,
        )
        for item in finished_fixture_items(response.payload, now=now):
            lg = item.get("league") or {}
            lid = str(lg.get("id") or "").strip()
            meeting_comp = league_to_comp.get(lid, competition_id)
            meeting_season = str(lg.get("season") or season).strip()
            for payload in history_rows_from_fixture(
                item,
                competition_id=meeting_comp,
                season=meeting_season,
                source_raw_hash=stable_hash(item),
                endpoint_capture_id=capture_id,
                captured_at=response.captured_at.astimezone(UTC),
                provider_to_w2=mapping,
            ):
                if _freeze_h2h_history_row(session, payload):
                    inserted += 1

        session.commit()
    return inserted


def capture_h2h_for_competition(
    *,
    competition_id: str,
    season: str = "2026",
    client: ApiFootballClient | None = None,
) -> dict[str, int]:
    """对新赛季某联赛的 fixture 自动补 H2H（只补尚无交锋者，幂等）。

    返回 {"fixtures": 检查数, "captured": 已补场数, "skipped": 已有交锋跳过数}。
    """
    from w2.infrastructure.persistence.matchday_intake_models import MatchdayFixtureIdentityModel

    engine = create_engine()
    with Session(engine) as session:
        fixtures = list(
            session.scalars(
                select(MatchdayFixtureIdentityModel).where(
                    MatchdayFixtureIdentityModel.competition_id == competition_id,
                    MatchdayFixtureIdentityModel.season == season,
                )
            )
        )
        has_h2h = set()
        for home_w2, away_w2 in session.execute(
            select(
                CanonicalTeamMatchHistoryModel.team_w2_id,
                CanonicalTeamMatchHistoryModel.opponent_w2_id,
            ).distinct()
        ):
            has_h2h.add((home_w2, away_w2))

    provider = client or ApiFootballClient(
        allow_live=True, allowed_live_endpoints=frozenset({"h2h"})
    )
    captured = 0
    skipped = 0
    for fixture in fixtures:
        home_pid = fixture.home_provider_team_id
        away_pid = fixture.away_provider_team_id
        if not home_pid or not away_pid:
            continue
        if fixture.home_w2_team_id and fixture.away_w2_team_id:
            pair = (fixture.home_w2_team_id, fixture.away_w2_team_id)
            if pair in has_h2h or (fixture.away_w2_team_id, fixture.home_w2_team_id) in has_h2h:
                skipped += 1
                continue
        capture_h2h_for_pair(
            home_provider_team_id=home_pid,
            away_provider_team_id=away_pid,
            competition_id=competition_id,
            season=season,
            client=provider,
        )
        captured += 1
    return {"fixtures": len(fixtures), "captured": captured, "skipped": skipped}
