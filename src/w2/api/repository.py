from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.config import Environment, get_settings
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.shadow_strategy_models import (
    ShadowStrategyEvaluationModel,
    ShadowStrategyLockModel,
    ShadowStrategyRunModel,
)
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
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
from w2.strategy.analysis_recommendation import DISCLAIMER

ROOT = Path(__file__).resolve().parents[3]
REPORTS = ROOT / "reports"
RUNTIME = ROOT / "runtime"
WORLD_CUP_PROFILE = ROOT / "config/competitions/world_cup_2026.v1.json"
WORLD_CUP_FIXTURES = RUNTIME / "stage5b/processed/national_fixtures_cleaned.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def future_refresh_read_model() -> Path:
    return RUNTIME / "future_refresh/read_model"


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
        for item in load_json(future_refresh_read_model() / "fixtures.json", {}).get("items", []):
            fixture_id = str(item.get("fixture", {}).get("id"))
            if fixture_id and fixture_id != "None":
                fixtures[fixture_id] = item
        for path in sorted((RUNTIME / "stage7c/raw").glob("*_fixtures.json")):
            payload = load_json(path, {}).get("payload", {})
            for item in payload.get("response", []):
                fixture_id = str(item.get("fixture", {}).get("id"))
                if fixture_id and fixture_id != "None":
                    fixtures[fixture_id] = item
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
            cast(
                list[dict[str, Any]],
                load_json(future_refresh_read_model() / "market_snapshots.json", []),
            )
        )
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
        return cast(
            list[dict[str, Any]],
            load_json(future_refresh_read_model() / "latest_market_observations.json", []),
        )

    def result_events(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], load_json(RUNTIME / "stage7e/result_events.json", []))

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
        dashboard = self.repository.dashboard_fixture(fixture_id)
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
            embedded = card.get("analysis_card")
            if isinstance(embedded, dict):
                return self._normalize_analysis_card(embedded, fixture_id=fixture_id)
            return self._fallback_analysis_card(
                fixture_id=fixture_id,
                market_coverage=dict(fixture.get("market_coverage", {})),
                source="matchday_card_without_analysis_payload",
            )
        dashboard = self.repository.dashboard_fixture(fixture_id)
        if dashboard is not None:
            embedded = dashboard.get("analysis_card")
            if isinstance(embedded, dict):
                return self._normalize_analysis_card(embedded, fixture_id=fixture_id)
            return self._fallback_analysis_card(
                fixture_id=fixture_id,
                market_coverage=dict(dashboard.get("market_coverage", {})),
                source="dashboard_without_analysis_payload",
            )
        for item in self.repository.fixture_payloads():
            if str(item.get("fixture", {}).get("id")) == fixture_id:
                observations = [
                    row
                    for row in self.repository.future_market_observations()
                    if str(row.get("fixture_id")) == fixture_id
                ]
                coverage = {
                    "ASIAN_HANDICAP": any(
                        row.get("canonical_market") == "ASIAN_HANDICAP" for row in observations
                    ),
                    "TOTALS": any(row.get("canonical_market") == "TOTALS" for row in observations),
                }
                return self._fallback_analysis_card(
                    fixture_id=fixture_id,
                    market_coverage=coverage,
                    source="future_refresh_without_analysis_payload",
                )
        return None

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
    ) -> dict[str, Any]:
        normalized = dict(payload)
        normalized.setdefault("fixture_id", fixture_id)
        normalized.setdefault("disclaimer", DISCLAIMER)
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
        return normalized

    def _fallback_analysis_card(
        self,
        *,
        fixture_id: str,
        market_coverage: dict[str, Any],
        source: str,
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
        return {
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
        }

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
        future_audit = load_json(RUNTIME / "future_refresh/future_refresh_audit.json", {})
        usage = self.repository.stage7e_usage()
        scheduler = self.repository.stage7e_scheduler()
        gate = load_json(REPORTS / "W2_STAGE7E_FIRST_LIVE_CYCLE.json", {}).get("gate", {})
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
            "provider_status": (
                "READY"
                if future_audit.get("remaining_quota") or usage.get("remaining_quota")
                else "UNKNOWN"
            ),
            "forward_cycle_age_seconds": age,
            "gate4_progress": gate,
            "generated_at": datetime.now(UTC),
        }

    def provider_status(self) -> dict[str, Any]:
        dashboard = self.repository.dashboard_provider()
        if dashboard is not None:
            return {
                "provider": str(dashboard.get("provider", "api_football")),
                "status": str(dashboard.get("status", "READY")),
                "remaining_quota": dashboard.get("remaining_quota"),
                "credential_status": str(dashboard.get("credential_status", "PRESENT")),
                "last_request_status": dashboard.get("last_request_status"),
                "last_successful_refresh_at": parse_provider_time(
                    dashboard.get("last_successful_request")
                ),
                "refresh_age_seconds": None,
                "blockers": [],
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
                return {
                    "provider": "api_football",
                    "status": projected_db.get("status", "READY"),
                    "remaining_quota": projected_db.get("remaining_quota"),
                    "credential_status": "PRESENT",
                    "last_request_status": projected_db.get("last_request_status"),
                    "last_successful_refresh_at": last_success_db,
                    "refresh_age_seconds": (
                        int((datetime.now(UTC) - last_success_db).total_seconds())
                        if last_success_db is not None
                        else None
                    ),
                    "blockers": projected_db.get("blockers", []),
                }
        projected = load_json(future_refresh_read_model() / "provider_status.json", {})
        if projected:
            last_success = parse_provider_time(projected.get("last_successful_refresh_at"))
            return {
                "provider": "api_football",
                "status": projected.get("status", "READY"),
                "remaining_quota": projected.get("remaining_quota"),
                "credential_status": "PRESENT",
                "last_request_status": projected.get("last_request_status"),
                "last_successful_refresh_at": last_success,
                "refresh_age_seconds": (
                    int((datetime.now(UTC) - last_success).total_seconds())
                    if last_success is not None
                    else None
                ),
                "blockers": projected.get("blockers", []),
            }
        usage = self.repository.stage7e_usage()
        audit = usage.get("audit") or []
        last = audit[-1] if audit else {}
        return {
            "provider": "api_football",
            "status": "READY" if usage.get("remaining_quota") else "UNKNOWN",
            "remaining_quota": usage.get("remaining_quota"),
            "credential_status": "PRESENT" if usage else "UNKNOWN",
            "last_request_status": last.get("status_code"),
            "last_successful_refresh_at": None,
            "refresh_age_seconds": None,
            "blockers": [],
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

    def _fixture_summary(self, item: dict[str, Any], timezone: str) -> dict[str, Any]:
        if "_dashboard" in item:
            dashboard = cast(dict[str, Any], item["_dashboard"])
            return self._dashboard_fixture_summary(dashboard, timezone)
        fixture = item.get("fixture", {})
        league = item.get("league", {})
        teams = item.get("teams", {})
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
            "home_team_id": str(teams.get("home", {}).get("id")),
            "away_team_id": str(teams.get("away", {}).get("id")),
            "lifecycle_state": (
                "WATCH" if fixture.get("status", {}).get("short") == "NS" else "DATA"
            ),
            "data_state": "CAPTURED_AT",
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
            "away_team_id": str(item["away_team_id"]),
            "lifecycle_state": str(item.get("decision_status", "SKIP")),
            "data_state": str(item.get("data_status", "CAPTURED_AT")),
            "published_grade": item.get("published_grade") or item.get("research_grade"),
            "primary_market": item.get("primary_market"),
            "primary_line": item.get("primary_line"),
            "primary_odds": self._optional_string(item.get("primary_executable_odds")),
            "last_captured": self._optional_datetime(item.get("captured_at")),
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
        }
