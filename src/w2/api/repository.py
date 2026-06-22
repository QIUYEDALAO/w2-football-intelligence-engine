from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.config import Environment, get_settings
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.operations.leagues import run_top_five_audit
from w2.operations.tournament import (
    build_operations_plan,
    load_stage5b_world_cup_fixtures,
    load_tournament_profile,
    readiness_report,
)

ROOT = Path(__file__).resolve().parents[3]
REPORTS = ROOT / "reports"
RUNTIME = ROOT / "runtime"
WORLD_CUP_PROFILE = ROOT / "config/competitions/world_cup_2026.v1.json"
WORLD_CUP_FIXTURES = RUNTIME / "stage5b/processed/national_fixtures_cleaned.json"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


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
        dashboard = self.dashboard_latest_fixtures()
        if dashboard:
            return [self._dashboard_fixture_to_provider_payload(item) for item in dashboard]
        fixtures: dict[str, dict[str, Any]] = {}
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
        for item in self.repository.fixture_payloads():
            row = self._fixture_summary(item, timezone)
            if row["status"] == "NS" and row["kickoff_utc"] < datetime.now(UTC):
                continue
            rows.append(row)
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
                observations = [
                    item
                    for item in self.repository.future_market_observations()
                    if item["fixture_id"] == fixture_id
                ]
                locks = [
                    item
                    for item in self.repository.forward_locks()
                    if item["fixture_id"] == fixture_id
                ]
                row.update(
                    {
                        "request_id": "",
                        "venue": item.get("fixture", {}).get("venue", {}).get("name"),
                        "bookmaker_count": max(
                            [snapshot.get("bookmaker_count", 0) for snapshot in snapshots]
                            + [len({str(item.get("bookmaker_id")) for item in observations})]
                            or [0]
                        ),
                        "market_coverage": {
                            "ONE_X_TWO": any(
                                item.get("canonical_market") == "ONE_X_TWO"
                                for item in observations
                            )
                            or bool(snapshots),
                            "ASIAN_HANDICAP": any(
                                item.get("canonical_market") == "ASIAN_HANDICAP"
                                for item in observations
                            ),
                            "TOTALS": any(
                                item.get("canonical_market") == "TOTALS" for item in observations
                            ),
                            "BTTS": any(
                                item.get("canonical_market") == "BTTS" for item in observations
                            ),
                        },
                        "forward_decision": locks[0]["decision"] if locks else "SKIP",
                        "provenance": {
                            "fixture_source": "api_football_cached",
                            "probability_source": "stage7e_forward_holdout",
                        },
                        "risk_notes": [] if snapshots else ["market_not_comparable"],
                    }
                )
                return row
        return None

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
                        "bookmaker": None,
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
        for item in self.repository.fixture_payloads():
            row = self._fixture_summary(item, "UTC")
            if row["status"] == "NS" and row["kickoff_utc"] < datetime.now(UTC):
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
        return {
            "fixture_id": str(fixture.get("id")),
            "competition_id": str(league.get("id")),
            "competition_name": str(league.get("name")),
            "kickoff_utc": kickoff,
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
        return {
            "fixture_id": str(item["fixture_id"]),
            "competition_id": str(item["competition_id"]),
            "competition_name": str(item["competition_name"]),
            "kickoff_utc": kickoff,
            "kickoff_display": kickoff.astimezone(display_tz).isoformat(),
            "status": str(item["status"]),
            "home_team_id": str(item["home_team_id"]),
            "away_team_id": str(item["away_team_id"]),
            "lifecycle_state": str(item.get("decision_status", "SKIP")),
            "data_state": str(item.get("data_status", "CAPTURED_AT")),
        }
