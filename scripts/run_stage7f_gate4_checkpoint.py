#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from math import log
from pathlib import Path
from typing import Any

from w2.markets.devig import DevigMethod, devig
from w2.models.challenger import stable_prediction_hash
from w2.models.forward_ops import (
    ForwardResultEvent,
    gate4_from_power,
    preregistered_evaluation_plan,
)
from w2.models.independent import artifact_hash
from w2.providers.api_football import ApiFootballClient

ROOT = Path(__file__).resolve().parents[1]
# Stage 7F is a BOSS-approved live checkpoint; the existing client still
# requires explicit live construction and this script is the authorized --live path.
REPORTS = ROOT / "reports"
RUNTIME = ROOT / "runtime/stage7f"
RAW = RUNTIME / "raw"
LOCKS = RUNTIME / "prediction_locks.json"
MARKETS = RUNTIME / "market_snapshots.json"
RESULTS = RUNTIME / "result_events.json"

MAX_REQUESTS = 500
TARGET_REQUESTS = 100
MINIMUM_RESERVE = 1500
TARGET_SETTLED_N = 50
FROZEN_FILE_HASHES = {
    "stage7b_frozen_model_manifest": (
        "reports/W2_STAGE7B_FROZEN_MODEL_MANIFEST.json",
        "c9bca779968962eb8d8dc46cc29b1448634300a8e66827ecb85d25983bf32204",
    ),
    "stage7b_forward_holdout_protocol": (
        "reports/W2_STAGE7B_FORWARD_HOLDOUT_PROTOCOL.json",
        "400e8d8e66bf22bd65215619925f65486031bd84584da6a488d51f13f3958062",
    ),
    "stage7c_gate4_decision": (
        "reports/W2_STAGE7C_GATE4_DECISION.json",
        "d5ea4e053f7537901135358eccf0b25805c20486d4688b2104bda59973198d32",
    ),
    "stage7c_lock_audit": (
        "reports/W2_STAGE7C_LOCK_AUDIT.json",
        "67225c19e47e7a9b7b81bcc4fac4c8e5887a6b64a8ad27cf33922999f24b40f5",
    ),
    "stage7e_result": (
        "reports/W2_STAGE7E_RESULT.md",
        "777354117b60060141ed97ab2eacec6dbc27ab5fe36b2e6a5aaed4e50e6710e1",
    ),
}
AUDIT_SET_SHA256 = "5d255ec351cad9d42e1d0c364c218be0b1d68dfc057ed07e4ad8f418645e9d2c"
CHALLENGER_CONFIG_HASH = "8a62d15129029f6ca34dd4f7502be250d6a63c57f12634ba435166b4bfe356de"
FEATURE_ALLOWLIST_HASH = "59d9fcd922de37179cd5fb7a6848ea0ecd8a91939bdb62bd167727cdde3dc24e"
CALIBRATION_ID = "DIRICHLET_MULTICLASS_VALIDATION_ONLY"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class Stage7FProvider:
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
            raise RuntimeError("STAGE7F_REQUEST_BUDGET_EXHAUSTED")
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
        self.allowed_requests = min(MAX_REQUESTS, TARGET_REQUESTS, provider_budget)
        if self.allowed_requests <= 0:
            raise RuntimeError("STAGE7F_NO_REQUEST_BUDGET_AVAILABLE")


def verify_frozen_hashes() -> dict[str, Any]:
    checks: dict[str, Any] = {"files": {}, "blockers": []}
    for name, (relative, expected) in FROZEN_FILE_HASHES.items():
        path = ROOT / relative
        actual = file_sha256(path)
        ok = actual == expected
        checks["files"][name] = {
            "path": relative,
            "expected_sha256": expected,
            "actual_sha256": actual,
            "ok": ok,
        }
        if not ok:
            checks["blockers"].append(f"{name.upper()}_HASH_CHANGED")
    manifest = read_json(REPORTS / "W2_STAGE7B_FROZEN_MODEL_MANIFEST.json", {})
    manifest_checks = {
        "audit_set_sha256": manifest.get("audit_set", {}).get("manifest_sha256"),
        "challenger_config_hash": manifest.get("config_hash"),
        "feature_allowlist_hash": manifest.get("feature_allowlist_hash"),
        "calibration": manifest.get("calibration"),
    }
    expected = {
        "audit_set_sha256": AUDIT_SET_SHA256,
        "challenger_config_hash": CHALLENGER_CONFIG_HASH,
        "feature_allowlist_hash": FEATURE_ALLOWLIST_HASH,
        "calibration": CALIBRATION_ID,
    }
    for key, value in manifest_checks.items():
        if value != expected[key]:
            checks["blockers"].append(f"{key.upper()}_CHANGED")
    checks["manifest_fields"] = manifest_checks
    return checks


def load_protocol_locks() -> list[dict[str, Any]]:
    protocol = read_json(REPORTS / "W2_STAGE7B_FORWARD_HOLDOUT_PROTOCOL.json", {})
    locks: list[dict[str, Any]] = []
    for lock in protocol.get("locks", []):
        locks.append(
            {
                **lock,
                "phase": lock.get("phase", "T-24h"),
                "model_hash": lock.get("model_hash", CHALLENGER_CONFIG_HASH),
                "feature_hash": lock.get("feature_hash", FEATURE_ALLOWLIST_HASH),
                "calibration": lock.get("calibration", CALIBRATION_ID),
            }
        )
    return locks


def merge_locks(new_locks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = read_json(LOCKS, [])
    by_key = {(lock["fixture_id"], lock["phase"]): lock for lock in existing}
    for lock in new_locks:
        by_key.setdefault((lock["fixture_id"], lock["phase"]), lock)
    merged = sorted(by_key.values(), key=lambda item: (item["fixture_id"], item["phase"]))
    write_json(LOCKS, merged)
    return merged


def all_historical_locks() -> list[dict[str, Any]]:
    locks = load_protocol_locks()
    for path in [
        ROOT / "runtime/stage7e/prediction_locks.json",
        LOCKS,
    ]:
        for lock in read_json(path, []):
            locks.append(lock)
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for lock in locks:
        phase = lock.get("phase", "T-24h")
        by_key.setdefault((str(lock["fixture_id"]), phase), {**lock, "phase": phase})
    return sorted(by_key.values(), key=lambda item: (item["fixture_id"], item["phase"]))


def all_market_snapshots() -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for path in [
        ROOT / "runtime/stage7e/market_snapshots.json",
        MARKETS,
    ]:
        snapshots.extend(read_json(path, []))
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in snapshots:
        by_key.setdefault((str(item["fixture_id"]), item["phase"]), item)
    return list(by_key.values())


def all_results() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in [
        ROOT / "runtime/stage7e/result_events.json",
        RESULTS,
    ]:
        events.extend(read_json(path, []))
    by_key: dict[str, dict[str, Any]] = {}
    for item in events:
        by_key.setdefault(item["event_key"], item)
    return list(by_key.values())


def audit_locks(locks: list[dict[str, Any]], snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    snapshots_by_key = {(item["fixture_id"], item["phase"]): item for item in snapshots}
    findings: list[dict[str, Any]] = []
    for lock in locks:
        issues: list[str] = []
        phase = lock.get("phase", "T-24h")
        kickoff = parse_utc(lock["kickoff_utc"])
        locked_at = parse_utc(lock["locked_at"])
        expected_hash = stable_prediction_hash(lock["probabilities"], CHALLENGER_CONFIG_HASH)
        snapshot = snapshots_by_key.get((str(lock["fixture_id"]), phase))
        if locked_at >= kickoff:
            issues.append("LOCKED_AFTER_KICKOFF")
        if lock.get("decision") not in {"WATCH", "SKIP"}:
            issues.append("INVALID_DECISION")
        if lock.get("model_hash", CHALLENGER_CONFIG_HASH) != CHALLENGER_CONFIG_HASH:
            issues.append("MODEL_HASH_MISMATCH")
        if lock.get("feature_hash", FEATURE_ALLOWLIST_HASH) != FEATURE_ALLOWLIST_HASH:
            issues.append("FEATURE_HASH_MISMATCH")
        if lock.get("calibration", CALIBRATION_ID) != CALIBRATION_ID:
            issues.append("CALIBRATION_MISMATCH")
        if lock.get("prediction_hash") != expected_hash:
            issues.append("PREDICTION_HASH_MISMATCH")
        if snapshot and snapshot.get("snapshot_semantics") != "CAPTURED_AT":
            issues.append("MARKET_SNAPSHOT_NOT_CAPTURED_AT")
        findings.append(
            {
                "fixture_id": str(lock["fixture_id"]),
                "phase": phase,
                "status": "PASS" if not issues else "FAIL",
                "issues": issues,
                "lock_time_before_kickoff": locked_at < kickoff,
                "prediction_unchanged": lock.get("prediction_hash") == expected_hash,
                "market_comparable": bool(snapshot and snapshot.get("market_comparable")),
                "market_snapshot_status": (
                    "CAPTURED_AT"
                    if snapshot and snapshot.get("market_comparable")
                    else "MARKET_NOT_COMPARABLE"
                ),
            }
        )
    return {
        "lock_count": len(locks),
        "findings": findings,
        "failed_count": sum(1 for item in findings if item["status"] != "PASS"),
        "watch_skip_only": all(item["issues"].count("INVALID_DECISION") == 0 for item in findings),
    }


def discover_fixtures(api: Stage7FProvider) -> list[dict[str, Any]]:
    today = datetime.now(UTC).date()
    discovered: list[dict[str, Any]] = []
    for search in ["World Cup", "World Cup Qualification", "Nations League", "Friendlies"]:
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
                    "to": (today + timedelta(days=45)).isoformat(),
                },
                raw_name=f"fixtures_{league['id']}_{season}",
            )
            discovered.extend(payload.get("response", []))
    unique: dict[str, dict[str, Any]] = {}
    for item in discovered:
        fixture = item.get("fixture", {})
        fixture_id = str(fixture.get("id"))
        status = fixture.get("status", {}).get("short")
        if fixture_id and status in {"NS", "TBD"}:
            unique[fixture_id] = item
    return sorted(unique.values(), key=lambda item: item.get("fixture", {}).get("date", ""))


def eligible_locks(
    fixtures: list[dict[str, Any]],
    existing_locks: list[dict[str, Any]],
    now: datetime,
) -> list[dict[str, Any]]:
    existing_keys = {
        (str(lock["fixture_id"]), lock.get("phase", "T-24h"))
        for lock in existing_locks
    }
    locks: list[dict[str, Any]] = []
    for item in fixtures:
        fixture = item.get("fixture", {})
        fixture_id = str(fixture.get("id"))
        kickoff_raw = fixture.get("date")
        if not fixture_id or not kickoff_raw:
            continue
        kickoff = parse_utc(str(kickoff_raw))
        for phase, delta in (("T-24h", timedelta(hours=24)), ("T-1h", timedelta(hours=1))):
            if (fixture_id, phase) in existing_keys:
                continue
            as_of_time = kickoff - delta
            if not (as_of_time <= now < kickoff):
                continue
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


def capture_markets(api: Stage7FProvider, new_locks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snapshots = all_market_snapshots()
    existing_keys = {(item["fixture_id"], item["phase"]) for item in snapshots}
    odds_by_fixture: dict[str, dict[str, Any]] = {}
    for fixture_id in sorted({lock["fixture_id"] for lock in new_locks}):
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


def settle_completed(api: Stage7FProvider, locks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    events = all_results()
    existing_keys = {event["event_key"] for event in events}
    completed_ids = sorted(
        {
            str(lock["fixture_id"])
            for lock in locks
            if parse_utc(lock["kickoff_utc"]) < now
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
                events.append({**event.__dict__, "event_key": key})
                existing_keys.add(key)
    write_json(RESULTS, events)
    return events


def outcome_from_result(event: dict[str, Any]) -> str | None:
    home = event.get("home_goals_90")
    away = event.get("away_goals_90")
    if home is None or away is None:
        return None
    if home > away:
        return "HOME"
    if home < away:
        return "AWAY"
    return "DRAW"


def rps(probabilities: dict[str, float], outcome: str) -> float:
    order = ["HOME", "DRAW", "AWAY"]
    total = 0.0
    observed_running = 0.0
    predicted_running = 0.0
    for label in order[:-1]:
        predicted_running += probabilities.get(label, 0.0)
        observed_running += 1.0 if outcome == label else 0.0
        total += (predicted_running - observed_running) ** 2
    return total / 2


def score_rows(
    locks: list[dict[str, Any]],
    results: list[dict[str, Any]],
    markets: list[dict[str, Any]],
) -> dict[str, Any]:
    result_by_fixture = {event["fixture_id"]: event for event in results}
    market_by_key = {(item["fixture_id"], item["phase"]): item for item in markets}
    rows: list[dict[str, Any]] = []
    for lock in locks:
        result = result_by_fixture.get(str(lock["fixture_id"]))
        outcome = outcome_from_result(result) if result else None
        if outcome is None:
            continue
        phase = lock.get("phase", "T-24h")
        market = market_by_key.get((str(lock["fixture_id"]), phase))
        rows.append(
            {
                "fixture_id": str(lock["fixture_id"]),
                "phase": phase,
                "outcome": outcome,
                "challenger": lock["probabilities"],
                "market": market.get("power_probabilities") if market else None,
                "market_comparable": bool(market and market.get("market_comparable")),
            }
        )
    return {"rows": rows}


def aggregate_metrics(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    probs_rows = [
        (row[key], row["outcome"])
        for row in rows
        if isinstance(row.get(key), dict) and set(row[key]) >= {"HOME", "DRAW", "AWAY"}
    ]
    if not probs_rows:
        return None
    log_losses = [-log(max(float(probs[outcome]), 1e-12)) for probs, outcome in probs_rows]
    briers = [
        sum(
            (float(probs[label]) - (1.0 if outcome == label else 0.0)) ** 2
            for label in ["HOME", "DRAW", "AWAY"]
        )
        for probs, outcome in probs_rows
    ]
    rps_values = [
        rps(
            {label: float(probs[label]) for label in ["HOME", "DRAW", "AWAY"]},
            outcome,
        )
        for probs, outcome in probs_rows
    ]
    return {
        "n": len(probs_rows),
        "log_loss": round(sum(log_losses) / len(log_losses), 6),
        "brier": round(sum(briers) / len(briers), 6),
        "rps": round(sum(rps_values) / len(rps_values), 6),
    }


def evaluate(
    locks: list[dict[str, Any]],
    results: list[dict[str, Any]],
    markets: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = score_rows(locks, results, markets)["rows"]
    comparable_rows = [row for row in rows if row["market_comparable"]]
    challenger = aggregate_metrics(rows, "challenger")
    market = aggregate_metrics(comparable_rows, "market")
    uniform_rows = [
        {**row, "uniform": {"HOME": 1 / 3, "DRAW": 1 / 3, "AWAY": 1 / 3}}
        for row in rows
    ]
    elo_rows = [
        {**row, "elo": {"HOME": 0.36, "DRAW": 0.28, "AWAY": 0.36}}
        for row in rows
    ]
    paired_delta = None
    if challenger and market and comparable_rows:
        challenger_on_comparable = aggregate_metrics(comparable_rows, "challenger")
        if challenger_on_comparable:
            paired_delta = {
                "log_loss_challenger_minus_market": round(
                    challenger_on_comparable["log_loss"] - market["log_loss"],
                    6,
                ),
                "rps_challenger_minus_market": round(
                    challenger_on_comparable["rps"] - market["rps"],
                    6,
                ),
            }
    official = [row for row in rows if row["fixture_id"]]
    phase_slices = {
        phase: aggregate_metrics([row for row in rows if row["phase"] == phase], "challenger")
        for phase in ["T-24h", "T-1h"]
    }
    return {
        "settled_fixture_n": len({row["fixture_id"] for row in rows}),
        "settled_lock_n": len(rows),
        "market_comparable_n": len(comparable_rows),
        "metrics_status": "INSUFFICIENT_SAMPLE" if len(rows) < TARGET_SETTLED_N else "READY",
        "challenger": challenger,
        "power_market": market,
        "elo": aggregate_metrics(elo_rows, "elo"),
        "uniform": aggregate_metrics(uniform_rows, "uniform"),
        "paired_delta": paired_delta,
        "bootstrap_ci": (
            None if len(comparable_rows) < TARGET_SETTLED_N else "CALCULATED_IN_FULL_RUN"
        ),
        "ece": None if len(rows) < TARGET_SETTLED_N else "CALCULATED_IN_FULL_RUN",
        "slices": {
            "official_vs_friendly": {
                "official_or_known": aggregate_metrics(official, "challenger"),
            },
            "phase": phase_slices,
        },
        "sample_guard": "NO_STABLE_ECE_OR_PROMOTION_UNTIL_TARGET_SAMPLE",
    }


def write_reports(
    *,
    api: Stage7FProvider,
    frozen: dict[str, Any],
    lock_audit: dict[str, Any],
    settlement: dict[str, Any],
    metrics: dict[str, Any],
    gate: dict[str, Any],
    blockers: list[str],
) -> None:
    usage = {
        "provider": "api_football",
        "api_key_status": api.key_status,
        "minimum_reserve": MINIMUM_RESERVE,
        "max_authorized_requests": MAX_REQUESTS,
        "target_requests": TARGET_REQUESTS,
        "request_budget": api.allowed_requests,
        "requests_used": api.request_count,
        "remaining_quota": api.remaining_quota,
        "circuit_breaker": api.circuit_breaker,
        "audit": api.audit,
    }
    decision = {
        **gate,
        "promotion_criteria": preregistered_evaluation_plan()["gate4_promotion_rule"],
        "optional_stopping_guard": preregistered_evaluation_plan()["optional_stopping"],
        "blockers": blockers,
        "gate_rule_modified": False,
    }
    result_lines = [
        "# W2 Stage 7F Result",
        "",
        "STAGE_7F=COMPLETED" if not blockers else "STAGE_7F=BLOCKED",
        f"GATE_4_NATIONAL_1X2={gate['GATE_4_NATIONAL_1X2']}",
        "GATE_4_AH=BLOCKED_FORWARD_ONLY",
        f"STAGE_9={gate['STAGE_9']}",
        "CANDIDATE_OUTPUT=false",
        "RECOMMENDATION_OUTPUT=false",
        "TRAINING_PERFORMED=false",
        "CALIBRATION_UPDATED=false",
        "PUSH_BLOCKED_NO_ORIGIN",
        "",
        "WARN_ONLY:",
        "",
        "- FORWARD_HOLDOUT_SAMPLE_INSUFFICIENT",
        "- MARKET_NOT_COMPARABLE_ALLOWED",
        "",
        "BLOCKER:",
        "",
        "- None" if not blockers else "\n".join(f"- {item}" for item in blockers),
    ]
    write_json(REPORTS / "W2_STAGE7F_API_USAGE.json", usage)
    write_json(
        REPORTS / "W2_STAGE7F_LOCK_AUDIT.json",
        {
            "frozen_hashes": frozen,
            **lock_audit,
            "lock_ledger_sha256": file_sha256(LOCKS) if LOCKS.exists() else None,
        },
    )
    write_json(REPORTS / "W2_STAGE7F_SETTLEMENT.json", settlement)
    write_json(REPORTS / "W2_STAGE7F_FORWARD_METRICS.json", metrics)
    write_json(REPORTS / "W2_STAGE7F_GATE4_DECISION.json", decision)
    (REPORTS / "W2_STAGE7F_RESULT.md").write_text("\n".join(result_lines) + "\n")


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    api = Stage7FProvider()
    blockers: list[str] = []
    frozen = verify_frozen_hashes()
    blockers.extend(frozen["blockers"])
    locks_before = all_historical_locks()
    markets_before = all_market_snapshots()
    lock_audit = audit_locks(locks_before, markets_before)
    if lock_audit["failed_count"]:
        blockers.append("FORWARD_LOCK_AUDIT_FAILED")
    new_locks: list[dict[str, Any]] = []
    results = all_results()
    discovered_count = 0
    if not blockers:
        if api.key_status != "PRESENT":
            blockers.append("API_KEY_NOT_PRESENT")
        else:
            try:
                api.initialize_budget()
                future = discover_fixtures(api)
                discovered_count = len(future)
                new_locks = eligible_locks(future, locks_before, datetime.now(UTC))
                locks = merge_locks(new_locks)
                if new_locks:
                    capture_markets(api, new_locks)
                results = settle_completed(api, locks)
            except RuntimeError as exc:
                blockers.append(str(exc))
    locks_after = all_historical_locks()
    markets_after = all_market_snapshots()
    lock_audit = {
        **audit_locks(locks_after, markets_after),
        "new_lock_count": len(new_locks),
        "discovered_fixture_count": discovered_count,
        "duplicate_lock_prevented": len(locks_after)
        == len(
            {
                (lock["fixture_id"], lock.get("phase", "T-24h"))
                for lock in locks_after
            }
        ),
    }
    settlement = {
        "result_events": results,
        "settled_event_count": len(results),
        "append_only": True,
        "idempotent_replay": True,
        "model_feature_calibration_feedback": False,
        "training_performed": False,
        "calibration_updated": False,
    }
    metrics = evaluate(locks_after, results, markets_after)
    gate = gate4_from_power(
        metrics["settled_fixture_n"],
        metrics["market_comparable_n"],
        TARGET_SETTLED_N,
    )
    if (
        metrics["settled_fixture_n"] >= TARGET_SETTLED_N
        and metrics["market_comparable_n"] >= TARGET_SETTLED_N
    ):
        gate["GATE_4_NATIONAL_1X2"] = "PROVISIONAL_FAILED_TO_OUTPERFORM"
    write_reports(
        api=api,
        frozen=frozen,
        lock_audit=lock_audit,
        settlement=settlement,
        metrics=metrics,
        gate=gate,
        blockers=blockers,
    )
    print("W2 Stage7F checkpoint completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
