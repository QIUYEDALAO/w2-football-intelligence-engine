from __future__ import annotations

import json
import math
import os
from contextlib import suppress
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from time import monotonic
from typing import Any, cast
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from w2.competitions.registry import CompetitionRegistry
from w2.config import Environment, get_settings
from w2.dashboard.performance import dashboard_performance
from w2.dashboard.readiness import (
    build_analysis_readiness,
    build_watch_recommendation,
)
from w2.dashboard.recommendations import build_recommendation
from w2.dashboard.results import (
    normalize_match_status,
    result_from_dashboard_row,
    result_from_provider_fixture,
)
from w2.dashboard.scorelines import scoreline_picks_from_card
from w2.dashboard.validation import validate_recommendation
from w2.features.engine import FeatureInputs, build_feature_set
from w2.features.framework import FeatureContext
from w2.features.live_factors import TeamXgSnapshot
from w2.features.market_factors import BookmakerQuote
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.shadow_strategy_models import (
    ShadowStrategyEvaluationModel,
    ShadowStrategyLockModel,
    ShadowStrategyRunModel,
)
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.markets.movement import MarketSnapshot
from w2.matchday.coverage import MatchdayCoverageReconciler
from w2.matchday.timezone import (
    BEIJING_TZ,
    BeijingOperationalDayPolicy,
    FixtureOperationalDateResolver,
    next_36_hours_window,
)
from w2.operations.leagues import run_top_five_audit
from w2.operations.tournament import (
    build_operations_plan,
    load_stage5b_world_cup_fixtures,
    load_tournament_profile,
    readiness_report,
)
from w2.providers.quota import api_football_quota_policy, parse_int
from w2.pricing.shadow import build_pricing_shadow
from w2.strategy.analysis_recommendation import (
    DISCLAIMER,
    AnalysisBuildInputs,
    AnalysisMarket,
    HalfGoalModelInput,
    MarketAnalysis,
    MultiMarketAnalysisCard,
    build_multi_market_analysis,
)
from w2.strategy.bookmaker_intent import infer_bookmaker_intent
from w2.strategy.score_scenarios import Direction

ROOT = Path(__file__).resolve().parents[3]
REPORTS = ROOT / "reports"
RUNTIME = ROOT / "runtime"
WORLD_CUP_PROFILE = ROOT / "config/competitions/world_cup_2026.v1.json"
WORLD_CUP_FIXTURES = RUNTIME / "stage5b/processed/national_fixtures_cleaned.json"
STAGING_DASHBOARD_SEED = RUNTIME / "dashboard/staging_seed_dashboard.json"

MARKET_LABELS_CN = {
    "ASIAN_HANDICAP": "让球",
    "TOTALS": "大小球",
    "FIRST_HALF_GOALS": "半场进球",
    "SCORE": "比分",
}
INTENT_LABELS_CN = {
    "HOME_LEAN": "偏主队",
    "AWAY_LEAN": "偏客队",
    "OVER_LEAN": "偏大球",
    "UNDER_LEAN": "偏小球",
    "INSUFFICIENT_DATA": "数据不足",
    "CONFLICTED": "分歧较大",
    "LEAKAGE_BLOCKED": "防泄漏拦截",
}


def load_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def future_refresh_db_repository() -> FutureRefreshDbRepository | None:
    try:
        return FutureRefreshDbRepository()
    except Exception:
        return None


def parse_provider_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def release_env(name: str, default: str = "UNKNOWN") -> str:
    value = os.getenv(name)
    return value if value else default


class ReadModelRepository:
    def dashboard_checkpoints(self, prefix: str = "dashboard:") -> list[dict[str, Any]]:
        try:
            engine = create_engine()
            with Session(engine) as session:
                rows = session.scalars(
                    select(ReadModelCheckpointModel)
                    .where(ReadModelCheckpointModel.checkpoint_key.like(f"{prefix}%"))
                    .order_by(ReadModelCheckpointModel.checkpoint_key)
                ).all()
            return [
                {
                    "checkpoint_key": row.checkpoint_key,
                    "source_hash": row.source_hash,
                    "created_at": row.created_at,
                    "payload": row.payload,
                }
                for row in rows
            ]
        except Exception:
            return []

    def dashboard_checkpoint_payload(self, key: str) -> dict[str, Any] | None:
        for row in self.dashboard_checkpoints(key):
            if row["checkpoint_key"] == key:
                return cast(dict[str, Any], row["payload"])
        return None

    def dashboard_latest_fixtures(self) -> list[dict[str, Any]]:
        return [
            cast(dict[str, Any], row["payload"])
            for row in self.dashboard_checkpoints("dashboard:fixture_latest:")
        ]

    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        return self.dashboard_checkpoint_payload(f"dashboard:fixture_latest:{fixture_id}")

    def dashboard_provider(self) -> dict[str, Any] | None:
        return self.dashboard_checkpoint_payload("dashboard:provider_status")

    def dashboard_data_health(self) -> dict[str, Any] | None:
        return self.dashboard_checkpoint_payload("dashboard:data_health")

    def dashboard_forward_status(self) -> dict[str, Any] | None:
        return self.dashboard_checkpoint_payload("dashboard:forward_status")

    def stage10c_matchday_cards(self) -> list[dict[str, Any]]:
        payload = self.dashboard_checkpoint_payload("dashboard:stage10c_matchday_cards")
        if payload is None:
            return []
        items = payload.get("items", [])
        return cast(list[dict[str, Any]], items) if isinstance(items, list) else []

    def matchday_cards(self) -> list[dict[str, Any]]:
        stage10c_cards = self.stage10c_matchday_cards()
        if stage10c_cards:
            return stage10c_cards
        report = load_json(REPORTS / "W2_STAGE10C_ALL_MARKET_CARDS.json", {})
        items = report.get("items", []) if isinstance(report, dict) else []
        if isinstance(items, list) and items:
            return cast(list[dict[str, Any]], items)
        dashboard = self.dashboard_latest_fixtures()
        return [
            {
                "fixture": item,
                "card": {
                    "fixture_id": item["fixture_id"],
                    "action": item.get("decision_status", "SKIP"),
                    "published_grade": item.get("research_grade", "D"),
                    "primary_market_direction": {
                        "market": item.get("primary_market"),
                        "selection": item.get("primary_selection"),
                        "line": item.get("primary_line"),
                        "executable_decimal_odds": item.get("primary_executable_odds"),
                        "risk_adjusted_ev": item.get("primary_risk_adjusted_ev"),
                    },
                    "secondary_market_direction": None,
                    "formal_recommendation": False,
                    "candidate": False,
                    "temporal_status": item.get("temporal_status", "PREMATCH_LOCKED"),
                },
                "market_ranking": item.get("all_market_ranking", []),
                "temporal": {
                    "source_snapshot_id": item.get("provenance", {}).get("snapshot_id"),
                    "source_captured_at": item.get("captured_at"),
                    "source_phase": item.get("phase"),
                    "kickoff_utc": item.get("kickoff_utc"),
                    "valuation_generated_at": item.get(
                        "valuation_generated_at",
                        item.get("captured_at"),
                    ),
                    "projector_generated_at": item.get(
                        "projector_generated_at",
                        item.get("captured_at"),
                    ),
                    "temporal_status": item.get("temporal_status", "PREMATCH_LOCKED"),
                    "locked_before_kickoff": True,
                    "recomputed_after_kickoff": False,
                },
                "integrity": {"integrity_status": item.get("integrity_status", "UNKNOWN")},
            }
            for item in dashboard
        ]

    def stage7e_usage(self) -> dict[str, Any]:
        return cast(dict[str, Any], load_json(REPORTS / "W2_STAGE7E_API_USAGE.json", {}))

    def stage7e_first_cycle(self) -> dict[str, Any]:
        return cast(dict[str, Any], load_json(REPORTS / "W2_STAGE7E_FIRST_LIVE_CYCLE.json", {}))

    def stage7e_scheduler(self) -> dict[str, Any]:
        return cast(dict[str, Any], load_json(REPORTS / "W2_STAGE7E_SCHEDULER_AUDIT.json", {}))

    def stage7e_result(self) -> str:
        path = REPORTS / "W2_STAGE7E_RESULT.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def stage8_summary(self) -> dict[str, Any]:
        return cast(dict[str, Any], load_json(REPORTS / "W2_STAGE8_REPLAY_SUMMARY.json", {}))

    def fixture_payloads(self) -> list[dict[str, Any]]:
        fixtures: dict[str, dict[str, Any]] = {}
        for item in self.dashboard_latest_fixtures():
            fixture_id = str(item.get("fixture_id"))
            if fixture_id and fixture_id != "None":
                fixtures[fixture_id] = self._dashboard_fixture_to_provider_payload(item)
        db_repository = future_refresh_db_repository()
        if db_repository is not None:
            try:
                for item in db_repository.fixture_payloads():
                    fixture_id = str(item.get("fixture", {}).get("id"))
                    if fixture_id and fixture_id != "None":
                        fixtures[fixture_id] = item
            except Exception:
                fixtures = {}
        if not fixtures and get_settings().environment in {Environment.LOCAL, Environment.TEST}:
            fixtures["stage10a-contract-fixture"] = self._contract_fixture_payload()
        return sorted(fixtures.values(), key=lambda item: item.get("fixture", {}).get("date", ""))

    def forward_locks(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], load_json(RUNTIME / "stage7e/prediction_locks.json", []))

    def market_snapshots(self) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        db_repository = future_refresh_db_repository()
        if db_repository is not None:
            try:
                snapshots.extend(db_repository.market_snapshots())
            except Exception:
                snapshots = []
        snapshots.extend(
            cast(list[dict[str, Any]], load_json(RUNTIME / "stage7e/market_snapshots.json", []))
        )
        return snapshots

    def future_market_observations(self) -> list[dict[str, Any]]:
        db_repository = future_refresh_db_repository()
        if db_repository is not None:
            try:
                rows = db_repository.latest_market_observations()
                if rows:
                    return rows
            except Exception:
                rows = []
        return []

    def future_market_observations_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> list[dict[str, Any]]:
        db_repository = future_refresh_db_repository()
        if db_repository is not None:
            try:
                reader = getattr(db_repository, "latest_market_observations_for_fixtures", None)
                if callable(reader):
                    return cast(list[dict[str, Any]], reader(fixture_ids))
            except Exception:
                return []
        return []

    def result_events(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], load_json(RUNTIME / "stage7e/result_events.json", []))

    def staging_seed_dashboard(self) -> dict[str, Any] | None:
        payload = load_json(STAGING_DASHBOARD_SEED, None)
        return cast(dict[str, Any], payload) if isinstance(payload, dict) else None

    def release_counts(self) -> dict[str, int]:
        return {
            "read_model_fixture_count": len(self.dashboard_latest_fixtures()),
            "matchday_card_count": len(self.matchday_cards()),
            "future_fixture_count": len(self.fixture_payloads()),
            "result_event_count": len(self.result_events()),
        }

    def world_cup_profile(self) -> dict[str, Any]:
        return cast(dict[str, Any], load_json(WORLD_CUP_PROFILE, {}))

    def world_cup_readiness(self) -> dict[str, Any]:
        existing = load_json(REPORTS / "W2_STAGE13A_READINESS.json", {})
        if existing:
            return cast(dict[str, Any], existing)
        try:
            profile = load_tournament_profile(WORLD_CUP_PROFILE)
            fixtures = load_stage5b_world_cup_fixtures(WORLD_CUP_FIXTURES)
            plan = build_operations_plan(profile, fixtures)
            return readiness_report(profile, plan)
        except Exception:
            profile_payload = self.world_cup_profile()
            return {
                "competition_id": profile_payload.get("competition_id", "world_cup_2026"),
                "profile_version": profile_payload.get("version", "v1"),
                "fixture_coverage_count": 0,
                "data_coverage": {"status": "EMPTY_READ_MODEL"},
                "phase_count_per_fixture": 0,
                "gate_status": "PROVISIONAL_FORWARD_HOLDOUT_PENDING",
                "strategy_version": "NOT_AVAILABLE_GATE4",
                "production_deployment": "DISABLED",
                "shadow_runtime": "DISABLED_PENDING_GATE4",
                "blockers": ["WORLD_CUP_FIXTURE_READ_MODEL_EMPTY"],
            }

    def league_readiness(self) -> dict[str, Any]:
        existing = load_json(REPORTS / "W2_STAGE14A_READINESS.json", {})
        if existing:
            return cast(dict[str, Any], existing)
        try:
            return cast(dict[str, Any], run_top_five_audit()["readiness"])
        except Exception:
            return {}

    def operations_report(self) -> dict[str, Any]:
        return cast(dict[str, Any], load_json(REPORTS / "W2_STAGE15A_OPERATIONS.json", {}))

    def release_readiness(self) -> dict[str, Any]:
        return cast(dict[str, Any], load_json(REPORTS / "W2_STAGE15A_RELEASE_READINESS.json", {}))

    def shadow_strategy_replay(self) -> dict[str, Any]:
        try:
            engine = create_engine()
            with Session(engine) as session:
                latest = session.scalars(
                    select(ShadowStrategyRunModel).order_by(
                        ShadowStrategyRunModel.started_at.desc()
                    )
                ).first()
            if latest is None:
                return {
                    "run_state": "NO_RUN",
                    "strategy_version": "W2_SHADOW_STRATEGY_V1",
                    "decisions": [],
                    "locks": [],
                }
            return {
                "run_state": "COMPLETED_WITH_RESULTS"
                if latest.status == "COMPLETED"
                else latest.status,
                "run_id": latest.run_id,
                "strategy_version": latest.strategy_version,
                "manifest_sha256": latest.manifest_sha256,
                "started_at": latest.started_at,
                "completed_at": latest.completed_at,
                "payload": latest.payload,
                "decisions": latest.payload.get("decisions", []),
                "locks": self.shadow_strategy_locks(),
            }
        except Exception:
            return {
                "run_state": "ERROR",
                "strategy_version": "W2_SHADOW_STRATEGY_V1",
                "decisions": [],
                "locks": [],
            }

    def shadow_strategy_status(self) -> dict[str, Any]:
        replay = self.shadow_strategy_replay()
        decisions = replay.get("decisions", [])
        locks = self.shadow_strategy_locks()
        decisions_count = len(decisions) if isinstance(decisions, list) else 0
        locks_count = len(locks)
        run_state = str(replay.get("run_state", "NO_RUN"))
        return {
            "status": run_state
            if run_state != "COMPLETED_WITH_RESULTS"
            else "SHADOW_READY",
            "strategy_version": str(replay.get("strategy_version", "W2_SHADOW_STRATEGY_V1")),
            "gate4_status": "PROVISIONAL_FORWARD_HOLDOUT_PENDING",
            "gate5_status": "PROVISIONAL_BLOCKED_GATE4",
            "formal_recommendation": False,
            "candidate": False,
            "decisions": decisions_count,
            "locks": locks_count,
            "latest_run_id": replay.get("run_id") if replay else None,
        }

    def shadow_strategy_locks(self) -> list[dict[str, Any]]:
        try:
            engine = create_engine()
            with Session(engine) as session:
                rows = session.scalars(
                    select(ShadowStrategyLockModel).order_by(
                        ShadowStrategyLockModel.locked_at.desc()
                    )
                ).all()
            return [
                {
                    "fixture_id": row.fixture_id,
                    "phase": row.phase,
                    "strategy_version": row.strategy_version,
                    "decision_hash": row.decision_hash,
                    "locked_at": row.locked_at,
                    "payload": row.payload,
                }
                for row in rows
            ]
        except Exception:
            return []

    def shadow_strategy_evaluations(self) -> list[dict[str, Any]]:
        try:
            engine = create_engine()
            with Session(engine) as session:
                rows = session.scalars(
                    select(ShadowStrategyEvaluationModel).order_by(
                        ShadowStrategyEvaluationModel.evaluated_at.desc()
                    )
                ).all()
            if rows:
                return [
                    {
                        "fixture_id": row.fixture_id,
                        "phase": row.phase,
                        "strategy_version": row.strategy_version,
                        "evaluated_at": row.evaluated_at,
                        **row.payload,
                    }
                    for row in rows
                ]
        except Exception:
            return []
        replay = self.shadow_strategy_replay()
        decisions = replay.get("decisions", [])
        if not isinstance(decisions, list):
            return []
        return [
            {
                "fixture_id": item.get("fixture_id"),
                "phase": item.get("phase"),
                "public_decision": item.get("public_decision"),
                "published_grade": item.get("published_grade"),
                "primary": item.get("primary"),
                "secondary": item.get("secondary"),
                "formal_recommendation": False,
                "candidate": False,
            }
            for item in decisions
            if isinstance(item, dict)
        ]

    def gate5_preflight(self) -> dict[str, Any]:
        return cast(dict[str, Any], load_json(REPORTS / "W2_GATE5_PREFLIGHT.json", {}))

    def w1_w2_shadow_comparison(self) -> dict[str, Any]:
        return cast(dict[str, Any], load_json(REPORTS / "W2_STAGE12B_W1_W2_COMPARISON.json", {}))

    def _dashboard_fixture_to_provider_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "fixture": {
                "id": item["fixture_id"],
                "date": item["kickoff_utc"],
                "status": {"short": item["status"]},
                "venue": {"name": item.get("venue")},
            },
            "league": {
                "id": item["competition_id"],
                "name": item["competition_name"],
                "round": item.get("stage"),
            },
            "teams": {
                "home": {"id": item["home_team_id"], "name": item.get("home_team_name")},
                "away": {"id": item["away_team_id"], "name": item.get("away_team_name")},
            },
            "_dashboard": item,
        }

    def _contract_fixture_payload(self) -> dict[str, Any]:
        return {
            "fixture": {
                "id": "stage10a-contract-fixture",
                "date": "2026-06-22T17:00:00Z",
                "status": {"short": "NS"},
                "venue": {"name": "Contract Venue"},
            },
            "league": {"id": "contract", "name": "Contract Competition"},
            "teams": {
                "home": {"id": "home", "name": "Home"},
                "away": {"id": "away", "name": "Away"},
            },
        }


class ReadModelService:
    def __init__(self, repository: ReadModelRepository | None = None) -> None:
        self.repository = repository or ReadModelRepository()
        self.day_policy = BeijingOperationalDayPolicy()
        self.date_resolver = FixtureOperationalDateResolver()
        self._fixture_payloads_cache: list[dict[str, Any]] | None = None
        self._fixture_payload_index_cache: dict[str, dict[str, Any]] | None = None
        self._future_market_observations_cache: list[dict[str, Any]] | None = None
        self._observations_by_fixture_cache: dict[str, list[dict[str, Any]]] | None = None
        self._future_refresh_repository_cache: FutureRefreshDbRepository | None = None
        self._team_xg_snapshots_by_fixture_cache: dict[str, list[dict[str, Any]]] = {}
        self._team_xg_matches_cache: list[dict[str, Any]] | None = None
        self._raw_payloads_by_endpoint_cache: dict[str, list[dict[str, Any]]] = {}
        self._dashboard_response_cache: dict[
            tuple[str, str, str, bool], tuple[float, dict[str, Any]]
        ] = {}

    def _reset_read_caches(self) -> None:
        self._fixture_payloads_cache = None
        self._fixture_payload_index_cache = None
        self._future_market_observations_cache = None
        self._observations_by_fixture_cache = None
        self._team_xg_snapshots_by_fixture_cache = {}
        self._team_xg_matches_cache = None
        self._raw_payloads_by_endpoint_cache = {}

    def _future_refresh_repository(self) -> FutureRefreshDbRepository | None:
        if self._future_refresh_repository_cache is None:
            self._future_refresh_repository_cache = future_refresh_db_repository()
        return self._future_refresh_repository_cache

    def _cached_fixture_payloads(self) -> list[dict[str, Any]]:
        if self._fixture_payloads_cache is None:
            fixture_reader = getattr(self.repository, "fixture_payloads", None)
            self._fixture_payloads_cache = (
                fixture_reader() if callable(fixture_reader) else []
            )
        return self._fixture_payloads_cache

    def _fixture_payload_by_id(self, fixture_id: str) -> dict[str, Any] | None:
        if self._fixture_payload_index_cache is None:
            self._fixture_payload_index_cache = {}
            for item in self._cached_fixture_payloads():
                key = str(item.get("fixture", {}).get("id") or "")
                if key:
                    self._fixture_payload_index_cache[key] = item
        return self._fixture_payload_index_cache.get(fixture_id)

    def _cached_future_market_observations(self) -> list[dict[str, Any]]:
        if self._future_market_observations_cache is None:
            observation_reader = getattr(self.repository, "future_market_observations", None)
            self._future_market_observations_cache = (
                observation_reader() if callable(observation_reader) else []
            )
        return self._future_market_observations_cache

    def _observations_for_fixture(self, fixture_id: str) -> list[dict[str, Any]]:
        if self._observations_by_fixture_cache is None:
            grouped: dict[str, list[dict[str, Any]]] = {}
            for row in self._cached_future_market_observations():
                key = str(row.get("fixture_id") or "")
                if key:
                    grouped.setdefault(key, []).append(row)
            self._observations_by_fixture_cache = grouped
        return self._observations_by_fixture_cache.get(fixture_id, [])

    def _prime_observations_for_rows(self, rows: list[dict[str, Any]]) -> None:
        reader = getattr(self.repository, "future_market_observations_for_fixtures", None)
        if not callable(reader):
            return
        fixture_ids = [str(row.get("fixture_id") or "") for row in rows]
        self._future_market_observations_cache = reader(fixture_ids)
        self._observations_by_fixture_cache = None

    def version(self) -> dict[str, Any]:
        generated_at = datetime.now(UTC)
        settings = get_settings()
        database_ready = True
        try:
            counts = self.repository.release_counts()
        except Exception:
            database_ready = False
            counts = {
                "read_model_fixture_count": 0,
                "matchday_card_count": 0,
                "future_fixture_count": 0,
                "result_event_count": 0,
            }
        data_profile = os.getenv("W2_DATA_PROFILE")
        data_source = os.getenv("W2_DATA_SOURCE")
        if not data_profile:
            data_profile = (
                "real-db"
                if counts["matchday_card_count"] or counts["read_model_fixture_count"]
                else "empty"
            )
        if not data_source:
            data_source = "read-model-db" if data_profile == "real-db" else "empty"
        return {
            "service": "w2-football-intelligence-engine",
            "environment": settings.environment.value,
            "api_git_sha": release_env("W2_GIT_SHA"),
            "api_build_time": os.getenv("W2_BUILD_TIME"),
            "release_id": os.getenv("W2_RELEASE_ID") or release_env("W2_GIT_SHA"),
            "data_profile": data_profile,
            "data_source": data_source,
            "database_ready": database_ready,
            "read_model_fixture_count": counts["read_model_fixture_count"],
            "matchday_card_count": counts["matchday_card_count"],
            "result_event_count": counts["result_event_count"],
            "generated_at": generated_at,
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
            else datetime.now(UTC).astimezone(ZoneInfo(BEIJING_TZ)).date()
        )
        cache_key = (requested_date.isoformat(), window, timezone, include_debug)
        cached = self._dashboard_response_cache.get(cache_key)
        now = monotonic()
        if cached is not None:
            cached_at, cached_payload = cached
            if now - cached_at <= self._dashboard_cache_ttl(window, include_debug):
                return cached_payload

        self._reset_read_caches()
        version = self.version()
        counts = self.repository.release_counts()
        seed = self.repository.staging_seed_dashboard()
        if (
            not counts["read_model_fixture_count"]
            and not counts["matchday_card_count"]
            and seed
        ):
            return self._seed_dashboard_response(
                seed,
                requested_date=requested_date,
                window=window,
                timezone=timezone,
                version=version,
                counts=counts,
                include_debug=include_debug,
            )

        today_rows = self.matchday(target_date=requested_date.isoformat()).get("items", [])
        next36_rows = self.matchday_next_36_hours().get("items", [])
        result_rows = [
            row
            for row in self._all_matchday_rows()
            if str(row.get("status", "")).upper() in {"FT", "AET", "PEN", "FINISHED"}
        ]
        future_rows, future_parse_error_count = self._future_fixture_rows_with_errors()
        future_today_rows = self._filter_rows_for_operational_date(
            future_rows,
            requested_date=requested_date,
        )
        future_next36_rows = self._filter_rows_for_next36(future_rows)
        today_rows = self._dedupe_dashboard_rows(
            [*cast(list[dict[str, Any]], today_rows), *future_today_rows]
        )
        next36_rows = self._dedupe_dashboard_rows(
            [*cast(list[dict[str, Any]], next36_rows), *future_next36_rows]
        )
        selected_rows: list[dict[str, Any]]
        if window == "next36":
            selected_rows = next36_rows
        elif window == "results":
            selected_rows = result_rows
        elif window == "all":
            selected_rows = self._dedupe_dashboard_rows(
                [
                    *today_rows,
                    *next36_rows,
                    *result_rows,
                    *future_rows,
                ]
            )
        else:
            selected_rows = today_rows

        self._prime_observations_for_rows(selected_rows)
        all_cards = [self._dashboard_card_from_matchday(row) for row in selected_rows]
        recommendations = [
            card
            for card in all_cards
            if isinstance(card.get("recommendation"), dict)
            and str(cast(dict[str, Any], card["recommendation"]).get("tier"))
            in {"FORMAL", "CANDIDATE", "ANALYSIS_PICK"}
        ]
        upcoming = [
            card
            for card in all_cards
            if str(card.get("status", "")).upper() != "FINISHED"
        ]
        finished = [
            card
            for card in all_cards
            if str(card.get("status", "")).upper() == "FINISHED"
        ]
        debug = self._dashboard_debug(
            counts=counts,
            requested_date=requested_date,
            selected_rows=selected_rows,
            future_rows=future_rows,
            future_parse_error_count=future_parse_error_count,
            include=include_debug,
        )
        data_profile = str(version["data_profile"])
        if all_cards and data_profile == "empty":
            data_profile = "real-db"
        if not all_cards and data_profile == "real-db":
            data_profile = "empty"
        payload = {
            "generated_at": datetime.now(UTC),
            "date": requested_date.isoformat(),
            "timezone": timezone,
            "window": window,
            "data_profile": data_profile,
            "data_source": version["data_source"],
            "version": {
                "api_git_sha": version["api_git_sha"],
                "release_id": version["release_id"],
            },
            "debug": debug,
            "performance": self._dashboard_performance(all_cards),
            "recommendations": recommendations,
            "upcoming": upcoming,
            "finished": finished,
            "all": all_cards,
        }
        self._dashboard_response_cache[cache_key] = (now, payload)
        return payload

    def _dashboard_cache_ttl(self, window: str, include_debug: bool) -> float:
        if include_debug:
            return 300.0 if window in {"today", "next36"} else 600.0
        return 900.0 if window in {"today", "next36"} else 1800.0

    def dashboard_summary(
        self,
        *,
        target_date: str | None = None,
        window: str = "today",
        timezone: str = BEIJING_TZ,
    ) -> dict[str, Any]:
        payload = self.dashboard(
            target_date=target_date,
            window=window,
            timezone=timezone,
            include_debug=False,
        )
        return {
            "generated_at": payload["generated_at"],
            "date": payload["date"],
            "timezone": payload["timezone"],
            "window": payload["window"],
            "data_profile": payload["data_profile"],
            "data_source": payload["data_source"],
            "version": payload["version"],
            "totals": {
                "recommendations": len(cast(list[Any], payload["recommendations"])),
                "upcoming": len(cast(list[Any], payload["upcoming"])),
                "finished": len(cast(list[Any], payload["finished"])),
                "all": len(cast(list[Any], payload["all"])),
            },
            "performance": payload["performance"],
        }

    def warm_dashboard_cache(self) -> None:
        for window in ("today", "next36", "all"):
            with suppress(Exception):
                self.dashboard(window=window, include_debug=False)
        self._reset_read_caches()

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
        rows = []
        is_dashboard: list[bool] = []
        for item in self.repository.fixture_payloads():
            rows.append(self._fixture_summary(item, timezone))
            is_dashboard.append("_dashboard" in item)
        now = datetime.now(UTC)
        visible = [
            row
            for row, dash in zip(rows, is_dashboard, strict=False)
            if dash or not (row["status"] == "NS" and row["kickoff_utc"] < now)
        ]
        rows = visible
        if date_from:
            rows = [row for row in rows if row["kickoff_utc"] >= date_from.astimezone(UTC)]
        if date_to:
            rows = [row for row in rows if row["kickoff_utc"] <= date_to.astimezone(UTC)]
        if competition_id:
            rows = [row for row in rows if row["competition_id"] == competition_id]
        if status:
            rows = [row for row in rows if row["status"] == status]
        if team_id:
            rows = [
                row
                for row in rows
                if team_id in {row["home_team_id"], row["away_team_id"]}
            ]
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start : start + page_size], total

    def matchday(
        self,
        *,
        target_date: str | None = None,
        competition_id: str | None = None,
        status: str | None = None,
        research_grade: str | None = None,
        data_status: str | None = None,
    ) -> dict[str, Any]:
        requested_date = (
            date.fromisoformat(target_date)
            if target_date
            else datetime.now(UTC).astimezone(ZoneInfo(BEIJING_TZ)).date()
        )
        window = self.day_policy.window_for_date(requested_date)
        cards = self.repository.matchday_cards()
        rows = [self._matchday_item(card) for card in cards]
        rows = [
            row
            for row in rows
            if window.contains(
                datetime.fromisoformat(str(row["kickoff_utc"]).replace("Z", "+00:00"))
            )
        ]
        if competition_id:
            rows = [row for row in rows if row["competition_id"] == competition_id]
        if status:
            rows = [row for row in rows if row["status"] == status]
        if research_grade:
            rows = [row for row in rows if row.get("published_grade") == research_grade]
        if data_status:
            rows = [row for row in rows if row.get("data_health") == data_status]
        return {
            "date": requested_date.isoformat(),
            "timezone": BEIJING_TZ,
            "window_start_beijing": window.start_local.isoformat(),
            "window_end_beijing": window.end_local.isoformat(),
            "window_start_utc": window.start_utc.isoformat().replace("+00:00", "Z"),
            "window_end_utc": window.end_utc.isoformat().replace("+00:00", "Z"),
            "total": len(rows),
            "items": rows,
        }

    def matchday_next_36_hours(self, *, now_utc: datetime | None = None) -> dict[str, Any]:
        start, end = next_36_hours_window(now_utc)
        rows = [self._matchday_item(card) for card in self.repository.matchday_cards()]
        rows = [
            row
            for row in rows
            if start
            <= datetime.fromisoformat(
                str(row["kickoff_utc"]).replace("Z", "+00:00")
            ).astimezone(UTC)
            < end
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
        requested_date = (
            date.fromisoformat(target_date)
            if target_date
            else datetime.now(UTC).astimezone(ZoneInfo(BEIJING_TZ)).date()
        )
        window = self.day_policy.window_for_date(requested_date)
        cards = self.repository.matchday_cards()
        read_model = self.repository.dashboard_latest_fixtures()
        authoritative = [
            {
                "fixture_id": row["fixture_id"],
                "competition": row["competition_name"],
                "kickoff_utc": row["kickoff_utc"],
            }
            for row in read_model
        ]
        return MatchdayCoverageReconciler().reconcile(
            window=window,
            authoritative_fixtures=authoritative,
            cards=cards,
            read_model_fixtures=read_model,
            displayed_fixtures=read_model,
        )

    def research_card(self, fixture_id: str) -> dict[str, Any] | None:
        for card in self.repository.matchday_cards():
            if str(card.get("fixture", {}).get("fixture_id")) == fixture_id:
                return cast(dict[str, Any], card.get("card", {}))
        dashboard_reader = getattr(self.repository, "dashboard_fixture", None)
        dashboard = dashboard_reader(fixture_id) if callable(dashboard_reader) else None
        if dashboard is None:
            return None
        return {
            "fixture_id": fixture_id,
            "action": dashboard.get("decision_status", "SKIP"),
            "published_grade": dashboard.get("research_grade", "D"),
            "primary_market_direction": {
                "market": dashboard.get("primary_market"),
                "selection": dashboard.get("primary_selection"),
                "line": dashboard.get("primary_line"),
                "executable_decimal_odds": dashboard.get("primary_executable_odds"),
                "risk_adjusted_ev": dashboard.get("primary_risk_adjusted_ev"),
            },
            "secondary_market_direction": dashboard.get("secondary_market_direction"),
            "formal_recommendation": False,
            "candidate": False,
        }

    def analysis_card(self, fixture_id: str) -> dict[str, Any] | None:
        for card in self.repository.matchday_cards():
            fixture = card.get("fixture", {})
            if str(fixture.get("fixture_id")) != fixture_id:
                continue
            context = self._analysis_context_from_flat_fixture(fixture)
            embedded = card.get("analysis_card")
            if isinstance(embedded, dict):
                return self._normalize_analysis_card(
                    embedded,
                    fixture_id=fixture_id,
                    fixture_context=context,
                )
            return self._fallback_analysis_card(
                fixture_id=fixture_id,
                market_coverage=dict(fixture.get("market_coverage", {})),
                source="matchday_card_without_analysis_payload",
                fixture_context=context,
            )
        dashboard_reader = getattr(self.repository, "dashboard_fixture", None)
        dashboard = dashboard_reader(fixture_id) if callable(dashboard_reader) else None
        if dashboard is not None:
            context = self._analysis_context_from_flat_fixture(dashboard)
            embedded = dashboard.get("analysis_card")
            if isinstance(embedded, dict):
                return self._normalize_analysis_card(
                    embedded,
                    fixture_id=fixture_id,
                    fixture_context=context,
                )
            return self._fallback_analysis_card(
                fixture_id=fixture_id,
                market_coverage=dict(dashboard.get("market_coverage", {})),
                source="dashboard_without_analysis_payload",
                fixture_context=context,
            )
        item = self._fixture_payload_by_id(fixture_id)
        if item is not None:
            return self._analysis_card_from_provider_payload(fixture_id, item)
        return None

    def _analysis_card_from_provider_payload(
        self,
        fixture_id: str,
        item: dict[str, Any],
    ) -> dict[str, Any]:
        observations = self._observations_for_fixture(fixture_id)
        coverage = {
            "ASIAN_HANDICAP": any(
                row.get("canonical_market") == "ASIAN_HANDICAP" for row in observations
            ),
            "TOTALS": any(row.get("canonical_market") == "TOTALS" for row in observations),
        }
        generated = self._db_analysis_card_from_fixture(item, observations)
        if generated is not None:
            return self._normalize_analysis_card(
                generated,
                fixture_id=fixture_id,
                fixture_context=self._analysis_context_from_provider_fixture(item),
            )
        return self._fallback_analysis_card(
            fixture_id=fixture_id,
            market_coverage=coverage,
            source="future_refresh_without_analysis_payload",
            fixture_context=self._analysis_context_from_provider_fixture(item),
        )

    def _db_analysis_card_from_fixture(
        self,
        item: dict[str, Any],
        observations: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not observations:
            return None
        fixture = item.get("fixture", {}) if isinstance(item.get("fixture"), dict) else {}
        teams = item.get("teams", {}) if isinstance(item.get("teams"), dict) else {}
        home = teams.get("home", {}) if isinstance(teams.get("home"), dict) else {}
        away = teams.get("away", {}) if isinstance(teams.get("away"), dict) else {}
        fixture_id = str(fixture.get("id") or "")
        kickoff = parse_provider_time(fixture.get("date"))
        home_id = str(home.get("id") or "")
        away_id = str(away.get("id") or "")
        if not fixture_id or kickoff is None or not home_id or not away_id:
            return None
        repository = self._future_refresh_repository()
        if repository is None:
            return None
        context = FeatureContext(
            fixture_id=fixture_id,
            competition_id="world_cup_2026",
            home_team_id=home_id,
            away_team_id=away_id,
            kickoff_at=kickoff,
            as_of=min(datetime.now(UTC), kickoff),
            stage_id="group",
        )
        snapshot_reader = getattr(repository, "team_xg_rolling_snapshots", None)
        if fixture_id in self._team_xg_snapshots_by_fixture_cache:
            snapshots = self._team_xg_snapshots_by_fixture_cache[fixture_id]
        else:
            try:
                snapshots = (
                    snapshot_reader(fixture_id=fixture_id) if callable(snapshot_reader) else []
                )
            except SQLAlchemyError:
                snapshots = []
            self._team_xg_snapshots_by_fixture_cache[fixture_id] = snapshots
        home_xg = [
            self._team_xg_feature_snapshot(row, observed_at_cap=context.as_of)
            for row in snapshots
            if str(row.get("team_id")) == home_id
        ]
        away_xg = [
            self._team_xg_feature_snapshot(row, observed_at_cap=context.as_of)
            for row in snapshots
            if str(row.get("team_id")) == away_id
        ]
        mainline_selection = self._mainline_market_selection(observations)
        mainline_observations = [
            row
            for selection in mainline_selection.values()
            for row in cast(list[dict[str, Any]], selection.get("observations", []))
        ]
        feature_observations = mainline_observations or observations
        market_snapshots = self._market_snapshots_from_observations(feature_observations)
        bookmaker_quotes = self._bookmaker_quotes_from_observations(feature_observations)
        if not market_snapshots and not home_xg and not away_xg:
            return None
        registry = CompetitionRegistry()
        coverage = registry.require_enabled("world_cup_2026").coverage_profile
        feature_set = build_feature_set(
            context=context,
            inputs=FeatureInputs(
                market_snapshots=market_snapshots,
                bookmaker_quotes=bookmaker_quotes,
                home_xg=home_xg,
                away_xg=away_xg,
            ),
            registry=registry,
        )
        ah_snapshots = [row for row in market_snapshots if row.market == "ASIAN_HANDICAP"]
        ou_snapshots = [row for row in market_snapshots if row.market == "TOTALS"]
        ah_quotes = [row for row in bookmaker_quotes if row.market == "ASIAN_HANDICAP"]
        ou_quotes = [row for row in bookmaker_quotes if row.market == "TOTALS"]
        ah_intent = infer_bookmaker_intent(
            context=context,
            profile=coverage,
            market_kind="AH",
            snapshots=ah_snapshots,
            quotes=ah_quotes,
        )
        ou_intent = infer_bookmaker_intent(
            context=context,
            profile=coverage,
            market_kind="OU",
            snapshots=ou_snapshots,
            quotes=ou_quotes,
        )
        missing: set[AnalysisMarket] = set()
        if mainline_selection["ASIAN_HANDICAP"]["status"] != "READY":
            missing.add(AnalysisMarket.ASIAN_HANDICAP)
        if mainline_selection["TOTALS"]["status"] != "READY":
            missing.add(AnalysisMarket.TOTALS)
        latest_home_xg = max(home_xg, key=lambda row: row.observed_at, default=None)
        latest_away_xg = max(away_xg, key=lambda row: row.observed_at, default=None)
        half_goals: HalfGoalModelInput | None = None
        score_matrix: dict[tuple[int, int], float] | None = None
        score_direction: Direction | None = None
        if latest_home_xg is None or latest_away_xg is None:
            missing.update({AnalysisMarket.FIRST_HALF_GOALS, AnalysisMarket.SCORE})
        else:
            expected_home = max(
                (latest_home_xg.xg_for + latest_away_xg.xg_against) / 2,
                0.05,
            )
            expected_away = max(
                (latest_away_xg.xg_for + latest_home_xg.xg_against) / 2,
                0.05,
            )
            half_goals = HalfGoalModelInput(
                expected_home_goals=expected_home,
                expected_away_goals=expected_away,
            )
            score_matrix = self._poisson_score_matrix(expected_home, expected_away)
            if expected_home > expected_away + 0.10:
                score_direction = "HOME"
            elif expected_away > expected_home + 0.10:
                score_direction = "AWAY"
            else:
                score_direction = "DRAW"
        card = build_multi_market_analysis(
            fixture_id=fixture_id,
            inputs=AnalysisBuildInputs(
                ah_intent=ah_intent,
                ou_intent=ou_intent,
                feature_set=feature_set,
                half_goals=half_goals,
                score_matrix=score_matrix,
                score_direction=score_direction,
                missing_markets=frozenset(missing),
            ),
        )
        payload = self._analysis_card_payload(card)
        self._apply_mainline_market_selection(payload, mainline_selection)
        payload.update(
            self._analysis_input_summary(
                fixture_id=fixture_id,
                kickoff=kickoff,
                home_team_id=home_id,
                away_team_id=away_id,
                xg_snapshots=snapshots,
                observations=observations,
                mainline_selection=mainline_selection,
                home_xg=latest_home_xg,
                away_xg=latest_away_xg,
                score_matrix=score_matrix,
            )
        )
        self._attach_xg_reason_values(
            payload,
            home_xg=latest_home_xg,
            away_xg=latest_away_xg,
        )
        return payload

    def _mainline_market_selection(
        self,
        observations: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        return {
            "ASIAN_HANDICAP": self._select_mainline_observations(
                observations,
                market="ASIAN_HANDICAP",
            ),
            "TOTALS": self._select_mainline_observations(
                observations,
                market="TOTALS",
            ),
        }

    def _select_mainline_observations(
        self,
        observations: list[dict[str, Any]],
        *,
        market: str,
        min_bookmakers: int = 1,
    ) -> dict[str, Any]:
        grouped: dict[Decimal, list[dict[str, Any]]] = {}
        for row in observations:
            if (
                str(row.get("canonical_market")) != market
                or row.get("suspended")
                or row.get("live")
            ):
                continue
            line = self._decimal_line(row)
            if line is None:
                continue
            grouped.setdefault(self._mainline_group_key(market, line), []).append(row)
        if not grouped:
            return {
                "market": market,
                "status": "UNAVAILABLE",
                "line": None,
                "observations": [],
                "bookmaker_count": 0,
            }
        candidates: list[
            tuple[Decimal, Decimal, int, str, Decimal, list[dict[str, Any]], dict[str, Any]]
        ] = []
        paired_lines = 0
        for line, rows in grouped.items():
            side_state = self._line_side_state(market, rows)
            if not side_state:
                continue
            paired_lines += 1
            bookmaker_count = len(
                {
                    str(row.get("bookmaker_id") or row.get("bookmaker_name"))
                    for row in rows
                    if row.get("bookmaker_id") or row.get("bookmaker_name")
                }
            )
            if bookmaker_count < min_bookmakers:
                continue
            latest_capture = max((str(row.get("captured_at") or "") for row in rows), default="")
            balance_gap = Decimal(str(side_state["balance_gap"]))
            mid_distance = Decimal(str(abs(float(side_state["mid_price"]) - 1.9)))
            min_side_price = Decimal(str(side_state["min_price"]))
            if balance_gap > Decimal("0.90") or min_side_price < Decimal("1.40"):
                continue
            candidates.append(
                (
                    balance_gap,
                    mid_distance,
                    -bookmaker_count,
                    latest_capture,
                    line,
                    rows,
                    side_state,
                )
            )
        if not candidates:
            closest_line = min(
                grouped,
                key=lambda line: self._closest_unbalanced_score(
                    market,
                    grouped[line],
                ),
            )
            closest_rows = grouped[closest_line]
            side_state = self._line_side_state(market, closest_rows) or {}
            bookmaker_count = len(
                {
                    str(row.get("bookmaker_id") or row.get("bookmaker_name"))
                    for row in closest_rows
                    if row.get("bookmaker_id") or row.get("bookmaker_name")
                }
            )
            return {
                "market": market,
                "status": "NO_BALANCED_MAINLINE" if paired_lines else "UNAVAILABLE",
                "line": self._format_decimal_line(closest_line),
                "observations": closest_rows,
                "bookmaker_count": bookmaker_count,
                **side_state,
            }
        _gap, _mid_distance, bookmaker_count_key, _latest, line, rows, side_state = min(candidates)
        return {
            "market": market,
            "status": "READY",
            "line": self._format_decimal_line(line),
            "observations": rows,
            "bookmaker_count": -bookmaker_count_key,
            **side_state,
        }

    def _apply_mainline_market_selection(
        self,
        payload: dict[str, Any],
        selection: dict[str, dict[str, Any]],
    ) -> None:
        markets = payload.get("markets")
        if not isinstance(markets, list):
            return
        for market in markets:
            if not isinstance(market, dict):
                continue
            market_name = str(market.get("market") or "")
            if market_name not in selection:
                continue
            resolved = selection[market_name]
            status = str(resolved.get("status") or "UNAVAILABLE")
            market["line_status"] = status
            market["bookmaker_count"] = int(resolved.get("bookmaker_count") or 0)
            if status == "READY":
                side = self._market_tendency_side(market_name, market)
                side_line = self._side_line(resolved, side)
                side_price = self._side_price(resolved, side)
                market["line"] = side_line or resolved.get("line")
                market["balanced_line"] = resolved.get("line")
                market["balanced_prices"] = resolved.get("side_prices", {})
                if side_price is not None:
                    market["odds"] = side_price
                should_downgrade_to_watch = (
                    str(market.get("decision") or "") != "SKIP"
                    and (
                        (side_price is not None and float(side_price) < 1.40)
                        or float(market.get("confidence") or 0.0) < 0.50
                    )
                )
                if should_downgrade_to_watch:
                    market["decision"] = "WATCH"
                    market["tendency"] = None
                    market["confidence"] = min(float(market.get("confidence") or 0.0), 0.49)
                    market["reasons"] = ["跟随市场 · 无独立优势 · 仅参考"]
                    market["risks"] = ["低赔率或信号不足时不作为主看。"]
                continue
            if status in {"EXTREME_LINE_ONLY", "NO_BALANCED_MAINLINE", "UNAVAILABLE"}:
                market["decision"] = "SKIP"
                market["tendency"] = None
                market["confidence"] = 0.0
                market["line"] = resolved.get("line")
                market["balanced_line"] = resolved.get("line")
                market["balanced_prices"] = resolved.get("side_prices", {})
                market["reasons"] = ["无有效主盘"]
                market["risks"] = ["主盘口缺失时保持 SKIP。"]
        self._refresh_analysis_card_decision(payload)

    def _refresh_analysis_card_decision(self, payload: dict[str, Any]) -> None:
        markets = payload.get("markets")
        if not isinstance(markets, list):
            return
        decisions = {
            str(market.get("decision") or "")
            for market in markets
            if isinstance(market, dict)
        }
        if "PICK" in decisions or "ANALYSIS_PICK" in decisions:
            payload["decision"] = "ANALYSIS_PICK"
        elif "WATCH" in decisions:
            payload["decision"] = "WATCH"
        else:
            payload["decision"] = "SKIP"

    def _mainline_group_key(self, market: str, line: Decimal) -> Decimal:
        if market == "ASIAN_HANDICAP":
            return abs(line)
        return line

    def _line_side_state(self, market: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        latest_by_side_bookmaker: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            side = self._observation_side(market, row)
            if side is None:
                continue
            bookmaker = str(row.get("bookmaker_id") or row.get("bookmaker_name") or "")
            if not bookmaker:
                continue
            key = (side, bookmaker)
            current = latest_by_side_bookmaker.get(key)
            if current is None or str(row.get("captured_at") or "") > str(
                current.get("captured_at") or "",
            ):
                latest_by_side_bookmaker[key] = row
        side_names = ("HOME", "AWAY") if market == "ASIAN_HANDICAP" else ("OVER", "UNDER")
        side_rows: dict[str, list[dict[str, Any]]] = {
            side: [
                row
                for (row_side, _bookmaker), row in latest_by_side_bookmaker.items()
                if row_side == side
            ]
            for side in side_names
        }
        if not all(side_rows.values()):
            return None
        prices: dict[str, float] = {}
        lines: dict[str, str] = {}
        for side, current_rows in side_rows.items():
            side_prices: list[float] = []
            for row in current_rows:
                try:
                    price = float(row["decimal_odds"])
                except (KeyError, TypeError, ValueError):
                    continue
                if price > 1:
                    side_prices.append(price)
            if not side_prices:
                return None
            prices[side.lower()] = round(sum(side_prices) / len(side_prices), 4)
            latest = max(current_rows, key=lambda row: str(row.get("captured_at") or ""))
            lines[side.lower()] = self._line_value(latest) or ""
        values = list(prices.values())
        return {
            "side_prices": prices,
            "side_lines": lines,
            "balance_gap": round(abs(values[0] - values[1]), 4),
            "mid_price": round(sum(values) / len(values), 4),
            "min_price": round(min(values), 4),
        }

    def _closest_unbalanced_score(
        self,
        market: str,
        rows: list[dict[str, Any]],
    ) -> tuple[int, float]:
        state = self._line_side_state(market, rows)
        if not state:
            return (1, 999.0)
        return (0, float(state.get("balance_gap") or 999.0))

    def _observation_side(self, market: str, row: dict[str, Any]) -> str | None:
        selection = str(row.get("selection") or "").lower()
        if market == "ASIAN_HANDICAP":
            if "home" in selection:
                return "HOME"
            if "away" in selection:
                return "AWAY"
            return None
        if market == "TOTALS":
            if "over" in selection:
                return "OVER"
            if "under" in selection:
                return "UNDER"
        return None

    def _market_tendency_side(self, market: str, row: dict[str, Any]) -> str | None:
        tendency = str(row.get("tendency") or "")
        if market == "ASIAN_HANDICAP":
            if tendency == "HOME_AH":
                return "home"
            if tendency == "AWAY_AH":
                return "away"
        if market == "TOTALS":
            if tendency == "OVER":
                return "over"
            if tendency == "UNDER":
                return "under"
        return None

    def _side_price(self, selection: dict[str, Any], side: str | None) -> str | None:
        if side is None:
            return None
        prices = selection.get("side_prices")
        if not isinstance(prices, dict) or prices.get(side) is None:
            return None
        return str(prices[side])

    def _side_line(self, selection: dict[str, Any], side: str | None) -> str | None:
        if side is None:
            return None
        lines = selection.get("side_lines")
        if not isinstance(lines, dict):
            return None
        line = lines.get(side)
        return str(line) if line not in {None, ""} else None

    def _team_xg_feature_snapshot(
        self,
        row: dict[str, Any],
        *,
        observed_at_cap: datetime,
    ) -> TeamXgSnapshot:
        observed_at = parse_provider_time(row["as_of_time"]) or observed_at_cap
        return TeamXgSnapshot(
            team_id=str(row["team_id"]),
            observed_at=min(observed_at, observed_at_cap),
            xg_for=float(row["rolling_xg_for"]),
            xg_against=float(row["rolling_xg_against"]),
            goals_for=round(float(row["rolling_goals_for"])),
            goals_against=round(float(row["rolling_goals_against"])),
        )

    def _market_snapshots_from_observations(
        self,
        observations: list[dict[str, Any]],
    ) -> list[MarketSnapshot]:
        rows: list[MarketSnapshot] = []
        for row in observations:
            captured = parse_provider_time(row.get("captured_at"))
            if captured is None:
                continue
            try:
                price = Decimal(str(row["decimal_odds"]))
                line = Decimal(str(row["line"])) if row.get("line") is not None else None
            except (ArithmeticError, KeyError, TypeError, ValueError):
                continue
            rows.append(
                MarketSnapshot(
                    fixture_id=str(row["fixture_id"]),
                    market=str(row["canonical_market"]),
                    selection=str(row["selection"]),
                    price=price,
                    line=line,
                    captured_at=captured,
                    snapshot_semantics="CAPTURED_AT",
                )
            )
        return rows

    def _bookmaker_quotes_from_observations(
        self,
        observations: list[dict[str, Any]],
    ) -> list[BookmakerQuote]:
        rows: list[BookmakerQuote] = []
        for row in observations:
            captured = parse_provider_time(row.get("captured_at"))
            provider_updated = parse_provider_time(row.get("provider_last_update")) or captured
            if captured is None or provider_updated is None:
                continue
            try:
                decimal_odds = Decimal(str(row["decimal_odds"]))
                line = Decimal(str(row["line"])) if row.get("line") is not None else None
            except (ArithmeticError, KeyError, TypeError, ValueError):
                continue
            rows.append(
                BookmakerQuote(
                    bookmaker=str(row.get("bookmaker_name") or row.get("bookmaker_id")),
                    market=str(row["canonical_market"]),
                    selection=str(row["selection"]),
                    decimal_odds=decimal_odds,
                    line=line,
                    captured_at=captured,
                    provider_updated_at=provider_updated,
                    suspended=bool(row.get("suspended")),
                    live=bool(row.get("live")),
                )
            )
        return rows

    def _poisson_score_matrix(self, home_mu: float, away_mu: float) -> dict[tuple[int, int], float]:
        matrix: dict[tuple[int, int], float] = {}
        for home_goals in range(5):
            for away_goals in range(5):
                matrix[(home_goals, away_goals)] = (
                    math.exp(-home_mu)
                    * home_mu**home_goals
                    / math.factorial(home_goals)
                    * math.exp(-away_mu)
                    * away_mu**away_goals
                    / math.factorial(away_goals)
                )
        return matrix

    def _analysis_card_payload(self, card: MultiMarketAnalysisCard) -> dict[str, Any]:
        return {
            "fixture_id": card.fixture_id,
            "decision": card.decision.value,
            "markets": [self._analysis_market_payload(row) for row in card.markets],
            "bookmaker_intent": card.bookmaker_intent.as_dict(),
            "risks": sorted({risk for market in card.markets for risk in market.risks}),
            "source": "db_feature_materialized_analysis",
            "disclaimer": DISCLAIMER,
            "candidate": False,
            "formal_recommendation": False,
        }

    def _analysis_input_summary(
        self,
        *,
        fixture_id: str,
        kickoff: datetime,
        home_team_id: str,
        away_team_id: str,
        xg_snapshots: list[dict[str, Any]],
        observations: list[dict[str, Any]],
        mainline_selection: dict[str, dict[str, Any]],
        home_xg: TeamXgSnapshot | None,
        away_xg: TeamXgSnapshot | None,
        score_matrix: dict[tuple[int, int], float] | None,
    ) -> dict[str, Any]:
        bookmaker_ids = {
            str(row.get("bookmaker_id") or row.get("bookmaker_name"))
            for row in observations
            if row.get("bookmaker_id") or row.get("bookmaker_name")
        }
        captured_points = {
            str(row.get("captured_at"))
            for row in observations
            if row.get("captured_at")
        }
        lineups_status = self._enrichment_status(fixture_id=fixture_id, endpoint="lineups")
        statistics_status = self._enrichment_status(fixture_id=fixture_id, endpoint="statistics")
        xg_status = self._xg_readiness_status(
            kickoff=kickoff,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            snapshots=xg_snapshots,
        )
        summary: dict[str, Any] = {
            "data_readiness": {
                "market_observations": len(observations),
                "bookmakers": len(bookmaker_ids),
                "odds_snapshots": len(captured_points),
                "xg": home_xg is not None and away_xg is not None,
                "xg_status": xg_status["status"],
                "xg_home_match_count": xg_status["home_match_count"],
                "xg_away_match_count": xg_status["away_match_count"],
                "xg_snapshot_count": xg_status["snapshot_count"],
                "h2h": False,
                "lineups": lineups_status["ready"],
                "lineups_status": lineups_status["status"],
                "lineups_captured_at": lineups_status["captured_at"],
                "statistics_status": statistics_status["status"],
                "statistics_captured_at": statistics_status["captured_at"],
            }
        }
        current_odds: dict[str, Any] = {}
        line_movement: dict[str, Any] = {}
        for market, key in (("ASIAN_HANDICAP", "ah"), ("TOTALS", "ou")):
            selected = mainline_selection.get(market, {})
            if selected.get("status") != "READY":
                continue
            selected_observations = cast(list[dict[str, Any]], selected.get("observations", []))
            ordered = self._ordered_observations_for_market(selected_observations, market)
            if not ordered:
                continue
            current = ordered[-1]
            odds_entry = self._balanced_odds_entry(selected)
            if odds_entry:
                current_odds[key] = odds_entry
            first_line = self._line_value(ordered[0])
            current_line = self._line_value(current)
            if first_line is not None:
                line_movement[f"{key}_open"] = first_line
            if current_line is not None:
                line_movement[f"{key}_current"] = current_line
        if current_odds:
            summary["current_odds"] = current_odds
        if line_movement:
            summary["line_movement"] = line_movement
        market_probabilities = self._market_probabilities_from_observations(observations)
        if market_probabilities:
            summary["market_probabilities"] = market_probabilities
        if score_matrix:
            summary["model_probabilities"] = self._model_probabilities_from_score_matrix(
                score_matrix
            )
        return summary

    def _xg_readiness_status(
        self,
        *,
        kickoff: datetime,
        home_team_id: str,
        away_team_id: str,
        snapshots: list[dict[str, Any]],
    ) -> dict[str, Any]:
        snapshot_team_ids = {str(row.get("team_id") or "") for row in snapshots}
        home_snapshot_ready = home_team_id in snapshot_team_ids
        away_snapshot_ready = away_team_id in snapshot_team_ids
        home_match_count = self._team_xg_match_count(team_id=home_team_id, before=kickoff)
        away_match_count = self._team_xg_match_count(team_id=away_team_id, before=kickoff)
        if home_snapshot_ready and away_snapshot_ready:
            status = "READY"
        elif home_snapshot_ready or away_snapshot_ready:
            status = "PARTIAL_HISTORY"
        elif home_match_count or away_match_count:
            status = "INSUFFICIENT_HISTORY"
        else:
            status = "PROVIDER_EMPTY_OR_UNAVAILABLE"
        return {
            "status": status,
            "home_match_count": home_match_count,
            "away_match_count": away_match_count,
            "snapshot_count": len(snapshots),
        }

    def _team_xg_match_count(self, *, team_id: str, before: datetime) -> int:
        matches = self._team_xg_matches()
        count = 0
        for row in matches:
            if str(row.get("team_id") or "") != team_id:
                continue
            kickoff = parse_provider_time(row.get("kickoff_at"))
            if kickoff is not None and kickoff < before:
                count += 1
        return count

    def _team_xg_matches(self) -> list[dict[str, Any]]:
        if self._team_xg_matches_cache is not None:
            return self._team_xg_matches_cache
        repository = self._future_refresh_repository()
        reader = getattr(repository, "team_xg_matches", None) if repository is not None else None
        if not callable(reader):
            self._team_xg_matches_cache = []
            return []
        try:
            rows = cast(list[dict[str, Any]], reader())
        except SQLAlchemyError:
            rows = []
        self._team_xg_matches_cache = rows
        return rows

    def _enrichment_status(self, *, fixture_id: str, endpoint: str) -> dict[str, Any]:
        rows = self._raw_payloads_for_endpoint(endpoint)
        matching = [
            row
            for row in rows
            if self._raw_payload_fixture_id(row.get("payload")) == fixture_id
        ]
        if not matching:
            return {
                "ready": False,
                "status": "NOT_REQUESTED",
                "captured_at": None,
                "response_count": 0,
            }
        latest = max(matching, key=lambda row: str(row.get("captured_at") or ""))
        payload = latest.get("payload") if isinstance(latest, dict) else {}
        response = payload.get("response") if isinstance(payload, dict) else None
        response_count = len(response) if isinstance(response, list) else 0
        if response_count == 0:
            status = "PROVIDER_EMPTY"
            ready = False
        elif endpoint == "lineups":
            ready = self._lineups_ready(response)
            status = "READY" if ready else "PARTIAL"
        else:
            ready = True
            status = "READY"
        return {
            "ready": ready,
            "status": status,
            "captured_at": latest.get("captured_at"),
            "response_count": response_count,
        }

    def _raw_payloads_for_endpoint(self, endpoint: str) -> list[dict[str, Any]]:
        if endpoint in self._raw_payloads_by_endpoint_cache:
            return self._raw_payloads_by_endpoint_cache[endpoint]
        repository = self._future_refresh_repository()
        reader = getattr(repository, "raw_payloads", None) if repository is not None else None
        if not callable(reader):
            self._raw_payloads_by_endpoint_cache[endpoint] = []
            return []
        try:
            rows = cast(list[dict[str, Any]], reader(endpoint))
        except SQLAlchemyError:
            rows = []
        self._raw_payloads_by_endpoint_cache[endpoint] = rows
        return rows

    def _raw_payload_fixture_id(self, payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        parameters = payload.get("parameters")
        if isinstance(parameters, dict) and parameters.get("fixture") is not None:
            return str(parameters["fixture"])
        response = payload.get("response")
        if isinstance(response, list):
            for item in response:
                if not isinstance(item, dict):
                    continue
                fixture = item.get("fixture")
                if isinstance(fixture, dict) and fixture.get("id") is not None:
                    return str(fixture["id"])
        return None

    def _lineups_ready(self, response: Any) -> bool:
        if not isinstance(response, list) or len(response) < 2:
            return False
        ready_teams = 0
        for item in response:
            if not isinstance(item, dict):
                continue
            start_xi = item.get("startXI")
            if isinstance(start_xi, list) and start_xi:
                ready_teams += 1
        return ready_teams >= 2

    def _market_probabilities_from_observations(
        self,
        observations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        latest_by_selection: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in observations:
            if row.get("suspended") or row.get("live"):
                continue
            market = str(row.get("canonical_market") or "")
            selection = str(row.get("selection") or "")
            if not market or not selection or row.get("decimal_odds") is None:
                continue
            line = self._line_value(row) or "NO_LINE"
            key = (market, line, selection)
            current = latest_by_selection.get(key)
            if current is None or str(row.get("captured_at") or "") > str(
                current.get("captured_at") or ""
            ):
                latest_by_selection[key] = row
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for (market, line, _selection), row in latest_by_selection.items():
            grouped.setdefault((market, line), []).append(row)
        probabilities: dict[str, Any] = {}
        for (market, line), rows in grouped.items():
            implied: dict[str, float] = {}
            for row in rows:
                try:
                    price = float(row["decimal_odds"])
                except (TypeError, ValueError):
                    continue
                if price <= 1.0:
                    continue
                implied[str(row["selection"])] = 1 / price
            total = sum(implied.values())
            if len(implied) < 2 or total <= 0:
                continue
            probabilities[f"{market}:{line}"] = {
                selection: round(value / total, 4)
                for selection, value in sorted(implied.items())
            }
        return probabilities

    def _model_probabilities_from_score_matrix(
        self,
        matrix: dict[tuple[int, int], float],
    ) -> dict[str, Any]:
        total = sum(max(value, 0.0) for value in matrix.values())
        if total <= 0:
            return {}
        home = sum(
            value
            for (home_goals, away_goals), value in matrix.items()
            if home_goals > away_goals
        )
        draw = sum(
            value
            for (home_goals, away_goals), value in matrix.items()
            if home_goals == away_goals
        )
        away = sum(
            value
            for (home_goals, away_goals), value in matrix.items()
            if home_goals < away_goals
        )
        over_2_5 = sum(
            value
            for (home_goals, away_goals), value in matrix.items()
            if home_goals + away_goals > 2.5
        )
        under_2_5 = total - over_2_5
        return {
            "one_x_two": {
                "HOME": round(home / total, 4),
                "DRAW": round(draw / total, 4),
                "AWAY": round(away / total, 4),
            },
            "totals_2_5": {
                "OVER": round(over_2_5 / total, 4),
                "UNDER": round(under_2_5 / total, 4),
            },
        }

    def _ordered_observations_for_market(
        self,
        observations: list[dict[str, Any]],
        market: str,
    ) -> list[dict[str, Any]]:
        rows = [
            row
            for row in observations
            if str(row.get("canonical_market")) == market
            and not row.get("suspended")
            and not row.get("live")
        ]
        return sorted(
            rows,
            key=lambda row: (
                str(row.get("captured_at") or ""),
                str(row.get("bookmaker_name") or row.get("bookmaker_id") or ""),
                str(row.get("selection") or ""),
            ),
        )

    def _odds_entry(self, row: dict[str, Any]) -> dict[str, Any] | None:
        line = self._line_value(row)
        price = row.get("decimal_odds")
        if line is None or price is None:
            return None
        try:
            decimal_price = round(float(price), 4)
        except (TypeError, ValueError):
            return None
        return {"line": line, "price": decimal_price}

    def _balanced_odds_entry(self, selection: dict[str, Any]) -> dict[str, Any] | None:
        line = selection.get("line")
        if line is None:
            return None
        entry: dict[str, Any] = {"line": str(line)}
        side_prices = selection.get("side_prices")
        if isinstance(side_prices, dict):
            for key, value in side_prices.items():
                try:
                    entry[f"{key}_price"] = round(float(value), 4)
                except (TypeError, ValueError):
                    continue
        side_lines = selection.get("side_lines")
        if isinstance(side_lines, dict):
            for key, value in side_lines.items():
                if value not in {None, ""}:
                    entry[f"{key}_line"] = str(value)
        prices = [
            float(value)
            for key, value in entry.items()
            if key.endswith("_price") and isinstance(value, int | float)
        ]
        if prices:
            entry["price"] = round(sum(prices) / len(prices), 4)
        return entry

    def _line_value(self, row: dict[str, Any]) -> str | None:
        line = row.get("line")
        if line is None:
            return None
        try:
            line_number = float(line)
        except (TypeError, ValueError):
            return str(line)
        if line_number.is_integer():
            return str(int(line_number))
        return f"{line_number:g}"

    def _decimal_line(self, row: dict[str, Any]) -> Decimal | None:
        line = row.get("line")
        if line is None:
            return None
        try:
            return Decimal(str(line))
        except (ArithmeticError, TypeError, ValueError):
            return None

    def _format_decimal_line(self, line: Decimal) -> str:
        if line == line.to_integral_value():
            return str(int(line))
        return f"{line.normalize():f}".rstrip("0").rstrip(".")

    def _attach_xg_reason_values(
        self,
        payload: dict[str, Any],
        *,
        home_xg: TeamXgSnapshot | None,
        away_xg: TeamXgSnapshot | None,
    ) -> None:
        if home_xg is None or away_xg is None:
            return
        side_reason = (
            f"滚动 xG 主 {home_xg.xg_for:.2f}/{home_xg.xg_against:.2f} "
            f"vs 客 {away_xg.xg_for:.2f}/{away_xg.xg_against:.2f}"
        )
        totals_reason = f"两队滚动 xG 进攻合计 {home_xg.xg_for + away_xg.xg_for:.2f}"
        markets = payload.get("markets")
        if not isinstance(markets, list):
            return
        for market in markets:
            if not isinstance(market, dict) or market.get("decision") == "SKIP":
                continue
            reasons = [str(item) for item in market.get("reasons", []) if item]
            if market.get("market") == "ASIAN_HANDICAP":
                market["reasons"] = [side_reason, *reasons]
            elif market.get("market") == "TOTALS":
                market["reasons"] = [totals_reason, *reasons]

    def _analysis_market_payload(self, market: MarketAnalysis) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "market": market.market.value,
            "decision": market.decision.value,
            "tendency": market.tendency,
            "confidence": market.confidence,
            "reasons": list(market.reasons),
            "risks": list(market.risks),
            "invalidation_conditions": list(market.invalidation_conditions),
            "disclaimer": market.disclaimer,
            "candidate": False,
            "formal_recommendation": False,
        }
        if market.score_card is not None:
            payload["score_card"] = market.score_card.model_dump(mode="json")
        return payload

    def market_ranking(self, fixture_id: str) -> list[dict[str, Any]]:
        for card in self.repository.matchday_cards():
            if str(card.get("fixture", {}).get("fixture_id")) == fixture_id:
                return cast(list[dict[str, Any]], card.get("market_ranking", []))
        dashboard = self.repository.dashboard_fixture(fixture_id)
        if dashboard is None:
            return []
        return cast(list[dict[str, Any]], dashboard.get("all_market_ranking", []))

    def integrity(self, fixture_id: str) -> dict[str, Any] | None:
        for card in self.repository.matchday_cards():
            if str(card.get("fixture", {}).get("fixture_id")) == fixture_id:
                return cast(dict[str, Any], card.get("integrity", {}))
        dashboard = self.repository.dashboard_fixture(fixture_id)
        if dashboard is None:
            return None
        return {"integrity_status": dashboard.get("integrity_status", "UNKNOWN")}

    def fixture(self, fixture_id: str, timezone: str) -> dict[str, Any] | None:
        dashboard = self.repository.dashboard_fixture(fixture_id)
        if dashboard is not None:
            row = self._dashboard_fixture_summary(dashboard, timezone)
            row.update(
                {
                    "request_id": "",
                    "venue": dashboard.get("venue"),
                    "bookmaker_count": dashboard.get("bookmaker_count", 0),
                    "market_coverage": dashboard.get("market_coverage", {}),
                    "forward_decision": dashboard.get("decision_status", "SKIP"),
                    "provenance": dashboard.get("provenance", {}),
                    "risk_notes": dashboard.get("risk_notes", []),
                    "primary_market": dashboard.get("primary_market"),
                    "primary_selection": dashboard.get("primary_selection"),
                    "primary_line": dashboard.get("primary_line"),
                    "primary_executable_odds": self._optional_string(
                        dashboard.get("primary_executable_odds")
                    ),
                    "primary_hong_kong_odds": self._optional_string(
                        dashboard.get("primary_hong_kong_odds")
                    ),
                    "primary_model_fair_odds": self._optional_string(
                        dashboard.get("primary_model_fair_odds")
                    ),
                    "primary_risk_adjusted_ev": self._optional_string(
                        dashboard.get("primary_risk_adjusted_ev")
                    ),
                    "research_grade": dashboard.get("research_grade"),
                    "ah_ladder": dashboard.get("ah_ladder", []),
                    "ou_ladder": dashboard.get("ou_ladder", []),
                    "all_market_ranking": dashboard.get("all_market_ranking", []),
                    "one_x_two_ranking": [
                        row
                        for row in dashboard.get("all_market_ranking", [])
                        if row.get("market") == "ONE_X_TWO"
                    ],
                    "btts_ranking": [
                        row
                        for row in dashboard.get("all_market_ranking", [])
                        if row.get("market") == "BTTS"
                    ],
                    "secondary_market_direction": dashboard.get(
                        "secondary_market_direction"
                    ),
                    "source_snapshot_id": dashboard.get("provenance", {}).get("snapshot_id"),
                    "source_captured_at": self._optional_datetime(dashboard.get("captured_at")),
                    "source_phase": dashboard.get("phase"),
                    "valuation_generated_at": self._optional_datetime(
                        dashboard.get("valuation_generated_at", dashboard.get("captured_at"))
                    ),
                    "projector_generated_at": self._optional_datetime(
                        dashboard.get("projector_generated_at", dashboard.get("captured_at"))
                    ),
                    "temporal_status": dashboard.get("temporal_status"),
                    "integrity_status": dashboard.get("integrity_status"),
                    "analysis_card": self.analysis_card(fixture_id),
                }
            )
            return row
        for item in self.repository.fixture_payloads():
            if str(item.get("fixture", {}).get("id")) == fixture_id:
                row = self._fixture_summary(item, timezone)
                snapshots = [
                    item
                    for item in self.repository.market_snapshots()
                    if item["fixture_id"] == fixture_id
                ]
                locks = [
                    item
                    for item in self.repository.forward_locks()
                    if item["fixture_id"] == fixture_id
                ]
                observations = [
                    item
                    for item in self.repository.future_market_observations()
                    if str(item.get("fixture_id")) == fixture_id
                ]
                observed_markets: set[str] = {
                    str(item["canonical_market"])
                    for item in observations
                    if item.get("canonical_market")
                }
                obs_bookmaker_ids: set[str] = {
                    str(item["bookmaker_id"])
                    for item in observations
                    if item.get("bookmaker_id")
                }
                row.update(
                    {
                        "request_id": "",
                        "venue": item.get("fixture", {}).get("venue", {}).get("name"),
                        "bookmaker_count": max(
                            [snapshot.get("bookmaker_count", 0) for snapshot in snapshots]
                            + [len(obs_bookmaker_ids)]
                            or [0]
                        ),
                        "market_coverage": {
                            "ONE_X_TWO": bool(snapshots) or "ONE_X_TWO" in observed_markets,
                            "ASIAN_HANDICAP": "ASIAN_HANDICAP" in observed_markets,
                            "TOTALS": "TOTALS" in observed_markets,
                            "BTTS": "BTTS" in observed_markets,
                        },
                        "forward_decision": locks[0]["decision"] if locks else "SKIP",
                        "provenance": {
                            "fixture_source": "api_football_cached",
                            "probability_source": "stage7e_forward_holdout",
                        },
                        "risk_notes": [] if snapshots else ["market_not_comparable"],
                        "analysis_card": self.analysis_card(fixture_id),
                    }
                )
                return row
        return None

    def _normalize_analysis_card(
        self,
        payload: dict[str, Any],
        *,
        fixture_id: str,
        fixture_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = dict(payload)
        normalized.setdefault("fixture_id", fixture_id)
        normalized.setdefault("disclaimer", DISCLAIMER)
        normalized.setdefault("risks", normalized.get("risks_cn", []))
        normalized["candidate"] = False
        normalized["formal_recommendation"] = False
        markets = normalized.get("markets")
        if isinstance(markets, list):
            normalized["markets"] = [
                {
                    **dict(item),
                    "candidate": False,
                    "formal_recommendation": False,
                    "disclaimer": dict(item).get("disclaimer", DISCLAIMER),
                }
                for item in markets
                if isinstance(item, dict)
            ]
        return self._decorate_analysis_card(normalized, fixture_context=fixture_context)

    def _fallback_analysis_card(
        self,
        *,
        fixture_id: str,
        market_coverage: dict[str, Any],
        source: str,
        fixture_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        markets = [
            self._analysis_market_skip(
                "ASIAN_HANDICAP",
                "AH_ANALYSIS_INPUT_UNAVAILABLE"
                if market_coverage.get("ASIAN_HANDICAP")
                else "AH_MARKET_UNAVAILABLE",
            ),
            self._analysis_market_skip(
                "TOTALS",
                "OU_ANALYSIS_INPUT_UNAVAILABLE"
                if market_coverage.get("TOTALS")
                else "OU_MARKET_UNAVAILABLE",
            ),
            self._analysis_market_skip("FIRST_HALF_GOALS", "HALF_GOAL_INPUT_UNAVAILABLE"),
            self._analysis_market_skip("SCORE", "SCORE_MATRIX_UNAVAILABLE"),
        ]
        return self._decorate_analysis_card(
            {
                "fixture_id": fixture_id,
                "decision": "SKIP",
                "markets": markets,
                "bookmaker_intent": {
                    "intent": "INSUFFICIENT_DATA",
                    "confidence": 0.0,
                    "reason": "BOOKMAKER_INTENT_INPUT_UNAVAILABLE",
                },
                "risks": ["数据不足时保持 SKIP。"],
                "attention_level": "LOW",
                "source": source,
                "disclaimer": DISCLAIMER,
                "candidate": False,
                "formal_recommendation": False,
            },
            fixture_context=fixture_context,
        )

    def _analysis_market_skip(self, market: str, reason: str) -> dict[str, Any]:
        return {
            "market": market,
            "decision": "SKIP",
            "tendency": None,
            "confidence": 0.0,
            "reasons": [reason],
            "risks": ["数据不足时保持 SKIP。"],
            "invalidation_conditions": ["补齐 as-of 分析输入后重新评估"],
            "disclaimer": DISCLAIMER,
            "candidate": False,
            "formal_recommendation": False,
        }

    def _decorate_analysis_card(
        self,
        card: dict[str, Any],
        *,
        fixture_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        decorated = dict(card)
        if fixture_context:
            for key, value in fixture_context.items():
                decorated.setdefault(key, value)
        competition_name = self._first_text(
            decorated.get("competition_name"),
            decorated.get("competition_cn"),
            "世界杯",
        )
        home_name = self._first_text(
            decorated.get("home_name"),
            decorated.get("home_cn"),
            decorated.get("home_team_name"),
            "主队",
        )
        away_name = self._first_text(
            decorated.get("away_name"),
            decorated.get("away_cn"),
            decorated.get("away_team_name"),
            "客队",
        )
        decorated["competition_name"] = competition_name
        decorated.setdefault("competition_cn", competition_name)
        decorated["home_name"] = home_name
        decorated["away_name"] = away_name
        decorated["home_cn"] = home_name
        decorated["away_cn"] = away_name
        decorated.setdefault("watch_level", self._watch_level(decorated))
        decorated.setdefault("risks_cn", list(decorated.get("risks") or ["数据不足时保持 SKIP。"]))
        decorated.setdefault("disclaimer_cn", DISCLAIMER)
        decorated.setdefault(
            "data_readiness",
            {
                "market_observations": 0,
                "bookmakers": 0,
                "odds_snapshots": 0,
                "xg": False,
                "xg_status": "UNKNOWN",
                "xg_home_match_count": 0,
                "xg_away_match_count": 0,
                "xg_snapshot_count": 0,
                "h2h": False,
                "lineups": False,
                "lineups_status": "UNKNOWN",
                "lineups_captured_at": None,
                "statistics_status": "UNKNOWN",
                "statistics_captured_at": None,
            },
        )
        decorated["candidate"] = False
        decorated["formal_recommendation"] = False
        decorated["pricing_shadow"] = build_pricing_shadow(
            fixture_id=str(decorated.get("fixture_id") or ""),
            model_probabilities=decorated.get("model_probabilities")
            if isinstance(decorated.get("model_probabilities"), dict)
            else None,
            market_probabilities=decorated.get("market_probabilities")
            if isinstance(decorated.get("market_probabilities"), dict)
            else None,
            current_odds=decorated.get("current_odds")
            if isinstance(decorated.get("current_odds"), dict)
            else None,
        )
        decorated["bookmaker_intent"] = self._decorate_bookmaker_intent(
            decorated.get("bookmaker_intent")
        )
        decorated["markets"] = [
            self._decorate_analysis_market(item)
            for item in decorated.get("markets", [])
            if isinstance(item, dict)
        ]
        return decorated

    def _first_text(self, *values: Any) -> str:
        for value in values:
            if isinstance(value, str) and value:
                return value
        return ""

    def _decorate_bookmaker_intent(self, payload: Any) -> dict[str, Any]:
        intent = dict(payload) if isinstance(payload, dict) else {}
        intent_value = str(intent.get("intent") or "INSUFFICIENT_DATA")
        intent["intent"] = intent_value
        intent.setdefault("label_cn", INTENT_LABELS_CN.get(intent_value, intent_value))
        intent.setdefault("opening_line", None)
        intent.setdefault("current_line", None)
        intent.setdefault("confidence", 0.0)
        return intent

    def _decorate_analysis_market(self, payload: dict[str, Any]) -> dict[str, Any]:
        market = dict(payload)
        market_name = str(market.get("market") or "UNKNOWN")
        original_decision = str(market.get("decision") or "SKIP")
        market["analysis_decision"] = original_decision
        if original_decision == "SKIP":
            market["decision"] = "SKIP"
        elif original_decision == "WATCH":
            market["decision"] = "WATCH"
        else:
            market["decision"] = "PICK"
        market["label_cn"] = MARKET_LABELS_CN.get(market_name, market_name)
        market["lean_cn"] = self._lean_cn(market)
        market["reason_cn"] = self._reason_cn(market)
        market["lean"] = market["lean_cn"]
        market["reason"] = market["reason_cn"]
        market["risks_cn"] = list(market.get("risks") or ["数据不足时保持 SKIP。"])
        market.setdefault("confidence", 0.0)
        market.setdefault("reference_scores", self._reference_scores(market))
        market.setdefault(
            "scores",
            [
                str(row.get("scoreline"))
                for row in market["reference_scores"]
                if row.get("scoreline")
            ],
        )
        market["candidate"] = False
        market["formal_recommendation"] = False
        return market

    def _analysis_context_from_flat_fixture(self, item: dict[str, Any]) -> dict[str, Any]:
        competition = str(item.get("competition_name") or "世界杯")
        stage = item.get("stage") or item.get("round") or item.get("group")
        competition_cn = f"{competition} · {stage}" if stage else competition
        home_name = str(item.get("home_team_name") or item.get("home_cn") or "主队")
        away_name = str(item.get("away_team_name") or item.get("away_cn") or "客队")
        return {
            "kickoff_utc": item.get("kickoff_utc"),
            "competition_name": competition,
            "competition_cn": competition_cn,
            "home_name": home_name,
            "away_name": away_name,
            "home_cn": home_name,
            "away_cn": away_name,
        }

    def _analysis_context_from_provider_fixture(self, item: dict[str, Any]) -> dict[str, Any]:
        league = item.get("league", {}) if isinstance(item.get("league"), dict) else {}
        fixture = item.get("fixture", {}) if isinstance(item.get("fixture"), dict) else {}
        teams = item.get("teams", {}) if isinstance(item.get("teams"), dict) else {}
        home = teams.get("home", {}) if isinstance(teams.get("home"), dict) else {}
        away = teams.get("away", {}) if isinstance(teams.get("away"), dict) else {}
        competition = str(league.get("name") or "世界杯")
        stage = league.get("round")
        competition_cn = f"{competition} · {stage}" if stage else competition
        home_name = str(home.get("name") or "主队")
        away_name = str(away.get("name") or "客队")
        return {
            "kickoff_utc": fixture.get("date"),
            "competition_name": competition,
            "competition_cn": competition_cn,
            "home_name": home_name,
            "away_name": away_name,
            "home_cn": home_name,
            "away_cn": away_name,
        }

    def _watch_level(self, card: dict[str, Any]) -> int:
        if str(card.get("decision")) == "SKIP":
            return 0
        confidences = [
            float(item.get("confidence", 0.0))
            for item in card.get("markets", [])
            if isinstance(item, dict) and item.get("decision") != "SKIP"
        ]
        confidence = max(confidences, default=0.0)
        return max(1, min(4, round(confidence * 4)))

    def _lean_cn(self, market: dict[str, Any]) -> str | None:
        if market.get("decision") == "SKIP":
            return None
        tendency = str(market.get("tendency") or "")
        line = market.get("line")
        mapping = {
            "HOME_AH": "主队方向",
            "AWAY_AH": "客队方向",
            "OVER": "大球",
            "UNDER": "小球",
            "1H_OVER": "半场有球",
            "1H_UNDER": "半场谨慎",
            "HOME": "主队方向",
            "AWAY": "客队方向",
            "DRAW": "平局方向",
        }
        label = mapping.get(tendency, tendency or None)
        if label and line:
            return f"{label} {line}"
        return label

    def _reason_cn(self, market: dict[str, Any]) -> str:
        reasons = [str(item) for item in market.get("reasons", []) if item]
        if reasons:
            return " + ".join(reasons[:3])
        if market.get("decision") == "SKIP":
            return "数据不足，等待盘口快照与 xG 富集。"
        return "多因素信号形成倾向。"

    def _reference_scores(self, market: dict[str, Any]) -> list[dict[str, Any]]:
        score_card = market.get("score_card")
        if not isinstance(score_card, dict):
            return []
        scenarios = score_card.get("scenarios", [])
        if not isinstance(scenarios, list):
            return []
        rows: list[dict[str, Any]] = []
        for item in scenarios[:3]:
            if not isinstance(item, dict):
                continue
            scoreline = item.get("scoreline")
            if scoreline is None and {"home_goals", "away_goals"} <= set(item):
                scoreline = f"{item['home_goals']}-{item['away_goals']}"
            rows.append(
                {
                    "scoreline": str(scoreline),
                    "conditional_probability": item.get("conditional_probability"),
                }
            )
        return rows

    def odds_timeline(self, fixture_id: str) -> list[dict[str, Any]]:
        dashboard = self.repository.dashboard_fixture(fixture_id)
        if dashboard is not None:
            return [
                {
                    "captured_at": datetime.fromisoformat(
                        str(row["captured_at_utc"]).replace("Z", "+00:00")
                    ),
                    "snapshot_semantics": "CAPTURED_AT",
                    "market": row["market"],
                    "selection": row["selection"],
                    "line": row.get("line"),
                    "decimal_odds": str(row.get("executable_odds")),
                    "bookmaker": row.get("bookmaker"),
                    "bookmaker_count": int(row.get("available_bookmaker_count", 0)),
                    "first_seen": False,
                    "closing": False,
                }
                for row in dashboard.get("value_rows", [])
            ]
        points: list[dict[str, Any]] = []
        first_seen: set[tuple[str, str, str | None, str | None]] = set()
        observations = [
            item
            for item in self.repository.future_market_observations()
            if str(item.get("fixture_id")) == fixture_id
        ]
        observations.sort(
            key=lambda item: (
                str(item.get("captured_at")),
                str(item.get("canonical_market")),
                str(item.get("selection")),
                str(item.get("line")),
                str(item.get("bookmaker_id")),
            )
        )
        for observation in observations:
            identity = (
                str(observation.get("canonical_market")),
                str(observation.get("selection")),
                None if observation.get("line") is None else str(observation.get("line")),
                str(observation.get("bookmaker_id")),
            )
            captured_at = datetime.fromisoformat(
                str(observation["captured_at"]).replace("Z", "+00:00")
            ).astimezone(UTC)
            points.append(
                {
                    "captured_at": captured_at,
                    "snapshot_semantics": "CAPTURED_AT",
                    "market": str(observation.get("canonical_market")),
                    "selection": str(observation.get("selection")),
                    "line": (
                        None
                        if observation.get("line") is None
                        else str(observation.get("line"))
                    ),
                    "decimal_odds": str(observation.get("decimal_odds")),
                    "bookmaker_count": 1,
                    "bookmaker": str(observation.get("bookmaker_name")),
                    "first_seen": identity not in first_seen,
                    "closing": False,
                }
            )
            first_seen.add(identity)
        for snapshot in self.repository.market_snapshots():
            if snapshot["fixture_id"] != fixture_id:
                continue
            probabilities = snapshot.get("power_probabilities") or {}
            for selection, probability in probabilities.items():
                points.append(
                    {
                        "captured_at": datetime.fromisoformat(snapshot["captured_at"]),
                        "snapshot_semantics": "CAPTURED_AT",
                        "market": "ONE_X_TWO",
                        "selection": selection,
                        "line": None,
                        "decimal_odds": f"{1 / probability:.4f}" if probability else None,
                        "bookmaker_count": snapshot.get("bookmaker_count", 0),
                        "first_seen": True,
                        "closing": False,
                    }
                )
        return sorted(points, key=lambda item: item["captured_at"])

    def market_probabilities(self, fixture_id: str) -> dict[str, Any]:
        dashboard = self.repository.dashboard_fixture(fixture_id)
        if dashboard is not None:
            return {
                "probability_type": "market_fair_probability",
                "probabilities": dashboard.get("market_probabilities", {}),
                "source": "POWER devig from append-only dashboard read model",
                "as_of_time": datetime.fromisoformat(str(dashboard["captured_at"])),
                "quality": dashboard.get("data_status", "READY"),
            }
        for snapshot in self.repository.market_snapshots():
            if snapshot["fixture_id"] == fixture_id and snapshot.get("power_probabilities"):
                return {
                    "probability_type": "market_fair_probability",
                    "probabilities": snapshot["power_probabilities"],
                    "source": "POWER devig from captured market snapshot",
                    "as_of_time": datetime.fromisoformat(snapshot["captured_at"]),
                    "quality": snapshot["quality"],
                }
        return {
            "probability_type": "market_fair_probability",
            "probabilities": {},
            "source": "not_available",
            "as_of_time": None,
            "quality": "MARKET_NOT_COMPARABLE",
        }

    def model_probabilities(self, fixture_id: str) -> dict[str, Any]:
        dashboard = self.repository.dashboard_fixture(fixture_id)
        if dashboard is not None:
            return {
                "probability_type": "independent_model_probability",
                "probabilities": dashboard.get("independent_model_probabilities", {}),
                "source": "frozen_stage7b_challenger_dashboard_read_model",
                "as_of_time": datetime.fromisoformat(str(dashboard["captured_at"])),
                "quality": dashboard.get("decision_status", "SKIP"),
                "calibrated": True,
            }
        for lock in self.repository.forward_locks():
            if lock["fixture_id"] == fixture_id:
                return {
                    "probability_type": "independent_model_probability",
                    "probabilities": lock["probabilities"],
                    "source": "frozen_stage7b_challenger",
                    "as_of_time": datetime.fromisoformat(lock["as_of_time"]),
                    "quality": lock["decision"],
                    "calibrated": True,
                }
        return {
            "probability_type": "independent_model_probability",
            "probabilities": {},
            "source": "not_available",
            "as_of_time": None,
            "quality": "SKIP",
            "calibrated": False,
        }

    def data_health(self) -> dict[str, Any]:
        dashboard = self.repository.dashboard_data_health()
        if dashboard is not None:
            return {
                "stale_data_count": int(dashboard.get("stale_data_count", 0)),
                "provider_status": str(dashboard.get("provider_status", "READY")),
                "forward_cycle_age_seconds": dashboard.get("forward_cycle_age_seconds"),
                "gate4_progress": dashboard.get("gate4_progress", {}),
                "generated_at": datetime.fromisoformat(str(dashboard["generated_at"])),
            }
        scheduler = self.repository.stage7e_scheduler()
        gate = load_json(REPORTS / "W2_STAGE7E_FIRST_LIVE_CYCLE.json", {}).get("gate", {})
        provider = self.provider_status()
        finished = scheduler.get("finished_at")
        age = None
        if finished:
            age = int((datetime.now(UTC) - datetime.fromisoformat(finished)).total_seconds())
        stale_count = 0
        now = datetime.now(UTC)
        for item in self.repository.fixture_payloads():
            row = self._fixture_summary(item, "UTC")
            if row["status"] == "NS" and row["kickoff_utc"] < now:
                stale_count += 1
        return {
            "stale_data_count": stale_count,
            "provider_status": str(provider.get("status", "UNKNOWN")),
            "forward_cycle_age_seconds": age,
            "gate4_progress": gate,
            "generated_at": datetime.now(UTC),
        }

    def provider_status(self) -> dict[str, Any]:
        dashboard = self.repository.dashboard_provider()
        if dashboard is not None:
            remaining_quota = dashboard.get("remaining_quota")
            parsed_remaining_quota = parse_int(remaining_quota)
            return {
                "provider": str(dashboard.get("provider", "api_football")),
                "status": str(dashboard.get("status", "READY")),
                "remaining_quota": parsed_remaining_quota,
                "credential_status": str(dashboard.get("credential_status", "PRESENT")),
                "last_request_status": dashboard.get("last_request_status"),
                "last_successful_refresh_at": parse_provider_time(
                    dashboard.get("last_successful_request")
                ),
                "refresh_age_seconds": None,
                "blockers": [],
                "quota_policy": api_football_quota_policy(parsed_remaining_quota),
            }

        db_repository = future_refresh_db_repository()
        if db_repository is not None:
            try:
                projected_db = db_repository.provider_status()
            except Exception:
                projected_db = {}
            if projected_db:
                last_success_db = parse_provider_time(
                    projected_db.get("last_successful_refresh_at")
                )
                remaining_quota = projected_db.get("remaining_quota")
                parsed_remaining_quota = parse_int(remaining_quota)
                return {
                    "provider": "api_football",
                    "status": projected_db.get("status", "READY"),
                    "remaining_quota": parsed_remaining_quota,
                    "credential_status": "PRESENT",
                    "last_request_status": projected_db.get("last_request_status"),
                    "last_successful_refresh_at": last_success_db,
                    "refresh_age_seconds": (
                        int((datetime.now(UTC) - last_success_db).total_seconds())
                        if last_success_db is not None
                        else None
                    ),
                    "blockers": projected_db.get("blockers", []),
                    "quota_policy": api_football_quota_policy(parsed_remaining_quota),
                }
        usage = self.repository.stage7e_usage()
        audit = usage.get("audit") or []
        last = audit[-1] if audit else {}
        remaining_quota = usage.get("remaining_quota")
        parsed_remaining_quota = parse_int(remaining_quota)
        return {
            "provider": "api_football",
            "status": "READY" if parsed_remaining_quota else "UNKNOWN",
            "remaining_quota": parsed_remaining_quota,
            "credential_status": "PRESENT" if usage else "UNKNOWN",
            "last_request_status": last.get("status_code"),
            "last_successful_refresh_at": None,
            "refresh_age_seconds": None,
            "blockers": [],
            "quota_policy": api_football_quota_policy(parsed_remaining_quota),
        }

    def forward_status(self) -> dict[str, Any]:
        dashboard = self.repository.dashboard_forward_status()
        if dashboard is not None:
            return {
                "status": str(dashboard.get("status", "SKIP")),
                "locks": int(dashboard.get("locks", 0)),
                "market_comparable": int(dashboard.get("market_comparable", 0)),
                "current_settled_n": int(dashboard.get("current_settled_n", 0)),
                "target_n": int(dashboard.get("target_n", 50)),
            }
        first = self.repository.stage7e_first_cycle()
        gate = first.get("gate", {})
        return {
            "status": "WATCH",
            "locks": len(self.repository.forward_locks()),
            "market_comparable": first.get("checkpoint", {}).get("market_snapshot_count", 0),
            "current_settled_n": gate.get("current_settled_n", 0),
            "target_n": gate.get("target_n", 50),
        }

    def operations_items(self, name: str) -> list[dict[str, Any]]:
        mapping = {
            "quota": self.provider_status(),
            "tasks": self.repository.stage7e_scheduler(),
            "alerts": {"status": "READY", "items": []},
            "mapping-conflicts": {"status": "READY", "items": []},
            "forward-cycles": self.repository.stage7e_first_cycle(),
            "locks": {"count": len(self.repository.forward_locks())},
            "settlements": {"count": len(self.repository.result_events())},
            "gates": self.repository.stage7e_first_cycle().get("gate", {}),
        }
        payload = mapping.get(name, {})
        return [{"key": name, "status": "READY", "payload": payload}]

    def competition_operations_profile(self, competition_id: str) -> dict[str, Any] | None:
        payload = self.repository.world_cup_profile()
        if payload.get("competition_id") != competition_id:
            return None
        return {
            "competition_id": payload["competition_id"],
            "version": payload["version"],
            "season": payload["season"],
            "hosts": payload["hosts"],
            "neutral_site_policy": payload["neutral_site_policy"],
            "stages": payload["stages"],
            "groups": payload["groups"],
            "knockout_rounds": payload["knockout_rounds"],
            "operations_schedule": payload["operations_schedule"],
            "strategy_version": payload["strategy_version"],
            "freeze_policy": payload["freeze_policy"],
        }

    def world_cup_readiness(self) -> dict[str, Any]:
        return self.repository.world_cup_readiness()

    def leagues(self) -> list[dict[str, Any]]:
        readiness = self.repository.league_readiness()
        output: list[dict[str, Any]] = []
        for competition_id, payload in sorted(readiness.items()):
            audit = payload["audit"]
            latest_season = sorted(audit["seasons"])[-1] if audit["seasons"] else None
            rollover_status = payload["rollover"]["status"]
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
                    "latest_season": latest_season,
                    "blocker": (
                        "MANUAL_REVIEW_REQUIRED"
                        if rollover_status == "MANUAL_REVIEW_REQUIRED"
                        else None
                    ),
                }
            )
        return output

    def league_readiness(self, competition_id: str) -> dict[str, Any] | None:
        readiness = self.repository.league_readiness()
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

    def league_onboarding(self) -> list[dict[str, Any]]:
        items = []
        for summary in self.leagues():
            readiness = self.league_readiness(summary["competition_id"])
            if readiness is not None:
                items.append({"request_id": "", **readiness})
        return items

    def operations_cycles(self) -> list[dict[str, Any]]:
        return list(self.repository.operations_report().get("cycles", []))

    def operations_latest(self) -> dict[str, Any]:
        cycles = self.operations_cycles()
        return cycles[-1] if cycles else {}

    def releases_readiness(self) -> dict[str, Any]:
        release = self.repository.release_readiness()
        return {
            "approval_status": release.get("approval_status", "PRODUCTION_RELEASE_DISABLED"),
            "production_release": release.get("production_release", "DISABLED"),
            "dependency_blocker": release.get("dependency_blocker"),
        }

    def retention_status(self) -> dict[str, Any]:
        operations = self.repository.operations_report()
        return {
            "status": "DRY_RUN_ONLY",
            "policy": operations.get("retention", {}),
        }

    def shadow_strategy_status(self) -> dict[str, Any]:
        return self.repository.shadow_strategy_status()

    def shadow_strategy_locks(self) -> list[dict[str, Any]]:
        return self.repository.shadow_strategy_locks()

    def shadow_strategy_evaluations(self) -> list[dict[str, Any]]:
        return self.repository.shadow_strategy_evaluations()

    def shadow_strategy_replay(self) -> dict[str, Any]:
        return self.repository.shadow_strategy_replay()

    def gate5_preflight(self) -> dict[str, Any]:
        return self.repository.gate5_preflight()

    def w1_w2_shadow_comparison(self) -> dict[str, Any]:
        return self.repository.w1_w2_shadow_comparison()

    def _all_matchday_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for card in self.repository.matchday_cards():
            with suppress(Exception):
                rows.append(self._matchday_item(card))
        return rows

    def _future_fixture_rows_with_errors(self) -> tuple[list[dict[str, Any]], int]:
        rows: list[dict[str, Any]] = []
        parse_error_count = 0
        for item in self._cached_fixture_payloads():
            try:
                row = self._fixture_summary(item, BEIJING_TZ)
            except Exception:
                parse_error_count += 1
                continue
            row["_dashboard_source"] = "future_fixture_payload"
            rows.append(row)
        return rows, parse_error_count

    def _filter_rows_for_operational_date(
        self,
        rows: list[dict[str, Any]],
        *,
        requested_date: date,
    ) -> list[dict[str, Any]]:
        return [
            row
            for row in rows
            if str(row.get("operational_date_beijing") or "") == requested_date.isoformat()
        ]

    def _filter_rows_for_next36(
        self,
        rows: list[dict[str, Any]],
        *,
        now_utc: datetime | None = None,
    ) -> list[dict[str, Any]]:
        start, end = next_36_hours_window(now_utc)
        filtered: list[dict[str, Any]] = []
        for row in rows:
            kickoff = self._row_kickoff_utc(row)
            if kickoff is not None and start <= kickoff < end:
                filtered.append(row)
        return filtered

    def _row_kickoff_utc(self, row: dict[str, Any]) -> datetime | None:
        value = row.get("kickoff_utc")
        if isinstance(value, datetime):
            return value.astimezone(UTC)
        return parse_provider_time(value)

    def _dedupe_dashboard_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for row in rows:
            fixture_id = str(row.get("fixture_id") or "")
            if not fixture_id or fixture_id in seen:
                continue
            seen.add(fixture_id)
            deduped.append(row)
        return deduped

    def _dashboard_card_from_matchday(self, row: dict[str, Any]) -> dict[str, Any]:
        fixture_id = str(row.get("fixture_id") or "")
        analysis: dict[str, Any] | None = None
        if fixture_id and row.get("_dashboard_source") == "future_fixture_payload":
            item = self._fixture_payload_by_id(fixture_id)
            if item is not None:
                analysis = self._analysis_card_from_provider_payload(fixture_id, item)
        elif fixture_id:
            analysis = self.analysis_card(fixture_id)
        card = analysis or self._fallback_analysis_card(
            fixture_id=fixture_id or "unknown-fixture",
            market_coverage={},
            source=str(row.get("_dashboard_source") or "dashboard_without_analysis_card"),
            fixture_context={
                "kickoff_utc": row.get("kickoff_utc"),
                "competition_name": row.get("competition_name"),
                "competition_cn": row.get("competition_name"),
                "home_name": row.get("home_team_name"),
                "away_name": row.get("away_team_name"),
                "home_cn": row.get("home_team_name"),
                "away_cn": row.get("away_team_name"),
            },
        )
        markets = [
            item
            for item in card.get("markets", [])
            if isinstance(item, dict)
        ]
        picked = next((item for item in markets if str(item.get("decision")) == "PICK"), None)
        scoreline_picks = scoreline_picks_from_card(card)
        result = result_from_dashboard_row(row)
        analysis_readiness = build_analysis_readiness(
            card,
            fixture_status=normalize_match_status(row.get("status")),
            result=result,
            scoreline_picks=scoreline_picks,
        )
        recommendation = build_recommendation(card, picked)
        if recommendation is None:
            recommendation = build_watch_recommendation(
                readiness=analysis_readiness,
                fixture_status=normalize_match_status(row.get("status")),
            )
        validation = validate_recommendation(
            fixture_id=fixture_id,
            recommendation=recommendation,
            result=result,
            scoreline_picks=scoreline_picks,
        )
        raw_status = row.get("status")
        return {
            "fixture_id": fixture_id,
            "kickoff_utc": row.get("kickoff_utc") or card.get("kickoff_utc"),
            "kickoff_beijing": row.get("kickoff_beijing"),
            "operational_date_beijing": row.get("operational_date_beijing"),
            "competition_id": row.get("competition_id"),
            "competition_name": card.get("competition_cn") or row.get("competition_name"),
            "home_team_name": card.get("home_cn") or row.get("home_team_name"),
            "away_team_name": card.get("away_cn") or row.get("away_team_name"),
            "status": normalize_match_status(raw_status),
            "raw_status": raw_status,
            "data_state": row.get("data_health") or row.get("data_state"),
            "lifecycle_state": row.get("action") or row.get("lifecycle_state"),
            "watch_level": card.get("watch_level", 0),
            "data_readiness": card.get("data_readiness", {}),
            "analysis_readiness": analysis_readiness,
            "recommendation": recommendation,
            "scoreline_picks": scoreline_picks,
            "result": result,
            "validation": validation,
            "current_odds": card.get("current_odds", {}),
            "odds_movement": card.get("line_movement", {}),
            "market_strip": markets,
            "bookmaker_intent": card.get("bookmaker_intent", {}),
            "pricing_shadow": card.get("pricing_shadow"),
            "missing_inputs": self._missing_inputs_from_analysis_card(card),
            "candidate": bool(recommendation.get("candidate")) if recommendation else False,
            "formal_recommendation": bool(recommendation.get("formal_recommendation"))
            if recommendation
            else False,
        }

    def _recommendation_from_analysis_market(
        self,
        card: dict[str, Any],
        market: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        return build_recommendation(card, market)

    def _scoreline_picks_from_card(self, card: dict[str, Any]) -> list[dict[str, Any]]:
        return scoreline_picks_from_card(card)

    def _missing_inputs_from_analysis_card(self, card: dict[str, Any]) -> list[str]:
        readiness = card.get("data_readiness", {})
        if not isinstance(readiness, dict):
            return []
        missing: list[str] = []
        if not readiness.get("bookmakers") and not readiness.get("odds_snapshots"):
            missing.append("盘口快照")
        if not readiness.get("xg"):
            missing.append("xG")
        if not readiness.get("h2h"):
            missing.append("交锋")
        if not readiness.get("lineups"):
            missing.append("首发")
        return missing

    def _dashboard_performance(self, cards: list[dict[str, Any]]) -> dict[str, Any]:
        return dashboard_performance(cards)

    def _dashboard_debug(
        self,
        *,
        counts: dict[str, int],
        requested_date: date,
        selected_rows: list[dict[str, Any]],
        future_rows: list[dict[str, Any]],
        future_parse_error_count: int,
        include: bool,
    ) -> dict[str, Any]:
        if not include:
            return {}
        future_stats = self._future_fixture_debug_stats(
            future_rows,
            requested_date=requested_date,
            parse_error_count=future_parse_error_count,
        )
        next_available = self._next_available_date(requested_date, future_rows=future_rows)
        empty_reason = None
        empty_detail = None
        if not any(counts.values()):
            empty_reason = "READ_MODEL_EMPTY"
        elif not selected_rows:
            empty_reason = "SELECTED_DATE_EMPTY"
            if counts.get("future_fixture_count", 0) > 0:
                empty_detail = (
                    "Future fixture payloads exist, but none fall inside the selected dashboard "
                    "window after kickoff/status parsing."
                )
        return {
            **counts,
            **future_stats,
            "selected_date": requested_date.isoformat(),
            "selected_date_has_data": bool(selected_rows),
            "next_available_date": next_available,
            "empty_reason": empty_reason,
            "empty_detail": empty_detail,
            "suggested_actions": [
                "run staging seed if this is a preview environment",
                "check ingestion and future-refresh request audit",
                "check read-model checkpoints",
                "check selected dashboard date/window",
            ],
        }

    def _next_available_date(
        self,
        requested_date: date,
        *,
        future_rows: list[dict[str, Any]] | None = None,
    ) -> str | None:
        dates: list[date] = []
        for row in [*self._all_matchday_rows(), *(future_rows or [])]:
            raw = row.get("operational_date_beijing")
            try:
                if raw:
                    dates.append(date.fromisoformat(str(raw)))
            except ValueError:
                continue
        future_dates = sorted(value for value in dates if value >= requested_date)
        return future_dates[0].isoformat() if future_dates else None

    def _future_fixture_debug_stats(
        self,
        rows: list[dict[str, Any]],
        *,
        requested_date: date,
        parse_error_count: int,
    ) -> dict[str, Any]:
        status_distribution: dict[str, int] = {}
        date_distribution: dict[str, int] = {}
        kickoffs: list[datetime] = []
        in_window = 0
        for row in rows:
            status = str(row.get("status") or "UNKNOWN")
            status_distribution[status] = status_distribution.get(status, 0) + 1
            operational_date = str(row.get("operational_date_beijing") or "UNKNOWN")
            date_distribution[operational_date] = date_distribution.get(operational_date, 0) + 1
            kickoff = self._row_kickoff_utc(row)
            if kickoff is None:
                continue
            kickoffs.append(kickoff)
            if operational_date == requested_date.isoformat():
                in_window += 1
        sorted_dates = dict(sorted(date_distribution.items())[:20])
        return {
            "future_fixture_in_window_count": in_window,
            "future_fixture_parse_error_count": parse_error_count,
            "future_fixture_status_distribution": dict(sorted(status_distribution.items())),
            "future_fixture_date_distribution": sorted_dates,
            "future_fixture_min_kickoff_utc": min(kickoffs).isoformat().replace("+00:00", "Z")
            if kickoffs
            else None,
            "future_fixture_max_kickoff_utc": max(kickoffs).isoformat().replace("+00:00", "Z")
            if kickoffs
            else None,
        }

    def _seed_dashboard_response(
        self,
        seed: dict[str, Any],
        *,
        requested_date: date,
        window: str,
        timezone: str,
        version: dict[str, Any],
        counts: dict[str, int],
        include_debug: bool,
    ) -> dict[str, Any]:
        cards = [
            item
            for item in seed.get("all", seed.get("upcoming", []))
            if isinstance(item, dict)
        ]
        debug = {
            **counts,
            "selected_date": requested_date.isoformat(),
            "selected_date_has_data": bool(cards),
            "next_available_date": requested_date.isoformat() if cards else None,
            "empty_reason": None if cards else "STAGING_SEED_EMPTY",
            "suggested_actions": ["staging seed is active; run live ingestion for real data"],
        } if include_debug else {}
        return {
            "generated_at": datetime.now(UTC),
            "date": requested_date.isoformat(),
            "timezone": timezone,
            "window": window,
            "data_profile": "staging-seed",
            "data_source": "staging-json-fallback",
            "version": {
                "api_git_sha": version["api_git_sha"],
                "release_id": version["release_id"],
            },
            "debug": debug,
            "performance": self._dashboard_performance(cards),
            "recommendations": [card for card in cards if card.get("recommendation")],
            "upcoming": cards,
            "finished": [],
            "all": cards,
        }

    def _fixture_summary(self, item: dict[str, Any], timezone: str) -> dict[str, Any]:
        if "_dashboard" in item:
            dashboard = cast(dict[str, Any], item["_dashboard"])
            return self._dashboard_fixture_summary(dashboard, timezone)
        fixture = item.get("fixture", {})
        league = item.get("league", {})
        teams = item.get("teams", {})
        home = teams.get("home", {}) if isinstance(teams.get("home"), dict) else {}
        away = teams.get("away", {}) if isinstance(teams.get("away"), dict) else {}
        kickoff = datetime.fromisoformat(str(fixture.get("date")).replace("Z", "+00:00"))
        kickoff = kickoff.astimezone(UTC)
        display_tz = ZoneInfo(timezone)
        beijing = self.date_resolver.annotate(kickoff)
        return {
            "fixture_id": str(fixture.get("id")),
            "competition_id": str(league.get("id")),
            "competition_name": str(league.get("name")),
            "kickoff_utc": kickoff,
            "kickoff_beijing": beijing["kickoff_beijing"],
            "operational_date_beijing": beijing["operational_date_beijing"],
            "kickoff_display": kickoff.astimezone(display_tz).isoformat(),
            "status": str(fixture.get("status", {}).get("short")),
            "home_team_id": str(home.get("id")),
            "home_team_name": home.get("name"),
            "away_team_id": str(away.get("id")),
            "away_team_name": away.get("name"),
            "lifecycle_state": (
                "WATCH" if fixture.get("status", {}).get("short") == "NS" else "DATA"
            ),
            "data_state": "CAPTURED_AT",
            "_result": result_from_provider_fixture(item),
        }

    def _dashboard_fixture_summary(self, item: dict[str, Any], timezone: str) -> dict[str, Any]:
        kickoff = datetime.fromisoformat(str(item["kickoff_utc"]).replace("Z", "+00:00"))
        kickoff = kickoff.astimezone(UTC)
        display_tz = ZoneInfo(timezone)
        beijing = self.date_resolver.annotate(kickoff)
        return {
            "fixture_id": str(item["fixture_id"]),
            "competition_id": str(item["competition_id"]),
            "competition_name": str(item["competition_name"]),
            "kickoff_utc": kickoff,
            "kickoff_beijing": beijing["kickoff_beijing"],
            "operational_date_beijing": beijing["operational_date_beijing"],
            "kickoff_display": kickoff.astimezone(display_tz).isoformat(),
            "status": str(item["status"]),
            "home_team_id": str(item["home_team_id"]),
            "home_team_name": item.get("home_team_name"),
            "away_team_id": str(item["away_team_id"]),
            "away_team_name": item.get("away_team_name"),
            "lifecycle_state": str(item.get("decision_status", "SKIP")),
            "data_state": str(item.get("data_status", "CAPTURED_AT")),
            "published_grade": item.get("published_grade") or item.get("research_grade"),
            "primary_market": item.get("primary_market"),
            "primary_line": item.get("primary_line"),
            "primary_odds": self._optional_string(item.get("primary_executable_odds")),
            "last_captured": self._optional_datetime(item.get("captured_at")),
            "_result": result_from_dashboard_row(item),
        }

    def _optional_string(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    def _optional_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    def _matchday_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        fixture = cast(dict[str, Any], payload.get("fixture", {}))
        card = cast(dict[str, Any], payload.get("card", {}))
        temporal = cast(dict[str, Any], payload.get("temporal", {}))
        primary = cast(dict[str, Any] | None, card.get("primary_market_direction"))
        kickoff = datetime.fromisoformat(str(fixture.get("kickoff_utc")).replace("Z", "+00:00"))
        beijing = self.date_resolver.annotate(kickoff)
        return {
            "fixture_id": str(fixture.get("fixture_id")),
            "competition_id": str(fixture.get("competition_id")),
            "competition_name": str(fixture.get("competition_name")),
            "kickoff_utc": fixture.get("kickoff_utc"),
            "kickoff_beijing": beijing["kickoff_beijing"],
            "operational_date_beijing": beijing["operational_date_beijing"],
            "status": fixture.get("status"),
            "home_team_id": str(fixture.get("home_team_id")),
            "home_team_name": fixture.get("home_team_name"),
            "away_team_id": str(fixture.get("away_team_id")),
            "away_team_name": fixture.get("away_team_name"),
            "published_grade": card.get("published_grade"),
            "action": card.get("action"),
            "primary_market": primary.get("market") if primary else None,
            "primary_selection": primary.get("selection") if primary else None,
            "primary_line": primary.get("line") if primary else None,
            "primary_odds": primary.get("executable_decimal_odds") if primary else None,
            "last_captured": temporal.get("source_captured_at") or fixture.get("last_captured"),
            "data_health": fixture.get("data_health"),
            "temporal_status": temporal.get("temporal_status"),
            "integrity_status": payload.get("integrity", {}).get("integrity_status"),
            "formal_recommendation": False,
            "candidate": False,
            "_result": result_from_dashboard_row(fixture),
        }
