"""create independent model forecast validation and raw Statistics retention ledgers

Revision ID: 0054_model_forecast_validation_ledger
Revises: 0053_backfill_reviewed_team_identity
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0054_model_forecast_validation_ledger"
down_revision: str | None = "0053_backfill_reviewed_team_identity"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "raw_statistics_retention",
        sa.Column("raw_payload_sha256", sa.String(64), nullable=False),
        sa.Column("retained_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["raw_payload_sha256"],
            ["raw_payload.sha256"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("raw_payload_sha256"),
    )
    op.execute(
        sa.text(
            "insert into raw_statistics_retention (raw_payload_sha256, retained_at) "
            "select sha256, coalesce(inserted_at, captured_at) from raw_payload "
            "where endpoint='statistics'"
        )
    )
    _create_raw_statistics_immutability_guards()
    op.create_table(
        "model_forecast_capture",
        sa.Column("capture_identity_hash", sa.String(64), nullable=False),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("competition_id", sa.String(128), nullable=False),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_family", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("model_input_manifest_hash", sa.String(64), nullable=False),
        sa.Column("four_field_xg_identity_hash", sa.String(64), nullable=False),
        sa.Column("score_matrix_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("inserted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("capture_identity_hash"),
        sa.UniqueConstraint(
            "fixture_id",
            "model_family",
            "model_version",
            name="uq_model_forecast_capture_fixture_model",
        ),
    )
    op.create_index(
        "ix_model_forecast_capture_fixture_kickoff",
        "model_forecast_capture",
        ["fixture_id", "kickoff_utc"],
    )
    op.create_table(
        "model_forecast_outcome",
        sa.Column("outcome_identity_hash", sa.String(64), nullable=False),
        sa.Column("capture_identity_hash", sa.String(64), nullable=False),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("authoritative_result_identity", sa.String(64), nullable=False),
        sa.Column("brier", sa.Float(), nullable=False),
        sa.Column("log_loss", sa.Float(), nullable=False),
        sa.Column("rps", sa.Float(), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("inserted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["capture_identity_hash"],
            ["model_forecast_capture.capture_identity_hash"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("outcome_identity_hash"),
        sa.UniqueConstraint(
            "capture_identity_hash",
            name="uq_model_forecast_outcome_capture",
        ),
    )
    op.create_index(
        "ix_model_forecast_outcome_fixture_settled",
        "model_forecast_outcome",
        ["fixture_id", "settled_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_model_forecast_outcome_fixture_settled",
        table_name="model_forecast_outcome",
    )
    op.drop_table("model_forecast_outcome")
    op.drop_index(
        "ix_model_forecast_capture_fixture_kickoff",
        table_name="model_forecast_capture",
    )
    op.drop_table("model_forecast_capture")
    _drop_raw_statistics_immutability_guards()
    op.drop_table("raw_statistics_retention")


def _create_raw_statistics_immutability_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            sa.text(
                "create trigger raw_statistics_no_update before update on raw_payload "
                "when old.endpoint='statistics' or new.endpoint='statistics' "
                "begin select raise(abort, 'raw Statistics payloads are immutable'); end"
            )
        )
        op.execute(
            sa.text(
                "create trigger raw_statistics_no_delete before delete on raw_payload "
                "when old.endpoint='statistics' "
                "begin select raise(abort, 'raw Statistics payloads are immutable'); end"
            )
        )
        op.execute(
            sa.text(
                "create trigger raw_statistics_retention_no_update before update "
                "on raw_statistics_retention begin select raise(abort, "
                "'raw Statistics retention is append-only'); end"
            )
        )
        op.execute(
            sa.text(
                "create trigger raw_statistics_retention_no_delete before delete "
                "on raw_statistics_retention begin select raise(abort, "
                "'raw Statistics retention is append-only'); end"
            )
        )
    elif dialect == "postgresql":
        op.execute(
            sa.text(
                "create function w2_reject_raw_statistics_mutation() returns trigger "
                "language plpgsql as $$ begin "
                "if tg_op = 'DELETE' then "
                "if old.endpoint = 'statistics' then "
                "raise exception 'raw Statistics payloads are immutable'; end if; "
                "return old; end if; "
                "if tg_op = 'UPDATE' and "
                "(old.endpoint = 'statistics' or new.endpoint = 'statistics') then "
                "raise exception 'raw Statistics payloads are immutable'; end if; "
                "return new; end $$"
            )
        )
        op.execute(
            sa.text(
                "create trigger raw_statistics_no_update before update on raw_payload "
                "for each row execute function w2_reject_raw_statistics_mutation()"
            )
        )
        op.execute(
            sa.text(
                "create trigger raw_statistics_no_delete before delete on raw_payload "
                "for each row execute function w2_reject_raw_statistics_mutation()"
            )
        )
        op.execute(
            sa.text(
                "create function w2_reject_raw_statistics_retention_mutation() "
                "returns trigger language plpgsql as $$ begin "
                "raise exception 'raw Statistics retention is append-only'; end $$"
            )
        )
        for operation in ("update", "delete"):
            op.execute(
                sa.text(
                    f"create trigger raw_statistics_retention_no_{operation} before "
                    f"{operation} on raw_statistics_retention for each row execute "
                    "function w2_reject_raw_statistics_retention_mutation()"
                )
            )


def _drop_raw_statistics_immutability_guards() -> None:
    dialect = op.get_bind().dialect.name
    for trigger in (
        "raw_statistics_no_update",
        "raw_statistics_no_delete",
        "raw_statistics_retention_no_update",
        "raw_statistics_retention_no_delete",
    ):
        table = (
            "raw_payload"
            if trigger.startswith("raw_statistics_no_")
            else "raw_statistics_retention"
        )
        if dialect == "postgresql":
            op.execute(sa.text(f"drop trigger if exists {trigger} on {table}"))
        elif dialect == "sqlite":
            op.execute(sa.text(f"drop trigger if exists {trigger}"))
    if dialect == "postgresql":
        op.execute(sa.text("drop function if exists w2_reject_raw_statistics_mutation()"))
        op.execute(sa.text("drop function if exists w2_reject_raw_statistics_retention_mutation()"))
