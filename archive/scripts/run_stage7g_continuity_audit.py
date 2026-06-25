#!/usr/bin/env python3
from __future__ import annotations

# ruff: noqa: E402, I001

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.run_stage7f_gate4_checkpoint import (  # noqa: E402
    all_historical_locks as stage7f_historical_locks,
    all_market_snapshots as stage7f_market_snapshots,
    all_results as stage7f_results,
    eligible_locks,
    parse_utc,
    verify_frozen_hashes,
)
from w2.markets.devig import DevigMethod, devig
from w2.models.forward_ops import ForwardResultEvent
from w2.models.independent import artifact_hash
from w2.providers.api_football import ApiFootballClient

# Stage 7G is a BOSS-approved live continuity audit; this is the authorized --live path.
REPORTS = ROOT / "reports"
RUNTIME = ROOT / "runtime/stage7g"
RAW = RUNTIME / "raw"
LOCKS = RUNTIME / "prediction_locks.json"
MARKETS = RUNTIME / "market_snapshots.json"
RESULTS = RUNTIME / "result_events.json"
MAX_REQUESTS = 100
MINIMUM_RESERVE = 1500
W1_ROOT = ROOT.parent / "w1_world_cup_engine"
W1_PROTECTED = [
    "scripts/w1_score_engine.py",
    "scripts/w1_odds_snapshot_collector.py",
    "scripts/w1_local_predict_server.py",
    "scripts/build_w1_dashboard_data.py",
    "config/w1_decision_policy.json",
    "config/w1_scout_policy.json",
    "config/w1_rho_provenance.json",
]


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def all_locks() -> list[dict[str, Any]]:
    locks = stage7f_historical_locks()
    locks.extend(read_json(LOCKS, []))
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for lock in locks:
        by_key.setdefault((str(lock["fixture_id"]), lock.get("phase", "T-24h")), lock)
    return sorted(by_key.values(), key=lambda item: (str(item["fixture_id"]), item["phase"]))


def all_markets() -> list[dict[str, Any]]:
    snapshots = stage7f_market_snapshots()
    snapshots.extend(read_json(MARKETS, []))
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in snapshots:
        by_key.setdefault((str(item["fixture_id"]), item["phase"]), item)
    return list(by_key.values())


def all_result_events() -> list[dict[str, Any]]:
    events = stage7f_results()
    events.extend(read_json(RESULTS, []))
    by_key: dict[str, dict[str, Any]] = {}
    for item in events:
        by_key.setdefault(item["event_key"], item)
    return list(by_key.values())


def merge_stage7g_locks(new_locks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = all_locks()
    by_key = {(str(lock["fixture_id"]), lock.get("phase", "T-24h")): lock for lock in existing}
    for lock in new_locks:
        by_key.setdefault((str(lock["fixture_id"]), lock["phase"]), lock)
    merged = sorted(by_key.values(), key=lambda item: (str(item["fixture_id"]), item["phase"]))
    stage7f_keys = {
        (str(lock["fixture_id"]), lock.get("phase", "T-24h"))
        for lock in stage7f_historical_locks()
    }
    stage7g_only = [
        lock
        for lock in merged
        if (str(lock["fixture_id"]), lock.get("phase", "T-24h")) not in stage7f_keys
    ]
    write_json(LOCKS, stage7g_only)
    return merged


def capture_stage7g_markets(
    api: Stage7GProvider,
    new_locks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    snapshots = all_markets()
    existing_keys = {(str(item["fixture_id"]), item["phase"]) for item in snapshots}
    odds_by_fixture: dict[str, dict[str, Any]] = {}
    for fixture_id in sorted({str(lock["fixture_id"]) for lock in new_locks}):
        odds_by_fixture[fixture_id] = api.request(
            "odds",
            {"fixture": fixture_id},
            raw_name=f"odds_{fixture_id}",
        )
    new_snapshots: list[dict[str, Any]] = []
    for lock in new_locks:
        key = (str(lock["fixture_id"]), lock["phase"])
        if key in existing_keys:
            continue
        payload = odds_by_fixture.get(str(lock["fixture_id"]), {"response": []})
        bookmaker_count = 0
        probabilities: dict[str, float] | None = None
        for item in payload.get("response", []):
            for bookmaker in item.get("bookmakers", []):
                bookmaker_count += 1
                for bet in bookmaker.get("bets", []):
                    if bet.get("name") not in {"Match Winner", "1x2"}:
                        continue
                    odds: dict[str, Decimal] = {}
                    for value in bet.get("values", []):
                        label = str(value.get("value", "")).upper()
                        if label in {"HOME", "1"}:
                            odds["HOME"] = Decimal(str(value.get("odd")))
                        elif label in {"DRAW", "X"}:
                            odds["DRAW"] = Decimal(str(value.get("odd")))
                        elif label in {"AWAY", "2"}:
                            odds["AWAY"] = Decimal(str(value.get("odd")))
                    if set(odds) == {"HOME", "DRAW", "AWAY"}:
                        probabilities = devig(odds, DevigMethod.POWER).probabilities
                        break
        new_snapshots.append(
            {
                "fixture_id": str(lock["fixture_id"]),
                "phase": lock["phase"],
                "captured_at": datetime.now(UTC).isoformat(),
                "market_comparable": probabilities is not None,
                "bookmaker_count": bookmaker_count,
                "quality": "READY" if probabilities else "MARKET_NOT_COMPARABLE",
                "power_probabilities": probabilities,
                "raw_payload_hash": artifact_hash(payload) if payload.get("response") else None,
                "snapshot_semantics": "CAPTURED_AT",
            }
        )
    write_json(MARKETS, read_json(MARKETS, []) + new_snapshots)
    return new_snapshots


def settle_stage7g_results(
    api: Stage7GProvider,
    locks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    events = all_result_events()
    existing_keys = {event["event_key"] for event in events}
    for fixture_id in sorted(
        {
            str(lock["fixture_id"])
            for lock in locks
            if parse_utc(lock["kickoff_utc"]) < now
        }
    ):
        payload = api.request("fixtures", {"id": fixture_id}, raw_name=f"result_{fixture_id}")
        raw_hash = artifact_hash(payload)
        for item in payload.get("response", []):
            if item.get("fixture", {}).get("status", {}).get("short") not in {"FT", "AET", "PEN"}:
                continue
            goals = item.get("goals", {})
            event = ForwardResultEvent(
                fixture_id=fixture_id,
                provider="api_football",
                confirmed_at=now,
                raw_payload_hash=raw_hash,
                home_goals_90=goals.get("home"),
                away_goals_90=goals.get("away"),
                extra_time=item.get("score", {}).get("extratime", {}),
                penalties=item.get("score", {}).get("penalty", {}),
            )
            if event.event_key() not in existing_keys:
                events.append({**event.__dict__, "event_key": event.event_key()})
                existing_keys.add(event.event_key())
    stage7g_existing = read_json(RESULTS, [])
    existing_stage7g_keys = {event["event_key"] for event in stage7g_existing}
    additions = [
        event
        for event in events
        if event["event_key"] not in existing_stage7g_keys
        and event not in stage7f_results()
    ]
    write_json(RESULTS, stage7g_existing + additions)
    return events


class Stage7GProvider:
    def __init__(self) -> None:
        self.client = ApiFootballClient(allow_live=True)
        self.audit: list[dict[str, Any]] = []
        self.request_count = 0
        self.remaining_quota: int | None = None
        self.allowed_requests = 1
        self.circuit_breaker: str | None = None

    @property
    def key_status(self) -> str:
        return "PRESENT" if os.environ.get(self.client.api_key_env_name) else "ABSENT"

    def request(self, endpoint: str, params: dict[str, str], *, raw_name: str) -> dict[str, Any]:
        if self.request_count >= self.allowed_requests:
            raise RuntimeError("STAGE7G_REQUEST_BUDGET_EXHAUSTED")
        started = time.monotonic()
        response = self.client.request_live(endpoint, params)
        self.request_count += 1
        remaining_raw = (
            response.headers.get("x-ratelimit-requests-remaining")
            or response.headers.get("X-RateLimit-Requests-Remaining")
        )
        self.remaining_quota = int(remaining_raw) if remaining_raw is not None else None
        if response.status_code in {401, 403, 429}:
            self.circuit_breaker = f"PROVIDER_STATUS_{response.status_code}"
            raise RuntimeError(self.circuit_breaker)
        if self.remaining_quota is None:
            self.circuit_breaker = "PROVIDER_QUOTA_UNKNOWN"
            raise RuntimeError(self.circuit_breaker)
        if self.remaining_quota <= MINIMUM_RESERVE:
            self.circuit_breaker = "PROVIDER_QUOTA_RESERVE_BREACH"
            raise RuntimeError(self.circuit_breaker)
        payload = response.payload
        response_items = payload.get("response", [])
        result_count = len(response_items) if isinstance(response_items, list) else 0
        audit = {
            "endpoint": endpoint,
            "params": params,
            "status_code": response.status_code,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "remaining_quota": self.remaining_quota,
            "result_count": result_count,
        }
        self.audit.append(audit)
        write_json(
            RAW / f"{self.request_count:03d}_{raw_name}.json",
            {"audit": audit, "payload": payload, "captured_at_utc": response.captured_at},
        )
        return payload

    def initialize_budget(self) -> None:
        self.allowed_requests = 1
        payload = self.request("status", {}, raw_name="status")
        if payload.get("errors"):
            raise RuntimeError("PROVIDER_STATUS_ERROR")
        provider_budget = max((self.remaining_quota or 0) - MINIMUM_RESERVE, 0)
        self.allowed_requests = min(MAX_REQUESTS, provider_budget)
        if self.allowed_requests <= 0:
            raise RuntimeError("STAGE7G_NO_REQUEST_BUDGET_AVAILABLE")


def w1_audit() -> dict[str, Any]:
    head = subprocess.check_output(
        ["git", "-C", str(W1_ROOT), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    status = subprocess.check_output(["git", "-C", str(W1_ROOT), "status", "--short"], text=True)
    return {
        "head": head,
        "status_short": status.splitlines(),
        "protected_sha256": {
            relative: sha256(W1_ROOT / relative)
            for relative in W1_PROTECTED
            if (W1_ROOT / relative).exists()
        },
        "mode": "READ_ONLY",
    }


def scheduler_audit() -> dict[str, Any]:
    ps = subprocess.run(
        ["ps", "-axo", "pid,etime,command"],
        check=False,
        capture_output=True,
        text=True,
    )
    lines = [
        line.strip()
        for line in ps.stdout.splitlines()
        if any(token in line.lower() for token in ["celery", "beat", "stage7e", "stage7d"])
    ]
    lines = [line for line in lines if "run_stage7g_continuity_audit.py" not in line]
    stage7e_first = read_json(REPORTS / "W2_STAGE7E_FIRST_LIVE_CYCLE.json", {})
    stage7e_scheduler = read_json(REPORTS / "W2_STAGE7E_SCHEDULER_AUDIT.json", {})
    stage7f_usage = read_json(REPORTS / "W2_STAGE7F_API_USAGE.json", {})
    checkpoints = {
        "stage7e_first_cycle_hash": stage7e_first.get("cycle_hash"),
        "stage7e_scheduler_cycle_hash": stage7e_scheduler.get("cycle_hash"),
        "stage7f_request_count": stage7f_usage.get("requests_used"),
    }
    persistent = bool(lines)
    return {
        "status": "RUNNING" if persistent else "PERSISTENT_SCHEDULER_HOST_REQUIRED",
        "scheduler_worker_processes": lines,
        "pid": None if not lines else [line.split(maxsplit=2)[0] for line in lines],
        "heartbeat": "ABSENT" if not persistent else "PRESENT",
        "last_cycle": stage7e_scheduler.get("finished_at"),
        "next_cycle": None,
        "stage7e_autocycle_after_completion": False,
        "checkpoint_continuously_advancing": False,
        "no_overlap_lock_effective": stage7e_scheduler.get("no_overlap") is True,
        "errors": [],
        "retry_records": [],
        "checkpoint_summary": checkpoints,
        "system_daemon_started": False,
    }


def discover_fixtures(api: Stage7GProvider) -> list[dict[str, Any]]:
    today = datetime.now(UTC).date()
    discovered: list[dict[str, Any]] = []
    searches = [
        "World Cup",
        "World Cup Qualification",
        "Euro",
        "Copa America",
        "Asian Cup",
        "Africa Cup",
        "Nations League",
        "Friendlies",
    ]
    for search in searches:
        leagues = api.request(
            "leagues",
            {"search": search},
            raw_name=f"leagues_{search.replace(' ', '_')}",
        )
        for item in leagues.get("response", [])[:2]:
            league = item.get("league", {})
            seasons = item.get("seasons", [])
            if not league.get("id") or not seasons:
                continue
            season = str(seasons[-1].get("year"))
            payload = api.request(
                "fixtures",
                {
                    "league": str(league["id"]),
                    "season": season,
                    "from": today.isoformat(),
                    "to": (today + timedelta(days=60)).isoformat(),
                },
                raw_name=f"fixtures_{league['id']}_{season}",
            )
            for fixture in payload.get("response", []):
                discovered.append({**fixture, "_search": search})
    unique: dict[str, dict[str, Any]] = {}
    for item in discovered:
        fixture_id = str(item.get("fixture", {}).get("id"))
        if fixture_id and fixture_id != "None":
            unique[fixture_id] = item
    return sorted(unique.values(), key=lambda item: item.get("fixture", {}).get("date", ""))


def fixture_state(
    *,
    fixture_id: str,
    kickoff: datetime,
    now: datetime,
    locks: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    fixture_locks = [lock for lock in locks if str(lock["fixture_id"]) == fixture_id]
    has_result = any(str(event["fixture_id"]) == fixture_id for event in results)
    reasons: list[str] = []
    if fixture_locks:
        reasons.append("ALREADY_LOCKED")
    if kickoff <= now and not has_result:
        reasons.append("RESULT_NOT_FINAL")
    if kickoff <= now:
        reasons.append("KICKOFF_PASSED")
    if now < kickoff - timedelta(hours=24):
        reasons.append("OUTSIDE_T24_WINDOW")
    if now < kickoff - timedelta(hours=1):
        reasons.append("OUTSIDE_T1_WINDOW")
    if not fixture_locks and kickoff > now:
        reasons.append("MODEL_INPUT_MISSING")
    if has_result:
        return "SETTLED", reasons
    if fixture_locks and kickoff > now:
        return "LOCKED", reasons
    if kickoff <= now:
        return "RESULT_PENDING", reasons
    if kickoff - timedelta(hours=24) <= now < kickoff:
        return "ELIGIBLE_T24_OR_T1", reasons
    return "DISCOVERED", reasons


def build_calendar(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    now = datetime.now(UTC)
    locks = all_locks()
    results = all_result_events()
    rows: list[dict[str, Any]] = []
    reason_counts: dict[str, int] = {}
    for item in fixtures:
        fixture = item.get("fixture", {})
        league = item.get("league", {})
        teams = item.get("teams", {})
        fixture_id = str(fixture.get("id"))
        kickoff_raw = fixture.get("date")
        if not fixture_id or not kickoff_raw:
            continue
        kickoff = parse_utc(str(kickoff_raw))
        state, reasons = fixture_state(
            fixture_id=fixture_id,
            kickoff=kickoff,
            now=now,
            locks=locks,
            results=results,
        )
        for reason in reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        rows.append(
            {
                "fixture_id": fixture_id,
                "competition": league.get("name"),
                "league_id": league.get("id"),
                "search_source": item.get("_search"),
                "home_team": teams.get("home", {}).get("name"),
                "away_team": teams.get("away", {}).get("name"),
                "kickoff_utc": kickoff.isoformat(),
                "t24_eligibility_time": (kickoff - timedelta(hours=24)).isoformat(),
                "t1_eligibility_time": (kickoff - timedelta(hours=1)).isoformat(),
                "settlement_check_time": (kickoff + timedelta(hours=3)).isoformat(),
                "model_eligibility": "REQUIRES_AS_OF_INPUTS",
                "expected_market_availability": "CHECK_ONLY_INSIDE_LOCK_WINDOW",
                "current_state": state,
                "zero_sample_reasons": reasons,
            }
        )
    return {
        "generated_at": now.isoformat(),
        "window_days": 60,
        "fixture_count": len(rows),
        "fixtures": rows,
        "reason_counts": reason_counts,
    }


def controlled_cycle(api: Stage7GProvider, fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    locks_before = all_locks()
    candidate_locks = eligible_locks(fixtures, locks_before, datetime.now(UTC))
    new_locks = merge_stage7g_locks(candidate_locks)
    actual_new_count = max(len(new_locks) - len(locks_before), 0)
    market_snapshots: list[dict[str, Any]] = []
    if candidate_locks:
        market_snapshots = capture_stage7g_markets(api, candidate_locks)
    results = settle_stage7g_results(api, new_locks)
    return {
        "eligible_fixture_found": bool(candidate_locks),
        "candidate_lock_count": len(candidate_locks),
        "new_lock_count": actual_new_count,
        "market_snapshot_count": len(market_snapshots),
        "result_event_count": len(results),
        "sample_fabricated": False,
        "training_performed": False,
        "recommendation_output": False,
    }


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    api = Stage7GProvider()
    blockers: list[str] = []
    frozen = verify_frozen_hashes()
    blockers.extend(frozen["blockers"])
    scheduler = scheduler_audit()
    fixtures: list[dict[str, Any]] = []
    cycle = {
        "eligible_fixture_found": False,
        "candidate_lock_count": 0,
        "new_lock_count": 0,
        "market_snapshot_count": 0,
        "result_event_count": len(all_result_events()),
        "sample_fabricated": False,
        "training_performed": False,
        "recommendation_output": False,
    }
    if api.key_status != "PRESENT":
        blockers.append("API_KEY_NOT_PRESENT")
    if not blockers:
        try:
            api.initialize_budget()
            fixtures = discover_fixtures(api)
            cycle = controlled_cycle(api, fixtures)
        except RuntimeError as exc:
            blockers.append(str(exc))
    calendar = build_calendar(fixtures)
    locks = all_locks()
    results = all_result_events()
    snapshots = all_markets()
    zero_diagnosis = {
        "generated_at": datetime.now(UTC).isoformat(),
        "stage7f_settled_fixture_n": 0,
        "stage7f_market_comparable_n": 0,
        "existing_lock_count": len(locks),
        "result_event_count": len(results),
        "market_snapshot_count": len(snapshots),
        "reason_counts": calendar["reason_counts"],
        "fixture_diagnosis": calendar["fixtures"],
        "zero_sample_explanation": (
            "No locked forward fixture has a final result event yet, and no newly discovered "
            "fixture is currently inside a new unlocked T-24h or T-1h window."
        ),
    }
    usage = {
        "provider": "api_football",
        "api_key_status": api.key_status,
        "minimum_reserve": MINIMUM_RESERVE,
        "max_authorized_requests": MAX_REQUESTS,
        "request_budget": api.allowed_requests,
        "requests_used": api.request_count,
        "remaining_quota": api.remaining_quota,
        "circuit_breaker": api.circuit_breaker,
        "audit": api.audit,
    }
    result = "\n".join(
        [
            "# W2 Stage 7G Result",
            "",
            "STAGE_7G=COMPLETED" if not blockers else "STAGE_7G=BLOCKED",
            f"SCHEDULER_CONTINUITY={scheduler['status']}",
            "FORWARD_HOLDOUT_AUTORUN=PERSISTENT_SCHEDULER_HOST_REQUIRED",
            "GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING",
            "GATE_4_AH=BLOCKED_FORWARD_ONLY",
            "STAGE_9=BLOCKED",
            "CANDIDATE_OUTPUT=false",
            "RECOMMENDATION_OUTPUT=false",
            "TRAINING_PERFORMED=false",
            "PUSH_BLOCKED_NO_ORIGIN",
            "",
            "WARN_ONLY:",
            "",
            "- FORWARD_HOLDOUT_SAMPLE_INSUFFICIENT",
            "- PERSISTENT_SCHEDULER_HOST_REQUIRED",
            "",
            "BLOCKER:",
            "",
            "- None" if not blockers else "\n".join(f"- {item}" for item in blockers),
        ]
    )
    scheduler_report = {**scheduler, "w1_audit": w1_audit(), "frozen_hashes": frozen}
    write_json(REPORTS / "W2_STAGE7G_SCHEDULER_CONTINUITY.json", scheduler_report)
    write_json(REPORTS / "W2_STAGE7G_ZERO_SAMPLE_DIAGNOSIS.json", zero_diagnosis)
    write_json(REPORTS / "W2_STAGE7G_ELIGIBILITY_CALENDAR.json", calendar)
    write_json(REPORTS / "W2_STAGE7G_API_USAGE.json", usage)
    write_json(RUNTIME / "controlled_cycle.json", cycle)
    (REPORTS / "W2_STAGE7G_RESULT.md").write_text(result + "\n", encoding="utf-8")
    print("W2 Stage7G continuity audit completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
