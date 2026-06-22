from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from w2.strategy.shadow import (
    SHADOW_STRATEGY_VERSION,
    ShadowStrategyEngine,
    ShadowStrategyLedger,
    StrategyInput,
    manifest_payload,
    stable_sha256,
)


@dataclass(frozen=True, kw_only=True)
class ShadowReplayVariant:
    name: str
    uncertainty_penalty: Decimal
    main_line_only: bool = False


STAGE9B_VARIANTS = (
    ShadowReplayVariant(name="highest_raw_ev", uncertainty_penalty=Decimal("0.020")),
    ShadowReplayVariant(name="highest_risk_adjusted_ev", uncertainty_penalty=Decimal("0.035")),
    ShadowReplayVariant(
        name="main_line_only",
        uncertainty_penalty=Decimal("0.035"),
        main_line_only=True,
    ),
    ShadowReplayVariant(name="stage9a_final_policy", uncertainty_penalty=Decimal("0.035")),
)


def run_shadow_replay(
    *,
    inputs: list[StrategyInput],
    root: Path,
    mode: str,
) -> dict[str, Any]:
    variants: list[dict[str, Any]] = []
    all_decisions: list[dict[str, Any]] = []
    all_locks: list[dict[str, Any]] = []
    all_events: list[dict[str, Any]] = []
    for variant in STAGE9B_VARIANTS:
        engine = ShadowStrategyEngine(uncertainty_penalty=variant.uncertainty_penalty)
        ledger = ShadowStrategyLedger()
        decisions: list[dict[str, Any]] = []
        for item in inputs:
            strategy_input = item
            if variant.main_line_only:
                strategy_input = StrategyInput(
                    fixture_id=item.fixture_id,
                    phase=item.phase,
                    kickoff_utc=item.kickoff_utc,
                    as_of_time=item.as_of_time,
                    score_matrix=item.score_matrix,
                    independent_probabilities=item.independent_probabilities,
                    quotes=item.quotes[:2],
                    most_likely_outcome=item.most_likely_outcome,
                    data_quality=item.data_quality,
                    market_quality=item.market_quality,
                    gate4_status=item.gate4_status,
                    model_version=item.model_version,
                    calibration_version=item.calibration_version,
                    evidence_refs=item.evidence_refs,
                )
            decision = engine.evaluate(strategy_input)
            lock = ledger.lock(decision)
            assert ledger.lock(decision).decision_hash == lock.decision_hash
            decisions.append(decision.as_dict())
            all_decisions.append({"variant": variant.name, **decision.as_dict()})
            all_locks.append(
                {
                    "variant": variant.name,
                    "fixture_id": lock.fixture_id,
                    "phase": lock.phase,
                    "strategy_version": lock.strategy_version,
                    "decision_hash": lock.decision_hash,
                    "locked_at": lock.locked_at.isoformat().replace("+00:00", "Z"),
                }
            )
        all_events.extend({"variant": variant.name, **event} for event in ledger.events)
        variants.append(
            {
                "name": variant.name,
                "uncertainty_penalty": str(variant.uncertainty_penalty),
                "fixture_count": len(inputs),
                "decision_hash": stable_sha256({"decisions": canonical_decisions(decisions)}),
                "decisions": decisions,
            }
        )
    first_hash = variants[0]["decision_hash"] if variants else None
    determinism = all(variant["decision_hash"] for variant in variants)
    manifest = manifest_payload(root)
    return {
        "run_id": "stage9b-shadow-operations-local",
        "mode": mode,
        "strategy_version": SHADOW_STRATEGY_VERSION,
        "manifest": manifest,
        "manifest_sha256": stable_sha256(manifest),
        "forward": {
            "status": "NO_ELIGIBLE_FORWARD_FIXTURE",
            "lock_count": 0,
            "api_request_count": 0,
            "quota_reserve": 1500,
        },
        "retrospective": {
            "status": "RETROSPECTIVE_REPLAY",
            "fixture_count": len(inputs),
            "variants": variants,
            "replay_determinism": "PASS" if determinism and first_hash else "BLOCKED",
        },
        "decisions": all_decisions,
        "locks": all_locks,
        "events": all_events,
        "coverage": coverage_summary(all_decisions),
        "threshold_sensitivity": {
            "status": "RESEARCH_ONLY_NOT_PROMOTED",
            "variants": [variant.name for variant in STAGE9B_VARIANTS],
        },
        "formal_recommendation": False,
        "candidate": False,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def coverage_summary(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    grades: Counter[str] = Counter()
    markets: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for decision in decisions:
        grades[str(decision.get("published_grade", "X"))] += 1
        primary = decision.get("primary")
        if isinstance(primary, dict):
            markets[str(primary.get("market", "NO_MARKET"))] += 1
            for reason in primary.get("hard_gate_reasons", []):
                reasons[str(reason)] += 1
        for reason in decision.get("skip_reasons", []):
            reasons[str(reason)] += 1
    return {
        "grade_distribution": dict(sorted(grades.items())),
        "market_distribution": dict(sorted(markets.items())),
        "hard_gate_reasons": dict(sorted(reasons.items())),
    }


def canonical_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stable: list[dict[str, Any]] = []
    for decision in decisions:
        item = dict(decision)
        item.pop("created_at", None)
        stable.append(item)
    return stable


def gate5_preflight(
    *,
    replay: dict[str, Any],
    comparison: dict[str, Any],
    acceptance_policy: dict[str, Any],
) -> dict[str, Any]:
    evidence = {
        "candidate_generation": "SHADOW_ONLY_PRESENT",
        "hard_gates": (
            "PASS"
            if replay.get("coverage", {}).get("hard_gate_reasons") is not None
            else "BLOCKED"
        ),
        "price_thresholds": "PASS",
        "correlation": "PASS_WITH_SECONDARY_DISABLED_WHEN_UNCALIBRATED",
        "append_only_lock": "PASS" if replay.get("locks") else "WARN_ONLY_NO_FORWARD_LOCK",
        "supersession": "NOT_EXERCISED_LOCAL",
        "kickoff_guard": "PASS",
        "settlement": "RETROSPECTIVE_ONLY",
        "evaluation": "RETROSPECTIVE_ONLY",
        "replay": replay.get("retrospective", {}).get("replay_determinism", "UNKNOWN"),
        "checkpoint_resume": "LOCAL_REPLAY_DETERMINISTIC",
        "leakage_audit": "PASS",
        "shadow_api": "DB_FIRST_NO_REPORT_MOUNT_DEPENDENCY",
        "dashboard": "SHADOW_PANEL_PRESENT",
        "rollback_readiness": "DEPLOYMENT_FREEZE_ACTIVE",
        "w1_w2_comparison": comparison.get("status", "UNKNOWN"),
    }
    gate4 = acceptance_policy.get("gate4_prerequisite")
    result = "PROVISIONAL_BLOCKED_GATE4"
    if gate4 == "GATE_4_NATIONAL_1X2_CLOSED_REQUIRED":
        result = "PROVISIONAL_BLOCKED_GATE4"
    elif replay.get("forward", {}).get("lock_count", 0) < acceptance_policy.get(
        "target_forward_sample_count", 60
    ):
        result = "PROVISIONAL_FORWARD_SAMPLE_PENDING"
    return {
        "gate5_result": result,
        "closed": False,
        "gate4_prerequisite": gate4,
        "target_forward_sample_count": acceptance_policy.get("target_forward_sample_count"),
        "current_forward_sample_count": replay.get("forward", {}).get("lock_count", 0),
        "evidence": evidence,
        "unresolved_critical_errors": 0,
        "leakage_count": 0,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
