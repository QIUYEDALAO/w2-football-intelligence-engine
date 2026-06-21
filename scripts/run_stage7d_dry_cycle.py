#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from w2.models.forward_automation import (
    DemoFixture,
    ForwardHoldoutCycleService,
    ForwardHoldoutFixtureState,
    ForwardHoldoutStateMachine,
    NoOverlapLock,
    RequestQuotaPolicy,
)
from w2.models.independent import artifact_hash

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
CONFIG = ROOT / "config/policies/forward_holdout_schedule.v1.json"
RUNTIME = ROOT / "runtime/stage7d"

STAGE7B_FROZEN_MANIFEST_SHA256 = (
    "c9bca779968962eb8d8dc46cc29b1448634300a8e66827ecb85d25983bf32204"
)
STAGE7B_PROTOCOL_SHA256 = "400e8d8e66bf22bd65215619925f65486031bd84584da6a488d51f13f3958062"
STAGE7C_GATE_SHA256 = "d5ea4e053f7537901135358eccf0b25805c20486d4688b2104bda59973198d32"
STAGE7C_POWER_SHA256 = "fabc4b8d023b74a0766842bfb96836e1d46e27898e333379a8f076c10be28c4b"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    path.write_text(content, encoding="utf-8")


def frozen_hash_audit() -> dict[str, Any]:
    files = {
        "stage7b_frozen_manifest": (
            REPORTS / "W2_STAGE7B_FROZEN_MODEL_MANIFEST.json",
            STAGE7B_FROZEN_MANIFEST_SHA256,
        ),
        "stage7b_forward_protocol": (
            REPORTS / "W2_STAGE7B_FORWARD_HOLDOUT_PROTOCOL.json",
            STAGE7B_PROTOCOL_SHA256,
        ),
        "stage7c_gate_decision": (
            REPORTS / "W2_STAGE7C_GATE4_DECISION.json",
            STAGE7C_GATE_SHA256,
        ),
        "stage7c_power_analysis": (
            REPORTS / "W2_STAGE7C_POWER_ANALYSIS.json",
            STAGE7C_POWER_SHA256,
        ),
    }
    observed = {
        name: {"sha256": sha256(path), "expected": expected}
        for name, (path, expected) in files.items()
    }
    blockers = [
        f"{name.upper()}_HASH_CHANGED"
        for name, item in observed.items()
        if item["sha256"] != item["expected"]
    ]
    return {"observed": observed, "blockers": blockers}


def build_demo_fixtures(now: datetime) -> list[DemoFixture]:
    return [
        DemoFixture(
            fixture_id="demo-forward-t24",
            kickoff_utc=now + timedelta(hours=23, minutes=30),
            has_market_snapshot=True,
        ),
        DemoFixture(
            fixture_id="demo-forward-t1",
            kickoff_utc=now + timedelta(minutes=45),
            has_market_snapshot=False,
        ),
        DemoFixture(
            fixture_id="demo-forward-settled",
            kickoff_utc=now - timedelta(hours=2),
            settled=True,
        ),
    ]


def illegal_transition_audit(now: datetime) -> dict[str, Any]:
    machine = ForwardHoldoutStateMachine()
    checks: list[dict[str, Any]] = []
    for current, target in [
        (ForwardHoldoutFixtureState.LOCKED_T24, ForwardHoldoutFixtureState.DISCOVERED),
        (ForwardHoldoutFixtureState.SETTLED, ForwardHoldoutFixtureState.DISCOVERED),
        (ForwardHoldoutFixtureState.EVALUATED, ForwardHoldoutFixtureState.SETTLED),
    ]:
        try:
            machine.transition("demo-illegal", current, target, event_time=now, reason="negative")
            checks.append({"from": current, "to": target, "blocked": False})
        except ValueError:
            checks.append({"from": current, "to": target, "blocked": True})
    return {"checks": checks, "all_blocked": all(item["blocked"] for item in checks)}


def no_overlap_audit() -> dict[str, Any]:
    lock = NoOverlapLock()
    first = lock.acquire()
    second = lock.acquire()
    lock.release()
    third = lock.acquire()
    lock.release()
    return {"first_acquire": first, "overlap_blocked": not second, "resume_acquire": third}


def sample_plan() -> dict[str, Any]:
    power = json.loads((REPORTS / "W2_STAGE7C_POWER_ANALYSIS.json").read_text(encoding="utf-8"))
    target_n = int(power["minimum_settled_sample"])
    current_n = int(power["current_settled_n"])
    comparable_n = int(power["market_comparable_n"])
    return {
        "current_settled_n": current_n,
        "current_market_comparable_n": comparable_n,
        "preregistered_target_n": target_n,
        "remaining_n": max(target_n - current_n, 0),
        "expected_eligible_fixtures": "derived by disabled scheduler dry cycles only",
        "estimated_collection_windows": ["T-24h", "T-1h", "post-match settlement"],
        "promotion_criteria_modified": False,
    }


def main() -> int:
    now = datetime(2026, 6, 22, 4, 0, tzinfo=UTC)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    hash_audit = frozen_hash_audit()
    schedule = json.loads(CONFIG.read_text(encoding="utf-8"))
    quota_policy = RequestQuotaPolicy(
        daily_hard_budget=schedule["defaults"]["daily_hard_budget"],
        minimum_reserve=schedule["defaults"]["minimum_quota_reserve"],
        per_cycle_cap=schedule["defaults"]["per_cycle_request_cap"],
    )
    service = ForwardHoldoutCycleService(quota_policy=quota_policy)
    fixtures = build_demo_fixtures(now)
    result = service.run(
        fixtures=fixtures,
        now=now,
        remaining_quota=3000,
        dry_run=True,
        network_enabled=False,
        autorun_enabled=False,
    )
    resumed = service.run(
        fixtures=[],
        now=now + timedelta(minutes=1),
        remaining_quota=3000,
        dry_run=True,
        network_enabled=False,
        autorun_enabled=False,
        resume_from=result.checkpoints,
    )
    plan = {
        "stage": "7D",
        "autorun_default": schedule["defaults"]["W2_FORWARD_HOLDOUT_AUTORUN"],
        "network_default": schedule["defaults"]["W2_FORWARD_HOLDOUT_NETWORK"],
        "celery_beat_enabled_by_default": schedule["celery_beat"]["enabled_by_default"],
        "tasks": schedule["celery_beat"]["entries"],
        "quota_policy": {
            "daily_hard_budget": quota_policy.daily_hard_budget,
            "minimum_reserve": quota_policy.minimum_reserve,
            "per_cycle_cap": quota_policy.per_cycle_cap,
            "allowed_requests_at_3000_remaining": quota_policy.allowed_requests(3000),
            "allowed_requests_when_unknown": quota_policy.allowed_requests(None),
        },
        "hash_audit": hash_audit,
        "dry_cycle": {
            "cycle_id": result.cycle_id,
            "cycle_hash": result.cycle_hash,
            "resumed_checkpoint_count": len(resumed.checkpoints),
            "checkpoint_resume_consistent": (
                result.gate["GATE_4_NATIONAL_1X2"] == resumed.gate["GATE_4_NATIONAL_1X2"]
            ),
            "dry_run": result.dry_run,
            "network_enabled": result.network_enabled,
            "autorun_enabled": result.autorun_enabled,
            "transition_count": len(result.transitions),
            "audit": result.audit,
        },
        "negative_checks": {
            "illegal_transitions": illegal_transition_audit(now),
            "no_overlap": no_overlap_audit(),
        },
        "forbidden_outputs": {
            "training": False,
            "deepseek": False,
            "candidate": False,
            "recommend": False,
        },
    }
    power_progress = {
        **sample_plan(),
        "metrics": result.metrics.__dict__,
        "gate": result.gate,
    }
    status_lines = [
        "# W2 Stage 7D Result",
        "",
        "STAGE_7D=COMPLETED",
        "FORWARD_HOLDOUT_AUTORUN=DISABLED_PENDING_APPROVAL",
        "FORWARD_HOLDOUT_NETWORK=DISABLED_PENDING_APPROVAL",
        f"GATE_4_NATIONAL_1X2={result.gate['GATE_4_NATIONAL_1X2']}",
        "GATE_4_AH=BLOCKED_FORWARD_ONLY",
        "STAGE_9=BLOCKED",
        "CANDIDATE_OUTPUT=false",
        "RECOMMENDATION_OUTPUT=false",
        "NETWORK_USED=false",
        "PUSH_BLOCKED_NO_ORIGIN",
        "",
        "BLOCKER:",
        "",
        f"- {', '.join(hash_audit['blockers']) if hash_audit['blockers'] else 'None'}",
    ]
    write_json(REPORTS / "W2_STAGE7D_AUTOMATION_PLAN.json", plan)
    write_json(REPORTS / "W2_STAGE7D_POWER_PROGRESS.json", power_progress)
    (REPORTS / "W2_STAGE7D_RESULT.md").write_text("\n".join(status_lines) + "\n", encoding="utf-8")
    runtime_manifest = {
        "cycle_hash": result.cycle_hash,
        "report_hash": artifact_hash(plan),
        "raw_payloads": "none",
    }
    write_json(RUNTIME / "dry_cycle_manifest.json", runtime_manifest)
    print("W2 Stage7D dry cycle completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
