"""drop empty foreign-key components without current business paths

Revision ID: 0040_drop_empty_fk_components
Revises: 0039_drop_evidence_backed_dead_tables
Create Date: 2026-07-23 16:30:00.000000
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0040_drop_empty_fk_components"
down_revision: str | None = "0039_drop_evidence_backed_dead_tables"
branch_labels: str | None = None
depends_on: str | None = None

ColumnSpec = tuple[str, str, bool, bool]
ForeignKeySpec = tuple[tuple[str, ...], tuple[str, ...]]
UniqueSpec = tuple[str, tuple[str, ...]]
IndexSpec = tuple[str, tuple[str, ...], bool]
TableSpec = tuple[
    tuple[ColumnSpec, ...],
    tuple[ForeignKeySpec, ...],
    tuple[UniqueSpec, ...],
    tuple[IndexSpec, ...],
]


def _columns(*specs: ColumnSpec) -> tuple[ColumnSpec, ...]:
    return specs


TABLE_SPECS: dict[str, TableSpec] = {
    "replay_run": (
        _columns(
            ("id", "s36", False, True),
            ("run_key", "s128", False, False),
            ("created_at", "dt", False, False),
            ("manifest_sha256", "s64", False, False),
            ("status", "s32", False, False),
        ),
        (),
        (("uq_replay_run_key", ("run_key",)),),
        (("ix_replay_run_created", ("created_at",), False),),
    ),
    "ablation_run": (
        _columns(
            ("id", "s36", False, True),
            ("replay_run_id", "s36", False, False),
            ("ablation_key", "s128", False, False),
            ("status", "s32", False, False),
            ("metrics", "json", False, False),
        ),
        ((("replay_run_id",), ("replay_run.id",)),),
        (("uq_ablation_run", ("replay_run_id", "ablation_key")),),
        (),
    ),
    "evaluation_record": (
        _columns(
            ("id", "s36", False, True),
            ("replay_run_id", "s36", False, False),
            ("fixture_id", "s128", False, False),
            ("model_name", "s128", False, False),
            ("metrics", "json", False, False),
        ),
        ((("replay_run_id",), ("replay_run.id",)),),
        (("uq_evaluation_record", ("replay_run_id", "fixture_id", "model_name")),),
        (),
    ),
    "prediction_snapshot": (
        _columns(
            ("id", "s36", False, True),
            ("replay_run_id", "s36", False, False),
            ("fixture_id", "s128", False, False),
            ("model_name", "s128", False, False),
            ("prediction_hash", "s64", False, False),
            ("probabilities", "json", False, False),
            ("decision", "s32", False, False),
        ),
        ((("replay_run_id",), ("replay_run.id",)),),
        (("uq_prediction_snapshot", ("replay_run_id", "fixture_id", "model_name")),),
        (),
    ),
    "replay_checkpoint": (
        _columns(
            ("id", "s36", False, True),
            ("replay_run_id", "s36", False, False),
            ("checkpoint_key", "s128", False, False),
            ("last_event_id", "s128", True, False),
            ("ledger_hash", "s64", False, False),
            ("processed_events", "int", False, False),
        ),
        ((("replay_run_id",), ("replay_run.id",)),),
        (("uq_replay_checkpoint", ("replay_run_id", "checkpoint_key")),),
        (),
    ),
    "replay_event": (
        _columns(
            ("id", "s36", False, True),
            ("replay_run_id", "s36", False, False),
            ("event_id", "s128", False, False),
            ("fixture_id", "s128", False, False),
            ("event_type", "s64", False, False),
            ("event_time", "dt", False, False),
            ("payload", "json", False, False),
        ),
        ((("replay_run_id",), ("replay_run.id",)),),
        (("uq_replay_event_once", ("replay_run_id", "event_id")),),
        (("ix_replay_event_time", ("event_time",), False),),
    ),
    "dataset_versions": (
        _columns(
            ("id", "s36", False, True),
            ("dataset_id", "s128", False, False),
            ("version", "s128", False, False),
            ("created_at", "dt", False, False),
            ("source_ids", "json", False, False),
            ("manifest_sha256", "s64", False, False),
        ),
        (),
        (("uq_dataset_version", ("dataset_id", "version")),),
        (),
    ),
    "label_references": (
        _columns(
            ("id", "s36", False, True),
            ("fixture_id", "s128", False, False),
            ("result_status", "s64", False, False),
            ("home_goals", "int", True, False),
            ("away_goals", "int", True, False),
            ("confirmed_at", "dt", False, False),
            ("raw_payload_refs", "json", False, False),
        ),
        (),
        (("uq_label_reference", ("fixture_id", "confirmed_at")),),
        (),
    ),
    "asof_samples": (
        _columns(
            ("id", "s36", False, True),
            ("dataset_version_id", "s36", False, False),
            ("fixture_id", "s128", False, False),
            ("competition", "s128", False, False),
            ("season", "s64", False, False),
            ("kickoff_utc", "dt", False, False),
            ("prediction_phase", "s64", False, False),
            ("as_of_time", "dt", False, False),
            ("data_cutoff", "dt", False, False),
            ("feature_payload", "json", False, False),
            ("label_reference_id", "s36", False, False),
        ),
        (
            (("dataset_version_id",), ("dataset_versions.id",)),
            (("label_reference_id",), ("label_references.id",)),
        ),
        (("uq_asof_sample", ("fixture_id", "prediction_phase", "as_of_time")),),
        (
            ("ix_asof_samples_as_of_time", ("as_of_time",), False),
            ("ix_asof_samples_fixture", ("fixture_id",), False),
            ("ix_asof_samples_kickoff", ("kickoff_utc",), False),
        ),
    ),
    "dataset_artifacts": (
        _columns(
            ("id", "s36", False, True),
            ("dataset_version_id", "s36", False, False),
            ("artifact_id", "s128", False, False),
            ("path", "s512", False, False),
            ("media_type", "s128", False, False),
            ("sha256", "s64", False, False),
            ("row_count", "int", False, False),
        ),
        ((("dataset_version_id",), ("dataset_versions.id",)),),
        (("uq_dataset_artifact", ("dataset_version_id", "artifact_id")),),
        (),
    ),
    "model_experiment": (
        _columns(
            ("id", "s36", False, True),
            ("experiment_key", "s128", False, False),
            ("track", "s64", False, False),
            ("created_at", "dt", False, False),
            ("data_cutoff", "dt", False, False),
            ("config", "json", False, False),
        ),
        (),
        (("uq_model_experiment_key", ("experiment_key",)),),
        (("ix_model_experiment_created", ("created_at",), False),),
    ),
    "calibration_artifact": (
        _columns(
            ("id", "s36", False, True),
            ("experiment_id", "s36", False, False),
            ("method", "s64", False, False),
            ("fitted_on", "s32", False, False),
            ("parameters", "json", False, False),
            ("sha256", "s64", False, False),
        ),
        ((("experiment_id",), ("model_experiment.id",)),),
        (("uq_calibration_artifact", ("experiment_id", "method", "fitted_on")),),
        (),
    ),
    "model_artifact": (
        _columns(
            ("id", "s36", False, True),
            ("experiment_id", "s36", False, False),
            ("artifact_key", "s128", False, False),
            ("uri", "s512", False, False),
            ("sha256", "s64", False, False),
            ("manifest", "json", False, False),
        ),
        ((("experiment_id",), ("model_experiment.id",)),),
        (("uq_model_artifact_key", ("experiment_id", "artifact_key")),),
        (),
    ),
    "model_evaluation": (
        _columns(
            ("id", "s36", False, True),
            ("experiment_id", "s36", False, False),
            ("model_name", "s128", False, False),
            ("split", "s32", False, False),
            ("metrics", "json", False, False),
            ("slices", "json", False, False),
        ),
        ((("experiment_id",), ("model_experiment.id",)),),
        (("uq_model_evaluation", ("experiment_id", "model_name", "split")),),
        (("ix_model_evaluation_split", ("split",), False),),
    ),
    "forward_holdout_run": (
        _columns(
            ("id", "s36", False, True),
            ("run_key", "s128", False, False),
            ("created_at", "dt", False, False),
            ("status", "s32", False, False),
            ("protocol", "json", False, False),
        ),
        (),
        (("uq_forward_holdout_run_key", ("run_key",)),),
        (),
    ),
    "forward_prediction_lock": (
        _columns(
            ("id", "s36", False, True),
            ("forward_holdout_run_id", "s36", False, False),
            ("fixture_id", "s128", False, False),
            ("locked_at", "dt", False, False),
            ("kickoff_utc", "dt", False, False),
            ("prediction_hash", "s64", False, False),
            ("decision", "s32", False, False),
        ),
        ((("forward_holdout_run_id",), ("forward_holdout_run.id",)),),
        (("uq_forward_prediction_lock", ("forward_holdout_run_id", "fixture_id")),),
        (),
    ),
    "forward_evaluation": (
        _columns(
            ("id", "s36", False, True),
            ("forward_prediction_lock_id", "s36", False, False),
            ("evaluated_at", "dt", False, False),
            ("metrics", "json", False, False),
        ),
        ((("forward_prediction_lock_id",), ("forward_prediction_lock.id",)),),
        (("uq_forward_evaluation_once", ("forward_prediction_lock_id",)),),
        (),
    ),
    "market_baseline_run": (
        _columns(
            ("id", "s36", False, True),
            ("run_key", "s128", False, False),
            ("created_at", "dt", False, False),
            ("dataset_version", "s128", False, False),
            ("method_selection_policy", "s128", False, False),
            ("metrics", "json", False, False),
        ),
        (),
        (("uq_market_baseline_run_key", ("run_key",)),),
        (("ix_market_baseline_run_created", ("created_at",), False),),
    ),
    "market_fit_diagnostic": (
        _columns(
            ("id", "s36", False, True),
            ("market_baseline_run_id", "s36", False, False),
            ("fixture_id", "s128", False, False),
            ("diagnostic_type", "s64", False, False),
            ("residual", "num12_8", False, False),
            ("payload", "json", False, False),
        ),
        ((("market_baseline_run_id",), ("market_baseline_run.id",)),),
        (),
        (
            ("ix_market_fit_diagnostic_fixture", ("fixture_id",), False),
            ("ix_market_fit_diagnostic_run", ("market_baseline_run_id",), False),
        ),
    ),
    "raw_payload_references": (
        _columns(
            ("id", "s36", False, True),
            ("provider", "s64", False, False),
            ("object_uri", "s512", False, False),
            ("sha256", "s64", False, False),
            ("captured_at", "dt", False, False),
            ("immutable", "bool", False, False),
        ),
        (),
        (("uq_raw_payload_reference", ("provider", "object_uri", "sha256")),),
        (),
    ),
    "data_provenance": (
        _columns(
            ("id", "s36", False, True),
            ("entity_type", "s64", False, False),
            ("entity_id", "s36", False, False),
            ("layer", "s32", False, False),
            ("source_ref_id", "s36", True, False),
            ("event_time", "dt", False, False),
            ("provider_updated_at", "dt", True, False),
            ("ingested_at", "dt", False, False),
            ("as_of_time", "dt", True, False),
            ("confirmed_at", "dt", True, False),
        ),
        ((("source_ref_id",), ("raw_payload_references.id",)),),
        (),
        (
            ("ix_provenance_as_of_time", ("as_of_time",), False),
            ("ix_provenance_event_time", ("event_time",), False),
            ("ix_provenance_layer", ("layer",), False),
        ),
    ),
    "forward_cycle_run": (
        _columns(
            ("id", "s36", False, True),
            ("cycle_key", "s128", False, False),
            ("started_at", "dt", False, False),
            ("status", "s32", False, False),
            ("request_budget", "int", False, False),
            ("manifest", "json", False, False),
        ),
        (),
        (("uq_forward_cycle_run_key", ("cycle_key",)),),
        (),
    ),
    "forward_gate_audit": (
        _columns(
            ("id", "s36", False, True),
            ("cycle_run_id", "s36", False, False),
            ("gate_name", "s128", False, False),
            ("decision", "s64", False, False),
            ("audit_payload", "json", False, False),
        ),
        ((("cycle_run_id",), ("forward_cycle_run.id",)),),
        (("uq_forward_gate_audit", ("cycle_run_id", "gate_name")),),
        (),
    ),
    "bookmakers": (
        _columns(
            ("id", "s36", False, True),
            ("name", "s255", False, False),
        ),
        (),
        (("uq_bookmaker_name", ("name",)),),
        (),
    ),
    "players": (
        _columns(
            ("id", "s36", False, True),
            ("name", "s255", False, False),
            ("birth_date", "dt", True, False),
        ),
        (),
        (),
        (),
    ),
    "feature_snapshots": (
        _columns(
            ("id", "s36", False, True),
            ("fixture_id", "s36", False, False),
            ("as_of_time", "dt", False, False),
            ("features", "json", False, False),
            ("layer", "s32", False, False),
        ),
        ((("fixture_id",), ("fixtures.id",)),),
        (("uq_feature_fixture_as_of", ("fixture_id", "as_of_time")),),
        (("ix_feature_snapshots_as_of_time", ("as_of_time",), False),),
    ),
    "injuries": (
        _columns(
            ("id", "s36", False, True),
            ("player_id", "s36", False, False),
            ("team_id", "s36", False, False),
            ("status", "s64", False, False),
            ("as_of_time", "dt", False, False),
        ),
        (
            (("player_id",), ("players.id",)),
            (("team_id",), ("teams.id",)),
        ),
        (),
        (("ix_injuries_as_of_time", ("as_of_time",), False),),
    ),
    "lineups": (
        _columns(
            ("id", "s36", False, True),
            ("fixture_id", "s36", False, False),
            ("team_id", "s36", False, False),
            ("player_id", "s36", False, False),
            ("confirmed_at", "dt", True, False),
        ),
        (
            (("fixture_id",), ("fixtures.id",)),
            (("player_id",), ("players.id",)),
            (("team_id",), ("teams.id",)),
        ),
        (("uq_lineup_player", ("fixture_id", "team_id", "player_id")),),
        (),
    ),
    "market_consensus": (
        _columns(
            ("id", "s36", False, True),
            ("fixture_id", "s36", False, False),
            ("market", "s64", False, False),
            ("selection", "s64", False, False),
            ("line", "num10_3", True, False),
            ("as_of_time", "dt", False, False),
            ("method", "s64", False, False),
            ("fair_decimal_odds", "num10_4", True, False),
            ("effective_bookmakers", "int", False, False),
            ("quality_status", "s32", False, False),
            ("diagnostics", "json", False, False),
        ),
        ((("fixture_id",), ("fixtures.id",)),),
        (
            (
                "uq_market_consensus_identity",
                ("fixture_id", "market", "selection", "line", "as_of_time", "method"),
            ),
        ),
        (("ix_market_consensus_as_of", ("as_of_time",), False),),
    ),
    "markets": (
        _columns(
            ("id", "s36", False, True),
            ("fixture_id", "s36", False, False),
            ("market", "s64", False, False),
            ("settlement_rule", "s128", False, False),
        ),
        ((("fixture_id",), ("fixtures.id",)),),
        (("uq_market_fixture_rule", ("fixture_id", "market", "settlement_rule")),),
        (),
    ),
    "odds_observations": (
        _columns(
            ("id", "s36", False, True),
            ("fixture_id", "s36", False, False),
            ("bookmaker_id", "s36", False, False),
            ("market", "s64", False, False),
            ("selection", "s64", False, False),
            ("line", "num10_3", True, False),
            ("decimal_odds", "num10_4", False, False),
            ("suspended", "bool", False, False),
            ("live", "bool", False, False),
            ("stale", "bool", False, False),
            ("provider_updated_at", "dt", False, False),
            ("captured_at", "dt", False, False),
            ("raw_label", "s255", False, False),
            ("canonical_selection", "s64", False, False),
            ("settlement_rule", "s128", False, False),
        ),
        (
            (("bookmaker_id",), ("bookmakers.id",)),
            (("fixture_id",), ("fixtures.id",)),
        ),
        (
            (
                "uq_odds_observation_idempotency",
                (
                    "fixture_id",
                    "bookmaker_id",
                    "market",
                    "canonical_selection",
                    "line",
                    "provider_updated_at",
                    "captured_at",
                ),
            ),
        ),
        (
            ("ix_odds_captured_at", ("captured_at",), False),
            ("ix_odds_provider_updated_at", ("provider_updated_at",), False),
        ),
    ),
    "squads": (
        _columns(
            ("id", "s36", False, True),
            ("team_id", "s36", False, False),
            ("player_id", "s36", False, False),
            ("season_id", "s36", False, False),
            ("shirt_number", "int", True, False),
        ),
        (
            (("player_id",), ("players.id",)),
            (("season_id",), ("seasons.id",)),
            (("team_id",), ("teams.id",)),
        ),
        (("uq_squad_member", ("team_id", "player_id", "season_id")),),
        (),
    ),
    "suspensions": (
        _columns(
            ("id", "s36", False, True),
            ("player_id", "s36", False, False),
            ("team_id", "s36", False, False),
            ("reason", "s128", False, False),
            ("as_of_time", "dt", False, False),
        ),
        (
            (("player_id",), ("players.id",)),
            (("team_id",), ("teams.id",)),
        ),
        (),
        (("ix_suspensions_as_of_time", ("as_of_time",), False),),
    ),
    "team_ratings": (
        _columns(
            ("id", "s36", False, True),
            ("team_id", "s36", False, False),
            ("as_of_time", "dt", False, False),
            ("rating", "num10_4", False, False),
        ),
        ((("team_id",), ("teams.id",)),),
        (("uq_team_rating_as_of", ("team_id", "as_of_time")),),
        (("ix_team_ratings_as_of_time", ("as_of_time",), False),),
    ),
    "weather_observations": (
        _columns(
            ("id", "s36", False, True),
            ("fixture_id", "s36", False, False),
            ("observed_at", "dt", False, False),
            ("temperature_c", "num5_2", True, False),
        ),
        ((("fixture_id",), ("fixtures.id",)),),
        (),
        (("ix_weather_observed_at", ("observed_at",), False),),
    ),
}


def _type_factories() -> dict[str, Callable[[], sa.types.TypeEngine[Any]]]:
    return {
        "bool": sa.Boolean,
        "dt": lambda: sa.DateTime(timezone=True),
        "int": sa.Integer,
        "json": sa.JSON,
        "num5_2": lambda: sa.Numeric(precision=5, scale=2),
        "num10_3": lambda: sa.Numeric(precision=10, scale=3),
        "num10_4": lambda: sa.Numeric(precision=10, scale=4),
        "num12_8": lambda: sa.Numeric(precision=12, scale=8),
        **{
            f"s{length}": lambda length=length: sa.String(length=length)
            for length in (32, 36, 64, 128, 255, 512)
        },
    }


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table_name in reversed(tuple(TABLE_SPECS)):
        if inspector.has_table(table_name):
            op.drop_table(table_name)


def downgrade() -> None:
    type_factories = _type_factories()
    for table_name, (columns, foreign_keys, unique_constraints, indexes) in TABLE_SPECS.items():
        constraints: list[sa.SchemaItem] = [
            sa.ForeignKeyConstraint(local, remote)
            for local, remote in foreign_keys
        ]
        constraints.extend(
            sa.UniqueConstraint(*column_names, name=name)
            for name, column_names in unique_constraints
        )
        op.create_table(
            table_name,
            *(
                sa.Column(
                    name,
                    type_factories[type_name](),
                    nullable=nullable,
                    primary_key=primary_key,
                )
                for name, type_name, nullable, primary_key in columns
            ),
            *constraints,
        )
        for index_name, column_names, unique in indexes:
            op.create_index(index_name, table_name, list(column_names), unique=unique)
