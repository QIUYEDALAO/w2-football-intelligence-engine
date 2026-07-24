"""Projection-only production read service.

The API reads materialized payloads from ``read_model_checkpoint``. Analysis
features, pricing and simulation remain write-side concerns and are never
recomputed in a request.
"""

from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime
from time import monotonic
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from w2.competitions.registry import CompetitionRegistry, CompetitionRegistryError
from w2.config import get_settings
from w2.dashboard.date_window import (
    FOOTBALL_DAY_CUTOFF_HOUR,
    FOOTBALL_DAY_TZ,
    default_football_day,
    football_day_window,
)
from w2.dashboard.performance import dashboard_performance
from w2.dashboard.results import normalize_match_status
from w2.dashboard.validation_summary import validation_summary
from w2.domain.recommendation_capabilities import load_recommendation_capability_manifest
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.matchday.timezone import (
    BEIJING_TZ,
    BeijingOperationalDayPolicy,
    FixtureOperationalDateResolver,
    next_36_hours_window,
)
from w2.operations.leagues import run_top_five_audit
from w2.operations.release_evidence import build_release_identity
from w2.prematch.read_model_projection import (
    ANALYSIS_CARD_SHADOW_PREFIX,
    FrozenAnalysisError,
    validate_frozen_analysis_payload,
)
from w2.providers.quota import api_football_quota_policy, parse_int

MAX_PUBLIC_FIXTURES = 512
FINISHED_STATUSES = {"FT", "AET", "PEN", "FINISHED"}


class SystemDegradedError(RuntimeError):
    """The authoritative read model cannot be read or validated."""

    code = "SYSTEM_DEGRADED"


@dataclass(frozen=True)
class Checkpoint:
    key: str
    source_hash: str
    created_at: datetime
    payload: dict[str, Any]


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _checkpoint_metadata(row: Checkpoint) -> dict[str, Any]:
    return {
        "checkpoint_key": row.key,
        "source_hash": row.source_hash,
        "created_at": row.created_at.isoformat().replace("+00:00", "Z"),
    }


class ReadModelRepository:
    """Single production read authority backed by ``read_model_checkpoint``."""

    def checkpoints(self, prefix: str) -> list[Checkpoint]:
        try:
            with Session(create_engine()) as session:
                rows = session.scalars(
                    select(ReadModelCheckpointModel)
                    .where(ReadModelCheckpointModel.checkpoint_key.like(f"{prefix}%"))
                    .order_by(ReadModelCheckpointModel.checkpoint_key)
                ).all()
        except SQLAlchemyError as exc:
            raise SystemDegradedError("READ_MODEL_CHECKPOINT_QUERY_FAILED") from exc
        return [
            Checkpoint(
                key=row.checkpoint_key,
                source_hash=row.source_hash,
                created_at=row.created_at,
                payload=row.payload,
            )
            for row in rows
        ]

    def checkpoint(self, key: str) -> Checkpoint | None:
        try:
            with Session(create_engine()) as session:
                row = session.scalar(
                    select(ReadModelCheckpointModel).where(
                        ReadModelCheckpointModel.checkpoint_key == key
                    )
                )
        except SQLAlchemyError as exc:
            raise SystemDegradedError("READ_MODEL_CHECKPOINT_QUERY_FAILED") from exc
        if row is None:
            return None
        return Checkpoint(
            key=row.checkpoint_key,
            source_hash=row.source_hash,
            created_at=row.created_at,
            payload=row.payload,
        )

    def dashboard_latest_fixtures(self) -> list[dict[str, Any]]:
        return [
            {**deepcopy(row.payload), "_read_model_checkpoint": _checkpoint_metadata(row)}
            for row in self.checkpoints("dashboard:fixture_latest:")
        ]

    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        row = self.checkpoint(f"dashboard:fixture_latest:{fixture_id}")
        if row is None:
            return None
        return {**deepcopy(row.payload), "_read_model_checkpoint": _checkpoint_metadata(row)}

    def dashboard_provider(self) -> dict[str, Any] | None:
        row = self.checkpoint("dashboard:provider_status")
        return None if row is None else deepcopy(row.payload)

    def dashboard_data_health(self) -> dict[str, Any] | None:
        row = self.checkpoint("dashboard:data_health")
        return None if row is None else deepcopy(row.payload)

    def dashboard_forward_status(self) -> dict[str, Any] | None:
        row = self.checkpoint("dashboard:forward_status")
        return None if row is None else deepcopy(row.payload)

    def analysis_card_projection(self, fixture_id: str) -> dict[str, Any] | None:
        row = self.checkpoint(f"{ANALYSIS_CARD_SHADOW_PREFIX}{fixture_id}")
        if row is None:
            return None
        try:
            artifact = validate_frozen_analysis_payload(fixture_id, row.payload)
        except FrozenAnalysisError as exc:
            raise SystemDegradedError("ANALYSIS_PROJECTION_INVALID") from exc
        if artifact.checkpoint_key != row.key or artifact.source_hash != row.source_hash:
            raise SystemDegradedError("ANALYSIS_PROJECTION_IDENTITY_MISMATCH")
        payload = deepcopy(artifact.payload)
        card = cast(dict[str, Any], deepcopy(payload["analysis_card"]))
        card["read_model_projection"] = {
            "checkpoint_key": row.key,
            "projection_version": payload["projection_version"],
            "projection_hash": payload["projection_hash"],
            "source_hash": row.source_hash,
            "artifact_hash": artifact.artifact_hash,
            "source_event_type": payload["source_event_type"],
            "source_event_id": payload["source_event_id"],
            "source_event_hash": payload["source_event_hash"],
            "source_event_at": payload["source_event_at"],
            "last_projected_at": payload["last_projected_at"],
        }
        return card

    def operation_payloads(self, name: str) -> list[dict[str, Any]]:
        return [
            {
                "key": row.key,
                "status": str(row.payload.get("status") or "NOT_READY"),
                "payload": deepcopy(row.payload),
            }
            for row in self.checkpoints(f"operations:{name}:")
        ]

    def release_counts(self) -> dict[str, int]:
        fixtures = self.dashboard_latest_fixtures()
        return {
            "read_model_fixture_count": len(fixtures),
            "matchday_card_count": len(fixtures),
            "future_fixture_count": len(fixtures),
            "result_event_count": len(
                [
                    item
                    for item in fixtures
                    if str(item.get("status") or "").upper() in FINISHED_STATUSES
                ]
            ),
        }

    def public_release_counts(self, *, limit: int = MAX_PUBLIC_FIXTURES) -> dict[str, int]:
        bounded = max(0, min(int(limit), MAX_PUBLIC_FIXTURES))
        fixtures = self.dashboard_latest_fixtures()[:bounded]
        return {
            "read_model_fixture_count": len(fixtures),
            "matchday_card_count": len(fixtures),
            "future_fixture_count": len(fixtures),
            "result_event_count": len(
                [
                    item
                    for item in fixtures
                    if str(item.get("status") or "").upper() in FINISHED_STATUSES
                ]
            ),
        }


class ReadModelService:
    def __init__(self, repository: ReadModelRepository | None = None) -> None:
        self.repository = repository or ReadModelRepository()
        self.day_policy = BeijingOperationalDayPolicy()
        self.date_resolver = FixtureOperationalDateResolver()
        self._dashboard_response_cache: dict[
            tuple[str, str, str, bool], tuple[float, dict[str, Any]]
        ] = {}

    def public_dashboard(self, **kwargs: Any) -> dict[str, Any]:
        return self.dashboard(**kwargs)

    def public_dashboard_summary(self, **kwargs: Any) -> dict[str, Any]:
        return self.dashboard_summary(**kwargs)

    def public_validation_summary(self, **kwargs: Any) -> dict[str, Any]:
        return self.validation_summary(**kwargs)

    def warm_dashboard_cache(self) -> None:
        # Startup must remain available to return an explicit 503 if the
        # checkpoint database is degraded; reads are warmed lazily.
        return

    def version(self) -> dict[str, Any]:
        counts = self.repository.release_counts()
        settings = get_settings()
        sha = os.getenv("W2_GIT_SHA", "UNKNOWN")
        return {
            "service": "w2-football-intelligence-engine",
            "environment": settings.environment.value,
            "api_git_sha": sha,
            "api_build_time": os.getenv("W2_BUILD_TIME"),
            "release_id": os.getenv("W2_RELEASE_ID") or sha,
            "data_profile": "real-db" if counts["read_model_fixture_count"] else "empty",
            "data_source": "read_model_checkpoint",
            "database_ready": True,
            "read_model_fixture_count": counts["read_model_fixture_count"],
            "matchday_card_count": counts["matchday_card_count"],
            "result_event_count": counts["result_event_count"],
            "release_identity": build_release_identity(settings),
            "capability_manifest": load_recommendation_capability_manifest().public_summary(),
            "generated_at": datetime.now(UTC),
        }

    def dashboard(
        self,
        *,
        target_date: str | None = None,
        window: str = "today",
        timezone: str = BEIJING_TZ,
        include_debug: bool = True,
    ) -> dict[str, Any]:
        requested_date = (
            date.fromisoformat(target_date)
            if target_date
            else default_football_day(datetime.now(UTC))
        )
        cache_key = (requested_date.isoformat(), window, timezone, include_debug)
        now_tick = monotonic()
        cached = self._dashboard_response_cache.get(cache_key)
        if cached is not None and now_tick - cached[0] <= 60:
            return deepcopy(cached[1])

        version = self.version()
        fixtures = self.repository.dashboard_latest_fixtures()[:MAX_PUBLIC_FIXTURES]
        cards = [self._project_dashboard_card(item) for item in fixtures]
        selected = self._filter_dashboard_cards(cards, requested_date=requested_date, window=window)
        recommendations = [
            card
            for card in selected
            if str(card.get("decision_tier") or "") in {"RECOMMEND", "ANALYSIS_PICK"}
        ]
        upcoming = [card for card in selected if card["status"] != "FINISHED"]
        finished = [card for card in selected if card["status"] == "FINISHED"]
        generated_at = datetime.now(UTC)
        start, end = football_day_window(requested_date)
        performance = dashboard_performance(selected)
        payload = {
            "generated_at": generated_at,
            "page_updated_at": generated_at,
            "odds_last_confirmed_at": self._latest_projection_time(selected, "source_event_at"),
            "next_refresh_tick": None,
            "date": requested_date.isoformat(),
            "selected_date": requested_date.isoformat(),
            "selected_football_day": requested_date.isoformat(),
            "selected_date_has_data": bool(selected),
            "next_available_date": self._next_available_date(requested_date, cards),
            "football_day_timezone": str(FOOTBALL_DAY_TZ),
            "football_day_cutoff_hour": FOOTBALL_DAY_CUTOFF_HOUR,
            "football_day_start_utc": start.isoformat().replace("+00:00", "Z"),
            "football_day_end_utc": end.isoformat().replace("+00:00", "Z"),
            "timezone": timezone,
            "window": window,
            "data_profile": "real-db" if cards else "empty",
            "data_source": "read_model_checkpoint",
            "version": {
                "api_git_sha": version["api_git_sha"],
                "release_id": version["release_id"],
                "read_authority": "read_model_checkpoint",
            },
            "debug": {
                "read_authority": "read_model_checkpoint",
                "fixture_checkpoint_count": len(fixtures),
                "analysis_projection_count": len(
                    [card for card in cards if card.get("read_model_projection")]
                ),
                "system_degraded_count": len(
                    [
                        card
                        for card in cards
                        if cast(dict[str, Any], card["recommendation_decision_v3"]).get("outcome")
                        == "SYSTEM_DEGRADED"
                    ]
                ),
            }
            if include_debug
            else {},
            "performance": performance,
            "recommendations": recommendations,
            "upcoming": upcoming,
            "finished": finished,
            "all": selected,
        }
        self._dashboard_response_cache[cache_key] = (now_tick, deepcopy(payload))
        return payload

    def _project_dashboard_card(self, fixture: dict[str, Any]) -> dict[str, Any]:
        fixture_id = str(fixture.get("fixture_id") or fixture.get("provider_fixture_id") or "")
        if not fixture_id:
            raise SystemDegradedError("DASHBOARD_FIXTURE_IDENTITY_MISSING")
        analysis = self.repository.analysis_card_projection(fixture_id)
        card = (
            self._system_degraded_card(fixture_id, "ANALYSIS_PROJECTION_NOT_READY")
            if analysis is None
            else analysis
        )
        merged = {
            **deepcopy(fixture),
            **deepcopy(card),
            "fixture_id": fixture_id,
            "kickoff_utc": fixture.get("kickoff_utc") or card.get("kickoff_utc"),
            "competition_id": fixture.get("competition_id") or card.get("competition_id"),
            "competition_name": fixture.get("competition_name")
            or card.get("competition_name"),
            "home_team_id": fixture.get("home_team_id"),
            "home_team_name": fixture.get("home_team_name") or card.get("home_name"),
            "away_team_id": fixture.get("away_team_id"),
            "away_team_name": fixture.get("away_team_name") or card.get("away_name"),
            "status": normalize_match_status(fixture.get("status")),
            "raw_status": fixture.get("status"),
            "formal_recommendation": False,
            "candidate": False,
        }
        decision = merged.get("recommendation_decision_v3")
        selected = (
            cast(dict[str, Any], decision).get("selected_candidate")
            if isinstance(decision, dict)
            else None
        )
        merged["recommendation"] = (
            {
                **cast(dict[str, Any], selected),
                "tier": merged.get("decision_tier"),
                "formal_recommendation": False,
            }
            if isinstance(selected, dict)
            and str(merged.get("decision_tier") or "") in {"RECOMMEND", "ANALYSIS_PICK"}
            else None
        )
        return merged

    def _system_degraded_card(self, fixture_id: str, blocker: str) -> dict[str, Any]:
        return {
            "fixture_id": fixture_id,
            "decision": "SKIP",
            "decision_tier": "NOT_READY",
            "data_status": "BLOCKED",
            "lifecycle_status": "DRAFT",
            "outcome_tracked": False,
            "lock_eligible": False,
            "recommendation_id": None,
            "pick": None,
            "reason_code": blocker,
            "action": "等待权威读模型投影",
            "next_eval_at": None,
            "current_odds": {},
            "market_probabilities": {},
            "markets": [],
            "candidate": False,
            "formal_recommendation": False,
            "non_pick": {
                "reason_code": blocker,
                "reason_human": "权威读模型投影尚未就绪",
                "action": "等待权威读模型投影",
                "next_eval_at": None,
            },
            "decision_contract": {
                "decision_tier": "NOT_READY",
                "data_status": "BLOCKED",
                "lifecycle_status": "DRAFT",
                "outcome_tracked": False,
                "lock_eligible": False,
                "recommendation_id": None,
                "pick": None,
                "reason_code": blocker,
            },
            "recommendation_decision_v3": {
                "schema_version": "w2.recommendation_decision.v3",
                "outcome": "SYSTEM_DEGRADED",
                "reason": {"code": blocker, "message": "权威读模型投影尚未就绪"},
                "selected_candidate": None,
                "evaluated_candidate": None,
                "decision_hash": None,
            },
            "read_model_projection": None,
        }

    def _filter_dashboard_cards(
        self,
        cards: list[dict[str, Any]],
        *,
        requested_date: date,
        window: str,
    ) -> list[dict[str, Any]]:
        if window == "all":
            return sorted(cards, key=lambda row: str(row.get("kickoff_utc") or ""))
        if window == "next36":
            start, end = next_36_hours_window()
            return [
                card
                for card in cards
                if (kickoff := _parse_datetime(card.get("kickoff_utc"))) is not None
                and start <= kickoff < end
            ]
        if window == "future":
            start, _ = football_day_window(requested_date)
            return [
                card
                for card in cards
                if (kickoff := _parse_datetime(card.get("kickoff_utc"))) is not None
                and kickoff >= start
            ]
        if window == "results":
            return [
                card
                for card in cards
                if card.get("status") == "FINISHED"
                and self.day_policy.window_for_date(requested_date).contains(
                    cast(datetime, _parse_datetime(card.get("kickoff_utc")))
                )
            ]
        day_window = self.day_policy.window_for_date(requested_date)
        return [
            card
            for card in cards
            if (kickoff := _parse_datetime(card.get("kickoff_utc"))) is not None
            and day_window.contains(kickoff)
        ]

    def _latest_projection_time(self, cards: list[dict[str, Any]], field: str) -> str | None:
        values = [
            str(projection[field])
            for card in cards
            if isinstance((projection := card.get("read_model_projection")), dict)
            and projection.get(field)
        ]
        return max(values, default=None)

    def _next_available_date(
        self, requested_date: date, cards: list[dict[str, Any]]
    ) -> str | None:
        candidates = []
        for card in cards:
            kickoff = _parse_datetime(card.get("kickoff_utc"))
            if kickoff is None:
                continue
            operational = self.date_resolver.operational_date(kickoff)
            if operational > requested_date:
                candidates.append(operational)
        return min(candidates).isoformat() if candidates else None

    def dashboard_summary(self, **kwargs: Any) -> dict[str, Any]:
        payload = self.dashboard(**kwargs)
        return {
            "generated_at": payload["generated_at"],
            "date": payload["date"],
            "timezone": payload["timezone"],
            "window": payload["window"],
            "data_profile": payload["data_profile"],
            "data_source": payload["data_source"],
            "version": payload["version"],
            "totals": {
                key: len(cast(list[Any], payload[key]))
                for key in ("recommendations", "upcoming", "finished", "all")
            },
            "performance": payload["performance"],
        }

    def validation_summary(self, **kwargs: Any) -> dict[str, Any]:
        payload = self.dashboard(**kwargs)
        return {
            "generated_at": payload["generated_at"],
            "date": payload["date"],
            "timezone": payload["timezone"],
            "window": payload["window"],
            "data_profile": payload["data_profile"],
            "data_source": payload["data_source"],
            "version": payload["version"],
            "validation": validation_summary(cast(dict[str, Any], payload["performance"])),
        }

    def formal_tracking_summary(self) -> dict[str, Any]:
        return {
            "generated_at": datetime.now(UTC),
            "status": "NOT_READY",
            "label": "READ_MODEL_CHECKPOINT_ONLY",
            "min_bucket_samples_for_rate": 20,
            "snapshot_count": 0,
            "settlement_count": 0,
            "sample_count": 0,
            "win_count": 0,
            "win_rate": None,
            "roi": None,
            "buckets": {},
            "not_a_formal_gate": True,
            "posthoc_only": True,
        }

    def fixtures(
        self,
        *,
        timezone: str,
        page: int,
        page_size: int,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        competition_id: str | None = None,
        status: str | None = None,
        team_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [
            self._fixture_summary(row, timezone)
            for row in self.repository.dashboard_latest_fixtures()
        ]
        if date_from:
            rows = [row for row in rows if row["kickoff_utc"] >= date_from.astimezone(UTC)]
        if date_to:
            rows = [row for row in rows if row["kickoff_utc"] <= date_to.astimezone(UTC)]
        if competition_id:
            rows = [row for row in rows if row["competition_id"] == competition_id]
        if status:
            rows = [row for row in rows if row["status"] == status]
        if team_id:
            rows = [row for row in rows if team_id in {row["home_team_id"], row["away_team_id"]}]
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start : start + page_size], total

    def matchday(self, *, target_date: str | None = None, **filters: Any) -> dict[str, Any]:
        requested = (
            date.fromisoformat(target_date)
            if target_date
            else default_football_day(datetime.now(UTC))
        )
        rows = self._filter_dashboard_cards(
            [
                self._project_dashboard_card(row)
                for row in self.repository.dashboard_latest_fixtures()
            ],
            requested_date=requested,
            window="today",
        )
        for key in ("competition_id", "status"):
            if filters.get(key):
                rows = [row for row in rows if str(row.get(key)) == str(filters[key])]
        if filters.get("research_grade"):
            rows = [row for row in rows if row.get("research_grade") == filters["research_grade"]]
        if filters.get("data_status"):
            rows = [row for row in rows if row.get("data_status") == filters["data_status"]]
        return {"date": requested.isoformat(), "total": len(rows), "items": rows}

    def matchday_next_36_hours(self, *, now_utc: datetime | None = None) -> dict[str, Any]:
        start, end = next_36_hours_window(now_utc)
        rows = [
            self._project_dashboard_card(row)
            for row in self.repository.dashboard_latest_fixtures()
            if (kickoff := _parse_datetime(row.get("kickoff_utc"))) is not None
            and start <= kickoff < end
        ]
        return {
            "view": "NEXT_36_HOURS",
            "timezone": BEIJING_TZ,
            "now_utc": start.isoformat().replace("+00:00", "Z"),
            "window_end_utc": end.isoformat().replace("+00:00", "Z"),
            "total": len(rows),
            "items": rows,
        }

    def matchday_coverage(self, *, target_date: str | None = None) -> dict[str, Any]:
        requested = (
            date.fromisoformat(target_date)
            if target_date
            else default_football_day(datetime.now(UTC))
        )
        window = self.day_policy.window_for_date(requested)
        rows = self.matchday(target_date=requested.isoformat())["items"]
        count = len(cast(list[Any], rows))
        return {
            "local_date": requested,
            "start_local": window.start_local,
            "end_local": window.end_local,
            "start_utc": window.start_utc,
            "end_utc": window.end_utc,
            "authoritative_count": count,
            "discovered_count": count,
            "eligible_count": count,
            "card_count": count,
            "read_model_count": count,
            "displayed_count": count,
            "missing_count": 0,
            "reason_distribution": {},
            "coverage_status": "READY" if count else "NOT_READY",
        }

    def fixture(self, fixture_id: str, timezone: str) -> dict[str, Any] | None:
        row = self.repository.dashboard_fixture(fixture_id)
        if row is None:
            return None
        summary = self._fixture_summary(row, timezone)
        analysis = self.repository.analysis_card_projection(fixture_id)
        return {
            **summary,
            "venue": row.get("venue"),
            "bookmaker_count": int(row.get("bookmaker_count") or 0),
            "market_coverage": dict(row.get("market_coverage") or {}),
            "forward_decision": str(row.get("decision_status") or "NOT_READY"),
            "provenance": dict(row.get("provenance") or {}),
            "risk_notes": list(row.get("risk_notes") or []),
            "primary_market": row.get("primary_market"),
            "primary_selection": row.get("primary_selection"),
            "primary_line": row.get("primary_line"),
            "primary_executable_odds": row.get("primary_executable_odds"),
            "primary_hong_kong_odds": row.get("primary_hong_kong_odds"),
            "primary_model_fair_odds": row.get("primary_model_fair_odds"),
            "primary_risk_adjusted_ev": row.get("primary_risk_adjusted_ev"),
            "research_grade": row.get("research_grade"),
            "ah_ladder": list(row.get("ah_ladder") or []),
            "ou_ladder": list(row.get("ou_ladder") or []),
            "all_market_ranking": list(row.get("all_market_ranking") or []),
            "one_x_two_ranking": list(row.get("one_x_two_ranking") or []),
            "btts_ranking": list(row.get("btts_ranking") or []),
            "secondary_market_direction": row.get("secondary_market_direction"),
            "source_snapshot_id": dict(row.get("provenance") or {}).get("snapshot_id"),
            "source_captured_at": _parse_datetime(row.get("captured_at")),
            "source_phase": row.get("phase"),
            "valuation_generated_at": _parse_datetime(row.get("valuation_generated_at")),
            "projector_generated_at": _parse_datetime(row.get("projector_generated_at")),
            "temporal_status": row.get("temporal_status"),
            "integrity_status": row.get("integrity_status"),
            "analysis_card": analysis
            if analysis is not None
            else self._system_degraded_card(fixture_id, "ANALYSIS_PROJECTION_NOT_READY"),
        }

    def research_card(self, fixture_id: str) -> dict[str, Any] | None:
        return self.public_analysis_card_bounded(fixture_id)

    def public_analysis_card_bounded(
        self,
        fixture_id: str,
        *,
        evaluation_time: datetime | None = None,
        use_frozen_canary: bool = False,
    ) -> dict[str, Any] | None:
        del evaluation_time, use_frozen_canary
        if self.repository.dashboard_fixture(fixture_id) is None:
            return None
        return self.repository.analysis_card_projection(fixture_id) or self._system_degraded_card(
            fixture_id, "ANALYSIS_PROJECTION_NOT_READY"
        )

    def odds_timeline(self, fixture_id: str) -> list[dict[str, Any]]:
        card = self.public_analysis_card_bounded(fixture_id)
        return list(card.get("odds_timeline") or []) if card else []

    def market_ranking(self, fixture_id: str) -> list[dict[str, Any]]:
        card = self.public_analysis_card_bounded(fixture_id)
        return list(card.get("all_market_ranking") or card.get("markets") or []) if card else []

    def integrity(self, fixture_id: str) -> dict[str, Any] | None:
        card = self.public_analysis_card_bounded(fixture_id)
        return (
            None
            if card is None
            else dict(card.get("integrity") or {"integrity_status": "UNKNOWN"})
        )

    def market_probabilities(self, fixture_id: str) -> dict[str, Any]:
        card = self.public_analysis_card_bounded(fixture_id)
        probabilities = dict(card.get("market_probabilities") or {}) if card else {}
        projection = dict(card.get("read_model_projection") or {}) if card else {}
        return {
            "probability_type": "market_fair_probability",
            "probabilities": probabilities,
            "source": "read_model_checkpoint",
            "as_of_time": _parse_datetime(projection.get("last_projected_at")),
            "quality": "READY" if probabilities else "NOT_READY",
        }

    def model_probabilities(self, fixture_id: str) -> dict[str, Any]:
        card = self.public_analysis_card_bounded(fixture_id)
        probabilities = dict(card.get("model_probabilities") or {}) if card else {}
        projection = dict(card.get("read_model_projection") or {}) if card else {}
        return {
            "probability_type": "independent_model_probability",
            "probabilities": probabilities,
            "source": "read_model_checkpoint",
            "as_of_time": _parse_datetime(projection.get("last_projected_at")),
            "quality": "READY" if probabilities else "NOT_READY",
            "calibrated": False,
        }

    def data_health(self) -> dict[str, Any]:
        payload = self.repository.dashboard_data_health()
        if payload is None:
            return {
                "stale_data_count": 0,
                "provider_status": "SYSTEM_DEGRADED",
                "forward_cycle_age_seconds": None,
                "gate4_progress": {
                    "status": "SYSTEM_DEGRADED",
                    "reason": "DATA_HEALTH_PROJECTION_NOT_READY",
                },
                "generated_at": datetime.now(UTC),
            }
        return {
            "stale_data_count": int(payload.get("stale_data_count") or 0),
            "provider_status": str(payload.get("provider_status") or "NOT_READY"),
            "forward_cycle_age_seconds": payload.get("forward_cycle_age_seconds"),
            "gate4_progress": dict(payload.get("gate4_progress") or {}),
            "generated_at": _parse_datetime(payload.get("generated_at")) or datetime.now(UTC),
        }

    def provider_status(self) -> dict[str, Any]:
        payload = self.repository.dashboard_provider()
        if payload is None:
            return {
                "provider": "api_football",
                "status": "SYSTEM_DEGRADED",
                "remaining_quota": None,
                "credential_status": "UNKNOWN",
                "last_request_status": None,
                "blockers": ["PROVIDER_STATUS_PROJECTION_NOT_READY"],
                "quota_policy": api_football_quota_policy(None),
            }
        quota = parse_int(payload.get("remaining_quota"))
        return {
            "provider": str(payload.get("provider") or "api_football"),
            "status": str(payload.get("status") or "NOT_READY"),
            "remaining_quota": quota,
            "credential_status": str(payload.get("credential_status") or "UNKNOWN"),
            "last_request_status": payload.get("last_request_status"),
            "blockers": list(payload.get("blockers") or []),
            "quota_policy": api_football_quota_policy(quota),
        }

    def forward_status(self) -> dict[str, Any]:
        payload = self.repository.dashboard_forward_status()
        return {
            "status": str((payload or {}).get("status") or "SYSTEM_DEGRADED"),
            "locks": int((payload or {}).get("locks") or 0),
            "market_comparable": int((payload or {}).get("market_comparable") or 0),
            "current_settled_n": int((payload or {}).get("current_settled_n") or 0),
            "target_n": int((payload or {}).get("target_n") or 50),
        }

    def operations_items(self, name: str) -> list[dict[str, Any]]:
        return self.repository.operation_payloads(name)

    def competition_operations_profile(self, competition_id: str) -> dict[str, Any] | None:
        try:
            entry = CompetitionRegistry().entries().get(competition_id)
        except CompetitionRegistryError as exc:
            raise SystemDegradedError("COMPETITION_REGISTRY_UNAVAILABLE") from exc
        return None if entry is None else deepcopy(entry.profile_payload)

    def leagues(self) -> list[dict[str, Any]]:
        try:
            readiness = cast(dict[str, Any], run_top_five_audit()["readiness"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SystemDegradedError("LEAGUE_READ_MODEL_INVALID") from exc
        output = []
        for competition_id, payload in sorted(readiness.items()):
            audit = payload["audit"]
            seasons = list(audit["seasons"])
            output.append(
                {
                    "competition_id": competition_id,
                    "name": audit["name"],
                    "country": audit["country"],
                    "results_status": audit["market_state"]["RESULTS_READY"],
                    "market_status": {
                        "1X2": audit["market_state"]["MARKET_1X2_READY"],
                        "AH": audit["market_state"]["MARKET_AH_READY"],
                        "OU": audit["market_state"]["MARKET_OU_READY"],
                        "TIMELINE": audit["market_state"]["TIMELINE_READY"],
                    },
                    "latest_season": sorted(seasons)[-1] if seasons else None,
                    "blocker": (
                        "MANUAL_REVIEW_REQUIRED"
                        if payload["rollover"]["status"] == "MANUAL_REVIEW_REQUIRED"
                        else None
                    ),
                }
            )
        return output

    def league_readiness(self, competition_id: str) -> dict[str, Any] | None:
        try:
            readiness = cast(dict[str, Any], run_top_five_audit()["readiness"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SystemDegradedError("LEAGUE_READ_MODEL_INVALID") from exc
        payload = readiness.get(competition_id)
        if payload is None:
            return None
        return {
            "competition_id": competition_id,
            "audit": payload["audit"],
            "rollover": payload["rollover"],
            "checklist": payload["checklist"],
            "model_scope_policy": payload["model_scope_policy"],
        }

    def world_cup_readiness(self) -> dict[str, Any]:
        return {
            "competition_id": "world_cup_2026",
            "profile_version": "v1",
            "fixture_coverage_count": len(self.repository.dashboard_latest_fixtures()),
            "data_coverage": {"status": "READ_MODEL_CHECKPOINT_ONLY"},
            "phase_count_per_fixture": 0,
            "gate_status": "PROVISIONAL_FORWARD_HOLDOUT_PENDING",
            "strategy_version": "NOT_AVAILABLE_GATE4",
            "production_deployment": "DISABLED",
            "shadow_runtime": "DISABLED_PENDING_GATE4",
            "blockers": [],
        }

    def league_onboarding(self) -> list[dict[str, Any]]:
        rows = []
        for league in self.leagues():
            readiness = self.league_readiness(str(league["competition_id"]))
            if readiness is not None:
                rows.append({"request_id": "", **readiness})
        return rows

    def operations_cycles(self) -> list[dict[str, Any]]:
        return [item["payload"] for item in self.operations_items("cycles")]

    def operations_latest(self) -> dict[str, Any]:
        rows = self.operations_cycles()
        return rows[-1] if rows else {"status": "NOT_READY"}

    def releases_readiness(self) -> dict[str, Any]:
        return {
            "approval_status": "NOT_READY",
            "production_release": "DISABLED",
            "dependency_blocker": "RELEASE_READ_MODEL_UNAVAILABLE",
        }

    def retention_status(self) -> dict[str, Any]:
        return {"status": "DRY_RUN_ONLY", "policy": {}}

    def shadow_strategy_status(self) -> dict[str, Any]:
        return {
            "status": "NOT_READY",
            "strategy_version": "W2_SHADOW_STRATEGY_V1",
            "gate4_status": "PROVISIONAL_FORWARD_HOLDOUT_PENDING",
            "gate5_status": "NOT_READY",
            "formal_recommendation": False,
            "candidate": False,
            "decisions": 0,
            "locks": 0,
            "latest_run_id": None,
        }

    def shadow_strategy_locks(self) -> list[dict[str, Any]]:
        return [item["payload"] for item in self.operations_items("shadow-strategy-locks")]

    def shadow_strategy_evaluations(self) -> list[dict[str, Any]]:
        return [item["payload"] for item in self.operations_items("shadow-strategy-evaluations")]

    def shadow_strategy_replay(self) -> dict[str, Any]:
        rows = self.operations_items("shadow-strategy-replay")
        return rows[-1]["payload"] if rows else {"status": "NOT_READY"}

    def gate5_preflight(self) -> dict[str, Any]:
        return {"gate5_result": "NO_RUN", "production_release": "DISABLED"}

    def w1_w2_shadow_comparison(self) -> dict[str, Any]:
        return {"status": "NOT_READY"}

    def _fixture_summary(self, item: dict[str, Any], timezone: str) -> dict[str, Any]:
        kickoff = _parse_datetime(item.get("kickoff_utc"))
        if kickoff is None:
            raise SystemDegradedError("DASHBOARD_FIXTURE_KICKOFF_INVALID")
        return {
            "fixture_id": str(item.get("fixture_id") or ""),
            "competition_id": str(item.get("competition_id") or ""),
            "competition_name": str(item.get("competition_name") or ""),
            "kickoff_utc": kickoff,
            "kickoff_beijing": kickoff.astimezone(self.day_policy.timezone).isoformat(),
            "operational_date_beijing": self.date_resolver.operational_date(
                kickoff
            ).isoformat(),
            "kickoff_display": kickoff.astimezone(self.day_policy.timezone).strftime(
                "%Y-%m-%d %H:%M"
            ),
            "status": normalize_match_status(item.get("status")),
            "home_team_id": str(item.get("home_team_id") or ""),
            "home_team_name": item.get("home_team_name"),
            "away_team_id": str(item.get("away_team_id") or ""),
            "away_team_name": item.get("away_team_name"),
            "lifecycle_state": str(item.get("lifecycle_state") or "PREMATCH"),
            "data_state": str(item.get("data_status") or "NOT_READY"),
            "published_grade": item.get("research_grade"),
            "primary_market": item.get("primary_market"),
            "primary_line": item.get("primary_line"),
            "primary_odds": item.get("primary_executable_odds"),
            "last_captured": _parse_datetime(item.get("captured_at")),
        }
