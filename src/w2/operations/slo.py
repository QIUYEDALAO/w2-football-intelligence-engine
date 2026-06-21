from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, kw_only=True)
class SLOTarget:
    name: str
    objective: str
    threshold: str
    status: str = "CALIBRATION_REQUIRED"


SLO_TARGETS = [
    SLOTarget(
        name="api_availability",
        objective="API responds to read requests",
        threshold="CALIBRATION_REQUIRED",
    ),
    SLOTarget(
        name="ingestion_success",
        objective="Provider cycle completes",
        threshold="CALIBRATION_REQUIRED",
    ),
    SLOTarget(
        name="odds_freshness",
        objective="Pre-match odds are recent",
        threshold="CALIBRATION_REQUIRED",
    ),
    SLOTarget(
        name="fixture_mapping_integrity",
        objective="Fixture mappings remain unique",
        threshold="CALIBRATION_REQUIRED",
    ),
    SLOTarget(
        name="lock_success",
        objective="T-24h/T-1h locks complete before kickoff",
        threshold="CALIBRATION_REQUIRED",
    ),
    SLOTarget(
        name="result_sync_completeness",
        objective="Results append after match",
        threshold="CALIBRATION_REQUIRED",
    ),
    SLOTarget(
        name="scheduler_heartbeat",
        objective="Scheduler emits heartbeat",
        threshold="CALIBRATION_REQUIRED",
    ),
    SLOTarget(
        name="backup_freshness",
        objective="Local backup drill is current",
        threshold="CALIBRATION_REQUIRED",
    ),
]


def evaluate_slo(metrics: dict[str, float]) -> dict[str, Any]:
    return {
        "targets": [target.__dict__ for target in SLO_TARGETS],
        "metrics": metrics,
        "overall_status": "CALIBRATION_REQUIRED",
        "production_thresholds_declared": False,
    }
