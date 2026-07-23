"""drop evidence-backed dead tables

Revision ID: 0039_drop_evidence_backed_dead_tables
Revises: 0038_drop_unused_system_metadata
Create Date: 2026-07-23 13:00:00.000000
"""
from __future__ import annotations

from collections.abc import Callable

import sqlalchemy as sa
from alembic import op

revision: str = "0039_drop_evidence_backed_dead_tables"
down_revision: str | None = "0038_drop_unused_system_metadata"
branch_labels: str | None = None
depends_on: str | None = None

ColumnSpec = tuple[str, str, bool]

TABLE_COLUMNS: dict[str, tuple[ColumnSpec, ...]] = {
    "api_request_audit": (
        ("request_id", "s64", False),
        ("endpoint", "s256", False),
        ("status_code", "int", False),
        ("latency_ms", "int", False),
        ("created_at", "dt", False),
    ),
    "audit_events": (
        ("entity_type", "s64", False),
        ("entity_id", "s36", False),
        ("action", "s64", False),
        ("occurred_at", "dt", False),
        ("actor", "s128", False),
    ),
    "backup_run": (
        ("backup_id", "s128", False),
        ("created_at", "dt", False),
        ("source", "s128", False),
        ("sha256", "s64", False),
        ("payload", "json", False),
    ),
    "challenger_model": (
        ("model_key", "s128", False),
        ("family", "s128", False),
        ("config_hash", "s64", False),
        ("manifest", "json", False),
    ),
    "data_quality_runs": (
        ("dataset_id", "s128", False),
        ("version", "s128", False),
        ("run_at", "dt", False),
        ("status", "s32", False),
        ("checks", "json", False),
    ),
    "dataset_sources": (
        ("source_id", "s128", False),
        ("provider", "s128", False),
        ("registry_ref", "s255", False),
        ("provenance", "json", False),
    ),
    "dependency_risk": (
        ("package", "s128", False),
        ("source", "s64", False),
        ("severity", "s32", False),
        ("status", "s64", False),
        ("payload", "json", False),
    ),
    "forward_cycle_checkpoint": (
        ("cycle_id", "s128", False),
        ("step", "s64", False),
        ("payload_hash", "s64", False),
        ("created_at", "dt", False),
        ("payload", "json", False),
    ),
    "forward_operational_alert": (
        ("alert_key", "s128", False),
        ("severity", "s32", False),
        ("created_at", "dt", False),
        ("resolved_at", "dt", True),
        ("payload", "json", False),
    ),
    "forward_result_event": (
        ("fixture_id", "s128", False),
        ("provider", "s64", False),
        ("confirmed_at", "dt", False),
        ("raw_payload_hash", "s64", False),
        ("result_payload", "json", False),
    ),
    "forward_scheduler_run": (
        ("scheduler_key", "s128", False),
        ("scheduled_for", "dt", False),
        ("started_at", "dt", True),
        ("finished_at", "dt", True),
        ("status", "s32", False),
        ("audit_payload", "json", False),
    ),
    "forward_state_transition": (
        ("fixture_id", "s128", False),
        ("from_state", "s64", False),
        ("to_state", "s64", False),
        ("event_time", "dt", False),
        ("reason", "s256", False),
    ),
    "freshness_alerts": (
        ("entity_type", "s64", False),
        ("entity_id", "s36", False),
        ("observed_at", "dt", False),
        ("threshold_seconds", "int", False),
        ("severity", "s32", False),
        ("message", "s512", False),
    ),
    "league_team_membership": (
        ("competition_id", "s128", False),
        ("season", "s32", False),
        ("provider_team_id", "s128", False),
        ("payload", "json", False),
    ),
    "market_quality_assessment": (
        ("fixture_id", "s128", False),
        ("market", "s64", False),
        ("as_of_time", "dt", False),
        ("liquidity", "s32", False),
        ("bookmaker_coverage", "s32", False),
        ("freshness", "s32", False),
        ("dispersion", "s32", False),
        ("conflict", "s32", False),
        ("quality_status", "s32", False),
    ),
    "migration_dry_run": (
        ("run_id", "s128", False),
        ("created_at", "dt", False),
        ("manifest_sha256", "s64", False),
        ("payload", "json", False),
    ),
    "migration_quarantine_record": (
        ("domain", "s128", False),
        ("source_sha256", "s64", False),
        ("reason", "s256", False),
        ("payload", "json", False),
    ),
    "migration_source_asset": (
        ("domain", "s128", False),
        ("source_system", "s32", False),
        ("original_path", "s512", False),
        ("source_sha256", "s64", False),
        ("source_head", "s64", False),
        ("migration_eligibility", "s64", False),
        ("payload", "json", False),
    ),
    "migration_validation_record": (
        ("run_id", "s128", False),
        ("domain", "s128", False),
        ("status", "s64", False),
        ("payload", "json", False),
    ),
    "model_gate_decision": (
        ("gate_name", "s128", False),
        ("decision", "s64", False),
        ("decided_at", "dt", False),
        ("rationale", "json", False),
    ),
    "operational_alert": (
        ("alert_key", "s128", False),
        ("severity", "s32", False),
        ("created_at", "dt", False),
        ("resolved_at", "dt", True),
        ("payload", "json", False),
    ),
    "operational_metric_snapshot": (
        ("metric_key", "s128", False),
        ("captured_at", "dt", False),
        ("payload", "json", False),
    ),
    "operations_check_result": (
        ("cycle_id", "s128", False),
        ("check_name", "s128", False),
        ("status", "s64", False),
        ("payload", "json", False),
    ),
    "operations_cycle": (
        ("cycle_id", "s128", False),
        ("kind", "s32", False),
        ("status", "s32", False),
        ("deterministic_hash", "s64", False),
        ("started_at", "dt", False),
        ("completed_at", "dt", False),
        ("payload", "json", False),
    ),
    "promotion_relegation_mapping": (
        ("competition_id", "s128", False),
        ("from_season", "s32", False),
        ("to_season", "s32", False),
        ("status", "s64", False),
        ("payload", "json", False),
    ),
    "provider_entity_mappings": (
        ("entity_type", "s64", False),
        ("entity_id", "s36", False),
        ("provider", "s64", False),
        ("external_id", "s255", False),
        ("source", "s128", False),
        ("confidence", "num5_4", False),
        ("valid_from", "dt", False),
        ("valid_to", "dt", True),
    ),
    "release_audit": (
        ("release_id", "s128", False),
        ("audit_hash", "s64", False),
        ("created_at", "dt", False),
        ("payload", "json", False),
    ),
    "release_candidate": (
        ("release_id", "s128", False),
        ("status", "s64", False),
        ("payload", "json", False),
    ),
    "restore_run": (
        ("restore_id", "s128", False),
        ("backup_id", "s128", False),
        ("restored_at", "dt", False),
        ("verified", "bool", False),
        ("payload", "json", False),
    ),
    "retention_audit": (
        ("audit_id", "s128", False),
        ("status", "s64", False),
        ("payload", "json", False),
    ),
    "season_rollover_plan": (
        ("competition_id", "s128", False),
        ("next_season", "s32", False),
        ("status", "s64", False),
        ("payload", "json", False),
    ),
    "security_audit_event": (
        ("event_key", "s128", False),
        ("created_at", "dt", False),
        ("actor_role", "s32", False),
        ("action", "s128", False),
        ("payload", "json", False),
    ),
    "shadow_comparison_record": (
        ("run_id", "s128", False),
        ("fixture_identity", "s128", False),
        ("strategy_comparison_status", "s64", False),
        ("payload", "json", False),
    ),
    "shadow_run": (
        ("run_id", "s128", False),
        ("created_at", "dt", False),
        ("manifest_sha256", "s64", False),
        ("payload", "json", False),
    ),
    "shadow_strategy_candidate": (
        ("fixture_id", "s64", False),
        ("phase", "s32", False),
        ("strategy_version", "s64", False),
        ("rank", "int", False),
        ("shadow_action", "s32", False),
        ("public_decision", "s16", False),
        ("payload", "json", False),
    ),
    "shadow_strategy_event": (
        ("event_id", "s64", False),
        ("fixture_id", "s64", False),
        ("event_type", "s32", False),
        ("event_time", "dt", False),
        ("payload", "json", False),
    ),
    "shadow_strategy_settlement": (
        ("fixture_id", "s64", False),
        ("phase", "s32", False),
        ("strategy_version", "s64", False),
        ("settled_at", "dt", False),
        ("payload", "json", False),
    ),
    "slo_evaluation": (
        ("evaluation_key", "s128", False),
        ("evaluated_at", "dt", False),
        ("status", "s64", False),
        ("payload", "json", False),
    ),
    "sync_cursors": (
        ("provider", "s64", False),
        ("endpoint", "s64", False),
        ("cursor_name", "s128", False),
        ("cursor_value", "s512", False),
        ("updated_at", "dt", False),
    ),
    "tournament_operations_plan": (
        ("competition_id", "s128", False),
        ("plan_sha256", "s64", False),
        ("created_at", "dt", False),
        ("payload", "json", False),
    ),
    "tournament_profile": (
        ("competition_id", "s128", False),
        ("version", "s128", False),
        ("strategy_version", "s128", False),
        ("payload", "json", False),
    ),
    "tournament_readiness_audit": (
        ("competition_id", "s128", False),
        ("readiness_sha256", "s64", False),
        ("created_at", "dt", False),
        ("payload", "json", False),
    ),
}

UNIQUE_CONSTRAINTS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "api_request_audit": (("uq_api_request_audit_request_id", ("request_id",)),),
    "backup_run": (("uq_backup_run_id", ("backup_id",)),),
    "challenger_model": (("uq_challenger_model_key", ("model_key",)),),
    "dataset_sources": (("uq_dataset_source_id", ("source_id",)),),
    "dependency_risk": (("uq_dependency_risk", ("package", "source")),),
    "forward_cycle_checkpoint": (
        ("uq_forward_cycle_checkpoint", ("cycle_id", "step", "payload_hash")),
    ),
    "forward_operational_alert": (("uq_forward_operational_alert_key", ("alert_key",)),),
    "forward_result_event": (
        ("uq_forward_result_event", ("fixture_id", "provider", "raw_payload_hash")),
    ),
    "forward_scheduler_run": (
        ("uq_forward_scheduler_run", ("scheduler_key", "scheduled_for")),
    ),
    "forward_state_transition": (
        ("uq_forward_state_transition", ("fixture_id", "from_state", "to_state", "event_time")),
    ),
    "freshness_alerts": (
        ("uq_freshness_alert", ("entity_type", "entity_id", "observed_at", "threshold_seconds")),
    ),
    "league_team_membership": (
        ("uq_league_team_membership", ("competition_id", "season", "provider_team_id")),
    ),
    "market_quality_assessment": (
        ("uq_market_quality_identity", ("fixture_id", "market", "as_of_time")),
    ),
    "migration_dry_run": (("uq_migration_dry_run_id", ("run_id",)),),
    "migration_quarantine_record": (
        ("uq_migration_quarantine", ("domain", "source_sha256")),
    ),
    "migration_source_asset": (("uq_migration_source_asset", ("domain", "source_sha256")),),
    "migration_validation_record": (
        ("uq_migration_validation_domain", ("run_id", "domain")),
    ),
    "model_gate_decision": (("uq_model_gate_decision", ("gate_name", "decided_at")),),
    "operational_alert": (("uq_operational_alert_key", ("alert_key",)),),
    "operational_metric_snapshot": (
        ("uq_operational_metric_snapshot", ("metric_key", "captured_at")),
    ),
    "operations_check_result": (("uq_operations_check_result", ("cycle_id", "check_name")),),
    "operations_cycle": (("uq_operations_cycle_id", ("cycle_id",)),),
    "promotion_relegation_mapping": (
        ("uq_promo_rel", ("competition_id", "from_season", "to_season")),
    ),
    "provider_entity_mappings": (
        ("uq_provider_external_identity", ("provider", "entity_type", "external_id", "valid_from")),
    ),
    "release_audit": (("uq_release_audit", ("release_id", "audit_hash")),),
    "release_candidate": (("uq_release_candidate_id", ("release_id",)),),
    "restore_run": (("uq_restore_run_id", ("restore_id",)),),
    "retention_audit": (("uq_retention_audit_id", ("audit_id",)),),
    "season_rollover_plan": (("uq_season_rollover", ("competition_id", "next_season")),),
    "security_audit_event": (("uq_security_audit_event_key", ("event_key",)),),
    "shadow_comparison_record": (
        ("uq_shadow_comparison_fixture", ("run_id", "fixture_identity")),
    ),
    "shadow_run": (("uq_shadow_run_id", ("run_id",)),),
    "shadow_strategy_candidate": (
        (
            "uq_shadow_strategy_candidate_rank",
            ("fixture_id", "phase", "strategy_version", "rank"),
        ),
    ),
    "shadow_strategy_event": (("uq_shadow_strategy_event_id", ("event_id",)),),
    "shadow_strategy_settlement": (
        (
            "uq_shadow_strategy_settlement_fixture_phase_version",
            ("fixture_id", "phase", "strategy_version"),
        ),
    ),
    "slo_evaluation": (("uq_slo_evaluation_key", ("evaluation_key",)),),
    "sync_cursors": (("uq_sync_cursor", ("provider", "endpoint", "cursor_name")),),
    "tournament_operations_plan": (
        ("uq_tournament_plan_hash", ("competition_id", "plan_sha256")),
    ),
    "tournament_profile": (
        ("uq_tournament_profile_version", ("competition_id", "version")),
    ),
    "tournament_readiness_audit": (
        ("uq_readiness_hash", ("competition_id", "readiness_sha256")),
    ),
}

INDEXES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "audit_events": (("ix_audit_events_occurred_at", ("occurred_at",)),),
    "data_quality_runs": (
        ("ix_data_quality_run_at", ("run_at",)),
        ("ix_data_quality_dataset_version", ("dataset_id", "version")),
    ),
    "freshness_alerts": (("ix_freshness_alerts_observed_at", ("observed_at",)),),
    "market_quality_assessment": (("ix_market_quality_status", ("quality_status",)),),
    "provider_entity_mappings": (("ix_mapping_entity", ("entity_type", "entity_id")),),
    "shadow_strategy_candidate": (
        ("ix_shadow_strategy_candidate_fixture", ("fixture_id",)),
    ),
    "shadow_strategy_event": (
        ("ix_shadow_strategy_event_fixture", ("fixture_id",)),
        ("ix_shadow_strategy_event_time", ("event_time",)),
    ),
}


def _type_factories() -> dict[str, Callable[[], sa.types.TypeEngine]]:
    return {
        "bool": sa.Boolean,
        "dt": lambda: sa.DateTime(timezone=True),
        "int": sa.Integer,
        "json": sa.JSON,
        "num5_4": lambda: sa.Numeric(precision=5, scale=4),
        **{f"s{length}": lambda length=length: sa.String(length=length) for length in (
            16,
            32,
            36,
            64,
            128,
            255,
            256,
            512,
        )},
    }


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table_name in reversed(tuple(TABLE_COLUMNS)):
        if inspector.has_table(table_name):
            op.drop_table(table_name)


def downgrade() -> None:
    metadata = sa.MetaData()
    type_factories = _type_factories()
    for table_name, specs in TABLE_COLUMNS.items():
        constraints = [
            sa.UniqueConstraint(*columns, name=name)
            for name, columns in UNIQUE_CONSTRAINTS.get(table_name, ())
        ]
        table = sa.Table(
            table_name,
            metadata,
            sa.Column("id", sa.String(length=36), primary_key=True),
            *(
                sa.Column(name, type_factories[type_name](), nullable=nullable)
                for name, type_name, nullable in specs
            ),
            *constraints,
        )
        for index_name, columns in INDEXES.get(table_name, ()):
            sa.Index(index_name, *(table.c[column] for column in columns))
        table.create(bind=op.get_bind(), checkfirst=True)
