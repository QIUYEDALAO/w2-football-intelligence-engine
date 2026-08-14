from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.model_forecast_models import (
    ModelForecastCaptureModel,
    ModelForecastOutcomeModel,
)
from w2.infrastructure.persistence.outcome_ledger_models import OutcomeLedgerModel
from w2.ingestion.xg_retention import XgRetentionHardeningService
from w2.tracking.model_forecast_ledger import ModelForecastLedgerRepository

CANARY_TERMINAL = "FREE_MODE_MODEL_VALIDATION_CANARY_PASS"


def free_mode_model_validation_canary(
    *,
    engine: Engine | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_engine = engine or create_engine()
    tables = set(inspect(resolved_engine).get_table_names())
    required = {
        "model_forecast_capture",
        "model_forecast_outcome",
        "raw_statistics_retention",
    }
    if not required <= tables:
        return {
            "schema_version": "w2.free_mode_model_validation_canary.v1",
            "status": "BLOCKED",
            "provider_calls": 0,
            "db_writes": 0,
            "blockers": ["MODEL_FORECAST_OR_RETENTION_SCHEMA_NOT_READY"],
        }
    with Session(resolved_engine) as session:
        capture_count = int(
            session.scalar(select(func.count()).select_from(ModelForecastCaptureModel)) or 0
        )
        outcome_count = int(
            session.scalar(select(func.count()).select_from(ModelForecastOutcomeModel)) or 0
        )
        shadow_candidate_count = (
            int(
                session.scalar(
                    select(func.count())
                    .select_from(OutcomeLedgerModel)
                    .where(
                        OutcomeLedgerModel.record_type == "capture",
                        OutcomeLedgerModel.recommendation_scope == "VALIDATION",
                    )
                )
                or 0
            )
            if "outcome_ledger" in tables
            else 0
        )
    retention = XgRetentionHardeningService(resolved_engine, now=now).audit()
    ledger_integrity = ModelForecastLedgerRepository(resolved_engine).integrity()
    metrics = {
        "MODEL_ELIGIBLE_COUNT": capture_count,
        "MODEL_FORECAST_CAPTURE_COUNT": capture_count,
        "MODEL_FORECAST_SETTLED_COUNT": outcome_count,
        "PROBABILITY_METRICS_SAMPLE_COUNT": outcome_count,
        "SHADOW_CANDIDATE_COUNT": shadow_candidate_count,
        "RAW_STATISTICS_RESTORE_HASH_MATCH": retention["raw_statistics_restore_hash_match"],
    }
    blockers = [
        key
        for key in (
            "MODEL_ELIGIBLE_COUNT",
            "MODEL_FORECAST_CAPTURE_COUNT",
            "MODEL_FORECAST_SETTLED_COUNT",
            "PROBABILITY_METRICS_SAMPLE_COUNT",
        )
        if int(metrics[key]) <= 0
    ]
    if metrics["RAW_STATISTICS_RESTORE_HASH_MATCH"] is not True:
        blockers.append("RAW_STATISTICS_RESTORE_HASH_MATCH")
    if ledger_integrity["invalid_capture_count"]:
        blockers.append("MODEL_FORECAST_CAPTURE_INTEGRITY_INVALID")
    if ledger_integrity["invalid_outcome_count"]:
        blockers.append("MODEL_FORECAST_OUTCOME_INTEGRITY_INVALID")
    blockers.extend(str(item) for item in retention.get("blockers", []))
    status = CANARY_TERMINAL if not blockers else "BLOCKED"
    return {
        "schema_version": "w2.free_mode_model_validation_canary.v1",
        "status": status,
        "evaluated_at": (now or datetime.now(UTC)).astimezone(UTC).isoformat(),
        "provider_calls": 0,
        "db_writes": 0,
        "metrics": metrics,
        "xg_retention_hardening": retention,
        "model_forecast_ledger_integrity": ledger_integrity,
        "blockers": sorted(set(blockers)),
        "formal": "OFF",
        "lock": "OFF",
        "production": "OFF",
        "round_4": "NOT_STARTED",
        "pro": "NOT_PURCHASED_NOT_RENEWED",
    }


def write_pro_reopen_owner_decision_packet(
    path: Path,
    report: dict[str, Any],
) -> None:
    if report.get("status") != CANARY_TERMINAL:
        raise ValueError("PRO_REOPEN_OWNER_DECISION_PACKET_REQUIRES_CANARY_PASS")
    metrics = report["metrics"]
    retention = report["xg_retention_hardening"]
    raw_state = (
        f"{retention['raw_statistics_count']} / {retention['raw_statistics_aggregate_hash']}"
    )
    match_state = (
        f"{retention['team_xg_match_expected_count']} / {retention['team_xg_match_expected_hash']}"
    )
    snapshot_state = (
        f"{retention['rolling_snapshot_expected_count']} / "
        f"{retention['rolling_snapshot_expected_hash']}"
    )
    body = f"""# PRO_REOPEN_OWNER_DECISION_PACKET

Status: OWNER_DECISION_REQUIRED

This packet does not authorize a Pro purchase or renewal. The current decision remains
`NOT_PURCHASED_NOT_RENEWED` until the Owner explicitly changes it.

## Free-mode model validation proof

- Terminal: `{report["status"]}`
- MODEL_ELIGIBLE_COUNT: `{metrics["MODEL_ELIGIBLE_COUNT"]}`
- MODEL_FORECAST_CAPTURE_COUNT: `{metrics["MODEL_FORECAST_CAPTURE_COUNT"]}`
- MODEL_FORECAST_SETTLED_COUNT: `{metrics["MODEL_FORECAST_SETTLED_COUNT"]}`
- PROBABILITY_METRICS_SAMPLE_COUNT: `{metrics["PROBABILITY_METRICS_SAMPLE_COUNT"]}`
- SHADOW_CANDIDATE_COUNT: `{metrics["SHADOW_CANDIDATE_COUNT"]}`
- RAW_STATISTICS_RESTORE_HASH_MATCH: `{str(metrics["RAW_STATISTICS_RESTORE_HASH_MATCH"]).lower()}`
- raw Statistics count/hash: `{raw_state}`
- rebuilt team_xg_match count/hash: `{match_state}`
- rebuilt rolling snapshot count/hash: `{snapshot_state}`

## Owner choices

1. Keep Free mode and continue natural ModelForecast accumulation.
2. Reopen a separately bounded Pro backfill decision using a fresh net-request budget.

Formal, Lock, Production, real money, Round 4, new Statistics calls, cadence changes,
model-threshold changes, and league deletion remain outside this packet.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
