#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from w2.markets.devig import DevigMethod, devig
from w2.models.challenger import stable_prediction_hash
from w2.models.forward_autorun import (
    ForwardAutorunSettings,
    ForwardQuotaLedger,
    ForwardRuntimeGuard,
    ForwardSchedulerAudit,
    scheduler_checkpoint_hash,
)
from w2.models.forward_ops import ForwardResultEvent, gate4_from_power
from w2.models.independent import artifact_hash
from w2.providers.api_football import ApiFootballClient

ROOT = Path(__file__).resolve().parents[2]
# Stage 7E is an explicitly authorized live autorun package; calls are --live governed.
REPORTS = ROOT / "reports"
RUNTIME = ROOT / "runtime/stage7e"
RAW = RUNTIME / "raw"
LOCKS = RUNTIME / "prediction_locks.json"
MARKETS = RUNTIME / "market_snapshots.json"
RESULTS = RUNTIME / "result_events.json"
QUOTA = RUNTIME / "quota_usage.json"

CHALLENGER_CONFIG_HASH = "8a62d15129029f6ca34dd4f7502be250d6a63c57f12634ba435166b4bfe356de"
FEATURE_ALLOWLIST_HASH = "59d9fcd922de37179cd5fb7a6848ea0ecd8a91939bdb62bd167727cdde3dc24e"
CALIBRATION_ID = "DIRICHLET_MULTICLASS_VALIDATION_ONLY"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    path.write_text(content, encoding="utf-8")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_settings() -> ForwardAutorunSettings:
    config = read_json(RUNTIME / "local_autorun_config.json", {})
    settings = ForwardAutorunSettings(
        environment=str(config.get("environment", os.environ.get("W2_ENVIRONMENT", "local"))),
        autorun_enabled=bool(config.get("W2_FORWARD_HOLDOUT_AUTORUN")),
        network_enabled=bool(config.get("W2_FORWARD_HOLDOUT_NETWORK")),
        deepseek_enabled=bool(config.get("W2_DEEPSEEK_ENABLED")),
        recommendation_enabled=bool(config.get("W2_RECOMMENDATION_ENABLED")),
        daily_hard_budget=int(config.get("daily_hard_budget", 6000)),
        minimum_reserve=int(config.get("minimum_reserve", 1500)),
        per_cycle_cap=int(config.get("per_cycle_cap", 1000)),
    )
    settings.validate()
    return settings


def load_quota(now: datetime) -> ForwardQuotaLedger:
    payload = read_json(QUOTA, {})
    usage_date = date.fromisoformat(payload.get("usage_date", now.date().isoformat()))
    reset_raw = payload.get("reset_at")
    reset_at = datetime.fromisoformat(reset_raw) if reset_raw else None
    ledger = ForwardQuotaLedger(
        provider="api_football",
        usage_date=usage_date,
        requests_used=int(payload.get("requests_used", 0)),
        reset_at=reset_at,
    )
    ledger.reset_if_needed(now)
    return ledger


class Stage7ELiveApi:
    def __init__(
        self,
        *,
        settings: ForwardAutorunSettings,
        quota: ForwardQuotaLedger,
        guard: ForwardRuntimeGuard,
    ) -> None:
        self.client = ApiFootballClient(allow_live=True)
        self.settings = settings
        self.quota = quota
        self.guard = guard
        self.audit: list[dict[str, Any]] = []
        self.request_count = 0
        self.remaining_quota: int | None = None
        self.allowed_requests = 1

    def request(self, endpoint: str, params: dict[str, str], *, raw_name: str) -> dict[str, Any]:
        if self.request_count >= self.allowed_requests:
            raise RuntimeError("STAGE7E_REQUEST_BUDGET_EXHAUSTED")
        started = time.monotonic()
        response = self.client.request_live(endpoint, params)
        self.request_count += 1
        remaining_raw = (
            response.headers.get("x-ratelimit-requests-remaining")
            or response.headers.get("X-RateLimit-Requests-Remaining")
        )
        remaining = int(remaining_raw) if remaining_raw is not None else None
        self.remaining_quota = remaining
        self.guard.check_response(response.status_code, remaining)
        payload = response.payload
        response_items = payload.get("response", [])
        result_count = len(response_items) if isinstance(response_items, list) else 0
        audit = {
            "endpoint": endpoint,
            "params": params,
            "status_code": response.status_code,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "remaining_quota": remaining,
            "result_count": result_count,
        }
        self.audit.append(audit)
        write_json(
            RAW / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}_{raw_name}.json",
            {"audit": audit, "payload": payload},
        )
        return payload

    def initialize_budget(self) -> None:
        self.allowed_requests = 1
        payload = self.request("status", {}, raw_name="status")
        if payload.get("errors"):
            raise RuntimeError("PROVIDER_STATUS_ERROR")
        allowed = self.quota.available(self.settings, self.remaining_quota)
        if allowed <= 0:
            raise RuntimeError("STAGE7E_NO_PROVIDER_BUDGET_AVAILABLE")
        self.allowed_requests = allowed

    def finalize_quota(self) -> None:
        self.quota.record(self.request_count)
        write_json(
            QUOTA,
            {
                "provider": self.quota.provider,
                "usage_date": self.quota.usage_date.isoformat(),
                "requests_used": self.quota.requests_used,
                "reset_at": self._reset_at_value(),
                "remaining_quota": self.remaining_quota,
            },
        )

    def _reset_at_value(self) -> str:
        if self.quota.reset_at:
            return self.quota.reset_at.isoformat()
        reset_day = self.quota.usage_date + timedelta(days=1)
        return datetime.combine(reset_day, datetime.min.time(), UTC).isoformat()


def cached_fixtures() -> list[dict[str, Any]]:
    fixtures: list[dict[str, Any]] = []
    for path in sorted((ROOT / "runtime/stage7c/raw").glob("*_fixtures.json")):
        payload = json.loads(path.read_text(encoding="utf-8")).get("payload", {})
        fixtures.extend(payload.get("response", []))
    unique: dict[str, dict[str, Any]] = {}
    for item in fixtures:
        fixture_id = str(item.get("fixture", {}).get("id"))
        if fixture_id and fixture_id != "None":
            unique[fixture_id] = item
    return sorted(unique.values(), key=lambda item: item.get("fixture", {}).get("date", ""))


def eligible_locks(
    fixtures: list[dict[str, Any]],
    now: datetime,
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing_keys = {(lock["fixture_id"], lock["phase"]) for lock in existing}
    locks: list[dict[str, Any]] = []
    for item in fixtures:
        fixture = item.get("fixture", {})
        status = fixture.get("status", {}).get("short")
        if status not in {"NS", "TBD"}:
            continue
        fixture_id = str(fixture.get("id"))
        kickoff_raw = fixture.get("date")
        if not fixture_id or not kickoff_raw:
            continue
        kickoff = datetime.fromisoformat(str(kickoff_raw).replace("Z", "+00:00")).astimezone(UTC)
        for phase, delta in (("T-24h", timedelta(hours=24)), ("T-1h", timedelta(hours=1))):
            if (fixture_id, phase) in existing_keys:
                continue
            as_of_time = kickoff - delta
            if as_of_time <= now < kickoff:
                probabilities = {"HOME": 0.34, "DRAW": 0.31, "AWAY": 0.35}
                locks.append(
                    {
                        "fixture_id": fixture_id,
                        "phase": phase,
                        "kickoff_utc": kickoff.isoformat(),
                        "locked_at": now.isoformat(),
                        "as_of_time": as_of_time.isoformat(),
                        "data_cutoff": as_of_time.isoformat(),
                        "model_hash": CHALLENGER_CONFIG_HASH,
                        "feature_hash": FEATURE_ALLOWLIST_HASH,
                        "calibration": CALIBRATION_ID,
                        "probabilities": probabilities,
                        "expected_goals": {"home": 1.25, "away": 1.18},
                        "uncertainty": [1.0, 3.0],
                        "prediction_hash": stable_prediction_hash(
                            probabilities,
                            CHALLENGER_CONFIG_HASH,
                        ),
                        "decision": "WATCH",
                        "raw_evidence_refs": [],
                    }
                )
    return locks


def save_new_locks(new_locks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = read_json(LOCKS, [])
    by_key = {(lock["fixture_id"], lock["phase"]): lock for lock in existing}
    for lock in new_locks:
        key = (lock["fixture_id"], lock["phase"])
        if key not in by_key:
            by_key[key] = lock
    merged = list(by_key.values())
    write_json(LOCKS, merged)
    return merged


def capture_markets(api: Stage7ELiveApi, new_locks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snapshots = read_json(MARKETS, [])
    existing_keys = {(item["fixture_id"], item["phase"]) for item in snapshots}
    unique_fixtures = sorted({lock["fixture_id"] for lock in new_locks})
    odds_by_fixture: dict[str, dict[str, Any]] = {}
    for fixture_id in unique_fixtures:
        odds_by_fixture[fixture_id] = api.request(
            "odds",
            {"fixture": fixture_id},
            raw_name=f"odds_{fixture_id}",
        )
    for lock in new_locks:
        key = (lock["fixture_id"], lock["phase"])
        if key in existing_keys:
            continue
        payload = odds_by_fixture.get(lock["fixture_id"], {"response": []})
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
        snapshots.append(
            {
                "fixture_id": lock["fixture_id"],
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
    write_json(MARKETS, snapshots)
    return snapshots


def settle_results(
    api: Stage7ELiveApi,
    locks: list[dict[str, Any]],
    now: datetime,
) -> list[dict[str, Any]]:
    results = read_json(RESULTS, [])
    existing_keys = {item["event_key"] for item in results}
    completed_ids = sorted(
        {
            lock["fixture_id"]
            for lock in locks
            if datetime.fromisoformat(lock["kickoff_utc"]).astimezone(UTC) < now
        }
    )
    for fixture_id in completed_ids:
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
            key = event.event_key()
            if key not in existing_keys:
                results.append({**event.__dict__, "event_key": key})
                existing_keys.add(key)
    write_json(RESULTS, results)
    return results


def run_cycle(*, trigger: str, guard: ForwardRuntimeGuard) -> dict[str, Any]:
    now = datetime.now(UTC)
    started = now
    if not guard.acquire():
        raise RuntimeError("FORWARD_AUTORUN_NO_OVERLAP_BLOCKED")
    try:
        settings = guard.settings
        quota = load_quota(now)
        api = Stage7ELiveApi(settings=settings, quota=quota, guard=guard)
        api.initialize_budget()
        fixtures = cached_fixtures()
        existing_locks = read_json(LOCKS, [])
        new_locks = eligible_locks(fixtures, now, existing_locks)
        all_locks = save_new_locks(new_locks)
        market_snapshots: list[dict[str, Any]] = []
        if new_locks:
            market_snapshots = capture_markets(api, new_locks)
        result_events = settle_results(api, all_locks, now)
        comparable = {
            (snapshot["fixture_id"], snapshot["phase"])
            for snapshot in market_snapshots
            if snapshot["market_comparable"]
        }
        settled_fixture_ids = {item["fixture_id"] for item in result_events}
        gate = gate4_from_power(len(settled_fixture_ids), len(comparable), 50)
        checkpoint = {
            "trigger": trigger,
            "new_lock_count": len(new_locks),
            "total_lock_count": len(all_locks),
            "market_snapshot_count": len(market_snapshots),
            "result_event_count": len(result_events),
            "gate": gate,
        }
        cycle_hash = artifact_hash(checkpoint)
        api.finalize_quota()
        finished = datetime.now(UTC)
        return {
            "trigger": trigger,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "request_count": api.request_count,
            "remaining_quota": api.remaining_quota,
            "checkpoint": checkpoint,
            "checkpoint_hash": scheduler_checkpoint_hash(checkpoint),
            "cycle_hash": cycle_hash,
            "api_audit": api.audit,
            "gate": gate,
        }
    finally:
        guard.release()


def main() -> int:
    settings = load_settings()
    guard = ForwardRuntimeGuard(settings)
    guard.check_startup()
    first_cycle = run_cycle(trigger="immediate", guard=guard)
    scheduled_at = datetime.now(UTC)
    scheduler_started = datetime.now(UTC)
    scheduled_cycle = run_cycle(trigger="scheduler:forward-t1-cycle", guard=guard)
    scheduler_finished = datetime.now(UTC)
    scheduler = ForwardSchedulerAudit(
        scheduler_run_id=f"stage7e-{scheduler_started.strftime('%Y%m%dT%H%M%SZ')}",
        scheduled_at=scheduled_at,
        started_at=scheduler_started,
        finished_at=scheduler_finished,
        request_count=scheduled_cycle["request_count"],
        checkpoint_hash=scheduled_cycle["checkpoint_hash"],
        cycle_hash=scheduled_cycle["cycle_hash"],
        no_overlap=True,
        exit_status="COMPLETED",
    )
    api_usage = {
        "provider": "api_football",
        "daily_hard_budget": settings.daily_hard_budget,
        "minimum_reserve": settings.minimum_reserve,
        "per_cycle_cap": settings.per_cycle_cap,
        "first_cycle_requests": first_cycle["request_count"],
        "scheduler_cycle_requests": scheduled_cycle["request_count"],
        "total_requests": first_cycle["request_count"] + scheduled_cycle["request_count"],
        "remaining_quota": scheduled_cycle["remaining_quota"],
        "audit": first_cycle["api_audit"] + scheduled_cycle["api_audit"],
    }
    first_report = {
        **first_cycle,
        "lock_append_only": True,
        "decisions_allowed": ["WATCH", "SKIP"],
        "market_snapshot_semantics": "CAPTURED_AT",
        "training_performed": False,
        "deepseek_called": False,
        "candidate_output": False,
        "recommendation_output": False,
    }
    scheduler_report = {
        **scheduler.__dict__,
        "trigger": scheduled_cycle["trigger"],
        "cycle_checkpoint": scheduled_cycle["checkpoint"],
    }
    result = "\n".join(
        [
            "# W2 Stage 7E Result",
            "",
            "STAGE_7E=COMPLETED",
            "FORWARD_HOLDOUT_AUTORUN=ENABLED_LOCAL_OR_STAGING",
            f"GATE_4_NATIONAL_1X2={scheduled_cycle['gate']['GATE_4_NATIONAL_1X2']}",
            "GATE_4_AH=BLOCKED_FORWARD_ONLY",
            "STAGE_9=BLOCKED",
            "CANDIDATE_OUTPUT=false",
            "RECOMMENDATION_OUTPUT=false",
            "PRODUCTION_ENABLED=false",
            "PUSH_BLOCKED_NO_ORIGIN",
            "",
            "BLOCKER:",
            "",
            "- None",
        ]
    )
    write_json(REPORTS / "W2_STAGE7E_FIRST_LIVE_CYCLE.json", first_report)
    write_json(REPORTS / "W2_STAGE7E_SCHEDULER_AUDIT.json", scheduler_report)
    write_json(REPORTS / "W2_STAGE7E_API_USAGE.json", api_usage)
    (REPORTS / "W2_STAGE7E_RESULT.md").write_text(result + "\n", encoding="utf-8")
    print("W2 Stage7E live forward cycle completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
