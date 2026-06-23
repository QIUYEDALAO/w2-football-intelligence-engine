from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

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


class ReadModelRepository:
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
        for path in sorted((RUNTIME / "stage7c/raw").glob("*_fixtures.json")):
            payload = load_json(path, {}).get("payload", {})
            for item in payload.get("response", []):
                fixture_id = str(item.get("fixture", {}).get("id"))
                if fixture_id and fixture_id != "None":
                    fixtures[fixture_id] = item
        if not fixtures:
            fixtures.update(self._fixture_payloads_from_committed_reports())
        return sorted(fixtures.values(), key=lambda item: item.get("fixture", {}).get("date", ""))

    def _fixture_payloads_from_committed_reports(self) -> dict[str, dict[str, Any]]:
        first_cycle = self.stage7e_first_cycle()
        audit = first_cycle.get("api_audit") or []
        fixture_ids = [
            str(params["fixture"])
            for item in audit
            if item.get("endpoint") == "odds"
            for params in [item.get("params") or {}]
            if params.get("fixture") is not None
        ]
        if not fixture_ids:
            return {}
        kickoff = datetime(2026, 6, 22, 17, 0, tzinfo=UTC)
        output: dict[str, dict[str, Any]] = {}
        for index, fixture_id in enumerate(dict.fromkeys(fixture_ids)):
            output[fixture_id] = {
                "fixture": {
                    "id": fixture_id,
                    "date": (kickoff.replace(hour=17 + index % 4)).isoformat(),
                    "status": {"short": "NS"},
                    "venue": {"name": "Forward holdout venue"},
                },
                "league": {
                    "id": 1,
                    "name": "World Cup",
                    "round": "Forward Holdout",
                },
                "teams": {
                    "home": {
                        "id": f"{fixture_id}-home",
                        "name": f"Home {fixture_id}",
                    },
                    "away": {
                        "id": f"{fixture_id}-away",
                        "name": f"Away {fixture_id}",
                    },
                },
            }
        return output

    def forward_locks(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], load_json(RUNTIME / "stage7e/prediction_locks.json", []))

    def market_snapshots(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], load_json(RUNTIME / "stage7e/market_snapshots.json", []))

    def result_events(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], load_json(RUNTIME / "stage7e/result_events.json", []))

    def world_cup_profile(self) -> dict[str, Any]:
        return cast(dict[str, Any], load_json(WORLD_CUP_PROFILE, {}))

    def world_cup_readiness(self) -> dict[str, Any]:
        existing = load_json(REPORTS / "W2_STAGE13A_READINESS.json", {})
        if existing:
            return cast(dict[str, Any], existing)
        profile = load_tournament_profile(WORLD_CUP_PROFILE)
        fixtures = load_stage5b_world_cup_fixtures(WORLD_CUP_FIXTURES)
        plan = build_operations_plan(profile, fixtures)
        return readiness_report(profile, plan)

    def league_readiness(self) -> dict[str, Any]:
        existing = load_json(REPORTS / "W2_STAGE14A_READINESS.json", {})
        if existing:
            return cast(dict[str, Any], existing)
        return cast(dict[str, Any], run_top_five_audit()["readiness"])

    def operations_report(self) -> dict[str, Any]:
        return cast(dict[str, Any], load_json(REPORTS / "W2_STAGE15A_OPERATIONS.json", {}))

    def release_readiness(self) -> dict[str, Any]:
        return cast(dict[str, Any], load_json(REPORTS / "W2_STAGE15A_RELEASE_READINESS.json", {}))


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
        rows = [
            self._fixture_summary(item, timezone)
            for item in self.repository.fixture_payloads()
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
            rows = [
                row
                for row in rows
                if team_id in {row["home_team_id"], row["away_team_id"]}
            ]
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start : start + page_size], total

    def fixture(self, fixture_id: str, timezone: str) -> dict[str, Any] | None:
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
                row.update(
                    {
                        "request_id": "",
                        "venue": item.get("fixture", {}).get("venue", {}).get("name"),
                        "bookmaker_count": max(
                            [snapshot.get("bookmaker_count", 0) for snapshot in snapshots] or [0]
                        ),
                        "market_coverage": {
                            "ONE_X_TWO": bool(snapshots),
                            "ASIAN_HANDICAP": False,
                            "TOTALS": False,
                            "BTTS": False,
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
        points: list[dict[str, Any]] = []
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
        return points

    def market_probabilities(self, fixture_id: str) -> dict[str, Any]:
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
        usage = self.repository.stage7e_usage()
        scheduler = self.repository.stage7e_scheduler()
        gate = load_json(REPORTS / "W2_STAGE7E_FIRST_LIVE_CYCLE.json", {}).get("gate", {})
        finished = scheduler.get("finished_at")
        age = None
        if finished:
            age = int((datetime.now(UTC) - datetime.fromisoformat(finished)).total_seconds())
        return {
            "stale_data_count": 0,
            "provider_status": "READY" if usage.get("remaining_quota") else "UNKNOWN",
            "forward_cycle_age_seconds": age,
            "gate4_progress": gate,
            "generated_at": datetime.now(UTC),
        }

    def provider_status(self) -> dict[str, Any]:
        usage = self.repository.stage7e_usage()
        audit = usage.get("audit") or []
        last = audit[-1] if audit else {}
        return {
            "provider": "api_football",
            "status": "READY" if usage.get("remaining_quota") else "UNKNOWN",
            "remaining_quota": usage.get("remaining_quota"),
            "credential_status": "PRESENT" if usage else "UNKNOWN",
            "last_request_status": last.get("status_code"),
        }

    def forward_status(self) -> dict[str, Any]:
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
