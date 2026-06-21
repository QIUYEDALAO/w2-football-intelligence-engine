from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class OperationsCycleKind(StrEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MATCHDAY = "MATCHDAY"
    ROUND_END = "ROUND_END"
    SEASON_END = "SEASON_END"
    MODEL_RELEASE = "MODEL_RELEASE"


class OperationsCycleStatus(StrEnum):
    COMPLETED = "COMPLETED"
    WARN_ONLY = "WARN_ONLY"
    BLOCKER = "BLOCKER"


@dataclass(frozen=True, kw_only=True)
class OperationsCheck:
    name: str
    status: str
    finding: str
    gate4_mode: bool = False


@dataclass(frozen=True, kw_only=True)
class OperationsCycle:
    cycle_id: str
    kind: OperationsCycleKind
    started_at: datetime
    completed_at: datetime
    checkpoint: str
    status: OperationsCycleStatus
    checks: tuple[OperationsCheck, ...]
    findings: tuple[str, ...]
    warn_only: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    immutable_audit: bool = True
    deterministic_hash: str = field(init=False)

    def __post_init__(self) -> None:
        payload = {
            "cycle_id": self.cycle_id,
            "kind": self.kind.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "checkpoint": self.checkpoint,
            "status": self.status.value,
            "checks": [check.__dict__ for check in self.checks],
            "findings": self.findings,
            "warn_only": self.warn_only,
            "blockers": self.blockers,
            "immutable_audit": self.immutable_audit,
        }
        object.__setattr__(
            self,
            "deterministic_hash",
            hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest(),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "kind": self.kind.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "checkpoint": self.checkpoint,
            "deterministic_hash": self.deterministic_hash,
            "status": self.status.value,
            "checks": [check.__dict__ for check in self.checks],
            "findings": list(self.findings),
            "WARN_ONLY": list(self.warn_only),
            "BLOCKER": list(self.blockers),
            "immutable_audit": self.immutable_audit,
        }


@dataclass(frozen=True, kw_only=True)
class ModelCard:
    model_id: str
    version: str
    scope: str
    training_status: str = "NO_TRAINING_IN_STAGE15A"


@dataclass(frozen=True, kw_only=True)
class ReleaseCandidate:
    release_id: str
    model_card: ModelCard
    walk_forward_complete: bool
    ablation_complete: bool
    calibration_complete: bool
    shadow_complete: bool


@dataclass(frozen=True, kw_only=True)
class ReleaseApproval:
    release_id: str
    gate4_closed: bool
    gate5_closed: bool
    gate6_closed: bool
    production_release_enabled: bool

    def status(self) -> str:
        if not self.production_release_enabled:
            return "PRODUCTION_RELEASE_DISABLED"
        if not (self.gate4_closed and self.gate5_closed and self.gate6_closed):
            return "REJECTED_GATE_NOT_CLOSED"
        return "READY"


@dataclass(frozen=True, kw_only=True)
class RollbackManifest:
    release_id: str
    previous_artifact_hash: str
    rollback_ready: bool


@dataclass(frozen=True, kw_only=True)
class ChangeFreeze:
    scope: str
    active: bool
    reason: str


@dataclass(frozen=True, kw_only=True)
class ReleaseAudit:
    candidate: ReleaseCandidate
    approval: ReleaseApproval
    rollback: RollbackManifest
    change_freeze: ChangeFreeze

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate": {
                "release_id": self.candidate.release_id,
                "model_card": self.candidate.model_card.__dict__,
                "walk_forward_complete": self.candidate.walk_forward_complete,
                "ablation_complete": self.candidate.ablation_complete,
                "calibration_complete": self.candidate.calibration_complete,
                "shadow_complete": self.candidate.shadow_complete,
            },
            "approval_status": self.approval.status(),
            "approval": self.approval.__dict__,
            "rollback": self.rollback.__dict__,
            "change_freeze": self.change_freeze.__dict__,
            "model_published": False,
        }


RETENTION_POLICY = {
    "raw_payload": "retain_with_manifest",
    "normalized_feature_artifact": "retain_by_dataset_version",
    "replay_model_artifact": "retain_by_experiment_manifest",
    "audit": "retain_permanently",
    "cache_log_cleanup": "dry_run_only",
    "backup": "retain_by_local_staging_policy",
    "legal_hold": "manual_approval_required",
    "files_deleted": False,
}


def _base_checks(kind: OperationsCycleKind) -> tuple[OperationsCheck, ...]:
    gate_disabled = OperationsCheck(
        name="recommendation_related_items",
        status="DISABLED_GATE4",
        finding="Gate 4 is not closed; recommendation-facing checks remain disabled.",
        gate4_mode=True,
    )
    if kind == OperationsCycleKind.DAILY:
        names = [
            "scheduler_worker_api_health",
            "upcoming_fixture_coverage",
            "odds_freshness",
            "bookmaker_coverage",
            "quota",
            "mapping_conflict",
            "t24_t1_lock",
            "result_sync",
            "backup_freshness",
            "unresolved_alerts",
            "forward_holdout_progress",
        ]
    elif kind == OperationsCycleKind.WEEKLY:
        names = [
            "data_quality",
            "provider_quality",
            "market_coverage_movement",
            "drift",
            "forward_holdout_metrics",
            "failed_task_review",
            "quota_cost",
            "security_dependency",
            "backup_restore_status",
            "gate_status",
        ]
    elif kind == OperationsCycleKind.ROUND_END:
        names = [
            "prediction_completeness",
            "settlement_completeness",
            "error_slices",
            "market_baseline_comparison",
            "anomaly_registry",
        ]
    elif kind == OperationsCycleKind.SEASON_END:
        names = [
            "dataset_freeze",
            "source_manifest_hash",
            "model_report_archive",
            "competition_readiness_archive",
            "rollover_trigger",
            "retention_review",
        ]
    elif kind == OperationsCycleKind.MODEL_RELEASE:
        names = [
            "walk_forward",
            "ablation",
            "calibration",
            "shadow",
            "gate_status",
            "old_artifact_immutable",
        ]
    else:
        names = ["matchday_fixture_coverage", "market_freshness", "settlement_queue"]
    checks = tuple(
        OperationsCheck(name=name, status="READY", finding="dry-run check recorded")
        for name in names
    )
    return checks + (gate_disabled,)


def build_cycle(kind: OperationsCycleKind, *, blocker: str | None = None) -> OperationsCycle:
    started = datetime(2026, 6, 22, tzinfo=UTC)
    checks = _base_checks(kind)
    blockers = (blocker,) if blocker else ()
    status = OperationsCycleStatus.BLOCKER if blockers else OperationsCycleStatus.COMPLETED
    return OperationsCycle(
        cycle_id=f"stage15a-{kind.value.lower()}-dry-cycle",
        kind=kind,
        started_at=started,
        completed_at=started,
        checkpoint=f"{kind.value}:dry-run",
        status=status,
        checks=checks,
        findings=("dry-run only; no external notification; no production change",),
        warn_only=("CALIBRATION_REQUIRED",),
        blockers=blockers,
    )


def build_release_audit() -> dict[str, Any]:
    audit = ReleaseAudit(
        candidate=ReleaseCandidate(
            release_id="stage15a-no-release",
            model_card=ModelCard(
                model_id="stage7b-frozen-challenger",
                version="frozen",
                scope="NATIONAL_FORWARD_HOLDOUT",
            ),
            walk_forward_complete=False,
            ablation_complete=False,
            calibration_complete=False,
            shadow_complete=False,
        ),
        approval=ReleaseApproval(
            release_id="stage15a-no-release",
            gate4_closed=False,
            gate5_closed=False,
            gate6_closed=False,
            production_release_enabled=False,
        ),
        rollback=RollbackManifest(
            release_id="stage15a-no-release",
            previous_artifact_hash="UNCHANGED",
            rollback_ready=False,
        ),
        change_freeze=ChangeFreeze(
            scope="local_staging",
            active=True,
            reason="Stage15A governance dry-run does not publish models.",
        ),
    )
    payload = audit.as_dict()
    payload["release_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()
    return payload


def build_operations_report(dependency_blocker: str | None = None) -> dict[str, Any]:
    cycles = [
        build_cycle(OperationsCycleKind.DAILY),
        build_cycle(OperationsCycleKind.WEEKLY),
        build_cycle(OperationsCycleKind.MATCHDAY),
        build_cycle(OperationsCycleKind.ROUND_END),
        build_cycle(OperationsCycleKind.SEASON_END),
        build_cycle(OperationsCycleKind.MODEL_RELEASE, blocker="RELEASE_REJECTED_GATE_NOT_CLOSED"),
    ]
    payload = {
        "cycles": [cycle.as_dict() for cycle in cycles],
        "operational_autorun": False,
        "external_alerting": False,
        "production_release": False,
        "release_audit": build_release_audit(),
        "retention": RETENTION_POLICY,
        "dependency_blocker": dependency_blocker,
    }
    payload["operations_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()
    return payload
