from __future__ import annotations

import json
import math
import os
from contextlib import suppress
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import monotonic
from typing import Any, cast
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from w2.analysis.market_movement import (
    build_bookmaker_hypothesis,
    build_market_divergence,
    build_market_movement,
    build_market_timeline_reference,
)
from w2.competitions.registry import CompetitionRegistry, CompetitionRegistryError
from w2.config import Environment, get_settings
from w2.dashboard.date_window import (
    FOOTBALL_DAY_CUTOFF_HOUR,
    FOOTBALL_DAY_TZ,
    default_football_day,
    football_day_window,
)
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
from w2.dashboard.scorelines import scoreline_picks_from_card, scoreline_reference_from_card
from w2.dashboard.status_labels import (
    lineups_status_label,
    provider_status_label,
    xg_status_label,
)
from w2.dashboard.validation import validate_recommendation
from w2.dashboard.validation_summary import validation_summary
from w2.domain.decision_adapter import build_decision_contract_fields
from w2.domain.recommendation_capabilities import load_recommendation_capability_manifest
from w2.domain.recommendation_decision_v3 import project_decision_v3
from w2.features.engine import FeatureInputs, build_feature_set
from w2.features.framework import FeatureContext
from w2.features.live_factors import TeamXgSnapshot
from w2.features.market_factors import BookmakerQuote
from w2.features.team_factors import TeamMatchHistory, TeamRatingSnapshot, TeamValueSnapshot
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.shadow_strategy_models import (
    ShadowStrategyEvaluationModel,
    ShadowStrategyLockModel,
    ShadowStrategyRunModel,
)
from w2.ingestion.future_refresh import parse_line
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.ingestion.market_timeline import DEFAULT_TIMELINE_DIR, load_timeline, timeline_path
from w2.lineups.intelligence import (
    LineupGate,
    audited_coverage_rate,
    lineup_market_policy,
    lineup_requirement,
)
from w2.markets.asian_handicap_mainline import (
    CANONICAL_AH_MAINLINE_POLICY,
    select_canonical_ah_mainline,
)
from w2.markets.asian_handicap_scope import (
    is_full_time_asian_handicap_observation,
    is_full_time_totals_observation,
)
from w2.markets.market_candidate import build_market_candidates
from w2.markets.movement import MarketSnapshot
from w2.markets.poisson import (
    INDEPENDENT_XG_POISSON_MODEL_VERSION,
    IndependentXgPoissonOutput,
    independent_xg_poisson,
)
from w2.markets.quote_identity import (
    evaluate_quote_freshness,
    project_quote_identity,
    unavailable_quote_identity,
)
from w2.matchday.coverage import MatchdayCoverageReconciler
from w2.matchday.timezone import (
    BEIJING_TZ,
    BeijingOperationalDayPolicy,
    FixtureOperationalDateResolver,
    next_36_hours_window,
)
from w2.operations.leagues import run_top_five_audit
from w2.operations.observability import default_metric_registry
from w2.operations.release_evidence import build_release_identity
from w2.operations.tournament import (
    build_operations_plan,
    load_stage5b_world_cup_fixtures,
    load_tournament_profile,
    readiness_report,
)
from w2.pricing.shadow import build_pricing_shadow
from w2.providers.quota import api_football_quota_policy, parse_int
from w2.ratings.elo import rating_from_history
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
from w2.strategy.formal_recommendation import (
    AH_MAINLINE_STALE_MATERIALIZATION,
    ah_display_contract,
    build_formal_recommendation,
    canonical_ah_market,
    formal_recommendation_id,
    formal_recommendations_enabled,
)
from w2.strategy.market_selector import apply_market_selection, enrich_secondary_evidence
from w2.strategy.score_scenarios import Direction
from w2.strategy.simulate import SimulationInputs, SimulationOutput, run_simulation
from w2.tracking.formal_results import (
    endpoint_summary as formal_tracking_endpoint_summary,
)
from w2.tracking.formal_results import (
    load_settlements as load_formal_settlements,
)
from w2.tracking.formal_results import (
    load_snapshots as load_formal_snapshots,
)
from w2.tracking.forward_ledger_performance import forward_ledger_performance

ROOT = Path(os.getenv("W2_APP_ROOT", Path(__file__).resolve().parents[3])).resolve()
REPORTS = ROOT / "reports"
RUNTIME = Path(os.getenv("W2_RUNTIME_ROOT", ROOT / "runtime")).resolve()
FORWARD_LEDGER_LEGACY_RECOVERY = (
    ROOT / "config/policies/forward_ledger_legacy_recovery.staging.v1.json"
)
MAX_PUBLIC_FIXTURES = 512
WORLD_CUP_PROFILE = ROOT / "config/competitions/world_cup_2026.v1.json"
WORLD_CUP_FIXTURES = RUNTIME / "stage5b/processed/national_fixtures_cleaned.json"
STAGING_DASHBOARD_SEED = RUNTIME / "dashboard/staging_seed_dashboard.json"
BALANCED_MAINLINE_MAX_DISTANCE = 0.06
BALANCED_MAINLINE_MIN_DELTA = 0.03

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

LOCKED_PREMATCH_STATUSES = {"LIVE", "FINISHED"}


def load_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _parse_utc_text(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _next_future_evaluation(values: list[Any], *, now: datetime) -> str | None:
    candidates: list[tuple[datetime, str]] = []
    for value in values:
        parsed = _parse_utc_text(value)
        if parsed is not None and parsed > now:
            candidates.append((parsed, parsed.isoformat().replace("+00:00", "Z")))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def _truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False


def _runtime_ah_mainline_recompute_enabled() -> bool:
    return _truthy_flag(os.getenv("W2_RECOMPUTE_AH_MAINLINE_AT_READ"))


def _optional_truthy_flag(value: Any) -> bool | None:
    if value is None:
        return None
    return _truthy_flag(value)


def _fixture_neutral_site(item: dict[str, Any]) -> bool:
    league = item.get("league", {}) if isinstance(item.get("league"), dict) else {}
    explicit = _explicit_neutral_site(item)
    profile = load_json(WORLD_CUP_PROFILE, {})
    policy = str(profile.get("neutral_site_policy") or "")
    if _is_world_cup_2026_item(item, profile=profile, league=league) and policy:
        if "HOST_COUNTRY_MATCHES_ARE_NOT_NEUTRAL_FOR_HOST" in policy:
            home_name, away_name = _team_names_from_item(item)
            if _is_host_team(home_name, profile=profile):
                return False
            if _is_host_team(away_name, profile=profile):
                return True
        if "OTHER_MATCHES_NEUTRAL_BY_VENUE_CONTEXT" in policy:
            return explicit if explicit is not None else True
    return explicit if explicit is not None else False


def _explicit_neutral_site(item: dict[str, Any]) -> bool | None:
    fixture = item.get("fixture", {})
    dashboard = item.get("_dashboard", {})
    venue = fixture.get("venue", {}) if isinstance(fixture, dict) else {}
    candidates: tuple[Any, ...] = (
        item.get("neutral_site"),
        item.get("neutral"),
        dashboard.get("neutral_site") if isinstance(dashboard, dict) else None,
        dashboard.get("neutral") if isinstance(dashboard, dict) else None,
        fixture.get("neutral_site") if isinstance(fixture, dict) else None,
        fixture.get("neutral") if isinstance(fixture, dict) else None,
        venue.get("neutral_site") if isinstance(venue, dict) else None,
        venue.get("neutral") if isinstance(venue, dict) else None,
    )
    for value in candidates:
        parsed = _optional_truthy_flag(value)
        if parsed is not None:
            return parsed
    return None


def _is_world_cup_2026_item(
    item: dict[str, Any],
    *,
    profile: dict[str, Any],
    league: dict[str, Any],
) -> bool:
    provider_mapping = profile.get("provider_mapping", {})
    provider_league_id = (
        str(provider_mapping.get("api_football_league_id"))
        if isinstance(provider_mapping, dict)
        else ""
    )
    provider_season = (
        str(provider_mapping.get("api_football_season"))
        if isinstance(provider_mapping, dict)
        else ""
    )
    competition_id = str(profile.get("competition_id") or "world_cup_2026")
    identifiers = {
        str(item.get("competition_id") or ""),
        str(league.get("id") or ""),
    }
    names = {
        str(item.get("competition_name") or "").lower(),
        str(league.get("name") or "").lower(),
    }
    season = str(league.get("season") or item.get("season") or "")
    return (
        competition_id in identifiers
        or (
            provider_league_id in identifiers and (not provider_season or season == provider_season)
        )
        or any("world cup" in name or "世界杯" in name for name in names)
    )


def _team_names_from_item(item: dict[str, Any]) -> tuple[str, str]:
    teams = item.get("teams", {}) if isinstance(item.get("teams"), dict) else {}
    home = teams.get("home", {}) if isinstance(teams.get("home"), dict) else {}
    away = teams.get("away", {}) if isinstance(teams.get("away"), dict) else {}
    home_name = str(item.get("home_team_name") or home.get("name") or "")
    away_name = str(item.get("away_team_name") or away.get("name") or "")
    return home_name, away_name


def _is_host_team(name: str, *, profile: dict[str, Any]) -> bool:
    normalized = _normalize_team_name(name)
    hosts = profile.get("hosts", [])
    if not isinstance(hosts, list):
        hosts = []
    host_names = {_normalize_team_name(value) for value in hosts}
    host_aliases = {
        "unitedstates": {"usa", "us", "unitedstates", "unitedstatesofamerica"},
    }
    for host_name in list(host_names):
        host_names.update(host_aliases.get(host_name, set()))
    return normalized in host_names


def _normalize_team_name(value: Any) -> str:
    return "".join(char for char in str(value).lower() if char.isalnum())


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


def run_simulation_from_shadow(payload: Any) -> SimulationOutput | None:
    if not isinstance(payload, dict):
        return None
    simulation = payload.get("simulation")
    if not isinstance(simulation, dict) or not simulation.get("status"):
        return None
    scoreline_picks: list[dict[str, Any]] = (
        cast(list[dict[str, Any]], simulation.get("scoreline_picks"))
        if isinstance(simulation.get("scoreline_picks"), list)
        else []
    )
    score_matrix_summary: dict[str, Any] = (
        cast(dict[str, Any], simulation.get("score_matrix_summary"))
        if isinstance(simulation.get("score_matrix_summary"), dict)
        else {}
    )
    ah_probabilities: dict[str, Any] = (
        cast(dict[str, Any], simulation.get("ah_probabilities"))
        if isinstance(simulation.get("ah_probabilities"), dict)
        else {}
    )
    ou_probabilities: dict[str, Any] = (
        cast(dict[str, Any], simulation.get("ou_probabilities"))
        if isinstance(simulation.get("ou_probabilities"), dict)
        else {}
    )
    input_readiness: dict[str, Any] = (
        cast(dict[str, Any], simulation.get("input_readiness"))
        if isinstance(simulation.get("input_readiness"), dict)
        else {}
    )
    calibration: dict[str, Any] = (
        cast(dict[str, Any], simulation.get("calibration"))
        if isinstance(simulation.get("calibration"), dict)
        else {}
    )
    return SimulationOutput(
        model_version=str(simulation.get("model_version") or ""),
        calibration_version=simulation.get("calibration_version")
        if simulation.get("calibration_version") is not None
        else None,
        calibration_status=simulation.get("calibration_status")
        if simulation.get("calibration_status") is not None
        else None,
        lambda_home=_float_or_none(simulation.get("lambda_home")),
        lambda_away=_float_or_none(simulation.get("lambda_away")),
        lambda_sigma_home=_float_or_none(simulation.get("lambda_sigma_home")),
        lambda_sigma_away=_float_or_none(simulation.get("lambda_sigma_away")),
        fair_ah=_float_or_none(simulation.get("fair_ah")),
        fair_ou=_float_or_none(simulation.get("fair_ou")),
        scoreline_picks=scoreline_picks,
        score_matrix_summary=score_matrix_summary,
        ah_probabilities=ah_probabilities,
        ou_probabilities=ou_probabilities,
        input_readiness=input_readiness,
        status=str(simulation.get("status")),
        simulations=int(simulation.get("simulations") or 0),
        seed=int(simulation.get("seed") or 0),
        calibration=calibration,
    )


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _valid_formal_recommendation_payload(value: Any) -> bool:
    recommendation = value if isinstance(value, dict) else {}
    tier = str(recommendation.get("tier") or "").upper()
    if tier != "FORMAL" and recommendation.get("formal_recommendation") is not True:
        return False
    if str(recommendation.get("market") or "").upper() != "ASIAN_HANDICAP":
        return False
    if str(recommendation.get("selection") or "").upper() not in {"HOME_AH", "AWAY_AH"}:
        return False
    if _float_or_none(recommendation.get("line")) is None:
        return False
    odds = recommendation.get("odds")
    return odds is None or _float_or_none(odds) is not None


def _formal_payload_blocker(formal_result: Any) -> str:
    reason = getattr(formal_result, "formal_suppressed_reason", None)
    if reason:
        return str(reason)
    return "INVALID_FORMAL_RECOMMENDATION_PAYLOAD"


class ReadModelRepository:
    def analysis_card_canary_artifact(self, fixture_id: str) -> Any:
        from w2.api.frozen_analysis import read_frozen_analysis_artifact

        return read_frozen_analysis_artifact(create_engine(), fixture_id)

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

    def fixture_payload(self, fixture_id: str) -> dict[str, Any] | None:
        dashboard = self.dashboard_fixture(fixture_id)
        if dashboard is not None:
            return self._dashboard_fixture_to_provider_payload(dashboard)
        db_repository = future_refresh_db_repository()
        reader = getattr(db_repository, "fixture_payload", None) if db_repository else None
        if callable(reader):
            try:
                return cast(dict[str, Any] | None, reader(fixture_id, payload_limit=32))
            except Exception:
                return None
        if db_repository is not None and get_settings().environment in {
            Environment.LOCAL,
            Environment.TEST,
        }:
            offline_reader = getattr(db_repository, "fixture_payloads", None)
            if callable(offline_reader):
                with suppress(Exception):
                    return next(
                        (
                            item
                            for item in offline_reader()
                            if str(item.get("fixture", {}).get("id") or "") == fixture_id
                        ),
                        None,
                    )
        return None

    def public_fixture_payloads(self, *, limit: int = 512) -> list[dict[str, Any]]:
        bounded_limit = max(0, min(int(limit), 1024))
        fixtures: dict[str, dict[str, Any]] = {}
        for item in self.dashboard_latest_fixtures()[:bounded_limit]:
            fixture_id = str(item.get("fixture_id") or "")
            if fixture_id:
                fixtures[fixture_id] = self._dashboard_fixture_to_provider_payload(item)
        db_repository = future_refresh_db_repository()
        reader = (
            getattr(db_repository, "fixture_payloads_bounded", None)
            if db_repository is not None
            else None
        )
        if callable(reader):
            with suppress(Exception):
                for item in reader(payload_limit=32, item_limit=bounded_limit):
                    fixture_id = str(item.get("fixture", {}).get("id") or "")
                    if fixture_id:
                        fixtures[fixture_id] = item
        elif db_repository is not None and get_settings().environment in {
            Environment.LOCAL,
            Environment.TEST,
        }:
            offline_reader = getattr(db_repository, "fixture_payloads", None)
            if callable(offline_reader):
                with suppress(Exception):
                    for item in offline_reader()[:bounded_limit]:
                        fixture_id = str(item.get("fixture", {}).get("id") or "")
                        if fixture_id:
                            fixtures[fixture_id] = item
        return sorted(fixtures.values(), key=lambda item: item.get("fixture", {}).get("date", ""))

    def market_snapshots_for_fixture(self, fixture_id: str) -> list[dict[str, Any]]:
        db_repository = future_refresh_db_repository()
        reader = (
            getattr(db_repository, "market_snapshots_for_fixture", None)
            if db_repository is not None
            else None
        )
        if callable(reader):
            with suppress(Exception):
                return cast(list[dict[str, Any]], reader(fixture_id))
        if db_repository is not None and get_settings().environment in {
            Environment.LOCAL,
            Environment.TEST,
        }:
            offline_reader = getattr(db_repository, "market_snapshots", None)
            if callable(offline_reader):
                with suppress(Exception):
                    return [
                        row
                        for row in offline_reader()
                        if str(row.get("fixture_id") or "") == fixture_id
                    ]
        return []

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
        fixture_ids = list(dict.fromkeys(fixture_id for fixture_id in fixture_ids if fixture_id))
        if not fixture_ids or len(fixture_ids) > 64:
            return []
        db_repository = future_refresh_db_repository()
        if db_repository is not None:
            reader = getattr(db_repository, "latest_market_observations_for_fixtures", None)
            if callable(reader):
                return cast(list[dict[str, Any]], reader(fixture_ids))
            if get_settings().environment in {Environment.LOCAL, Environment.TEST}:
                offline_reader = getattr(db_repository, "latest_market_observations", None)
                if callable(offline_reader):
                    allowed = set(fixture_ids)
                    return [
                        row
                        for row in offline_reader()
                        if str(row.get("fixture_id") or "") in allowed
                    ]
        return []

    def public_market_refresh_status(
        self,
        fixture_ids: list[str],
    ) -> dict[str, str | None]:
        ids = [fixture_id for fixture_id in dict.fromkeys(fixture_ids) if fixture_id]
        if not ids or len(ids) > 64:
            return {"odds_last_confirmed_at": None, "next_refresh_tick": None}
        db_repository = future_refresh_db_repository()
        reader = (
            getattr(db_repository, "market_refresh_status_for_fixtures", None)
            if db_repository is not None
            else None
        )
        if callable(reader):
            with suppress(Exception):
                return cast(dict[str, str | None], reader(ids))
        return {"odds_last_confirmed_at": None, "next_refresh_tick": None}

    def public_next_market_refresh_by_fixture(
        self,
        fixture_ids: list[str],
    ) -> dict[str, str]:
        ids = [fixture_id for fixture_id in dict.fromkeys(fixture_ids) if fixture_id]
        if not ids or len(ids) > 64:
            return {}
        db_repository = future_refresh_db_repository()
        reader = (
            getattr(db_repository, "next_market_refresh_by_fixture", None)
            if db_repository is not None
            else None
        )
        if callable(reader):
            with suppress(Exception):
                return cast(dict[str, str], reader(ids))
        return {}

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

    def public_release_counts(self, *, limit: int = MAX_PUBLIC_FIXTURES) -> dict[str, int]:
        bounded_limit = max(0, min(int(limit), MAX_PUBLIC_FIXTURES))
        return {
            "read_model_fixture_count": len(self.dashboard_latest_fixtures()[:bounded_limit]),
            "matchday_card_count": len(self.matchday_cards()[:bounded_limit]),
            "future_fixture_count": len(self.public_fixture_payloads(limit=bounded_limit)),
            "result_event_count": len(self.result_events()[:bounded_limit]),
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
            "status": run_state if run_state != "COMPLETED_WITH_RESULTS" else "SHADOW_READY",
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
        self._formal_snapshots_by_fixture_cache: dict[str, list[dict[str, Any]]] | None = None
        self._formal_settlements_by_snapshot_cache: dict[str, dict[str, Any]] | None = None
        self._dashboard_response_cache: dict[
            tuple[str, str, str, bool, bool], tuple[float, dict[str, Any]]
        ] = {}
        self._bounded_public_request = False
        self._analysis_evaluation_time_override: datetime | None = None

    def _reset_read_caches(self) -> None:
        self._fixture_payloads_cache = None
        self._fixture_payload_index_cache = None
        self._future_market_observations_cache = None
        self._observations_by_fixture_cache = None
        self._team_xg_snapshots_by_fixture_cache = {}
        self._team_xg_matches_cache = None
        self._raw_payloads_by_endpoint_cache = {}
        self._formal_snapshots_by_fixture_cache = None
        self._formal_settlements_by_snapshot_cache = None

    def _future_refresh_repository(self) -> FutureRefreshDbRepository | None:
        if self._future_refresh_repository_cache is None:
            self._future_refresh_repository_cache = future_refresh_db_repository()
        return self._future_refresh_repository_cache

    def _cached_fixture_payloads(self) -> list[dict[str, Any]]:
        if self._fixture_payloads_cache is None:
            fixture_reader = getattr(
                self.repository,
                "public_fixture_payloads" if self._bounded_public_request else "fixture_payloads",
                None,
            )
            if (
                self._bounded_public_request
                and not callable(fixture_reader)
                and get_settings().environment in {Environment.LOCAL, Environment.TEST}
            ):
                fixture_reader = getattr(self.repository, "fixture_payloads", None)
                self._fixture_payloads_cache = (
                    fixture_reader()[:512] if callable(fixture_reader) else []
                )
                return self._fixture_payloads_cache
            self._fixture_payloads_cache = (
                fixture_reader(limit=512)
                if self._bounded_public_request and callable(fixture_reader)
                else fixture_reader()
                if callable(fixture_reader)
                else []
            )
        return self._fixture_payloads_cache

    def _fixture_payload_by_id(self, fixture_id: str) -> dict[str, Any] | None:
        scoped_reader = getattr(self.repository, "fixture_payload", None)
        if callable(scoped_reader):
            scoped = scoped_reader(fixture_id)
            if scoped is not None:
                return cast(dict[str, Any], scoped)
            if self._bounded_public_request:
                return None
        elif self._bounded_public_request:
            return None
        if self._fixture_payload_index_cache is None:
            self._fixture_payload_index_cache = {}
            for item in self._cached_fixture_payloads():
                key = str(item.get("fixture", {}).get("id") or "")
                if key:
                    self._fixture_payload_index_cache[key] = item
        return self._fixture_payload_index_cache.get(fixture_id)

    def _cached_future_market_observations(self) -> list[dict[str, Any]]:
        if self._future_market_observations_cache is None:
            if self._bounded_public_request:
                default_metric_registry().inc(
                    "w2_public_tripwire_blocks_total",
                    labels={"reader": "global_observation"},
                )
                return []
            observation_reader = getattr(self.repository, "future_market_observations", None)
            self._future_market_observations_cache = (
                observation_reader() if callable(observation_reader) else []
            )
        return self._future_market_observations_cache

    def public_dashboard(self, **kwargs: Any) -> dict[str, Any]:
        request_service = ReadModelService(repository=self.repository)
        request_service._bounded_public_request = True
        request_service._dashboard_response_cache = self._dashboard_response_cache
        return request_service.dashboard(**kwargs)

    def public_dashboard_summary(self, **kwargs: Any) -> dict[str, Any]:
        request_service = ReadModelService(repository=self.repository)
        request_service._bounded_public_request = True
        request_service._dashboard_response_cache = self._dashboard_response_cache
        return request_service.dashboard_summary(**kwargs)

    def public_validation_summary(self, **kwargs: Any) -> dict[str, Any]:
        request_service = ReadModelService(repository=self.repository)
        request_service._bounded_public_request = True
        request_service._dashboard_response_cache = self._dashboard_response_cache
        return request_service.validation_summary(**kwargs)

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
        fixture_ids = list(
            dict.fromkeys(str(row.get("fixture_id") or "") for row in rows if row.get("fixture_id"))
        )
        if not fixture_ids or len(fixture_ids) > 64:
            self._future_market_observations_cache = []
            self._observations_by_fixture_cache = {}
            return
        try:
            observations = cast(list[dict[str, Any]], reader(fixture_ids))
        except Exception:
            self._future_market_observations_cache = []
            self._observations_by_fixture_cache = {}
            return
        allowed = set(fixture_ids)
        if any(str(row.get("fixture_id") or "") not in allowed for row in observations):
            self._future_market_observations_cache = []
            self._observations_by_fixture_cache = {}
            return
        self._future_market_observations_cache = observations
        self._observations_by_fixture_cache = None

    def _fixture_observations_bounded(self, fixture_id: str) -> list[dict[str, Any]]:
        reader = getattr(self.repository, "future_market_observations_for_fixtures", None)
        if not callable(reader):
            return []
        try:
            rows = cast(list[dict[str, Any]], reader([fixture_id]))
        except Exception:
            return []
        if any(str(row.get("fixture_id") or "") != fixture_id for row in rows):
            return []
        return rows

    def _market_snapshots_bounded(self, fixture_id: str) -> list[dict[str, Any]]:
        reader = getattr(self.repository, "market_snapshots_for_fixture", None)
        if not callable(reader):
            return []
        try:
            rows = cast(list[dict[str, Any]], reader(fixture_id))
        except Exception:
            return []
        if any(str(row.get("fixture_id") or "") != fixture_id for row in rows):
            return []
        return rows[:64]

    def _formal_snapshots_by_fixture(self) -> dict[str, list[dict[str, Any]]]:
        if self._formal_snapshots_by_fixture_cache is None:
            grouped: dict[str, list[dict[str, Any]]] = {}
            for snapshot in load_formal_snapshots():
                fixture_id = str(snapshot.get("fixture_id") or "")
                if fixture_id:
                    grouped.setdefault(fixture_id, []).append(snapshot)
            for snapshots in grouped.values():
                snapshots.sort(
                    key=lambda row: (
                        _parse_utc_text(row.get("as_of")) or datetime.min.replace(tzinfo=UTC),
                        _parse_utc_text(row.get("captured_at")) or datetime.min.replace(tzinfo=UTC),
                    ),
                    reverse=True,
                )
            self._formal_snapshots_by_fixture_cache = grouped
        return self._formal_snapshots_by_fixture_cache

    def _formal_settlements_by_snapshot(self) -> dict[str, dict[str, Any]]:
        if self._formal_settlements_by_snapshot_cache is None:
            rows: dict[str, dict[str, Any]] = {}
            for settlement in load_formal_settlements():
                snapshot_id = str(settlement.get("snapshot_id") or "")
                if snapshot_id:
                    rows[snapshot_id] = settlement
            self._formal_settlements_by_snapshot_cache = rows
        return self._formal_settlements_by_snapshot_cache

    def version(self) -> dict[str, Any]:
        generated_at = datetime.now(UTC)
        settings = get_settings()
        database_ready = True
        try:
            counts = self._release_counts()
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
            "release_identity": build_release_identity(settings),
            "capability_manifest": load_recommendation_capability_manifest().public_summary(),
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
            else default_football_day(datetime.now(UTC))
        )
        cache_key = (
            requested_date.isoformat(),
            window,
            timezone,
            include_debug,
            self._bounded_public_request,
        )
        cached = self._dashboard_response_cache.get(cache_key)
        now = monotonic()
        if cached is not None:
            cached_at, cached_payload = cached
            if now - cached_at <= self._dashboard_cache_ttl(
                window, include_debug
            ) and self._dashboard_cache_matches_market_refresh(cached_payload):
                return cached_payload

        self._reset_read_caches()
        version = self.version()
        counts = self._release_counts()
        seed = self.repository.staging_seed_dashboard()
        if not counts["read_model_fixture_count"] and not counts["matchday_card_count"] and seed:
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
        result_rows = [row for row in self._all_matchday_rows() if self._is_finished_row(row)]
        result_rows = self._filter_rows_for_operational_date(
            result_rows,
            requested_date=requested_date,
        )
        future_rows, future_parse_error_count = self._future_fixture_rows_with_errors()
        future_today_rows = self._filter_rows_for_operational_date(
            future_rows,
            requested_date=requested_date,
        )
        future_next36_rows = self._filter_rows_for_next36(future_rows)
        future_horizon_rows = self._filter_rows_for_future_horizon(
            future_rows,
            requested_date=requested_date,
        )
        today_rows = self._dedupe_dashboard_rows(
            [*cast(list[dict[str, Any]], today_rows), *future_today_rows]
        )
        next36_rows = self._dedupe_dashboard_rows(
            [*cast(list[dict[str, Any]], next36_rows), *future_next36_rows]
        )
        selected_rows: list[dict[str, Any]]
        if window == "next36":
            selected_rows = next36_rows
        elif window == "future":
            selected_rows = future_horizon_rows
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

        if window == "all":
            all_cards = [self._dashboard_index_card_from_matchday(row) for row in selected_rows]
            response_cards = [self._compact_all_window_card(card) for card in all_cards]
        else:
            all_cards = [self._dashboard_card_from_matchday(row) for row in selected_rows]
            self._attach_last_known_odds(all_cards)
            response_cards = all_cards
        recommendations = [
            card
            for card in response_cards
            if isinstance(card.get("recommendation"), dict)
            and str(cast(dict[str, Any], card["recommendation"]).get("tier"))
            in {"FORMAL", "CANDIDATE", "ANALYSIS_PICK"}
        ]
        upcoming = [
            card for card in response_cards if str(card.get("status", "")).upper() != "FINISHED"
        ]
        finished = [
            card for card in response_cards if str(card.get("status", "")).upper() == "FINISHED"
        ]
        if window == "all":
            recommendations_payload = [
                self._all_window_card_reference(card) for card in recommendations
            ]
            upcoming_payload = [self._all_window_card_reference(card) for card in upcoming]
            finished_payload = [self._all_window_card_reference(card) for card in finished]
        else:
            recommendations_payload = recommendations
            upcoming_payload = upcoming
            finished_payload = finished
        debug = self._dashboard_debug(
            counts=counts,
            requested_date=requested_date,
            selected_rows=selected_rows,
            future_rows=future_rows,
            future_parse_error_count=future_parse_error_count,
            include=include_debug,
        )
        if window == "all":
            debug.update(self._all_window_surface_contract(include=include_debug))
        data_profile = str(version["data_profile"])
        if all_cards and data_profile == "empty":
            data_profile = "real-db"
        if not all_cards and data_profile == "real-db":
            data_profile = "empty"
        football_day_start, football_day_end = football_day_window(requested_date)
        next_available_date = self._next_available_date(requested_date, future_rows=future_rows)
        performance = self._dashboard_performance(all_cards)
        performance["forward_ledger"] = forward_ledger_performance(
            RUNTIME,
            legacy_recovery_manifest=FORWARD_LEDGER_LEGACY_RECOVERY,
        )
        if window == "all":
            performance.update(self._all_window_surface_contract(include=True))
        refresh_reader = getattr(self.repository, "public_market_refresh_status", None)
        visible_fixture_ids = [
            str(card.get("fixture_id") or "") for card in response_cards if card.get("fixture_id")
        ]
        refresh_status = (
            cast(dict[str, str | None], refresh_reader(visible_fixture_ids))
            if callable(refresh_reader)
            else {"odds_last_confirmed_at": None, "next_refresh_tick": None}
        )
        schedule_reader = getattr(
            self.repository,
            "public_next_market_refresh_by_fixture",
            None,
        )
        refresh_schedule = (
            cast(dict[str, str], schedule_reader(visible_fixture_ids))
            if callable(schedule_reader)
            else {}
        )
        generated_at = datetime.now(UTC)
        for card in response_cards:
            fixture_id = str(card.get("fixture_id") or "")
            scheduled = refresh_schedule.get(fixture_id)
            card["next_eval_at"] = _next_future_evaluation(
                [
                    card.get("next_eval_at"),
                    scheduled,
                    refresh_status.get("next_refresh_tick"),
                ],
                now=generated_at,
            )
            non_pick = card.get("non_pick")
            if isinstance(non_pick, dict):
                non_pick["next_eval_at"] = card["next_eval_at"]
        payload = {
            "generated_at": generated_at,
            "page_updated_at": generated_at,
            "odds_last_confirmed_at": refresh_status.get("odds_last_confirmed_at"),
            "next_refresh_tick": refresh_status.get("next_refresh_tick"),
            "date": requested_date.isoformat(),
            "selected_date": requested_date.isoformat(),
            "selected_football_day": requested_date.isoformat(),
            "selected_date_has_data": bool(selected_rows),
            "next_available_date": next_available_date,
            "football_day_timezone": str(FOOTBALL_DAY_TZ),
            "football_day_cutoff_hour": FOOTBALL_DAY_CUTOFF_HOUR,
            "football_day_start_utc": football_day_start.isoformat().replace("+00:00", "Z"),
            "football_day_end_utc": football_day_end.isoformat().replace("+00:00", "Z"),
            "timezone": timezone,
            "window": window,
            "data_profile": data_profile,
            "data_source": version["data_source"],
            "version": {
                "api_git_sha": version["api_git_sha"],
                "release_id": version["release_id"],
            },
            "debug": debug,
            "performance": performance,
            "recommendations": recommendations_payload,
            "upcoming": upcoming_payload,
            "finished": finished_payload,
            "all": response_cards,
        }
        self._dashboard_response_cache[cache_key] = (now, payload)
        return payload

    def _release_counts(self) -> dict[str, int]:
        if self._bounded_public_request:
            public_reader = getattr(self.repository, "public_release_counts", None)
            if callable(public_reader):
                return cast(dict[str, int], public_reader(limit=MAX_PUBLIC_FIXTURES))
        return self.repository.release_counts()

    def _dashboard_cache_ttl(self, window: str, include_debug: bool) -> float:
        if include_debug:
            return 300.0 if window in {"today", "next36", "future"} else 600.0
        return 900.0 if window in {"today", "next36", "future"} else 1800.0

    def _dashboard_cache_matches_market_refresh(
        self,
        payload: dict[str, Any],
    ) -> bool:
        reader = getattr(self.repository, "public_market_refresh_status", None)
        if not callable(reader):
            return True
        cards = payload.get("all")
        if not isinstance(cards, list):
            return True
        fixture_ids = [
            str(card.get("fixture_id") or "")
            for card in cards
            if isinstance(card, dict) and card.get("fixture_id")
        ]
        if not fixture_ids or len(fixture_ids) > MAX_PUBLIC_FIXTURES:
            return True
        try:
            current = cast(dict[str, str | None], reader(fixture_ids))
        except Exception:
            return True
        return payload.get("odds_last_confirmed_at") == current.get(
            "odds_last_confirmed_at"
        ) and payload.get("next_refresh_tick") == current.get("next_refresh_tick")

    def _all_window_surface_contract(self, *, include: bool) -> dict[str, str]:
        if not include:
            return {}
        return {
            "all_window_surface": "INDEX_ONLY",
            "all_window_formal_monitor_contract": "NOT_AUTHORITATIVE",
            "formal_candidate_detection": "USE_TODAY_NEXT36_OR_FULL_DETAIL",
        }

    def _dashboard_index_card_from_matchday(self, row: dict[str, Any]) -> dict[str, Any]:
        """Return a cheap all-window index card without loading analysis payloads."""
        fixture_id = str(row.get("fixture_id") or "")
        if fixture_id and self._uses_frozen_public_authority():
            card = self.public_analysis_card_bounded(fixture_id)
            if card is None:
                card = self._frozen_analysis_card_failure(
                    fixture_id,
                    blocker="FROZEN_ARTIFACT_MISSING",
                )
            contract = (
                cast(dict[str, Any], card["decision_contract"])
                if isinstance(card.get("decision_contract"), dict)
                else {}
            )
            provenance = card.get("frozen_artifact_provenance")
            return {
                "fixture_id": fixture_id,
                "kickoff_utc": row.get("kickoff_utc") or card.get("kickoff_utc"),
                "kickoff_beijing": row.get("kickoff_beijing"),
                "operational_date_beijing": row.get("operational_date_beijing"),
                "competition_id": row.get("competition_id"),
                "competition_name": row.get("competition_name"),
                "home_team_name": row.get("home_team_name"),
                "away_team_name": row.get("away_team_name"),
                "status": normalize_match_status(row.get("status")),
                "raw_status": row.get("raw_status") or row.get("status"),
                "recommendation": None,
                "candidate": False,
                "formal_recommendation": False,
                "formal_suppressed": True,
                "formal_suppressed_reason": "FROZEN_INDEX_NOT_FORMAL_AUTHORITY",
                "decision_tier": card.get("decision_tier") or contract.get("decision_tier"),
                "data_status": card.get("data_status") or contract.get("data_status"),
                "lifecycle_status": card.get("lifecycle_status")
                or contract.get("lifecycle_status"),
                "outcome_tracked": card.get("outcome_tracked", False),
                "lock_eligible": card.get("lock_eligible", False),
                "recommendation_id": card.get("recommendation_id"),
                "pick": card.get("pick"),
                "reason_code": card.get("reason_code") or contract.get("reason_code"),
                "action": card.get("action"),
                "next_eval_at": card.get("next_eval_at"),
                "provider_budget_status": card.get("provider_budget_status"),
                "current_odds": card.get("current_odds", {}),
                "quote_identity_audit": card.get("quote_identity_audit", {}),
                "frozen_artifact_provenance": provenance,
                "artifact_hash": (
                    cast(dict[str, Any], provenance).get("artifact_hash")
                    if isinstance(provenance, dict)
                    else None
                ),
            }
        recommendation = row.get("recommendation")
        compact_recommendation = (
            {
                "recommendation_id": cast(dict[str, Any], recommendation).get(
                    "recommendation_id",
                )
                or cast(dict[str, Any], recommendation).get("id"),
                "id": cast(dict[str, Any], recommendation).get("id"),
                "tier": cast(dict[str, Any], recommendation).get("tier"),
                "market": cast(dict[str, Any], recommendation).get("market"),
                "selection": cast(dict[str, Any], recommendation).get("selection"),
                "line": cast(dict[str, Any], recommendation).get("line"),
                "formal_recommendation": cast(dict[str, Any], recommendation).get(
                    "formal_recommendation",
                ),
            }
            if isinstance(recommendation, dict)
            else None
        )
        return {
            "fixture_id": row.get("fixture_id"),
            "kickoff_utc": row.get("kickoff_utc"),
            "kickoff_beijing": row.get("kickoff_beijing"),
            "operational_date_beijing": row.get("operational_date_beijing"),
            "competition_id": row.get("competition_id"),
            "competition_name": row.get("competition_name"),
            "home_team_name": row.get("home_team_name"),
            "away_team_name": row.get("away_team_name"),
            "status": normalize_match_status(row.get("status")),
            "raw_status": row.get("raw_status") or row.get("status"),
            "recommendation": compact_recommendation,
            "candidate": bool(row.get("candidate")),
            "formal_recommendation": bool(
                row.get("formal_recommendation")
                or (
                    isinstance(compact_recommendation, dict)
                    and compact_recommendation.get("formal_recommendation") is True
                ),
            ),
            "formal_suppressed": row.get("formal_suppressed"),
            "formal_suppressed_reason": row.get("formal_suppressed_reason"),
            "decision_tier": row.get("decision_tier"),
            "data_status": row.get("data_status"),
            "lifecycle_status": row.get("lifecycle_status"),
            "outcome_tracked": row.get("outcome_tracked"),
            "lock_eligible": row.get("lock_eligible"),
            "recommendation_id": row.get("recommendation_id"),
            "reason_code": row.get("reason_code"),
            "action": row.get("action"),
            "next_eval_at": row.get("next_eval_at"),
            "provider_budget_status": row.get("provider_budget_status"),
        }

    def _compact_all_window_card(self, card: dict[str, Any]) -> dict[str, Any]:
        """Return a lightweight index row for large all-window payloads."""
        payload = self._all_window_card_reference(card)
        payload.update(
            {
                "kickoff_beijing": card.get("kickoff_beijing"),
                "operational_date_beijing": card.get("operational_date_beijing"),
                "competition_id": card.get("competition_id"),
                "competition_name": card.get("competition_name"),
                "raw_status": card.get("raw_status"),
                "formal_suppressed": card.get("formal_suppressed"),
                "formal_suppressed_reason": card.get("formal_suppressed_reason"),
            }
        )
        provenance = card.get("frozen_artifact_provenance")
        if isinstance(provenance, dict):
            payload.update(
                {
                    "decision_tier": card.get("decision_tier"),
                    "data_status": card.get("data_status"),
                    "lifecycle_status": card.get("lifecycle_status"),
                    "outcome_tracked": card.get("outcome_tracked"),
                    "lock_eligible": card.get("lock_eligible"),
                    "recommendation_id": card.get("recommendation_id"),
                    "pick": card.get("pick"),
                    "quote_identity_audit": card.get("quote_identity_audit", {}),
                    "frozen_artifact_provenance": provenance,
                    "artifact_hash": card.get("artifact_hash"),
                }
            )
        return payload

    def _all_window_card_reference(self, card: dict[str, Any]) -> dict[str, Any]:
        recommendation = card.get("recommendation")
        return {
            "fixture_id": card.get("fixture_id"),
            "kickoff_utc": card.get("kickoff_utc"),
            "home_team_name": card.get("home_team_name"),
            "away_team_name": card.get("away_team_name"),
            "status": card.get("status"),
            "recommendation": {
                "recommendation_id": cast(dict[str, Any], recommendation).get(
                    "recommendation_id",
                )
                or cast(dict[str, Any], recommendation).get("id"),
                "id": cast(dict[str, Any], recommendation).get("id"),
                "tier": cast(dict[str, Any], recommendation).get("tier"),
                "market": cast(dict[str, Any], recommendation).get("market"),
                "selection": cast(dict[str, Any], recommendation).get("selection"),
                "line": cast(dict[str, Any], recommendation).get("line"),
                "formal_recommendation": cast(dict[str, Any], recommendation).get(
                    "formal_recommendation",
                ),
            }
            if isinstance(recommendation, dict)
            else None,
            "candidate": card.get("candidate"),
            "formal_recommendation": card.get("formal_recommendation"),
        }

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

    def validation_summary(
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
            "validation": validation_summary(cast(dict[str, Any], payload["performance"])),
        }

    def formal_tracking_summary(self) -> dict[str, Any]:
        return formal_tracking_endpoint_summary()

    def warm_dashboard_cache(self) -> None:
        for window in ("today", "next36", "all"):
            with suppress(Exception):
                self.public_dashboard(window=window, include_debug=False)
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
        public_reader = getattr(self.repository, "public_fixture_payloads", None)
        payloads = (
            cast(list[dict[str, Any]], public_reader(limit=512))
            if callable(public_reader)
            else self.repository.fixture_payloads()[:512]
        )
        for item in payloads:
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
            rows = [row for row in rows if team_id in {row["home_team_id"], row["away_team_id"]}]
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
            else default_football_day(datetime.now(UTC))
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
            <= datetime.fromisoformat(str(row["kickoff_utc"]).replace("Z", "+00:00")).astimezone(
                UTC
            )
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
            else default_football_day(datetime.now(UTC))
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
                normalized = self._normalize_analysis_card(
                    embedded,
                    fixture_id=fixture_id,
                    fixture_context=context,
                )
                if normalized.get("scoreline_readiness") is None:
                    refreshed = self._analysis_card_from_cached_fixture_payload(fixture_id)
                    if refreshed is not None:
                        return refreshed
                return normalized
            refreshed = self._analysis_card_from_cached_fixture_payload(fixture_id)
            if refreshed is not None:
                return refreshed
            return self._fallback_analysis_card(
                fixture_id=fixture_id,
                market_coverage=self._market_coverage_from_fixture_observations(
                    fixture_id=fixture_id,
                    existing=dict(fixture.get("market_coverage", {})),
                ),
                source="matchday_card_without_analysis_payload",
                fixture_context=context,
            )
        dashboard_reader = getattr(self.repository, "dashboard_fixture", None)
        dashboard = dashboard_reader(fixture_id) if callable(dashboard_reader) else None
        if dashboard is not None:
            context = self._analysis_context_from_flat_fixture(dashboard)
            embedded = dashboard.get("analysis_card")
            if isinstance(embedded, dict):
                normalized = self._normalize_analysis_card(
                    embedded,
                    fixture_id=fixture_id,
                    fixture_context=context,
                )
                if normalized.get("scoreline_readiness") is None:
                    refreshed = self._analysis_card_from_cached_fixture_payload(fixture_id)
                    if refreshed is not None:
                        return refreshed
                return normalized
            refreshed = self._analysis_card_from_cached_fixture_payload(fixture_id)
            if refreshed is not None:
                return refreshed
            return self._fallback_analysis_card(
                fixture_id=fixture_id,
                market_coverage=self._market_coverage_from_fixture_observations(
                    fixture_id=fixture_id,
                    existing=dict(dashboard.get("market_coverage", {})),
                ),
                source="dashboard_without_analysis_payload",
                fixture_context=context,
            )
        item = self._fixture_payload_by_id(fixture_id)
        if item is not None:
            return self._analysis_card_from_provider_payload(fixture_id, item)
        return None

    def public_analysis_card_bounded(
        self,
        fixture_id: str,
        *,
        evaluation_time: datetime | None = None,
        use_frozen_canary: bool = True,
    ) -> dict[str, Any] | None:
        """Build a public card with request-local, fixture-scoped observations."""
        if use_frozen_canary and self._uses_frozen_public_authority():
            return self._public_frozen_analysis_card(fixture_id)
        request_service = ReadModelService(repository=self.repository)
        request_service._bounded_public_request = True
        if evaluation_time is not None:
            if evaluation_time.tzinfo is None:
                raise ValueError("analysis-card evaluation_time must be timezone-aware")
            request_service._analysis_evaluation_time_override = evaluation_time.astimezone(UTC)
        reader = getattr(self.repository, "future_market_observations_for_fixtures", None)
        if not callable(reader):
            return request_service._bounded_analysis_card_failure(
                fixture_id,
                blocker="FIXTURE_SCOPED_OBSERVATION_READER_UNAVAILABLE",
            )
        try:
            observations = reader([fixture_id])
        except Exception:
            return request_service._bounded_analysis_card_failure(
                fixture_id,
                blocker="FIXTURE_SCOPED_OBSERVATION_READ_FAILED",
            )
        if any(str(row.get("fixture_id") or "") != fixture_id for row in observations):
            return request_service._bounded_analysis_card_failure(
                fixture_id,
                blocker="FIXTURE_SCOPED_OBSERVATION_CROSS_FIXTURE_ROWS",
            )
        request_service._future_market_observations_cache = list(observations)
        request_service._observations_by_fixture_cache = {fixture_id: list(observations)}
        card = request_service.analysis_card(fixture_id)
        if card is None:
            return None
        return request_service._project_public_analysis_decision_contract(
            fixture_id=fixture_id,
            card=card,
        )

    def _uses_frozen_public_authority(self) -> bool:
        reader = getattr(self.repository, "analysis_card_canary_artifact", None)
        return callable(reader)

    def _public_frozen_analysis_card(self, fixture_id: str) -> dict[str, Any]:
        from copy import deepcopy

        from w2.api.frozen_analysis import FrozenAnalysisError

        reader = getattr(self.repository, "analysis_card_canary_artifact", None)
        if not callable(reader):
            return self._frozen_analysis_card_failure(
                fixture_id,
                blocker="FROZEN_ARTIFACT_READER_UNAVAILABLE",
            )
        try:
            artifact = reader(fixture_id)
        except FrozenAnalysisError as exc:
            message = str(exc).lower()
            blocker = (
                "FROZEN_ARTIFACT_SCHEMA_INCOMPATIBLE"
                if "schema" in message
                else "FROZEN_ARTIFACT_IDENTITY_CONFLICT"
                if "identity" in message
                else "FROZEN_ARTIFACT_HASH_INVALID"
                if "hash" in message
                else "FROZEN_ARTIFACT_INVALID"
            )
            return self._frozen_analysis_card_failure(fixture_id, blocker=blocker)
        except Exception:
            return self._frozen_analysis_card_failure(
                fixture_id,
                blocker="FROZEN_ARTIFACT_READ_FAILED",
            )
        if artifact is None:
            return self._frozen_analysis_card_failure(
                fixture_id,
                blocker="FROZEN_ARTIFACT_MISSING",
            )
        card = cast(dict[str, Any], deepcopy(artifact.payload["analysis_card"]))
        card["bookmaker_intent"] = self._project_heuristic_signal_strength(
            card.get("bookmaker_intent")
        )
        card["markets"] = [
            self._project_heuristic_signal_strength(item)
            for item in card.get("markets", [])
            if isinstance(item, dict)
        ]
        card["frozen_artifact_provenance"] = {
            "status": "VERIFIED",
            "schema_version": artifact.payload["schema_version"],
            "checkpoint_namespace": artifact.payload["checkpoint_namespace"],
            "checkpoint_key": artifact.checkpoint_key,
            "source_hash": artifact.source_hash,
            "artifact_hash": artifact.artifact_hash,
            "fixture_identity": deepcopy(artifact.payload["fixture_identity"]),
            "input_manifest": deepcopy(artifact.payload["input_manifest"]),
        }
        self._enforce_non_pick_scoreline_invariant(card)
        return card

    def _frozen_analysis_card_failure(
        self,
        fixture_id: str,
        *,
        blocker: str,
    ) -> dict[str, Any]:
        return {
            "fixture_id": fixture_id,
            "source": "frozen_analysis_checkpoint",
            "decision": "SKIP",
            "decision_tier": "NOT_READY",
            "data_status": "BLOCKED",
            "lifecycle_status": "DRAFT",
            "outcome_tracked": False,
            "lock_eligible": False,
            "recommendation_id": None,
            "pick": None,
            "non_pick": {
                "reason_code": blocker,
                "reason_human": "冻结分析制品不可用",
                "action": "等待有效冻结制品",
                "next_eval_at": None,
            },
            "reason_code": blocker,
            "action": "等待有效冻结制品",
            "next_eval_at": None,
            "current_odds": {},
            "candidate": False,
            "formal_recommendation": False,
            "markets": [],
            "quote_identity_audit": {
                key: unavailable_quote_identity(market=market, blocker=blocker)
                for market, key in (("ASIAN_HANDICAP", "ah"), ("TOTALS", "ou"))
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
            "frozen_artifact_provenance": {
                "status": "BLOCKED",
                "blockers": [blocker],
            },
        }

    def _project_public_analysis_decision_contract(
        self,
        *,
        fixture_id: str,
        card: dict[str, Any],
    ) -> dict[str, Any]:
        item = self._fixture_payload_by_id(fixture_id)
        if item is None:
            return self._fail_closed_public_analysis_card(card)
        row = self._fixture_summary(item, "UTC")
        row["_dashboard_source"] = "future_fixture_payload"
        canonical = self._dashboard_card_from_matchday(row, analysis_override=card)
        contract = canonical.get("decision_contract")
        if not isinstance(contract, dict):
            return self._fail_closed_public_analysis_card(card)
        projected = {
            **card,
            **{
                key: canonical.get(key)
                for key in (
                    "decision_tier",
                    "data_status",
                    "lifecycle_status",
                    "outcome_tracked",
                    "lock_eligible",
                    "recommendation_id",
                    "pick",
                    "non_pick",
                    "reason_code",
                    "action",
                    "next_eval_at",
                    "card_hash",
                )
            },
            "decision_contract": contract,
        }
        tier = str(projected.get("decision_tier") or "NOT_READY")
        projected["decision"] = (
            "ANALYSIS_PICK"
            if tier in {"ANALYSIS_PICK", "RECOMMEND"}
            else "WATCH"
            if tier == "WATCH"
            else "SKIP"
        )
        if tier not in {"ANALYSIS_PICK", "RECOMMEND"}:
            projected["current_odds"] = {}
            projected["candidate"] = False
            projected["formal_recommendation"] = False
            self._clear_public_market_picks(projected, watch=tier == "WATCH")
        self._enforce_non_pick_scoreline_invariant(projected)
        return projected

    def _fail_closed_public_analysis_card(self, card: dict[str, Any]) -> dict[str, Any]:
        projected = {
            **card,
            "decision": "SKIP",
            "decision_tier": "NOT_READY",
            "outcome_tracked": False,
            "lock_eligible": False,
            "recommendation_id": None,
            "pick": None,
            "current_odds": {},
            "candidate": False,
            "formal_recommendation": False,
        }
        self._clear_public_market_picks(projected, watch=False)
        self._enforce_non_pick_scoreline_invariant(projected)
        return projected

    def _enforce_non_pick_scoreline_invariant(self, card: dict[str, Any]) -> None:
        """Do not expose directional scorelines without a canonical public pick."""
        contract = card.get("decision_contract")
        contract_mapping = contract if isinstance(contract, dict) else {}
        tier = str(
            contract_mapping.get("decision_tier") or card.get("decision_tier") or "NOT_READY"
        )
        pick = contract_mapping.get("pick", card.get("pick"))
        if tier in {"ANALYSIS_PICK", "RECOMMEND"} and isinstance(pick, dict):
            return
        card["scoreline_picks"] = []
        card["scoreline_reference"] = None
        card["secondary_picks"] = []

    def _clear_public_market_picks(self, card: dict[str, Any], *, watch: bool) -> None:
        card["primary_market"] = None
        card["secondary_picks"] = []
        markets = card.get("markets")
        if not isinstance(markets, list):
            return
        for market in markets:
            if not isinstance(market, dict):
                continue
            if str(market.get("decision") or "").upper() in {
                "PICK",
                "ANALYSIS_PICK",
                "RECOMMEND",
            }:
                market["decision"] = "WATCH" if watch else "SKIP"
                market["analysis_decision"] = market["decision"]
                market["tendency"] = None
                market["lean"] = None
                market.pop("odds", None)
            market["candidate"] = False
            market["formal_recommendation"] = False

    def _bounded_analysis_card_failure(
        self,
        fixture_id: str,
        *,
        blocker: str,
    ) -> dict[str, Any] | None:
        self._future_market_observations_cache = []
        self._observations_by_fixture_cache = {fixture_id: []}
        existing = self.analysis_card(fixture_id)
        if existing is None:
            return None
        context = {
            key: existing[key]
            for key in (
                "competition_id",
                "competition_name",
                "competition_cn",
                "kickoff_utc",
                "home_team_id",
                "away_team_id",
                "home_team_name",
                "away_team_name",
                "home_name",
                "away_name",
                "home_cn",
                "away_cn",
            )
            if key in existing
        }
        blocked = self._fallback_analysis_card(
            fixture_id=fixture_id,
            market_coverage={},
            source="fixture_scoped_observation_read_blocked",
            fixture_context=context,
        )
        blocked["quote_identity_audit"] = {
            key: unavailable_quote_identity(market=market, blocker=blocker)
            for market, key in (("ASIAN_HANDICAP", "ah"), ("TOTALS", "ou"))
        }
        blocked["bounded_read"] = {"status": "BLOCKED", "blockers": [blocker]}
        blocked["candidate"] = False
        blocked["formal_recommendation"] = False
        blocked["lock_eligible"] = False
        return blocked

    def _analysis_card_from_cached_fixture_payload(self, fixture_id: str) -> dict[str, Any] | None:
        item = self._fixture_payload_by_id(fixture_id)
        if item is None:
            return None
        return self._analysis_card_from_provider_payload(fixture_id, item)

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

    def _market_coverage_from_fixture_observations(
        self,
        *,
        fixture_id: str,
        existing: dict[str, Any],
    ) -> dict[str, Any]:
        coverage = dict(existing)
        observations = self._observations_for_fixture(fixture_id)
        if any(row.get("canonical_market") == "ASIAN_HANDICAP" for row in observations):
            coverage["ASIAN_HANDICAP"] = True
        if any(row.get("canonical_market") == "TOTALS" for row in observations):
            coverage["TOTALS"] = True
        return coverage

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
        competition_id = self._competition_id_from_provider_fixture(item)
        if competition_id is None:
            return None
        repository = self._future_refresh_repository()
        context = FeatureContext(
            fixture_id=fixture_id,
            competition_id=competition_id,
            home_team_id=home_id,
            away_team_id=away_id,
            kickoff_at=kickoff,
            as_of=min(self._analysis_evaluation_time_override or datetime.now(UTC), kickoff),
            stage_id="group",
        )
        scoped_snapshot_reader = getattr(
            repository,
            "team_xg_rolling_snapshots_for_teams",
            None,
        )
        legacy_snapshot_reader = getattr(repository, "team_xg_rolling_snapshots", None)
        if fixture_id in self._team_xg_snapshots_by_fixture_cache:
            snapshots = self._team_xg_snapshots_by_fixture_cache[fixture_id]
        else:
            try:
                if callable(scoped_snapshot_reader):
                    snapshots = scoped_snapshot_reader(
                        [home_id, away_id],
                        before=context.as_of,
                    )
                else:
                    snapshots = (
                        legacy_snapshot_reader(fixture_id=fixture_id)
                        if callable(legacy_snapshot_reader)
                        else []
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
        proxy_home_history, proxy_away_history = self._team_histories_from_existing_xg_matches(
            context=context,
            home_team_id=home_id,
            away_team_id=away_id,
        )
        home_history, away_history = self._team_fixture_histories_from_raw_payloads(
            context=context,
            home_team_id=home_id,
            away_team_id=away_id,
        )
        if not home_history and not away_history:
            home_history, away_history = proxy_home_history, proxy_away_history
        h2h_meetings = self._h2h_meetings_from_raw_payloads(
            context=context,
            home_team_id=home_id,
            away_team_id=away_id,
        )
        history_home_ratings, history_away_ratings = self._team_ratings_from_history(
            context=context,
            home_team_id=home_id,
            away_team_id=away_id,
            home_history=home_history,
            away_history=away_history,
        )
        home_ratings, away_ratings = self._team_ratings_from_static_mapping(
            context=context,
            home_team_id=home_id,
            away_team_id=away_id,
            history_home_ratings=history_home_ratings,
            history_away_ratings=history_away_ratings,
        )
        if not (home_ratings and away_ratings):
            home_ratings, away_ratings = history_home_ratings, history_away_ratings
        if not (home_ratings and away_ratings):
            home_ratings = self._team_ratings_from_existing_xg_snapshots(home_xg)
            away_ratings = self._team_ratings_from_existing_xg_snapshots(away_xg)
        home_values, away_values = self._team_values_from_static_mapping(
            context=context,
            home_team_id=home_id,
            away_team_id=away_id,
        )
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
        try:
            coverage = registry.require_enabled(competition_id).coverage_profile
        except CompetitionRegistryError:
            return None
        feature_set = build_feature_set(
            context=context,
            inputs=FeatureInputs(
                market_snapshots=market_snapshots,
                bookmaker_quotes=bookmaker_quotes,
                home_history=home_history,
                away_history=away_history,
                h2h_meetings=h2h_meetings,
                home_ratings=home_ratings,
                away_ratings=away_ratings,
                home_values=home_values,
                away_values=away_values,
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
        xg_readiness = self._xg_readiness_status(
            kickoff=kickoff,
            home_team_id=home_id,
            away_team_id=away_id,
            snapshots=snapshots,
        )
        half_goals: HalfGoalModelInput | None = None
        score_matrix: dict[tuple[int, int], float] | None = None
        score_direction: Direction | None = None
        scoreline_output: IndependentXgPoissonOutput | None = None
        latest_home_rating = max(home_ratings, key=lambda row: row.observed_at, default=None)
        latest_away_rating = max(away_ratings, key=lambda row: row.observed_at, default=None)
        latest_home_value = max(home_values, key=lambda row: row.observed_at, default=None)
        latest_away_value = max(away_values, key=lambda row: row.observed_at, default=None)
        neutral_site = _fixture_neutral_site(item)
        simulation_output = run_simulation(
            SimulationInputs(
                fixture_id=fixture_id,
                home_team_id=home_id,
                away_team_id=away_id,
                home_xg_for=latest_home_xg.xg_for if latest_home_xg is not None else None,
                home_xg_against=latest_home_xg.xg_against if latest_home_xg is not None else None,
                away_xg_for=latest_away_xg.xg_for if latest_away_xg is not None else None,
                away_xg_against=latest_away_xg.xg_against if latest_away_xg is not None else None,
                home_elo=latest_home_rating.elo if latest_home_rating is not None else None,
                away_elo=latest_away_rating.elo if latest_away_rating is not None else None,
                home_elo_source=latest_home_rating.source
                if latest_home_rating is not None
                else None,
                away_elo_source=latest_away_rating.source
                if latest_away_rating is not None
                else None,
                home_elo_collection_status=latest_home_rating.collection_status
                if latest_home_rating is not None
                else None,
                away_elo_collection_status=latest_away_rating.collection_status
                if latest_away_rating is not None
                else None,
                home_squad_value_eur=latest_home_value.squad_value_eur
                if latest_home_value is not None
                else None,
                away_squad_value_eur=latest_away_value.squad_value_eur
                if latest_away_value is not None
                else None,
                neutral_site=neutral_site,
                input_readiness={
                    "xg_status": xg_readiness["status"],
                    "history_ready": bool(home_history and away_history),
                    "h2h_ready": bool(h2h_meetings),
                    "ratings_ready": latest_home_rating is not None
                    and latest_away_rating is not None,
                    "raw_ratings_ready": latest_home_rating is not None
                    and latest_away_rating is not None,
                    "squad_value_ready": latest_home_value is not None
                    and latest_away_value is not None,
                },
            )
        )
        scoreline_readiness = self._scoreline_readiness(
            status="INSUFFICIENT_INDEPENDENT_XG",
            reason=str(xg_readiness["status"]),
            xg_sample_status=str(xg_readiness["status"]),
        )
        if xg_readiness["status"] != "READY" or latest_home_xg is None or latest_away_xg is None:
            missing.update({AnalysisMarket.FIRST_HALF_GOALS, AnalysisMarket.SCORE})
        else:
            scoreline_output = independent_xg_poisson(
                home_xg_for=latest_home_xg.xg_for,
                home_xg_against=latest_home_xg.xg_against,
                away_xg_for=latest_away_xg.xg_for,
                away_xg_against=latest_away_xg.xg_against,
            )
            expected_home = scoreline_output.lambda_home
            expected_away = scoreline_output.lambda_away
            half_goals = HalfGoalModelInput(
                expected_home_goals=expected_home,
                expected_away_goals=expected_away,
            )
            score_matrix = scoreline_output.score_matrix
            if expected_home > expected_away + 0.10:
                score_direction = "HOME"
            elif expected_away > expected_home + 0.10:
                score_direction = "AWAY"
            else:
                score_direction = "DRAW"
            scoreline_readiness = self._scoreline_readiness(
                status="READY",
                reason=None,
                xg_sample_status=str(xg_readiness["status"]),
                output=scoreline_output,
            )
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
        payload["feature_contributions"] = [
            self._feature_contribution_payload(item) for item in feature_set.contributions
        ]
        payload["simulation"] = simulation_output.as_dict()
        payload["scoreline_readiness"] = scoreline_readiness
        self._apply_mainline_market_selection(payload, mainline_selection)
        self._apply_lineup_gate(
            payload,
            fixture=item,
            fixture_id=fixture_id,
            as_of=context.as_of,
            mainline_selection=mainline_selection,
        )
        enrich_secondary_evidence(payload)
        apply_market_selection(payload)
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
                evaluated_at=context.as_of,
            )
        )
        self._isolate_non_current_quote_outputs(payload)
        self._attach_xg_reason_values(
            payload,
            home_xg=latest_home_xg,
            away_xg=latest_away_xg,
        )
        return payload

    def _apply_lineup_gate(
        self,
        payload: dict[str, Any],
        *,
        fixture: dict[str, Any],
        fixture_id: str,
        as_of: datetime,
        mainline_selection: dict[str, dict[str, Any]],
    ) -> None:
        competition_id = self._competition_id_from_provider_fixture(fixture)
        repository = self._future_refresh_repository()
        evidence_reader = getattr(repository, "lineup_gate_evidence", None)
        try:
            evidence = (
                evidence_reader(fixture_id=fixture_id, as_of=as_of)
                if callable(evidence_reader)
                else {"status": "INCOMPLETE", "blockers": ["LINEUP_EVIDENCE_UNAVAILABLE"]}
            )
        except SQLAlchemyError:
            evidence = {"status": "INCOMPLETE", "blockers": ["LINEUP_EVIDENCE_UNAVAILABLE"]}
        starter_counts = evidence.get("starter_counts")
        counts = starter_counts if isinstance(starter_counts, list) else []
        competition_code = competition_id or ""
        requirement = lineup_requirement(competition_code)
        gate = LineupGate().evaluate(
            competition_code=competition_code,
            confirmed=bool(evidence.get("confirmed")),
            home_starters=int(counts[0]) if len(counts) > 0 else 0,
            away_starters=int(counts[1]) if len(counts) > 1 else 0,
            uniquely_mapped_starters=parse_int(evidence.get("uniquely_mapped_starters")) or 0,
            valued_starters=parse_int(evidence.get("valued_starters")) or 0,
            formation_count=parse_int(evidence.get("formation_count")) or 0,
            # Market quote readiness is evaluated per candidate, not by lineup policy.
            quotes_complete_and_fresh=True,
            audited_coverage_rate=audited_coverage_rate(competition_code),
        )
        evidence_blockers = [
            str(blocker) for blocker in evidence.get("blockers", []) if str(blocker)
        ]
        confirmation_blockers = list(gate.blockers)
        enrichment_blockers = [
            blocker
            for blocker in evidence_blockers
            if blocker
            in {"PLAYER_IDENTITY_INCOMPLETE", "VALUATION_INCOMPLETE", "FORMATION_INCOMPLETE"}
        ]
        gate_blockers = list(dict.fromkeys([*confirmation_blockers, *enrichment_blockers]))
        gate_eligible = gate.eligible if requirement == "STRICT" else True
        adjustment_policy = lineup_market_policy().get("numeric_adjustment", {})
        adjustment_policy = adjustment_policy if isinstance(adjustment_policy, dict) else {}
        ah_adjustment_enabled = bool(adjustment_policy.get("ah_enabled")) and bool(
            gate.numeric_adjustment_enabled
        )
        totals_adjustment_enabled = bool(adjustment_policy.get("totals_enabled")) and bool(
            gate.numeric_adjustment_enabled
        )
        payload["lineup_provenance"] = {
            **evidence,
            "competition_id": competition_id,
            "requirement": requirement,
            "coverage_grade": gate.grade.value,
            "gate_eligible": gate_eligible,
            "lineup_confirmation_gate": {
                "status": "READY" if gate_eligible else "NOT_READY",
                "blockers": confirmation_blockers,
            },
            "lineup_enrichment_status": {
                "status": "INCOMPLETE" if enrichment_blockers else "READY",
                "blockers": enrichment_blockers,
            },
            "numeric_adjustment_enabled": (ah_adjustment_enabled or totals_adjustment_enabled),
            "lineup_ah_adjustment": 0.0,
            "lineup_totals_adjustment": 0.0,
            "lineup_ah_evidence_enabled": ah_adjustment_enabled,
            "lineup_totals_evidence_enabled": totals_adjustment_enabled,
            "adjustment_gate_reason": adjustment_policy.get("reason"),
            "blockers": gate_blockers if requirement == "STRICT" else [],
            "warnings": (
                []
                if requirement == "STRICT" or bool(evidence.get("confirmed"))
                else ["LINEUPS_NOT_CONFIRMED_ADVISORY"]
            ),
            "policy_version": "w2.lineup_market_policy.v1",
        }
        if gate_eligible or requirement != "STRICT":
            return
        markets = payload.get("markets")
        if isinstance(markets, list):
            for market in markets:
                if not isinstance(market, dict) or market.get("market") not in {
                    "ASIAN_HANDICAP",
                    "TOTALS",
                }:
                    continue
                if str(market.get("decision") or "") in {"PICK", "ANALYSIS_PICK"}:
                    market["decision"] = "WATCH"
                    market["tendency"] = None
                    market["reasons"] = ["五大联赛正式首发、身份或身价尚未完整确认。"]
                    market["risks"] = gate_blockers
        self._refresh_analysis_card_decision(payload)

    def _competition_id_from_provider_fixture(self, item: dict[str, Any]) -> str | None:
        league = item.get("league")
        provider_id = str(league.get("id") or "") if isinstance(league, dict) else ""
        if provider_id:
            registry = CompetitionRegistry()
            if provider_id in registry.entries():
                return provider_id
            for competition_id, entry in registry.entries().items():
                if str(entry.provider_mapping.get("api_football_league_id") or "") == provider_id:
                    return competition_id
        return None

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
        if market == "ASIAN_HANDICAP":
            fixture_id = str(
                next((row.get("fixture_id") for row in observations if row.get("fixture_id")), "")
            )
            captured_values: list[datetime] = []
            for row in observations:
                parsed_capture = parse_provider_time(
                    row.get("captured_at") or row.get("captured_at_utc"),
                )
                if parsed_capture is not None:
                    captured_values.append(parsed_capture)
            if not fixture_id or not captured_values:
                return {
                    "market": market,
                    "status": "UNAVAILABLE",
                    "line": None,
                    "observations": [],
                    "bookmaker_count": 0,
                }
            selected_ah = select_canonical_ah_mainline(
                observations=observations,
                fixture_id=fixture_id,
                target=max(captured_values),
                kickoff=datetime.max.replace(tzinfo=UTC),
            )
            if selected_ah.status != "READY" or selected_ah.line is None:
                return {
                    "market": market,
                    "status": selected_ah.status
                    if selected_ah.status != "UNAVAILABLE"
                    else "UNAVAILABLE",
                    "line": None,
                    "observations": [],
                    "bookmaker_count": 0,
                    "quarantined_observation_count": selected_ah.quarantined_count,
                    "quarantine_reasons": selected_ah.quarantine_reasons or {},
                }
            canonical_line = Decimal(str(selected_ah.line))
            selected_books = set(selected_ah.selected_bookmakers or [])
            home_price = float(selected_ah.home_price or 0)
            away_price = float(selected_ah.away_price or 0)
            return {
                "market": market,
                "status": "READY",
                "line": self._format_decimal_line(canonical_line),
                "observations": [
                    row
                    for row in observations
                    if str(row.get("bookmaker_id") or row.get("bookmaker_name") or "")
                    in selected_books
                ],
                "bookmaker_count": selected_ah.bookmaker_count,
                "selection_policy": CANONICAL_AH_MAINLINE_POLICY,
                "candidate_lines": selected_ah.candidate_lines,
                "rejected_lines": selected_ah.rejected_lines,
                "side_prices": selected_ah.side_prices or {},
                "side_lines": selected_ah.side_lines or {},
                "balance_distance": 0,
                "balance_gap": round(abs(home_price - away_price), 4),
                "mid_price": round((home_price + away_price) / 2, 4),
                "min_price": min(home_price, away_price),
                "quarantined_observation_count": selected_ah.quarantined_count,
                "quarantine_reasons": selected_ah.quarantine_reasons or {},
                "authoritative_quote_rows": selected_ah.authoritative_quote_rows or {},
            }
        grouped: dict[Decimal, list[dict[str, Any]]] = {}
        for row in observations:
            if (
                str(row.get("canonical_market")) != market
                or row.get("suspended")
                or row.get("live")
            ):
                continue
            if market == "ASIAN_HANDICAP" and not is_full_time_asian_handicap_observation(row):
                continue
            if market == "TOTALS" and not is_full_time_totals_observation(row):
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
        candidates: list[dict[str, Any]] = []
        paired_lines = 0
        for line, rows in grouped.items():
            side_state = self._line_side_state(market, rows)
            if not side_state:
                continue
            paired_lines += 1
            bookmaker_count = int(side_state.get("bookmaker_count") or 0)
            if bookmaker_count < min_bookmakers:
                continue
            latest_capture = max((str(row.get("captured_at") or "") for row in rows), default="")
            balance_gap = Decimal(str(side_state["balance_gap"]))
            mid_distance = Decimal(str(abs(float(side_state["mid_price"]) - 1.9)))
            min_side_price = Decimal(str(side_state["min_price"]))
            if balance_gap > Decimal("0.90") or min_side_price < Decimal("1.40"):
                continue
            candidates.append(
                {
                    "balance_distance": Decimal(str(side_state.get("balance_distance") or "999")),
                    "balance_gap": balance_gap,
                    "mid_distance": mid_distance,
                    "bookmaker_count": bookmaker_count,
                    "latest_capture": latest_capture,
                    "line": line,
                    "rows": rows,
                    "side_state": side_state,
                }
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
            bookmaker_count = int(side_state.get("bookmaker_count") or 0)
            return {
                "market": market,
                "status": "NO_BALANCED_MAINLINE" if paired_lines else "UNAVAILABLE",
                "line": self._format_decimal_line(closest_line),
                "observations": closest_rows,
                "bookmaker_count": bookmaker_count,
                **side_state,
            }
        if market == "ASIAN_HANDICAP":
            max_bookmaker_count = max(int(item["bookmaker_count"]) for item in candidates)
            consensus_floor = max_bookmaker_count
            override = None
            eligible = [
                item for item in candidates if int(item["bookmaker_count"]) == max_bookmaker_count
            ] or candidates
        elif market == "TOTALS":
            max_bookmaker_count = max(int(item["bookmaker_count"]) for item in candidates)
            consensus_floor = max_bookmaker_count
            override = None
            eligible = [
                item for item in candidates if int(item["bookmaker_count"]) == max_bookmaker_count
            ] or candidates
        else:
            eligible = candidates
            consensus_floor = 1
            override = None
        selected = min(
            eligible,
            key=lambda item: (
                -int(item["bookmaker_count"]),
                item["balance_distance"],
                item["balance_gap"],
                item["mid_distance"],
                abs(Decimal(str(item["line"]))),
            ),
        )
        line = cast(Decimal, selected["line"])
        rows = cast(list[dict[str, Any]], selected["rows"])
        side_state = cast(dict[str, Any], selected["side_state"])
        selection_warning = selected.get("selection_warning")
        selected_line = Decimal(str(line))
        candidate_lines = self._mainline_candidate_lines(
            candidates,
            selected_line=selected_line,
            consensus_floor=consensus_floor,
            override=override,
            selection_warning=str(selection_warning) if selection_warning else None,
        )
        rejected_lines = self._mainline_rejected_lines(
            candidates,
            selected_line=selected_line,
            consensus_floor=consensus_floor,
            override=override,
        )
        return {
            "market": market,
            "status": "READY",
            "line": self._format_decimal_line(line),
            "observations": rows,
            "bookmaker_count": int(selected["bookmaker_count"]),
            "selection_policy": "latest_bucket_ladder_balance_same_bookmaker_pair"
            if market in {"ASIAN_HANDICAP", "TOTALS"}
            else None,
            "candidate_lines": candidate_lines if market in {"ASIAN_HANDICAP", "TOTALS"} else None,
            "rejected_lines": rejected_lines if market in {"ASIAN_HANDICAP", "TOTALS"} else None,
            **({"selection_warning": selection_warning} if selection_warning else {}),
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
                should_downgrade_to_watch = str(market.get("decision") or "") != "SKIP" and (
                    (side_price is not None and float(side_price) < 1.40)
                    or float(market.get("signal_strength", market.get("confidence")) or 0.0) < 0.50
                )
                if should_downgrade_to_watch:
                    market["decision"] = "WATCH"
                    market["tendency"] = None
                    market["signal_strength"] = min(
                        float(market.get("signal_strength", market.get("confidence")) or 0.0),
                        0.49,
                    )
                    market.pop("confidence", None)
                    market["reasons"] = ["跟随市场 · 无独立优势 · 仅参考"]
                    market["risks"] = ["低赔率或信号不足时不作为主看。"]
                continue
            if status in {"EXTREME_LINE_ONLY", "NO_BALANCED_MAINLINE", "UNAVAILABLE"}:
                market["decision"] = "SKIP"
                market["tendency"] = None
                market["signal_strength"] = 0.0
                market.pop("confidence", None)
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
            str(market.get("decision") or "") for market in markets if isinstance(market, dict)
        }
        if "PICK" in decisions or "ANALYSIS_PICK" in decisions:
            payload["decision"] = "ANALYSIS_PICK"
        elif "NO_EDGE" in decisions:
            payload["decision"] = "NO_EDGE"
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
        side_bookmakers: dict[str, set[str]] = {
            side: {
                bookmaker
                for (row_side, bookmaker), row in latest_by_side_bookmaker.items()
                if row_side == side and row
            }
            for side in side_names
        }
        common_bookmakers = set.intersection(*side_bookmakers.values())
        if not common_bookmakers:
            return None
        pair_candidates: list[
            tuple[
                float,
                float,
                str,
                dict[str, float],
                dict[str, str],
                dict[str, dict[str, Any]],
            ]
        ] = []
        for bookmaker in common_bookmakers:
            prices: dict[str, float] = {}
            lines: dict[str, str] = {}
            authoritative_rows: dict[str, dict[str, Any]] = {}
            valid = True
            for side in side_names:
                row = latest_by_side_bookmaker[(side, bookmaker)]
                try:
                    price = float(row["decimal_odds"])
                except (KeyError, TypeError, ValueError):
                    valid = False
                    break
                if price <= 1:
                    valid = False
                    break
                prices[side.lower()] = price
                lines[side.lower()] = self._line_value(row) or ""
                authoritative_rows[side.lower()] = row
            if not valid:
                continue
            values = list(prices.values())
            balance_distance = self._devig_balance_distance(values)
            balance_gap = abs(values[0] - values[1])
            pair_candidates.append(
                (
                    balance_distance,
                    balance_gap,
                    str(bookmaker),
                    prices,
                    lines,
                    authoritative_rows,
                )
            )
        if not pair_candidates:
            return None
        _distance, _gap, _bookmaker, prices, lines, authoritative_rows = min(
            pair_candidates,
            key=lambda item: (item[0], item[1], item[2]),
        )
        values = list(prices.values())
        return {
            "side_prices": prices,
            "side_lines": lines,
            "bookmaker_count": len(common_bookmakers),
            "balance_distance": self._devig_balance_distance(values),
            "balance_gap": round(abs(values[0] - values[1]), 4),
            "mid_price": round(sum(values) / len(values), 4),
            "min_price": round(min(values), 4),
            "authoritative_quote_rows": authoritative_rows,
        }

    def _devig_balance_distance(self, values: list[float]) -> float:
        if len(values) != 2:
            return 999.0
        implied = [1 / value for value in values if value > 0]
        total = sum(implied)
        if len(implied) != 2 or total <= 0:
            return 999.0
        return round(abs((implied[0] / total) - 0.5), 4)

    def _balanced_override_candidate(
        self,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not candidates:
            return None
        ordered = sorted(
            candidates,
            key=lambda item: (
                item["balance_distance"],
                item["balance_gap"],
                item["mid_distance"],
                -int(item["bookmaker_count"]),
                abs(Decimal(str(item["line"]))),
            ),
        )
        best = ordered[0]
        second_distance = (
            Decimal(str(ordered[1]["balance_distance"])) if len(ordered) > 1 else Decimal("999")
        )
        best_distance = Decimal(str(best["balance_distance"]))
        if (
            int(best["bookmaker_count"]) >= 1
            and best_distance <= Decimal(str(BALANCED_MAINLINE_MAX_DISTANCE))
            and second_distance - best_distance >= Decimal(str(BALANCED_MAINLINE_MIN_DELTA))
        ):
            return best
        return None

    def _mainline_candidate_lines(
        self,
        candidates: list[dict[str, Any]],
        *,
        selected_line: Decimal,
        consensus_floor: int,
        override: dict[str, Any] | None,
        selection_warning: str | None,
    ) -> list[dict[str, Any]]:
        ordered = sorted(
            candidates,
            key=lambda item: (
                0 if Decimal(str(item["line"])) == selected_line else 1,
                -int(item["bookmaker_count"]),
                item["balance_distance"],
                item["balance_gap"],
                item["mid_distance"],
                abs(Decimal(str(item["line"]))),
            ),
        )
        override_line = Decimal(str(override["line"])) if override is not None else None
        rows: list[dict[str, Any]] = []
        for index, item in enumerate(ordered):
            line = Decimal(str(item["line"]))
            candidate: dict[str, Any] = {
                "line": self._format_decimal_line(line),
                "bookmaker_count": int(item["bookmaker_count"]),
                "balance_distance": float(item["balance_distance"]),
                "price_gap": float(item["balance_gap"]),
                "mid_distance": float(item["mid_distance"]),
                "selection_rank": index + 1,
                "bookmaker_consensus_floor": consensus_floor,
                "consensus_eligible": int(item["bookmaker_count"]) >= consensus_floor,
                "balanced_override_eligible": override_line is not None and line == override_line,
            }
            side_state = item.get("side_state")
            if isinstance(side_state, dict):
                side_prices = side_state.get("side_prices")
                if isinstance(side_prices, dict):
                    if side_prices.get("home") is not None:
                        candidate["home_price"] = side_prices.get("home")
                    if side_prices.get("away") is not None:
                        candidate["away_price"] = side_prices.get("away")
                    if side_prices.get("over") is not None:
                        candidate["over_price"] = side_prices.get("over")
                    if side_prices.get("under") is not None:
                        candidate["under_price"] = side_prices.get("under")
                side_lines = side_state.get("side_lines")
                if isinstance(side_lines, dict):
                    if side_lines.get("home") is not None:
                        candidate["home_line"] = side_lines.get("home")
                    if side_lines.get("away") is not None:
                        candidate["away_line"] = side_lines.get("away")
                    if side_lines.get("over") is not None:
                        candidate["over_line"] = side_lines.get("over")
                    if side_lines.get("under") is not None:
                        candidate["under_line"] = side_lines.get("under")
            if selection_warning and line == selected_line:
                candidate["selection_warning"] = selection_warning
            rows.append(candidate)
        return rows

    def _mainline_rejected_lines(
        self,
        candidates: list[dict[str, Any]],
        *,
        selected_line: Decimal,
        consensus_floor: int,
        override: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        override_line = Decimal(str(override["line"])) if override is not None else None
        rows: list[dict[str, Any]] = []
        for item in candidates:
            line = Decimal(str(item["line"]))
            if line == selected_line:
                continue
            rows.append(
                {
                    "line": self._format_decimal_line(line),
                    "reason": "LOWER_BOOKMAKER_CONSENSUS"
                    if int(item["bookmaker_count"]) < consensus_floor
                    and not (override_line is not None and line == override_line)
                    else "TIE_BREAK_LOWER_LADDER_BALANCE",
                }
            )
        return rows

    def _closest_unbalanced_score(
        self,
        market: str,
        rows: list[dict[str, Any]],
    ) -> tuple[int, float]:
        state = self._line_side_state(market, rows)
        if not state:
            return (1, 999.0)
        return (0, float(state.get("balance_distance") or state.get("balance_gap") or 999.0))

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

    def _scoreline_readiness(
        self,
        *,
        status: str,
        reason: str | None,
        xg_sample_status: str,
        output: IndependentXgPoissonOutput | None = None,
    ) -> dict[str, Any]:
        if status != "READY" or output is None:
            return {
                "status": "INSUFFICIENT_INDEPENDENT_XG",
                "reason": reason or xg_sample_status or "XG_DATA_UNAVAILABLE",
                "source": None,
                "model_version": INDEPENDENT_XG_POISSON_MODEL_VERSION,
                "lambda_home": None,
                "lambda_away": None,
                "fair_ou": None,
                "xg_sample_status": xg_sample_status,
            }
        return {
            "status": "READY",
            "reason": None,
            "source": output.source,
            "model_version": output.model_version,
            "lambda_home": output.lambda_home,
            "lambda_away": output.lambda_away,
            "fair_ou": output.fair_ou,
            "xg_sample_status": xg_sample_status,
        }

    def _attach_scoreline_pricing_fields(self, card: dict[str, Any]) -> None:
        readiness = card.get("scoreline_readiness")
        shadow = card.get("pricing_shadow")
        if not isinstance(readiness, dict) or not isinstance(shadow, dict):
            return
        if shadow.get("simulation_status") == "READY":
            return
        if (
            readiness.get("status") == "READY"
            and readiness.get("source") == "independent_xg_poisson"
            and isinstance(readiness.get("fair_ou"), int | float)
        ):
            shadow["fair_ou"] = float(readiness["fair_ou"])
            shadow["edge_ou"] = None
            return
        shadow["fair_ou"] = None
        shadow["edge_ou"] = None

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

    def _team_histories_from_existing_xg_matches(
        self,
        *,
        context: FeatureContext,
        home_team_id: str,
        away_team_id: str,
    ) -> tuple[list[TeamMatchHistory], list[TeamMatchHistory]]:
        matches = self._team_xg_matches_for_teams(
            [home_team_id, away_team_id],
            before=context.as_of,
        )
        home: list[TeamMatchHistory] = []
        away: list[TeamMatchHistory] = []
        for row in matches:
            history = self._team_history_from_xg_match(row, context=context)
            if history is None:
                continue
            if history.team_id == home_team_id:
                home.append(history)
            elif history.team_id == away_team_id:
                away.append(history)
        return home, away

    def _team_history_from_xg_match(
        self,
        row: dict[str, Any],
        *,
        context: FeatureContext,
    ) -> TeamMatchHistory | None:
        kickoff = parse_provider_time(row.get("kickoff_at"))
        if kickoff is None or kickoff > context.as_of:
            return None
        team_id = str(row.get("team_id") or "")
        opponent_id = str(row.get("opponent_team_id") or "")
        if not team_id or not opponent_id:
            return None
        goals_for = self._int_or_none(row.get("goals_for"))
        goals_against = self._int_or_none(row.get("goals_against"))
        if goals_for is None or goals_against is None:
            return None
        return TeamMatchHistory(
            team_id=team_id,
            opponent_id=opponent_id,
            kickoff_at=kickoff,
            goals_for=goals_for,
            goals_against=goals_against,
            ah_result=self._existing_ah_result(row),
            source="team_xg_match_proxy",
            source_group="xg",
            is_independent_signal=False,
            proxy_of="team_fixture_history",
            collection_status="PROXY_ONLY",
        )

    def _team_fixture_histories_from_raw_payloads(
        self,
        *,
        context: FeatureContext,
        home_team_id: str,
        away_team_id: str,
    ) -> tuple[list[TeamMatchHistory], list[TeamMatchHistory]]:
        rows = self._fixture_response_items_from_raw_payloads(
            endpoint="fixtures",
            team_ids=[home_team_id, away_team_id],
        )
        home = self._team_history_from_fixture_items(
            rows,
            team_id=home_team_id,
            context=context,
            source="api_football_fixtures_by_team",
        )
        away = self._team_history_from_fixture_items(
            rows,
            team_id=away_team_id,
            context=context,
            source="api_football_fixtures_by_team",
        )
        return home, away

    def _h2h_meetings_from_raw_payloads(
        self,
        *,
        context: FeatureContext,
        home_team_id: str,
        away_team_id: str,
    ) -> list[TeamMatchHistory]:
        rows = self._fixture_response_items_from_raw_payloads(
            endpoint="h2h",
            team_ids=[home_team_id, away_team_id],
        )
        if not rows:
            rows = [
                row
                for row in self._fixture_response_items_from_raw_payloads(
                    endpoint="fixtures",
                    team_ids=[home_team_id, away_team_id],
                )
                if self._fixture_has_teams(row, home_team_id, away_team_id)
            ]
        meetings: list[TeamMatchHistory] = []
        for item in rows:
            history = self._team_history_from_api_fixture(
                item,
                team_id=home_team_id,
                context=context,
                source="api_football_h2h",
                source_group="h2h",
            )
            if history is not None and history.opponent_id == away_team_id:
                meetings.append(history)
        return meetings

    def _team_ratings_from_history(
        self,
        *,
        context: FeatureContext,
        home_team_id: str,
        away_team_id: str,
        home_history: list[TeamMatchHistory],
        away_history: list[TeamMatchHistory],
    ) -> tuple[list[TeamRatingSnapshot], list[TeamRatingSnapshot]]:
        if not home_history or not away_history:
            return [], []
        home = rating_from_history(
            team_id=home_team_id,
            history=home_history,
            as_of=context.as_of,
        )
        away = rating_from_history(
            team_id=away_team_id,
            history=away_history,
            as_of=context.as_of,
        )
        return ([home] if home is not None else []), ([away] if away is not None else [])

    def _team_ratings_from_static_mapping(
        self,
        *,
        context: FeatureContext,
        home_team_id: str,
        away_team_id: str,
        history_home_ratings: list[TeamRatingSnapshot],
        history_away_ratings: list[TeamRatingSnapshot],
    ) -> tuple[list[TeamRatingSnapshot], list[TeamRatingSnapshot]]:
        ratings = self._team_rating_mapping()
        home = self._team_rating_snapshot(
            ratings.get(home_team_id),
            context=context,
            history_ratings=history_home_ratings,
        )
        away = self._team_rating_snapshot(
            ratings.get(away_team_id),
            context=context,
            history_ratings=history_away_ratings,
        )
        return ([home] if home is not None else []), ([away] if away is not None else [])

    def _team_rating_mapping(self) -> dict[str, dict[str, Any]]:
        path = ROOT / "config/team_ratings/world_cup_2026.v1.json"
        payload = load_json(path, {})
        rows = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return {}
        mapping: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            team_id = str(row.get("team_id") or row.get("provider_team_id") or "")
            if team_id:
                mapping[team_id] = row
        return mapping

    def _team_rating_snapshot(
        self,
        row: dict[str, Any] | None,
        *,
        context: FeatureContext,
        history_ratings: list[TeamRatingSnapshot],
    ) -> TeamRatingSnapshot | None:
        if not row:
            return None
        observed = parse_provider_time(row.get("observed_at"))
        if observed is None or observed > context.as_of:
            return None
        try:
            elo = float(row["elo"])
        except (KeyError, TypeError, ValueError):
            return None
        base = max(
            (rating for rating in history_ratings if rating.observed_at <= context.as_of),
            key=lambda rating: rating.observed_at,
            default=None,
        )
        return TeamRatingSnapshot(
            team_id=str(row.get("team_id") or row.get("provider_team_id") or ""),
            observed_at=observed,
            elo=elo,
            attack_strength=base.attack_strength if base is not None else 1.0,
            defence_strength=base.defence_strength if base is not None else 1.0,
            form_index=base.form_index if base is not None else 0.0,
            source=str(row.get("source_system") or "world_football_elo"),
            source_group="ratings",
            is_independent_signal=True,
            collection_status="REAL_ELO",
        )

    def _team_values_from_static_mapping(
        self,
        *,
        context: FeatureContext,
        home_team_id: str,
        away_team_id: str,
    ) -> tuple[list[TeamValueSnapshot], list[TeamValueSnapshot]]:
        values = self._team_value_mapping()
        home = self._team_value_snapshot(values.get(home_team_id), context=context)
        away = self._team_value_snapshot(values.get(away_team_id), context=context)
        return ([home] if home is not None else []), ([away] if away is not None else [])

    def _team_value_mapping(self) -> dict[str, dict[str, Any]]:
        path = ROOT / "config/team_values/world_cup_2026.v1.json"
        payload = load_json(path, {})
        rows = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return {}
        mapping: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            team_id = str(row.get("team_id") or row.get("provider_team_id") or "")
            if team_id:
                mapping[team_id] = row
        return mapping

    def _team_value_snapshot(
        self,
        row: dict[str, Any] | None,
        *,
        context: FeatureContext,
    ) -> TeamValueSnapshot | None:
        if not row:
            return None
        observed = parse_provider_time(row.get("observed_at")) or context.as_of
        if observed > context.as_of:
            return None
        try:
            value = float(row["squad_value_eur"])
        except (KeyError, TypeError, ValueError):
            return None
        return TeamValueSnapshot(
            team_id=str(row.get("team_id") or row.get("provider_team_id") or ""),
            observed_at=observed,
            squad_value_eur=value,
            source_system=str(row.get("source_system") or "static_team_value_mapping"),
            confidence=float(row.get("confidence") or 1.0),
            source_group="squad_value",
            is_independent_signal=True,
            collection_status="READY",
        )

    def _fixture_response_items_from_raw_payloads(
        self,
        endpoint: str = "fixtures",
        *,
        fixture_id: str | None = None,
        team_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        repository = self._future_refresh_repository()
        reader = (
            getattr(repository, "raw_payloads_for_scope", None) if repository is not None else None
        )
        rows = self._fixture_response_items_from_runtime_artifacts(
            endpoint=endpoint,
            fixture_id=fixture_id,
            team_ids=team_ids,
        )
        if not callable(reader):
            if not self._bounded_public_request:
                offline_reader = (
                    getattr(repository, "raw_payloads", None) if repository is not None else None
                )
                if callable(offline_reader):
                    with suppress(Exception):
                        for raw in offline_reader(endpoint):
                            payload = raw.get("payload") if isinstance(raw, dict) else None
                            response = (
                                payload.get("response") if isinstance(payload, dict) else None
                            )
                            if isinstance(response, list):
                                rows.extend(item for item in response if isinstance(item, dict))
            return rows
        with suppress(Exception):
            payload_rows = reader(
                endpoint,
                fixture_id=fixture_id,
                team_ids=team_ids,
                limit=32,
            )
            for raw in payload_rows:
                payload = raw.get("payload") if isinstance(raw, dict) else None
                if not isinstance(payload, dict):
                    continue
                response = payload.get("response")
                if isinstance(response, list):
                    remaining = max(0, 256 - len(rows))
                    rows.extend(item for item in response[:remaining] if isinstance(item, dict))
                    if len(rows) >= 256:
                        break
        return rows

    def _fixture_response_items_from_runtime_artifacts(
        self,
        *,
        endpoint: str,
        fixture_id: str | None = None,
        team_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        raw_dir = ROOT / "runtime/independent_signal_backfill/raw_payloads" / endpoint
        try:
            if not raw_dir.exists():
                return []
        except OSError:
            return []
        patterns: list[str] = []
        if fixture_id:
            patterns.append(f"*_{fixture_id}_*.json")
        scoped_teams = [str(team_id) for team_id in team_ids or [] if str(team_id)]
        if endpoint == "fixtures":
            patterns.extend(f"team_{team_id}_*.json" for team_id in scoped_teams)
        elif endpoint == "h2h" and len(scoped_teams) == 2:
            patterns.extend(
                (
                    f"{scoped_teams[0]}_{scoped_teams[1]}_*.json",
                    f"{scoped_teams[1]}_{scoped_teams[0]}_*.json",
                )
            )
        if not patterns:
            if self._bounded_public_request:
                return []
            patterns = ["*.json"]
        rows: list[dict[str, Any]] = []
        try:
            paths = sorted({path for pattern in patterns for path in raw_dir.glob(pattern)})[:32]
        except OSError:
            return []
        for path in paths:
            try:
                payload = load_json(path, {})
            except OSError:
                continue
            raw_payload = payload.get("payload") if isinstance(payload, dict) else None
            if not isinstance(raw_payload, dict):
                continue
            response = raw_payload.get("response")
            if isinstance(response, list):
                remaining = max(0, 256 - len(rows))
                rows.extend(item for item in response[:remaining] if isinstance(item, dict))
                if len(rows) >= 256:
                    break
        return rows

    def _team_history_from_fixture_items(
        self,
        items: list[dict[str, Any]],
        *,
        team_id: str,
        context: FeatureContext,
        source: str,
    ) -> list[TeamMatchHistory]:
        rows = [
            history
            for item in items
            if (
                history := self._team_history_from_api_fixture(
                    item,
                    team_id=team_id,
                    context=context,
                    source=source,
                    source_group="team_fixture_history",
                )
            )
            is not None
        ]
        rows.sort(key=lambda row: row.kickoff_at)
        return rows

    def _team_history_from_api_fixture(
        self,
        item: dict[str, Any],
        *,
        team_id: str,
        context: FeatureContext,
        source: str,
        source_group: str,
    ) -> TeamMatchHistory | None:
        fixture = self._dict_child(item, "fixture")
        teams = self._dict_child(item, "teams")
        goals = self._dict_child(item, "goals")
        kickoff = parse_provider_time(fixture.get("date"))
        if kickoff is None or kickoff > context.as_of:
            return None
        status = str((fixture.get("status") or {}).get("short") or "").upper()
        if status not in {"FT", "AET", "PEN"}:
            return None
        home = self._dict_child(teams, "home")
        away = self._dict_child(teams, "away")
        home_id = str(home.get("id") or "")
        away_id = str(away.get("id") or "")
        home_goals = self._int_or_none(goals.get("home"))
        away_goals = self._int_or_none(goals.get("away"))
        if home_goals is None or away_goals is None:
            return None
        if team_id == home_id and away_id:
            goals_for, goals_against, opponent_id = home_goals, away_goals, away_id
        elif team_id == away_id and home_id:
            goals_for, goals_against, opponent_id = away_goals, home_goals, home_id
        else:
            return None
        return TeamMatchHistory(
            team_id=team_id,
            opponent_id=opponent_id,
            kickoff_at=kickoff,
            goals_for=goals_for,
            goals_against=goals_against,
            ah_result=self._existing_ah_result(item),
            source=source,
            source_group=source_group,
            is_independent_signal=True,
            collection_status="READY",
        )

    def _fixture_has_teams(self, item: dict[str, Any], team_a_id: str, team_b_id: str) -> bool:
        teams = self._dict_child(item, "teams")
        home = self._dict_child(teams, "home")
        away = self._dict_child(teams, "away")
        ids = {str(home.get("id") or ""), str(away.get("id") or "")}
        return team_a_id in ids and team_b_id in ids

    def _dict_child(self, payload: dict[str, Any], key: str) -> dict[str, Any]:
        value = payload.get(key)
        return value if isinstance(value, dict) else {}

    def _int_or_none(self, value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _existing_ah_result(self, row: dict[str, Any]) -> str | None:
        value = row.get("ah_result") or row.get("settled_ah_result")
        if value is None:
            return None
        text = str(value).upper()
        return text if text in {"COVER", "NO_COVER"} else None

    def _team_ratings_from_existing_xg_snapshots(
        self,
        snapshots: list[TeamXgSnapshot],
    ) -> list[TeamRatingSnapshot]:
        ratings: list[TeamRatingSnapshot] = []
        for row in snapshots:
            ratings.append(
                TeamRatingSnapshot(
                    team_id=row.team_id,
                    observed_at=row.observed_at,
                    elo=1500.0 + (row.xg_for - row.xg_against) * 100.0,
                    attack_strength=row.xg_for,
                    defence_strength=row.xg_against,
                    form_index=(row.goals_for - row.goals_against) / 5.0,
                    source="rolling_xg_proxy",
                    source_group="xg",
                    is_independent_signal=False,
                    proxy_of="ratings",
                    collection_status="PROXY_ONLY",
                )
            )
        return ratings

    def _feature_contribution_payload(self, item: Any) -> dict[str, Any]:
        return {
            "id": str(getattr(item, "feature_id", "")),
            "side": str(getattr(getattr(item, "side", None), "value", "UNKNOWN")),
            "weight": float(getattr(item, "weight", 0.0)),
            "score": getattr(item, "score", None),
            "status": str(getattr(getattr(item, "status", None), "value", "UNKNOWN")),
            "source": getattr(item, "source", None),
            "source_group": getattr(item, "source_group", None),
            "is_independent_signal": bool(getattr(item, "is_independent_signal", False)),
            "proxy_of": getattr(item, "proxy_of", None),
            "collection_status": getattr(item, "collection_status", None),
            "inputs": getattr(item, "inputs", {}),
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
        evaluated_at: datetime,
    ) -> dict[str, Any]:
        bookmaker_ids = {
            str(row.get("bookmaker_id") or row.get("bookmaker_name"))
            for row in observations
            if row.get("bookmaker_id") or row.get("bookmaker_name")
        }
        captured_points = {
            str(row.get("captured_at")) for row in observations if row.get("captured_at")
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
        quote_identity_audit = {
            key: evaluate_quote_freshness(
                project_quote_identity(
                    market=market,
                    selected_line=mainline_selection.get(market, {}).get("line"),
                    authoritative_rows=mainline_selection.get(market, {}).get(
                        "authoritative_quote_rows"
                    ),
                )
                if mainline_selection.get(market, {}).get("status") == "READY"
                else unavailable_quote_identity(
                    market=market,
                    blocker="AUTHORITATIVE_MAINLINE_NOT_READY",
                ),
                evaluated_at=evaluated_at,
            )
            for market, key in (("ASIAN_HANDICAP", "ah"), ("TOTALS", "ou"))
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
            if odds_entry and quote_identity_audit[key]["freshness_status"] == "COMPLETE":
                current_odds[key] = odds_entry
            first_line = self._line_value(ordered[0])
            current_line = self._line_value(current)
            if first_line is not None:
                line_movement[f"{key}_open"] = first_line
            if current_line is not None:
                line_movement[f"{key}_current"] = current_line
        if current_odds:
            summary["current_odds"] = current_odds
        summary["quote_identity_audit"] = quote_identity_audit
        if line_movement:
            summary["line_movement"] = line_movement
        fresh_markets = {
            market
            for market, key in (("ASIAN_HANDICAP", "ah"), ("TOTALS", "ou"))
            if quote_identity_audit[key]["freshness_status"] == "COMPLETE"
        }
        market_probabilities = self._market_probabilities_from_observations(
            [row for row in observations if row.get("canonical_market") in fresh_markets]
        )
        if market_probabilities:
            summary["market_probabilities"] = market_probabilities
        if score_matrix:
            summary["model_probabilities"] = self._model_probabilities_from_score_matrix(
                score_matrix
            )
        return summary

    def _isolate_non_current_quote_outputs(self, payload: dict[str, Any]) -> None:
        audit = payload.get("quote_identity_audit")
        if not isinstance(audit, dict):
            return
        market_keys = {"ASIAN_HANDICAP": "ah", "TOTALS": "ou"}
        for market in payload.get("markets", []):
            if not isinstance(market, dict):
                continue
            key = market_keys.get(str(market.get("market") or ""))
            quote = audit.get(key) if key else None
            if isinstance(quote, dict) and quote.get("freshness_status") != "COMPLETE":
                market.pop("odds", None)

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
        matches = self._team_xg_matches_for_teams([team_id], before=before)
        count = 0
        for row in matches:
            if str(row.get("team_id") or "") != team_id:
                continue
            kickoff = parse_provider_time(row.get("kickoff_at"))
            if kickoff is not None and kickoff < before:
                count += 1
        return count

    def _team_xg_matches_for_teams(
        self,
        team_ids: list[str],
        *,
        before: datetime,
    ) -> list[dict[str, Any]]:
        repository = self._future_refresh_repository()
        reader = (
            getattr(repository, "team_xg_matches_for_teams", None)
            if repository is not None
            else None
        )
        if not callable(reader):
            return [] if self._bounded_public_request else self._team_xg_matches()
        try:
            return cast(
                list[dict[str, Any]],
                reader(team_ids, before=before, limit_per_team=20),
            )
        except Exception:
            return []

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
        matching = self._raw_payloads_for_fixture(endpoint, fixture_id=fixture_id)
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

    def _raw_payloads_for_fixture(
        self,
        endpoint: str,
        *,
        fixture_id: str,
    ) -> list[dict[str, Any]]:
        repository = self._future_refresh_repository()
        reader = (
            getattr(repository, "raw_payloads_for_scope", None) if repository is not None else None
        )
        if not callable(reader):
            if not self._bounded_public_request:
                offline_reader = (
                    getattr(repository, "raw_payloads", None) if repository is not None else None
                )
                if callable(offline_reader):
                    with suppress(Exception):
                        return [
                            row
                            for row in offline_reader(endpoint)
                            if self._raw_payload_fixture_id(row.get("payload")) == fixture_id
                        ]
            return []
        try:
            rows = cast(
                list[dict[str, Any]],
                reader(endpoint, fixture_id=fixture_id, team_ids=None, limit=32),
            )
        except Exception:
            return []
        return [
            row for row in rows if self._raw_payload_fixture_id(row.get("payload")) == fixture_id
        ]

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
            if market == "TOTALS" and not is_full_time_totals_observation(row):
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
                selection: round(value / total, 4) for selection, value in sorted(implied.items())
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
            value for (home_goals, away_goals), value in matrix.items() if home_goals > away_goals
        )
        draw = sum(
            value for (home_goals, away_goals), value in matrix.items() if home_goals == away_goals
        )
        away = sum(
            value for (home_goals, away_goals), value in matrix.items() if home_goals < away_goals
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
        for key in (
            "selection_policy",
            "selection_warning",
            "candidate_lines",
            "rejected_lines",
        ):
            if key in selection and selection.get(key) is not None:
                entry[key] = selection.get(key)
        return entry

    def _line_value(self, row: dict[str, Any]) -> str | None:
        line = parse_line(row.get("selection")) or row.get("line")
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
        line = parse_line(row.get("selection")) or row.get("line")
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
            "signal_strength": market.signal_strength,
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
                    "secondary_market_direction": dashboard.get("secondary_market_direction"),
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
                    "analysis_card": self.public_analysis_card_bounded(fixture_id),
                }
            )
            return row
        previous_bounded_state = self._bounded_public_request
        self._bounded_public_request = True
        try:
            item = self._fixture_payload_by_id(fixture_id)
        finally:
            self._bounded_public_request = previous_bounded_state
        if item is not None:
            row = self._fixture_summary(item, timezone)
            snapshots = self._market_snapshots_bounded(fixture_id)
            locks: list[dict[str, Any]] = []
            observations = self._fixture_observations_bounded(fixture_id)
            observed_markets: set[str] = {
                str(item["canonical_market"])
                for item in observations
                if item.get("canonical_market")
            }
            obs_bookmaker_ids: set[str] = {
                str(item["bookmaker_id"]) for item in observations if item.get("bookmaker_id")
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
                    "analysis_card": self.public_analysis_card_bounded(fixture_id),
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
        normalized.setdefault(
            "quote_identity_audit",
            {
                key: unavailable_quote_identity(
                    market=market,
                    blocker="AUTHORITATIVE_OBSERVATION_NOT_AVAILABLE",
                )
                for market, key in (("ASIAN_HANDICAP", "ah"), ("TOTALS", "ou"))
            },
        )
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
                    "signal_strength": 0.0,
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
            "signal_strength": 0.0,
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
            feature_contributions=decorated.get("feature_contributions")
            if isinstance(decorated.get("feature_contributions"), list)
            else None,
            current_odds=decorated.get("current_odds")
            if isinstance(decorated.get("current_odds"), dict)
            else None,
            simulation=decorated.get("simulation")
            if isinstance(decorated.get("simulation"), dict)
            else None,
        )
        self._attach_scoreline_pricing_fields(decorated)
        self._attach_market_movement_fields(decorated)
        self._attach_ah_display_contract(decorated)
        decorated["bookmaker_intent"] = self._decorate_bookmaker_intent(
            decorated.get("bookmaker_intent")
        )
        decorated["markets"] = [
            self._decorate_analysis_market(item)
            for item in decorated.get("markets", [])
            if isinstance(item, dict)
        ]
        decorated["market_candidates"] = build_market_candidates(
            markets=decorated["markets"],
            quote_identity_audit=decorated.get("quote_identity_audit")
            if isinstance(decorated.get("quote_identity_audit"), dict)
            else None,
            current_odds=decorated.get("current_odds")
            if isinstance(decorated.get("current_odds"), dict)
            else None,
            pricing_shadow=decorated.get("pricing_shadow")
            if isinstance(decorated.get("pricing_shadow"), dict)
            else None,
            simulation=decorated.get("simulation")
            if isinstance(decorated.get("simulation"), dict)
            else None,
            fixture_id=str(decorated.get("fixture_id") or ""),
            competition_id=str(decorated.get("competition_id") or ""),
        )
        for market in decorated["markets"]:
            if isinstance(market, dict):
                candidate_key = {
                    "ASIAN_HANDICAP": "ah",
                    "TOTALS": "ou",
                }.get(str(market.get("market") or ""))
                candidate = (
                    decorated["market_candidates"].get(candidate_key)
                    if candidate_key is not None
                    else None
                )
                if isinstance(candidate, dict):
                    market["market_candidate"] = candidate
                    if candidate.get("analysis_evidence_status") == "COMPLETE":
                        market["decision"] = (
                            "ANALYSIS_PICK"
                            if candidate.get("analysis_direction_allowed")
                            else "WATCH"
                        )
        apply_market_selection(decorated)
        return decorated

    def _attach_market_movement_fields(self, card: dict[str, Any]) -> None:
        fixture_id = str(card.get("fixture_id") or "")
        timeline = self._market_timeline_payload(fixture_id) if fixture_id else {}
        self._apply_signed_ah_line_from_timeline(card, timeline)
        movement = build_market_movement(timeline)
        divergence = build_market_divergence(
            pricing_shadow=card.get("pricing_shadow")
            if isinstance(card.get("pricing_shadow"), dict)
            else None,
            market_movement=movement,
            timeline=timeline,
            home_team_name=str(card.get("home_cn") or card.get("home_name") or ""),
            away_team_name=str(card.get("away_cn") or card.get("away_name") or ""),
        )
        card["market_movement"] = movement
        card["market_timeline"] = build_market_timeline_reference(timeline)
        card["market_divergence"] = divergence
        card["bookmaker_hypothesis"] = build_bookmaker_hypothesis(
            market_movement=movement,
            market_divergence=divergence,
        )

    def _apply_signed_ah_line_from_timeline(
        self,
        card: dict[str, Any],
        timeline: dict[str, Any],
    ) -> None:
        latest_ah = self._consensus_first_ah_snapshot(self._latest_ah_snapshot(timeline))
        signed_line = self._snapshot_float(latest_ah, "line")
        if signed_line is None:
            return
        if not self._timeline_ah_snapshot_is_canonical_ready(latest_ah):
            return
        if not _runtime_ah_mainline_recompute_enabled():
            shadow = card.get("pricing_shadow")
            if isinstance(shadow, dict):
                self._reconcile_pricing_shadow_ah_mainline(
                    shadow,
                    signed_line,
                    overwrite_materialized=False,
                )
                self._attach_ah_display_contract(card)
            return
        odds = card.get("current_odds")
        if not isinstance(odds, dict):
            odds = {}
            card["current_odds"] = odds
        ah = odds.get("ah")
        if not isinstance(ah, dict):
            ah = {}
            odds["ah"] = ah
        ah["home_line"] = f"{signed_line:g}"
        ah["away_line"] = f"{-signed_line:g}"
        ah["line"] = f"{abs(signed_line):g}"
        home_price = self._snapshot_float(latest_ah, "home_price")
        away_price = self._snapshot_float(latest_ah, "away_price")
        if home_price is not None:
            ah["home_price"] = home_price
        if away_price is not None:
            ah["away_price"] = away_price
        if home_price is not None or away_price is not None:
            ah["source"] = "market_timeline_snapshots"
        for key in ("selection_policy", "candidate_lines", "rejected_lines"):
            if isinstance(latest_ah, dict) and key in latest_ah:
                ah[key] = latest_ah.get(key)
        shadow = card.get("pricing_shadow")
        if isinstance(shadow, dict):
            self._reconcile_pricing_shadow_ah_mainline(shadow, signed_line)
        self._attach_ah_display_contract(card)

    def _reconcile_pricing_shadow_ah_mainline(
        self,
        pricing_shadow: dict[str, Any],
        selector_line: float,
        *,
        overwrite_materialized: bool = True,
    ) -> None:
        materialized_line = self._snapshot_float(pricing_shadow, "market_ah")
        if materialized_line is not None and abs(materialized_line - selector_line) > 0.001:
            pricing_shadow["materialized_market_ah"] = materialized_line
            pricing_shadow["selector_market_ah"] = selector_line
            pricing_shadow["mainline_materialization_status"] = "STALE"
            pricing_shadow["mainline_materialization_blocker"] = AH_MAINLINE_STALE_MATERIALIZATION
        elif materialized_line is not None:
            pricing_shadow["mainline_materialization_status"] = "READY"
        if not overwrite_materialized:
            return
        pricing_shadow["market_ah"] = selector_line
        fair = pricing_shadow.get("fair_ah")
        try:
            if fair is None:
                raise TypeError
            pricing_shadow["edge_ah"] = round(float(selector_line) - float(fair), 6)
        except (TypeError, ValueError):
            pricing_shadow["edge_ah"] = None

    def _attach_ah_display_contract(self, card: dict[str, Any]) -> None:
        odds = card.get("current_odds")
        if not isinstance(odds, dict):
            return
        ah = odds.get("ah")
        if not isinstance(ah, dict):
            return
        shadow = card.get("pricing_shadow")
        market_ah = self._snapshot_float(shadow, "market_ah") if isinstance(shadow, dict) else None
        raw_home_line = self._snapshot_float(ah, "home_line")
        canonical_home_line = market_ah if market_ah is not None else raw_home_line
        if canonical_home_line is None:
            return
        display = ah_display_contract(canonical_home_line)
        ah["home_line"] = f"{canonical_home_line:g}"
        ah["away_line"] = f"{-canonical_home_line:g}"
        ah["line"] = f"{abs(canonical_home_line):g}"
        ah.update(display)

    def _timeline_ah_snapshot_is_canonical_ready(
        self,
        snapshot: dict[str, Any] | None,
    ) -> bool:
        signed_line = self._snapshot_float(snapshot, "line")
        home_price = self._snapshot_float(snapshot, "home_price")
        away_price = self._snapshot_float(snapshot, "away_price")
        if signed_line is None or home_price is None or away_price is None:
            return False
        market = canonical_ah_market(
            current_odds={
                "ah": {
                    "home_line": signed_line,
                    "away_line": -signed_line,
                    "home_price": home_price,
                    "away_price": away_price,
                    "source": "market_timeline_snapshots",
                    "as_of": snapshot.get("as_of") if isinstance(snapshot, dict) else None,
                    "bookmaker_count": snapshot.get("bookmaker_count")
                    if isinstance(snapshot, dict)
                    else None,
                }
            },
            pricing_shadow={"market_ah": signed_line},
        )
        return market is not None and market.validation_status == "READY"

    def _latest_signed_ah_line(self, timeline: dict[str, Any]) -> float | None:
        return self._snapshot_float(
            self._consensus_first_ah_snapshot(self._latest_ah_snapshot(timeline)),
            "line",
        )

    def _latest_ah_snapshot(self, timeline: dict[str, Any]) -> dict[str, Any] | None:
        snapshots = timeline.get("snapshots") if isinstance(timeline, dict) else None
        if not isinstance(snapshots, list):
            return None
        ah_rows = [
            row
            for row in snapshots
            if isinstance(row, dict)
            and str(row.get("market")) == "ASIAN_HANDICAP"
            and row.get("line") is not None
        ]
        if not ah_rows:
            return None
        return max(
            ah_rows,
            key=lambda row: str(row.get("as_of") or row.get("generated_at") or ""),
        )

    def _consensus_first_ah_snapshot(
        self,
        snapshot: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(snapshot, dict):
            return snapshot
        candidate_lines = snapshot.get("candidate_lines")
        if not isinstance(candidate_lines, list):
            return snapshot
        candidates = [item for item in candidate_lines if isinstance(item, dict)]
        if not candidates:
            return snapshot
        max_count = max(int(item.get("bookmaker_count") or 0) for item in candidates)
        if max_count <= 0:
            return snapshot
        eligible = [
            item for item in candidates if int(item.get("bookmaker_count") or 0) == max_count
        ]
        selected = min(
            eligible,
            key=lambda item: (
                self._snapshot_float(item, "balance_distance") or 999.0,
                self._snapshot_float(item, "price_gap") or 999.0,
                self._snapshot_float(item, "mid_distance") or 999.0,
                abs(self._snapshot_float(item, "line") or 999.0),
            ),
        )
        selected_line = self._snapshot_float(selected, "line")
        if selected_line is None:
            return snapshot
        current_line = self._snapshot_float(snapshot, "line")
        if current_line is not None and abs(current_line - selected_line) <= 0.001:
            return snapshot
        corrected = dict(snapshot)
        corrected["line"] = selected_line
        corrected["bookmaker_count"] = int(selected.get("bookmaker_count") or max_count)
        corrected["selection_policy"] = "consensus_first_bookmaker_count_then_balance"
        corrected["selection_warning"] = "READTIME_CONSENSUS_MAINLINE_CORRECTED"
        for key in ("home_price", "away_price"):
            value = selected.get(key)
            if value is not None:
                corrected[key] = value
        corrected["candidate_lines"] = [
            {
                **item,
                "selection_rank": 1
                if self._snapshot_float(item, "line") == selected_line
                else int(item.get("selection_rank") or 999),
                "consensus_eligible": int(item.get("bookmaker_count") or 0) == max_count,
            }
            for item in candidates
        ]
        return corrected

    def _snapshot_float(self, snapshot: dict[str, Any] | None, key: str) -> float | None:
        if not isinstance(snapshot, dict):
            return None
        try:
            return float(snapshot[key])
        except (KeyError, TypeError, ValueError):
            return None

    def _market_timeline_payload(self, fixture_id: str) -> dict[str, Any]:
        configured = os.getenv("W2_MARKET_TIMELINE_RUNTIME_ROOT")
        root = Path(configured) if configured else ROOT / DEFAULT_TIMELINE_DIR
        return load_timeline(timeline_path(root, fixture_id))

    def _first_text(self, *values: Any) -> str:
        for value in values:
            if isinstance(value, str) and value:
                return value
        return ""

    def _decorate_bookmaker_intent(self, payload: Any) -> dict[str, Any]:
        intent = self._project_heuristic_signal_strength(payload)
        intent_value = str(intent.get("intent") or "INSUFFICIENT_DATA")
        intent["intent"] = intent_value
        intent.setdefault("label_cn", INTENT_LABELS_CN.get(intent_value, intent_value))
        intent.setdefault("opening_line", None)
        intent.setdefault("current_line", None)
        intent.setdefault("signal_strength", 0.0)
        return intent

    def _decorate_analysis_market(self, payload: dict[str, Any]) -> dict[str, Any]:
        market = self._project_heuristic_signal_strength(payload)
        market_name = str(market.get("market") or "UNKNOWN")
        original_decision = str(market.get("decision") or "SKIP")
        market["analysis_decision"] = original_decision
        if original_decision == "SKIP":
            market["decision"] = "SKIP"
        elif original_decision == "NO_EDGE":
            market["decision"] = "NO_EDGE"
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
        market.setdefault("signal_strength", 0.0)
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

    def _project_heuristic_signal_strength(self, payload: Any) -> dict[str, Any]:
        projected = dict(payload) if isinstance(payload, dict) else {}
        if "signal_strength" not in projected and "confidence" in projected:
            projected["signal_strength"] = projected["confidence"]
        projected.pop("confidence", None)
        return projected

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
        strengths = [
            _float_or_none(item.get("signal_strength", item.get("confidence"))) or 0.0
            for item in card.get("markets", [])
            if isinstance(item, dict) and item.get("decision") != "SKIP"
        ]
        signal_strength = max(strengths, default=0.0)
        return max(1, min(4, round(signal_strength * 4)))

    def _lean_cn(self, market: dict[str, Any]) -> str | None:
        if market.get("decision") == "SKIP":
            return None
        tendency = str(market.get("tendency") or "")
        if tendency in {"HOME_AH", "AWAY_AH"}:
            return None
        line = market.get("line")
        mapping = {
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
        observations = self._fixture_observations_bounded(fixture_id)
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
                        None if observation.get("line") is None else str(observation.get("line"))
                    ),
                    "decimal_odds": str(observation.get("decimal_odds")),
                    "bookmaker_count": 1,
                    "bookmaker": str(observation.get("bookmaker_name")),
                    "first_seen": identity not in first_seen,
                    "closing": False,
                }
            )
            first_seen.add(identity)
        for snapshot in self._market_snapshots_bounded(fixture_id):
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
        for snapshot in self._market_snapshots_bounded(fixture_id):
            if snapshot.get("power_probabilities"):
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
        public_reader = getattr(self.repository, "public_fixture_payloads", None)
        payloads = (
            cast(list[dict[str, Any]], public_reader(limit=512)) if callable(public_reader) else []
        )
        for item in payloads:
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
        window = self.day_policy.window_for_date(requested_date)
        filtered: list[dict[str, Any]] = []
        for row in rows:
            kickoff = self._row_kickoff_utc(row)
            if kickoff is not None and window.contains(kickoff):
                filtered.append(row)
        return filtered

    def _is_finished_row(self, row: dict[str, Any]) -> bool:
        status = str(row.get("status", "")).upper()
        raw_status = str(row.get("raw_status", "")).upper()
        if status in {"FT", "AET", "PEN", "FINISHED", "MATCH_FINISHED"}:
            return True
        if raw_status in {"FT", "AET", "PEN", "FINISHED", "MATCH_FINISHED"}:
            return True
        return row.get("_result") is not None or row.get("result") is not None

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

    def _filter_rows_for_future_horizon(
        self,
        rows: list[dict[str, Any]],
        *,
        requested_date: date,
        horizon_days: int = 14,
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        start, _ = football_day_window(requested_date)
        end = start + timedelta(days=horizon_days)
        filtered: list[dict[str, Any]] = []
        for row in rows:
            if self._is_finished_row(row):
                continue
            kickoff = self._row_kickoff_utc(row)
            if kickoff is not None and start <= kickoff < end:
                filtered.append(row)
        filtered.sort(
            key=lambda row: self._row_kickoff_utc(row) or datetime.max.replace(tzinfo=UTC)
        )
        return filtered[:limit]

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

    def _locked_pre_match_recommendation(
        self,
        *,
        fixture_id: str,
        fixture_status: str,
        result: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if fixture_status not in LOCKED_PREMATCH_STATUSES:
            return None
        snapshot = next(iter(self._formal_snapshots_by_fixture().get(fixture_id, [])), None)
        if snapshot is None:
            return {
                "status": "NO_PREMATCH_FORMAL",
                "fixture_id": fixture_id,
                "reason": "NO_PREMATCH_FORMAL_SNAPSHOT",
                "recommendation": None,
                "settlement": {
                    "status": "NO_BET",
                    "result": result,
                    "pnl": None,
                },
            }
        snapshot_id = str(snapshot.get("snapshot_id") or "")
        settlement = self._formal_settlements_by_snapshot().get(snapshot_id)
        settlement_payload = self._locked_settlement_payload(
            settlement=settlement,
            result=result,
            fixture_status=fixture_status,
        )
        return {
            "status": "LOCKED",
            "fixture_id": fixture_id,
            "snapshot_id": snapshot.get("snapshot_id"),
            "captured_at": snapshot.get("captured_at"),
            "as_of": snapshot.get("as_of"),
            "kickoff_utc": snapshot.get("kickoff_utc"),
            "home_team_name": snapshot.get("home_team_name"),
            "away_team_name": snapshot.get("away_team_name"),
            "recommendation": snapshot.get("recommendation"),
            "scoreline_reference": snapshot.get("scoreline_reference"),
            "simulation_evidence": snapshot.get("simulation_evidence"),
            "settlement": settlement_payload,
        }

    def _locked_settlement_payload(
        self,
        *,
        settlement: dict[str, Any] | None,
        result: dict[str, Any] | None,
        fixture_status: str,
    ) -> dict[str, Any]:
        if settlement is not None:
            return {
                "status": "SETTLED",
                "result": settlement.get("final_score") or result,
                "pnl": settlement.get("settled_units"),
                "settlement_outcome": settlement.get("settlement_outcome"),
                "sample_included": settlement.get("sample_included"),
                "win_included": settlement.get("win_included"),
                "evaluated_at": settlement.get("evaluated_at"),
            }
        if fixture_status == "FINISHED" and result is not None:
            return {
                "status": "PENDING",
                "result": result,
                "pnl": None,
            }
        return {
            "status": "WAITING_RESULT",
            "result": result,
            "pnl": None,
        }

    def _dashboard_card_from_matchday(
        self,
        row: dict[str, Any],
        *,
        analysis_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fixture_id = str(row.get("fixture_id") or "")
        analysis = analysis_override
        if analysis is None and fixture_id:
            if self._uses_frozen_public_authority():
                analysis = self.public_analysis_card_bounded(fixture_id)
            elif row.get("_dashboard_source") == "future_fixture_payload":
                item = self._fixture_payload_by_id(fixture_id)
                if item is not None:
                    analysis = self._analysis_card_from_provider_payload(fixture_id, item)
            else:
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
        markets = [item for item in card.get("markets", []) if isinstance(item, dict)]
        primary_market = str(card.get("primary_market") or "")
        picked = next(
            (
                item
                for item in markets
                if str(item.get("decision")) == "PICK"
                and str(item.get("market") or "") == primary_market
            ),
            None,
        )
        if picked is None and not primary_market:
            # Backward compatibility for immutable pre-LMM frozen artifacts.
            picked = next(
                (item for item in markets if str(item.get("decision")) == "PICK"),
                None,
            )
        scoreline_picks = scoreline_picks_from_card(card)
        result = result_from_dashboard_row(row)
        analysis_readiness = build_analysis_readiness(
            card,
            fixture_status=normalize_match_status(row.get("status")),
            result=result,
            scoreline_picks=scoreline_picks,
        )
        formal_result = build_formal_recommendation(
            fixture_status=normalize_match_status(row.get("status")),
            simulation=run_simulation_from_shadow(card.get("pricing_shadow")),
            current_odds=card.get("current_odds")
            if isinstance(card.get("current_odds"), dict)
            else None,
            ah_market_candidate=(
                card.get("market_candidates", {}).get("ah")
                if isinstance(card.get("market_candidates"), dict)
                else None
            ),
            pricing_shadow=card.get("pricing_shadow")
            if isinstance(card.get("pricing_shadow"), dict)
            else None,
            analysis_readiness=analysis_readiness,
            home_team_name=str(card.get("home_cn") or row.get("home_team_name") or "主队"),
            away_team_name=str(card.get("away_cn") or row.get("away_team_name") or "客队"),
        )
        formal_recommendation = (
            formal_result.recommendation
            if _valid_formal_recommendation_payload(formal_result.recommendation)
            else None
        )
        if formal_recommendation is not None and fixture_id:
            recommendation_id = formal_recommendation_id(
                fixture_id=fixture_id,
                recommendation=formal_recommendation,
            )
            formal_recommendation = {
                **formal_recommendation,
                "recommendation_id": recommendation_id,
                "id": recommendation_id,
            }
        formal_blockers = list(formal_result.blockers)
        if formal_result.formal_eligible and formal_recommendation is None:
            blocker = _formal_payload_blocker(formal_result)
            if blocker not in formal_blockers:
                formal_blockers.append(blocker)
        pricing_shadow = card.get("pricing_shadow")
        if isinstance(pricing_shadow, dict):
            pricing_shadow["formal_enabled"] = formal_recommendations_enabled()
            pricing_shadow["formal_eligible"] = formal_recommendation is not None
            pricing_shadow["formal_blockers"] = formal_blockers
            canonical_market = formal_result.canonical_ah_market
            pricing_shadow["canonical_ah_market"] = canonical_market
            if isinstance(canonical_market, dict):
                pricing_shadow["canonical_ah_market_source"] = canonical_market.get("source")
                pricing_shadow["canonical_ah_market_blocker"] = canonical_market.get("blocker")
                pricing_shadow["canonical_ah_market_validation_status"] = canonical_market.get(
                    "validation_status",
                )
        recommendation = formal_recommendation or build_recommendation(card, picked)
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
        fixture_status = normalize_match_status(raw_status)
        locked_recommendation = self._locked_pre_match_recommendation(
            fixture_id=fixture_id,
            fixture_status=fixture_status,
            result=result,
        )
        formal_suppressed = formal_result.formal_suppressed
        formal_suppressed_reason = formal_result.formal_suppressed_reason
        if isinstance(locked_recommendation, dict):
            formal_suppressed = True
            formal_suppressed_reason = (
                "FIXTURE_STARTED_LOCKED_PREMATCH"
                if locked_recommendation.get("status") == "LOCKED"
                else "FIXTURE_STARTED_NO_PREMATCH_FORMAL"
            )
        data_refresh = self._dashboard_data_refresh(
            card=card,
            readiness=analysis_readiness,
            row=row,
        )
        kickoff_for_contract = _parse_utc_text(row.get("kickoff_utc") or card.get("kickoff_utc"))
        as_of_for_contract = (
            self._analysis_evaluation_time_override
            or _parse_utc_text(row.get("last_captured"))
            or _parse_utc_text(card.get("generated_at"))
            or datetime.now(UTC)
        )
        frozen_provenance = card.get("frozen_artifact_provenance")
        stored_decision_contract = card.get("decision_contract")
        if (
            isinstance(frozen_provenance, dict)
            and frozen_provenance.get("status") == "VERIFIED"
            and isinstance(stored_decision_contract, dict)
        ):
            decision_contract = dict(stored_decision_contract)
        else:
            decision_contract = (
                build_decision_contract_fields(
                    card=card,
                    market=picked,
                    recommendation=recommendation,
                    readiness=analysis_readiness,
                    environment=str(os.getenv("W2_DECISION_ENVIRONMENT", "staging")),
                    as_of=as_of_for_contract,
                    kickoff_utc=kickoff_for_contract,
                    competition_id=str(row.get("competition_id") or ""),
                    fixture_id=fixture_id,
                )
                if kickoff_for_contract is not None
                else {}
            )
        non_pick = decision_contract.get("non_pick")
        if isinstance(non_pick, dict):
            for key in ("reason_code", "action", "next_eval_at"):
                if not decision_contract.get(key) and non_pick.get(key):
                    decision_contract[key] = non_pick[key]
        decision_pick = decision_contract.get("pick")
        scoreline_decision = (
            {
                **cast(dict[str, Any], decision_pick),
                "tier": decision_contract.get("decision_tier"),
            }
            if isinstance(decision_pick, dict)
            and decision_contract.get("decision_tier") in {"ANALYSIS_PICK", "RECOMMEND"}
            else None
        )
        public_scoreline_picks = scoreline_picks if scoreline_decision is not None else []
        scoreline_reference = (
            scoreline_reference_from_card(card, recommendation=scoreline_decision)
            if scoreline_decision is not None
            else None
        )
        decision_v3 = (
            project_decision_v3(
                decision_contract,
                manifest=load_recommendation_capability_manifest(),
            ).as_dict()
            if decision_contract
            else None
        )
        return {
            "fixture_id": fixture_id,
            "kickoff_utc": row.get("kickoff_utc") or card.get("kickoff_utc"),
            "kickoff_beijing": row.get("kickoff_beijing"),
            "operational_date_beijing": row.get("operational_date_beijing"),
            "competition_id": row.get("competition_id"),
            "competition_name": card.get("competition_cn") or row.get("competition_name"),
            "home_team_name": card.get("home_cn") or row.get("home_team_name"),
            "away_team_name": card.get("away_cn") or row.get("away_team_name"),
            "status": fixture_status,
            "raw_status": raw_status,
            "data_state": row.get("data_health") or row.get("data_state"),
            "lifecycle_state": row.get("action") or row.get("lifecycle_state"),
            "watch_level": card.get("watch_level", 0),
            "data_readiness": card.get("data_readiness", {}),
            "analysis_readiness": analysis_readiness,
            "data_refresh": data_refresh,
            "recommendation": recommendation,
            "formal_suppressed": formal_suppressed,
            "formal_suppressed_reason": formal_suppressed_reason,
            "locked_pre_match_recommendation": locked_recommendation,
            "scoreline_picks": public_scoreline_picks,
            "scoreline_reference": scoreline_reference,
            "scoreline_readiness": self._dashboard_scoreline_readiness(card),
            "result": result,
            "validation": validation,
            "current_odds": card.get("current_odds", {}),
            "market_candidates": card.get("market_candidates", {}),
            "odds_movement": card.get("line_movement", {}),
            "market_strip": markets,
            "bookmaker_intent": card.get("bookmaker_intent", {}),
            "market_movement": card.get("market_movement", {}),
            "market_timeline": card.get("market_timeline", {}),
            "market_divergence": card.get("market_divergence", {}),
            "bookmaker_hypothesis": card.get("bookmaker_hypothesis", {}),
            "pricing_shadow": card.get("pricing_shadow"),
            "quote_identity_audit": card.get("quote_identity_audit", {}),
            "frozen_artifact_provenance": card.get("frozen_artifact_provenance"),
            "artifact_hash": (
                cast(dict[str, Any], card["frozen_artifact_provenance"]).get("artifact_hash")
                if isinstance(card.get("frozen_artifact_provenance"), dict)
                else None
            ),
            "missing_inputs": self._missing_inputs_from_analysis_card(card),
            "candidate": bool(recommendation.get("candidate")) if recommendation else False,
            "formal_recommendation": bool(recommendation.get("formal_recommendation"))
            if recommendation
            else False,
            "recommendation_decision_v3": decision_v3,
            **decision_contract,
        }

    def _dashboard_scoreline_readiness(self, card: dict[str, Any]) -> dict[str, Any] | None:
        simulation = card.get("simulation")
        if not isinstance(simulation, dict):
            shadow = card.get("pricing_shadow")
            if isinstance(shadow, dict):
                simulation = shadow.get("simulation")
        if isinstance(simulation, dict) and simulation.get("status") == "READY":
            return {
                "status": "READY",
                "reason": None,
                "source": "formal_simulation",
                "model_version": simulation.get("model_version"),
                "calibration_version": simulation.get("calibration_version"),
                "calibration_status": simulation.get("calibration_status"),
                "lambda_home": simulation.get("lambda_home"),
                "lambda_away": simulation.get("lambda_away"),
                "fair_ou": simulation.get("fair_ou"),
            }
        readiness = card.get("scoreline_readiness")
        return readiness if isinstance(readiness, dict) else None

    def _dashboard_data_refresh(
        self,
        *,
        card: dict[str, Any],
        readiness: dict[str, Any],
        row: dict[str, Any],
    ) -> dict[str, Any]:
        raw_data_readiness = card.get("data_readiness")
        data_readiness: dict[str, Any] = (
            cast(dict[str, Any], raw_data_readiness) if isinstance(raw_data_readiness, dict) else {}
        )
        raw_available_inputs = readiness.get("available_inputs")
        available_inputs: dict[str, Any] = (
            cast(dict[str, Any], raw_available_inputs)
            if isinstance(raw_available_inputs, dict)
            else {}
        )
        odds_ready = bool(
            available_inputs.get("current_odds") or available_inputs.get("market_observations")
        )
        non_pick = card.get("non_pick")
        reason_code = str(
            card.get("reason_code")
            or (
                cast(dict[str, Any], non_pick).get("reason_code")
                if isinstance(non_pick, dict)
                else ""
            )
            or ""
        )
        odds_stale = (
            str(card.get("data_status") or "") == "STALE" or reason_code == "DATA_STALE_ODDS"
        )
        lineups_status = str(data_readiness.get("lineups_status") or "UNKNOWN")
        statistics_status = str(data_readiness.get("statistics_status") or "UNKNOWN")
        xg_ready = bool(available_inputs.get("xg") or data_readiness.get("xg"))
        provider_empty = lineups_status == "PROVIDER_EMPTY" or statistics_status == "PROVIDER_EMPTY"
        if provider_empty:
            status = "PROVIDER_EMPTY"
        elif str(readiness.get("status")) == "READY":
            status = "READY"
        elif odds_ready or lineups_status in {"READY", "NOT_REQUESTED"} or xg_ready:
            status = "PARTIAL"
        else:
            status = "WAITING"
        xg_status = (
            "READY" if xg_ready else str(data_readiness.get("xg_status") or statistics_status)
        )
        return {
            "status": status,
            "status_label": provider_status_label(status),
            "provider": "api_football",
            "source": str(card.get("source") or row.get("_dashboard_source") or "read-model"),
            "odds_status": "STALE" if odds_stale else "READY" if odds_ready else "WAITING",
            "lineups_status": lineups_status,
            "lineups_status_label": lineups_status_label(lineups_status),
            "xg_status": xg_status,
            "xg_status_label": xg_status_label(xg_status),
            "statistics_status": statistics_status,
            "lineups_captured_at": data_readiness.get("lineups_captured_at"),
            "statistics_captured_at": data_readiness.get("statistics_captured_at"),
            "last_refresh_hint": row.get("last_captured") or card.get("generated_at"),
        }

    def _attach_last_known_odds(self, cards: list[dict[str, Any]]) -> None:
        """Attach bounded, reference-only market snapshots without making them current odds."""
        fixture_ids = list(
            dict.fromkeys(
                str(card.get("fixture_id") or "") for card in cards if card.get("fixture_id")
            )
        )
        if not fixture_ids or len(fixture_ids) > 64:
            return
        reader = getattr(self.repository, "future_market_observations_for_fixtures", None)
        if not callable(reader):
            return
        try:
            observations = cast(list[dict[str, Any]], reader(fixture_ids))
        except Exception:
            return
        allowed = set(fixture_ids)
        if any(str(row.get("fixture_id") or "") not in allowed for row in observations):
            return
        by_fixture: dict[str, list[dict[str, Any]]] = {}
        for row in observations:
            fixture_id = str(row.get("fixture_id") or "")
            if fixture_id:
                by_fixture.setdefault(fixture_id, []).append(row)
        for card in cards:
            fixture_id = str(card.get("fixture_id") or "")
            snapshot = self._last_known_odds_snapshot(by_fixture.get(fixture_id, []))
            if snapshot:
                card["last_known_odds"] = snapshot
                data_refresh = card.get("data_refresh")
                if isinstance(data_refresh, dict) and not data_refresh.get("last_refresh_hint"):
                    data_refresh["last_refresh_hint"] = snapshot.get("captured_at")

    def _last_known_odds_snapshot(
        self,
        observations: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not observations:
            return None
        selection = self._mainline_market_selection(observations)
        markets: dict[str, Any] = {}
        for market, key in (("ASIAN_HANDICAP", "ah"), ("TOTALS", "ou")):
            selected = selection.get(market, {})
            if selected.get("status") != "READY":
                continue
            entry = self._balanced_odds_entry(selected)
            if entry is None:
                continue
            entry = {
                key: value
                for key, value in entry.items()
                if key
                in {
                    "line",
                    "home_line",
                    "away_line",
                    "home_price",
                    "away_price",
                    "over_line",
                    "under_line",
                    "over_price",
                    "under_price",
                }
            }
            entry["bookmaker_count"] = int(selected.get("bookmaker_count") or 0)
            markets[key] = entry
        if not markets:
            return None
        captured_at = max(
            (
                str(row.get("captured_at") or row.get("captured_at_utc") or "")
                for row in observations
            ),
            default="",
        )
        bookmaker_count = len(
            {
                str(row.get("bookmaker_id") or row.get("bookmaker_name") or "")
                for row in observations
                if row.get("bookmaker_id") or row.get("bookmaker_name")
            }
        )
        return {
            "status": "REFERENCE_ONLY",
            "captured_at": captured_at or None,
            "executable": False,
            "observation_count": len(observations),
            "bookmaker_count": bookmaker_count,
            "markets": markets,
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
            item for item in seed.get("all", seed.get("upcoming", [])) if isinstance(item, dict)
        ]
        debug = (
            {
                **counts,
                "selected_date": requested_date.isoformat(),
                "selected_date_has_data": bool(cards),
                "next_available_date": requested_date.isoformat() if cards else None,
                "empty_reason": None if cards else "STAGING_SEED_EMPTY",
                "suggested_actions": ["staging seed is active; run live ingestion for real data"],
            }
            if include_debug
            else {}
        )
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
