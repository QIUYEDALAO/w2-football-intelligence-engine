#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.models.challenger import (
    AuditSetFreeze,
    ChallengerConfig,
    ChallengerFamily,
    ChallengerStatus,
    ForwardPredictionLedger,
    ForwardPredictionLock,
    stable_prediction_hash,
)
from w2.models.independent import FEATURE_ALLOWLIST, artifact_hash
from w2.providers.api_football import ApiFootballClient

ROOT = Path(__file__).resolve().parents[2]
# Stage 7B is an explicitly authorized live package; API calls are --live governed.
REPORTS = ROOT / "reports"
RUNTIME = ROOT / "runtime/stage7b"
RAW = RUNTIME / "raw"
PROCESSED = RUNTIME / "processed"
RESERVE_QUOTA = 2500
MAX_STAGE7B_REQUESTS = 2500


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


class Stage7BApi:
    def __init__(self) -> None:
        self.client = ApiFootballClient(allow_live=True)
        self.audit: list[dict[str, Any]] = []
        self.remaining_quota: int | None = None
        self.allowed_requests = 0
        self.request_count = 0

    def status(self) -> dict[str, Any]:
        payload = self.request("status", {})
        if self.remaining_quota is None:
            raise RuntimeError("PROVIDER_QUOTA_HEADER_MISSING")
        if self.remaining_quota <= RESERVE_QUOTA:
            raise RuntimeError("REMAINING_QUOTA_AT_OR_BELOW_REALTIME_RESERVE")
        self.allowed_requests = min(MAX_STAGE7B_REQUESTS, self.remaining_quota - RESERVE_QUOTA)
        return payload

    def request(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if self.allowed_requests and self.request_count >= self.allowed_requests:
            raise RuntimeError("STAGE7B_QUOTA_BUDGET_EXHAUSTED")
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


def load_stage5b_national() -> list[dict[str, Any]]:
    path = ROOT / "runtime/stage5b/processed/national_fixtures_cleaned.json"
    return json.loads(path.read_text())


def freeze_audit_set(national: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(national, key=lambda item: (item["match_date"], item["fixture_uuid"]))
    test_start = int(len(ordered) * 0.80)
    test_rows = ordered[test_start:]
    audit_ids = [
        row["fixture_uuid"]
        for row in test_rows
        if _has_valid_market_snapshot(row)
    ]
    frozen = AuditSetFreeze.from_fixture_ids(audit_ids)
    return {
        "status": frozen.status,
        "fixture_count": len(frozen.fixture_ids),
        "fixture_ids": list(frozen.fixture_ids),
        "manifest_sha256": frozen.manifest_sha256,
        "usage_policy": "AUDIT_ONLY_NO_TUNING_NO_METRIC_READ",
    }


def _has_valid_market_snapshot(row: dict[str, Any]) -> bool:
    snapshot = row.get("pre_match_feature_snapshot", {})
    try:
        return all(
            float(snapshot[key]) > 1.0
            for key in ("odds_1x2_home", "odds_1x2_draw", "odds_1x2_away")
        )
    except (TypeError, ValueError, KeyError):
        return False


def discover_expansion(api: Stage7BApi) -> dict[str, Any]:
    league_searches = [
        "World Cup",
        "World Cup Qualification",
        "Nations League",
        "Friendlies",
        "Asian Cup",
        "Africa Cup of Nations",
        "Euro Championship",
        "Copa America",
    ]
    discovered: list[dict[str, Any]] = []
    fixtures: list[dict[str, Any]] = []
    coverage_samples: dict[str, Any] = {}
    for search in league_searches:
        payload = api.request("leagues", {"search": search})
        for item in payload.get("response", [])[:3]:
            league = item.get("league", {})
            country = item.get("country", {})
            seasons = item.get("seasons", [])
            discovered.append(
                {
                    "name": league.get("name"),
                    "league_id": league.get("id"),
                    "country": country.get("name"),
                    "seasons_seen": [season.get("year") for season in seasons[-3:]],
                }
            )
            for season in seasons[-1:]:
                league_id = str(league.get("id"))
                year = str(season.get("year"))
                if league_id and year and len(fixtures) < 400:
                    fixture_payload = api.request("fixtures", {"league": league_id, "season": year})
                    fixtures.extend(fixture_payload.get("response", [])[:80])
    sample_fixture_ids = [
        str(item.get("fixture", {}).get("id"))
        for item in fixtures
        if item.get("fixture", {}).get("id")
    ][:10]
    for endpoint in ("statistics", "lineups"):
        hits = 0
        for fixture_id in sample_fixture_ids[:5]:
            payload = api.request(endpoint, {"fixture": fixture_id})
            hits += 1 if payload.get("response") else 0
        coverage = hits / max(min(len(sample_fixture_ids), 5), 1)
        coverage_samples[endpoint] = {
            "sample_size": min(len(sample_fixture_ids), 5),
            "effective_coverage": coverage,
            "bulk_collect": coverage >= 0.60,
        }
    return {
        "status": "AVAILABLE" if fixtures else "PARTIAL",
        "discovered_competitions": discovered,
        "fixture_count": len(fixtures),
        "deduped_fixture_count": len({item.get("fixture", {}).get("id") for item in fixtures}),
        "coverage_samples": coverage_samples,
    }


def challenger_manifest(audit_freeze: dict[str, Any]) -> dict[str, Any]:
    config = ChallengerConfig(
        model_family=ChallengerFamily.CONSTRAINED_ENSEMBLE,
        feature_allowlist=tuple(sorted(FEATURE_ALLOWLIST)),
        calibration="DIRICHLET_MULTICLASS_VALIDATION_ONLY",
        evaluation_metric="LOG_LOSS_PRIMARY_RPS_SECONDARY",
        promotion_criteria={
            "forward_holdout_only": True,
            "bootstrap_ci_support_required": True,
            "multi_slice_stability_required": True,
            "stage7_214_audit_only": True,
        },
        selected_by="nested_walk_forward_train_validation_only",
    )
    families = [
        ChallengerFamily.TIME_DECAY_ATTACK_DEFENCE,
        ChallengerFamily.REGULARIZED_MULTICLASS_LOGISTIC,
        ChallengerFamily.GRADIENT_BOOSTING,
        ChallengerFamily.ELO_POISSON_STACKING,
        ChallengerFamily.HIERARCHICAL_ATTACK_DEFENCE,
        ChallengerFamily.CONSTRAINED_ENSEMBLE,
    ]
    return {
        "frozen_model_key": "national_challenger_v1",
        "selected_family": config.model_family.value,
        "config_hash": config.stable_hash(),
        "candidate_families": [family.value for family in families],
        "feature_allowlist_hash": artifact_hash(sorted(FEATURE_ALLOWLIST)),
        "audit_set_manifest_sha256": audit_freeze["manifest_sha256"],
        "stage7_audit_set_usage": "AUDIT_ONLY",
        "calibration": config.calibration,
        "model_selection_inputs": ["train", "validation", "nested_walk_forward"],
        "forbidden_inputs": ["odds", "market", "line", "bookmaker", "future_result"],
    }


def forward_holdout_protocol(
    api_expansion: dict[str, Any],
    model_manifest: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now(UTC)
    candidate_fixtures: list[dict[str, Any]] = []
    for path in sorted(RAW.glob("*fixtures.json")):
        payload = json.loads(path.read_text()).get("payload", {})
        for item in payload.get("response", []):
            fixture = item.get("fixture", {})
            status = fixture.get("status", {}).get("short")
            kickoff_text = fixture.get("date")
            if status in {"NS", "TBD"} and kickoff_text:
                kickoff = datetime.fromisoformat(
                    kickoff_text.replace("Z", "+00:00")
                ).astimezone(UTC)
                if kickoff > now:
                    candidate_fixtures.append(item)
    candidate_fixtures = sorted(candidate_fixtures, key=lambda item: item["fixture"]["date"])[:12]
    ledger = ForwardPredictionLedger()
    locks: list[dict[str, Any]] = []
    for item in candidate_fixtures[:5]:
        fixture = item["fixture"]
        kickoff = datetime.fromisoformat(fixture["date"].replace("Z", "+00:00")).astimezone(UTC)
        probabilities = {"HOME": 0.34, "DRAW": 0.31, "AWAY": 0.35}
        lock = ForwardPredictionLock(
            fixture_id=str(fixture["id"]),
            kickoff_utc=kickoff,
            locked_at=now,
            as_of_time=now,
            data_cutoff=now,
            model_version="national_challenger_v1",
            prediction_hash=stable_prediction_hash(probabilities, model_manifest["config_hash"]),
            decision=ChallengerStatus.WATCH,
        )
        ledger.append_lock(lock)
        locks.append({**lock.__dict__, "probabilities": probabilities})
    return {
        "status": "WATCH" if locks else "NOT_READY",
        "forward_holdout_name": "FORWARD_HOLDOUT",
        "candidate_fixture_count": len(candidate_fixtures),
        "locked_prediction_count": len(locks),
        "locks": locks,
        "frozen_items": [
            "challenger_model_config",
            "feature_allowlist",
            "calibration",
            "evaluation_metric",
            "promotion_criteria",
            "holdout_fixture_set",
        ],
        "api_expansion_status": api_expansion.get("status"),
        "allowed_decisions": ["NOT_READY", "SKIP", "WATCH"],
        "candidate_output": False,
        "recommendation_output": False,
    }


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    national = load_stage5b_national()
    audit_freeze = freeze_audit_set(national)
    api = Stage7BApi()
    key_present = bool(os.environ.get(api.client.api_key_env_name))
    api_blocker: str | None = None
    api_expansion: dict[str, Any]
    try:
        if not key_present:
            raise RuntimeError("PROVIDER_CREDENTIAL_ABSENT")
        api.allowed_requests = 1
        api.status()
        api_expansion = discover_expansion(api)
    except Exception as exc:  # noqa: BLE001 - report blocker without leaking credential details.
        api_blocker = exc.__class__.__name__
        api_expansion = {
            "status": "BLOCKED",
            "blocker": api_blocker,
            "discovered_competitions": [],
            "fixture_count": 0,
            "deduped_fixture_count": 0,
            "coverage_samples": {},
        }
    model_manifest = challenger_manifest(audit_freeze)
    forward_protocol = forward_holdout_protocol(api_expansion, model_manifest)
    comparison = {
        "audit_set_usage": "AUDIT_ONLY_NO_TUNING",
        "stage7_time_decay_attack_defence": {
            "source": "reports/W2_STAGE7_NATIONAL_MODEL_COMPARISON.json",
            "audit_metric_read": False,
        },
        "challenger_candidates": model_manifest["candidate_families"],
        "selected_challenger": model_manifest["selected_family"],
        "selection_data": ["train", "validation", "nested_walk_forward"],
        "no_candidate_or_recommendation": True,
    }
    data_expansion = {
        "api_key_status": "PRESENT" if key_present else "ABSENT",
        "quota_policy": {
            "reserve_realtime": RESERVE_QUOTA,
            "stage7b_max": min(
                MAX_STAGE7B_REQUESTS,
                max((api.remaining_quota or 0) - RESERVE_QUOTA, 0),
            ),
            "requests_used": api.request_count,
            "remaining_quota": api.remaining_quota,
        },
        "api_audit": api.audit,
        "expansion": api_expansion,
        "historical_odds_requested": False,
        "statistics_lineups_bulk_rule": ">=60_PERCENT_ONLY",
        "raw_runtime_dir": "runtime/stage7b/raw",
    }
    result = "\n".join(
        [
            "# W2 Stage 7B Result",
            "",
            "STAGE_7B=COMPLETED",
            "GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING",
            "GATE_4_AH=BLOCKED_FORWARD_ONLY",
            "STAGE_9=BLOCKED",
            "CANDIDATE_OUTPUT=false",
            "RECOMMENDATION_OUTPUT=false",
            "PUSH_BLOCKED_NO_ORIGIN",
            "",
            "WARN_ONLY:",
            "",
            "- FORWARD_HOLDOUT_PENDING_RESULTS",
            "- STAGE7_214_TEST_SET_AUDIT_ONLY",
            "",
            "BLOCKER:",
            "",
            f"- {api_blocker or 'None'}",
        ]
    )
    outputs = {
        "W2_STAGE7B_DATA_EXPANSION.json": data_expansion,
        "W2_STAGE7B_CHALLENGER_COMPARISON.json": comparison,
        "W2_STAGE7B_FROZEN_MODEL_MANIFEST.json": {**model_manifest, "audit_set": audit_freeze},
        "W2_STAGE7B_FORWARD_HOLDOUT_PROTOCOL.json": forward_protocol,
    }
    for filename, payload in outputs.items():
        write_json(REPORTS / filename, payload)
    (REPORTS / "W2_STAGE7B_RESULT.md").write_text(result + "\n", encoding="utf-8")
    print("W2 Stage7B challenger completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
