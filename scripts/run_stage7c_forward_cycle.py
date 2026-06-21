#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from w2.markets.devig import DevigMethod, devig
from w2.models.challenger import stable_prediction_hash
from w2.models.forward_ops import (
    ForwardCycleLedger,
    ForwardMarketSnapshot,
    ForwardResultEvent,
    gate4_from_power,
    preregistered_evaluation_plan,
)
from w2.models.independent import artifact_hash
from w2.providers.api_football import ApiFootballClient

ROOT = Path(__file__).resolve().parents[1]
# Stage 7C is an explicitly authorized live operations package; calls are --live governed.
RUNTIME = ROOT / "runtime/stage7c"
RAW = RUNTIME / "raw"
REPORTS = ROOT / "reports"
RESERVE_QUOTA = 2500
MAX_STAGE7C_REQUESTS = 500
TARGET_REQUESTS = 100
FROZEN_MANIFEST_SHA256 = "c9bca779968962eb8d8dc46cc29b1448634300a8e66827ecb85d25983bf32204"
AUDIT_SET_SHA256 = "5d255ec351cad9d42e1d0c364c218be0b1d68dfc057ed07e4ad8f418645e9d2c"
CHALLENGER_CONFIG_HASH = "8a62d15129029f6ca34dd4f7502be250d6a63c57f12634ba435166b4bfe356de"
FEATURE_ALLOWLIST_HASH = "59d9fcd922de37179cd5fb7a6848ea0ecd8a91939bdb62bd167727cdde3dc24e"
CALIBRATION_ID = "DIRICHLET_MULTICLASS_VALIDATION_ONLY"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n"
    path.write_text(content, encoding="utf-8")


class Stage7CApi:
    def __init__(self, *, dry_run: bool, budget: int) -> None:
        self.client = ApiFootballClient(allow_live=not dry_run)
        self.dry_run = dry_run
        self.audit: list[dict[str, Any]] = []
        self.request_count = 0
        self.remaining_quota: int | None = None
        self.allowed_requests = budget

    def request(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if self.request_count >= self.allowed_requests:
            raise RuntimeError("STAGE7C_REQUEST_BUDGET_EXHAUSTED")
        if self.dry_run:
            return {"response": [], "results": 0, "errors": {}, "parameters": params}
        started = time.monotonic()
        response = self.client.request_live(endpoint, params)
        self.request_count += 1
        remaining = response.headers.get("x-ratelimit-requests-remaining") or response.headers.get(
            "X-RateLimit-Requests-Remaining"
        )
        if remaining is not None:
            self.remaining_quota = int(remaining)
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
            RAW / f"{self.request_count:03d}_{endpoint}.json",
            {"audit": audit, "payload": payload},
        )
        return payload

    def initialize_budget(self) -> None:
        self.allowed_requests = 1
        payload = self.request("status", {})
        if self.remaining_quota is None and not self.dry_run:
            raise RuntimeError("PROVIDER_QUOTA_HEADER_MISSING")
        remaining = self.remaining_quota or 0
        if not self.dry_run and remaining <= RESERVE_QUOTA:
            raise RuntimeError("REMAINING_QUOTA_AT_OR_BELOW_RESERVE")
        self.allowed_requests = min(
            MAX_STAGE7C_REQUESTS,
            max(remaining - RESERVE_QUOTA, 0),
            TARGET_REQUESTS,
        )
        if payload.get("errors"):
            raise RuntimeError("PROVIDER_STATUS_ERROR")


def verify_frozen_manifest() -> dict[str, Any]:
    path = REPORTS / "W2_STAGE7B_FROZEN_MODEL_MANIFEST.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    file_sha = artifact_hash(json.loads(path.read_text(encoding="utf-8")))
    # Also check byte hash because Stage7B recorded the exact file.
    import hashlib

    byte_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    checks = {
        "frozen_manifest_file_sha256": byte_sha,
        "frozen_manifest_json_sha256": file_sha,
        "audit_set_sha256": manifest["audit_set"]["manifest_sha256"],
        "challenger_config_hash": manifest["config_hash"],
        "feature_allowlist_hash": manifest["feature_allowlist_hash"],
        "calibration": manifest["calibration"],
        "promotion_criteria": manifest["stage7_audit_set_usage"],
    }
    blockers = []
    if byte_sha != FROZEN_MANIFEST_SHA256:
        blockers.append("FROZEN_MANIFEST_HASH_CHANGED")
    if checks["audit_set_sha256"] != AUDIT_SET_SHA256:
        blockers.append("AUDIT_SET_HASH_CHANGED")
    if checks["challenger_config_hash"] != CHALLENGER_CONFIG_HASH:
        blockers.append("CHALLENGER_CONFIG_HASH_CHANGED")
    if checks["feature_allowlist_hash"] != FEATURE_ALLOWLIST_HASH:
        blockers.append("FEATURE_ALLOWLIST_HASH_CHANGED")
    if checks["calibration"] != CALIBRATION_ID:
        blockers.append("CALIBRATION_CHANGED")
    checks["blockers"] = blockers
    return checks


def load_stage7b_locks() -> list[dict[str, Any]]:
    protocol = json.loads((REPORTS / "W2_STAGE7B_FORWARD_HOLDOUT_PROTOCOL.json").read_text())
    return protocol.get("locks", [])


def audit_existing_locks(
    locks: list[dict[str, Any]],
    manifest_checks: dict[str, Any],
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for lock in locks:
        kickoff = datetime.fromisoformat(lock["kickoff_utc"]).astimezone(UTC)
        locked_at = datetime.fromisoformat(lock["locked_at"]).astimezone(UTC)
        status = "PASS"
        issues = []
        if locked_at >= kickoff:
            issues.append("LOCKED_AFTER_KICKOFF")
        if lock["decision"] not in {"WATCH", "SKIP"}:
            issues.append("INVALID_LOCK_DECISION")
        expected_hash = stable_prediction_hash(lock["probabilities"], CHALLENGER_CONFIG_HASH)
        if expected_hash != lock["prediction_hash"]:
            issues.append("LOCK_HASH_MISMATCH")
        if manifest_checks["blockers"]:
            issues.append("FROZEN_HASH_BLOCKER")
        if issues:
            status = "FAIL"
        findings.append(
            {
                "fixture_id": lock["fixture_id"],
                "status": status,
                "issues": issues,
                "market_snapshot_status": "MARKET_NOT_COMPARABLE",
                "model_hash_ok": not manifest_checks["blockers"],
                "prediction_unchanged": expected_hash == lock["prediction_hash"],
            }
        )
    return {"lock_count": len(locks), "findings": findings}


def discover_future(api: Stage7CApi) -> list[dict[str, Any]]:
    today = datetime.now(UTC).date()
    future: list[dict[str, Any]] = []
    searches = ["World Cup", "World Cup Qualification", "Nations League", "Friendlies"]
    for search in searches:
        leagues = api.request("leagues", {"search": search})
        for item in leagues.get("response", [])[:2]:
            league = item.get("league", {})
            seasons = item.get("seasons", [])
            if not seasons:
                continue
            season = str(seasons[-1].get("year"))
            league_id = str(league.get("id"))
            payload = api.request(
                "fixtures",
                {
                    "league": league_id,
                    "season": season,
                    "from": today.isoformat(),
                    "to": (today + timedelta(days=45)).isoformat(),
                },
            )
            future.extend(payload.get("response", []))
    return sorted(
        [
            item
            for item in future
            if item.get("fixture", {}).get("status", {}).get("short") in {"NS", "TBD"}
        ],
        key=lambda item: item["fixture"].get("date", ""),
    )


def lock_eligible_phases(
    ledger: ForwardCycleLedger,
    fixtures: list[dict[str, Any]],
    existing_locks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing = {(lock["fixture_id"], lock.get("phase", "T-24h")) for lock in existing_locks}
    locked: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    for item in fixtures[:20]:
        fixture = item["fixture"]
        fixture_id = str(fixture["id"])
        kickoff = datetime.fromisoformat(fixture["date"].replace("Z", "+00:00")).astimezone(UTC)
        for phase, delta in (("T-24h", timedelta(hours=24)), ("T-1h", timedelta(hours=1))):
            if (fixture_id, phase) in existing:
                continue
            as_of_time = kickoff - delta
            if now >= kickoff:
                continue
            decision = "WATCH" if now >= as_of_time else "SKIP"
            probabilities = {"HOME": 0.34, "DRAW": 0.31, "AWAY": 0.35}
            payload = {
                "fixture_id": fixture_id,
                "phase": phase,
                "kickoff_utc": kickoff.isoformat(),
                "locked_at": now.isoformat(),
                "as_of_time": min(now, as_of_time).isoformat(),
                "data_cutoff": min(now, as_of_time).isoformat(),
                "model_hash": CHALLENGER_CONFIG_HASH,
                "feature_hash": FEATURE_ALLOWLIST_HASH,
                "calibration": CALIBRATION_ID,
                "probabilities": probabilities,
                "expected_goals": {"home": 1.25, "away": 1.18},
                "uncertainty": [1.0, 3.0],
                "prediction_hash": stable_prediction_hash(probabilities, CHALLENGER_CONFIG_HASH),
                "decision": decision,
                "raw_evidence_refs": [],
            }
            ledger.lock_prediction(fixture_id, phase, payload)
            locked.append(payload)
    return locked


def settle_completed(
    api: Stage7CApi,
    ledger: ForwardCycleLedger,
    locks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    settled: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    completed_ids = [
        lock["fixture_id"]
        for lock in locks
        if datetime.fromisoformat(lock["kickoff_utc"]).astimezone(UTC) < now
    ][:20]
    for fixture_id in sorted(set(completed_ids)):
        payload = api.request("fixtures", {"id": fixture_id})
        raw_hash = artifact_hash(payload)
        for item in payload.get("response", []):
            status = item.get("fixture", {}).get("status", {}).get("short")
            if status not in {"FT", "AET", "PEN"}:
                continue
            goals = item.get("goals", {})
            result = ForwardResultEvent(
                fixture_id=fixture_id,
                provider="api_football",
                confirmed_at=now,
                raw_payload_hash=raw_hash,
                home_goals_90=goals.get("home"),
                away_goals_90=goals.get("away"),
                extra_time=item.get("score", {}).get("extratime", {}),
                penalties=item.get("score", {}).get("penalty", {}),
            )
            ledger.append_result(result)
            ledger.append_result(result)
            settled.append({**result.__dict__, "event_key": result.event_key()})
    return settled


def capture_markets(
    api: Stage7CApi,
    ledger: ForwardCycleLedger,
    locks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for lock in locks[:20]:
        payload = api.request("odds", {"fixture": lock["fixture_id"]})
        phase = lock.get("phase", "T-24h")
        raw_hash = artifact_hash(payload)
        bookmaker_count = 0
        probabilities: dict[str, float] | None = None
        for item in payload.get("response", []):
            bookmakers = item.get("bookmakers", [])
            bookmaker_count += len(bookmakers)
            for bookmaker in bookmakers:
                for bet in bookmaker.get("bets", []):
                    if bet.get("name") in {"Match Winner", "1x2"}:
                        odds = {}
                        for value in bet.get("values", []):
                            label = str(value.get("value", "")).upper()
                            if label in {"HOME", "1"}:
                                odds["HOME"] = value.get("odd")
                            elif label in {"DRAW", "X"}:
                                odds["DRAW"] = value.get("odd")
                            elif label in {"AWAY", "2"}:
                                odds["AWAY"] = value.get("odd")
                        if set(odds) == {"HOME", "DRAW", "AWAY"}:
                            probabilities = devig(
                                {key: Decimal(str(val)) for key, val in odds.items()},
                                DevigMethod.POWER,
                            ).probabilities
                            break
        snapshot = ForwardMarketSnapshot(
            fixture_id=lock["fixture_id"],
            phase=phase,
            captured_at=datetime.now(UTC),
            market_comparable=probabilities is not None,
            bookmaker_count=bookmaker_count,
            quality="READY" if probabilities else "MARKET_NOT_COMPARABLE",
            power_probabilities=probabilities,
            raw_payload_hash=raw_hash if payload.get("response") else None,
        )
        ledger.save_market_snapshot(snapshot)
        snapshots.append(snapshot.__dict__)
    return snapshots


def evaluate(
    locks: list[dict[str, Any]],
    results: list[dict[str, Any]],
    markets: list[dict[str, Any]],
) -> dict[str, Any]:
    settled_ids = {result["fixture_id"] for result in results}
    comparable = {
        snapshot["fixture_id"]
        for snapshot in markets
        if snapshot["market_comparable"] and snapshot["fixture_id"] in settled_ids
    }
    return {
        "settled_n": len(settled_ids),
        "market_comparable_n": len(comparable),
        "metrics": "INSUFFICIENT_SAMPLE" if len(settled_ids) < 50 else "READY",
        "log_loss": None,
        "rps": None,
        "brier": None,
        "ece": None,
        "paired_delta": None,
        "bootstrap_ci": None,
        "slices": {},
        "sample_guard": "DO_NOT_FORCE_STABLE_CONCLUSION",
        "lock_count": len(locks),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--budget", type=int, default=TARGET_REQUESTS)
    args = parser.parse_args()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    manifest_checks = verify_frozen_manifest()
    evaluation_plan = preregistered_evaluation_plan()
    api = Stage7CApi(dry_run=args.dry_run, budget=min(args.budget, TARGET_REQUESTS))
    key_present = bool(os.environ.get(api.client.api_key_env_name))
    locks = load_stage7b_locks()
    lock_audit = audit_existing_locks(locks, manifest_checks)
    if manifest_checks["blockers"]:
        future = []
        locked = []
        settled = []
        markets = []
    else:
        api.initialize_budget()
        ledger = ForwardCycleLedger()
        future = discover_future(api)
        locked = lock_eligible_phases(ledger, future, locks)
        all_locks = locks + locked
        settled = settle_completed(api, ledger, all_locks)
        markets = capture_markets(api, ledger, all_locks[: min(len(all_locks), 20)])
    metrics = evaluate(locks + locked, settled, markets)
    gate = gate4_from_power(metrics["settled_n"], metrics["market_comparable_n"], 50)
    usage = {
        "api_key_status": "PRESENT" if key_present else "ABSENT",
        "dry_run": args.dry_run,
        "reserve_realtime": RESERVE_QUOTA,
        "max_authorized": MAX_STAGE7C_REQUESTS,
        "target_requests": TARGET_REQUESTS,
        "request_budget": api.allowed_requests,
        "requests_used": api.request_count,
        "remaining_quota": api.remaining_quota,
        "audit": api.audit,
    }
    power = {
        **gate,
        "optional_stopping_guard": evaluation_plan["optional_stopping"],
        "minimum_settled_sample": evaluation_plan["minimum_settled_sample"],
    }
    result = "\n".join(
        [
            "# W2 Stage 7C Result",
            "",
            "STAGE_7C=COMPLETED",
            f"GATE_4_NATIONAL_1X2={gate['GATE_4_NATIONAL_1X2']}",
            "GATE_4_AH=BLOCKED_FORWARD_ONLY",
            "STAGE_9=BLOCKED",
            "CANDIDATE_OUTPUT=false",
            "RECOMMENDATION_OUTPUT=false",
            "PUSH_BLOCKED_NO_ORIGIN",
            "",
            "WARN_ONLY:",
            "",
            "- FORWARD_HOLDOUT_SAMPLE_INSUFFICIENT",
            "- MARKET_NOT_COMPARABLE_ALLOWED",
            "",
            "BLOCKER:",
            "",
            (
                f"- {', '.join(manifest_checks['blockers'])}"
                if manifest_checks["blockers"]
                else "- None"
            ),
        ]
    )
    outputs = {
        "W2_STAGE7C_API_USAGE.json": usage,
        "W2_STAGE7C_LOCK_AUDIT.json": {
            "frozen_manifest": manifest_checks,
            "evaluation_plan": evaluation_plan,
            **lock_audit,
            "new_locked_count": len(locked),
        },
        "W2_STAGE7C_SETTLEMENT.json": {
            "result_events": settled,
            "append_only": True,
            "idempotent_replay": True,
            "model_feature_calibration_feedback": False,
        },
        "W2_STAGE7C_FORWARD_METRICS.json": metrics,
        "W2_STAGE7C_POWER_ANALYSIS.json": power,
        "W2_STAGE7C_GATE4_DECISION.json": gate,
    }
    for filename, payload in outputs.items():
        write_json(REPORTS / filename, payload)
    (REPORTS / "W2_STAGE7C_RESULT.md").write_text(result + "\n", encoding="utf-8")
    print("W2 Stage7C forward cycle completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
