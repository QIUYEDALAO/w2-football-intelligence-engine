"""isolate raw fixture scopes and factor shadow v2 ledgers

Revision ID: 0070_factor_shadow_v2_gate0
Revises: 0069_outcome_ledger_run_state
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0070_factor_shadow_v2_gate0"
down_revision: str | None = "0069_outcome_ledger_run_state"
branch_labels: str | None = None
depends_on: str | None = None

V2_ROLE = "w2_factor_shadow_v2_writer"
V2_TABLES = (
    "factor_shadow_forecast_capture",
    "factor_shadow_market_opportunity",
    "factor_shadow_market_attempt",
    "factor_shadow_forecast_outcome",
    "factor_shadow_v2_admission",
)


def upgrade() -> None:
    op.create_table(
        "raw_fixture_scope_membership",
        sa.Column("membership_hash", sa.String(64), primary_key=True),
        sa.Column(
            "raw_payload_sha256",
            sa.String(64),
            sa.ForeignKey("raw_payload.sha256", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("provider_fixture_id", sa.String(64), nullable=False),
        sa.Column("scope_policy_version", sa.String(64), nullable=False),
        sa.Column("source_scope", sa.String(32), nullable=False),
        sa.Column("request_identity", sa.String(64), nullable=False),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_league_id", sa.String(64)),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "raw_payload_sha256",
            "provider_fixture_id",
            "scope_policy_version",
            name="uq_raw_fixture_scope_membership_identity",
        ),
        sa.CheckConstraint(
            "source_scope in ('LIVE_DISCOVERY','HISTORICAL_TRAINING','CONTROLLED_AUDIT')",
            name="ck_raw_fixture_scope_membership_scope",
        ),
    )
    op.create_index(
        "ix_raw_fixture_scope_membership_scope_kickoff",
        "raw_fixture_scope_membership",
        ["source_scope", "scope_policy_version", "provider_league_id", "kickoff_utc"],
    )

    op.create_table(
        "factor_shadow_forecast_capture",
        sa.Column("forecast_identity_hash", sa.String(64), primary_key=True),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("competition_id", sa.String(128), nullable=False),
        sa.Column(
            "production_capture_identity_hash",
            sa.String(64),
            sa.ForeignKey("model_forecast_capture.capture_identity_hash", ondelete="RESTRICT"),
        ),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_mode", sa.String(32), nullable=False),
        sa.Column("model_family", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("feature_registry_version", sa.String(128), nullable=False),
        sa.Column("calibration_version", sa.String(128), nullable=False),
        sa.Column("pit_input_identity_hash", sa.String(64), nullable=False),
        sa.Column("lambda_home", sa.Float(), nullable=False),
        sa.Column("lambda_away", sa.Float(), nullable=False),
        sa.Column("score_matrix_hash", sa.String(64), nullable=False),
        sa.Column("probability_method", sa.String(32), nullable=False),
        sa.Column("sampling_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("inserted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "fixture_id",
            "captured_at",
            "model_version",
            "feature_registry_version",
            "calibration_version",
            "source_mode",
            name="uq_factor_shadow_forecast_scope",
        ),
        sa.CheckConstraint(
            "source_mode in ('HISTORICAL_REPLAY','FORWARD_SHADOW')",
            name="ck_factor_shadow_forecast_source_mode",
        ),
        sa.CheckConstraint(
            "probability_method = 'EXACT_MATRIX' and sampling_used = false",
            name="ck_factor_shadow_forecast_exact_matrix",
        ),
    )
    op.create_index(
        "ix_factor_shadow_forecast_fixture",
        "factor_shadow_forecast_capture",
        ["fixture_id", "captured_at"],
    )

    op.create_table(
        "factor_shadow_market_opportunity",
        sa.Column("opportunity_identity_hash", sa.String(64), primary_key=True),
        sa.Column(
            "forecast_identity_hash",
            sa.String(64),
            sa.ForeignKey(
                "factor_shadow_forecast_capture.forecast_identity_hash",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("source_mode", sa.String(32), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("evaluation_policy_version", sa.String(128), nullable=False),
        sa.Column("evaluation_slot_id", sa.String(64), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("inserted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "forecast_identity_hash",
            "market",
            "evaluation_policy_version",
            "evaluation_slot_id",
            name="uq_factor_shadow_market_opportunity_scope",
        ),
        sa.CheckConstraint(
            "source_mode in ('HISTORICAL_REPLAY','FORWARD_SHADOW')",
            name="ck_factor_shadow_market_opportunity_source_mode",
        ),
    )
    op.create_index(
        "ix_factor_shadow_market_opportunity_fixture",
        "factor_shadow_market_opportunity",
        ["fixture_id", "scheduled_at"],
    )

    op.create_table(
        "factor_shadow_market_attempt",
        sa.Column("attempt_identity_hash", sa.String(64), primary_key=True),
        sa.Column(
            "opportunity_identity_hash",
            sa.String(64),
            sa.ForeignKey(
                "factor_shadow_market_opportunity.opportunity_identity_hash",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("quote_identity_hash", sa.String(64), nullable=False),
        sa.Column("source_event_identity", sa.String(128), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("inserted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_factor_shadow_market_attempt_opportunity",
        "factor_shadow_market_attempt",
        ["opportunity_identity_hash"],
    )
    op.create_index(
        "ix_factor_shadow_market_attempt_evaluated",
        "factor_shadow_market_attempt",
        ["evaluated_at"],
    )

    op.create_table(
        "factor_shadow_forecast_outcome",
        sa.Column("outcome_identity_hash", sa.String(64), primary_key=True),
        sa.Column(
            "forecast_identity_hash",
            sa.String(64),
            sa.ForeignKey(
                "factor_shadow_forecast_capture.forecast_identity_hash",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("authoritative_result_identity", sa.String(64), nullable=False),
        sa.Column("brier", sa.Float()),
        sa.Column("log_loss", sa.Float()),
        sa.Column("rps", sa.Float()),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("inserted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "forecast_identity_hash",
            name="uq_factor_shadow_outcome_forecast",
        ),
    )
    op.create_index(
        "ix_factor_shadow_outcome_fixture",
        "factor_shadow_forecast_outcome",
        ["fixture_id", "settled_at"],
    )

    op.create_table(
        "factor_shadow_v2_admission",
        sa.Column("admission_identity_hash", sa.String(64), primary_key=True),
        sa.Column("source_mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("feature_registry_version", sa.String(128), nullable=False),
        sa.Column("calibration_version", sa.String(128), nullable=False),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("inserted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_mode in ('HISTORICAL_REPLAY','FORWARD_SHADOW')",
            name="ck_factor_shadow_admission_source_mode",
        ),
    )
    op.create_index(
        "ix_factor_shadow_v2_admission_time",
        "factor_shadow_v2_admission",
        ["admitted_at"],
    )
    _grant_factor_shadow_role()


def downgrade() -> None:
    _revoke_factor_shadow_role()
    op.drop_index(
        "ix_factor_shadow_v2_admission_time",
        table_name="factor_shadow_v2_admission",
    )
    op.drop_table("factor_shadow_v2_admission")
    op.drop_index(
        "ix_factor_shadow_outcome_fixture",
        table_name="factor_shadow_forecast_outcome",
    )
    op.drop_table("factor_shadow_forecast_outcome")
    op.drop_index(
        "ix_factor_shadow_market_attempt_evaluated",
        table_name="factor_shadow_market_attempt",
    )
    op.drop_index(
        "ix_factor_shadow_market_attempt_opportunity",
        table_name="factor_shadow_market_attempt",
    )
    op.drop_table("factor_shadow_market_attempt")
    op.drop_index(
        "ix_factor_shadow_market_opportunity_fixture",
        table_name="factor_shadow_market_opportunity",
    )
    op.drop_table("factor_shadow_market_opportunity")
    op.drop_index(
        "ix_factor_shadow_forecast_fixture",
        table_name="factor_shadow_forecast_capture",
    )
    op.drop_table("factor_shadow_forecast_capture")
    op.drop_index(
        "ix_raw_fixture_scope_membership_scope_kickoff",
        table_name="raw_fixture_scope_membership",
    )
    op.drop_table("raw_fixture_scope_membership")


def _grant_factor_shadow_role() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = 'w2_factor_shadow_v2_writer'
              ) THEN
                CREATE ROLE w2_factor_shadow_v2_writer
                  NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
              END IF;
            END
            $$
            """
        )
    )
    op.execute(sa.text(f"GRANT USAGE ON SCHEMA public TO {V2_ROLE}"))
    op.execute(sa.text(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {V2_ROLE}"))
    op.execute(
        sa.text(
            f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER "
            f"ON ALL TABLES IN SCHEMA public FROM {V2_ROLE}"
        )
    )
    op.execute(
        sa.text(
            f"GRANT INSERT, SELECT ON {', '.join(V2_TABLES)} TO {V2_ROLE}"
        )
    )


def _revoke_factor_shadow_role() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        sa.text(
            f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER "
            f"ON {', '.join(V2_TABLES)} FROM {V2_ROLE}"
        )
    )
