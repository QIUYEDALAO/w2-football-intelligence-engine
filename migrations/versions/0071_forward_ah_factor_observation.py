"""create forward_ah_factor_observations

Revision ID: 0071_forward_ah_factor_observation
Revises: 0070_notification_delivery_routing

Additive. A new table only: no existing table, column, index or constraint is
touched, so historical prematch attempt payloads keep their identity, their
hashes and their HISTORICAL_NO_FACTOR_VERDICT_IDENTITY semantics unchanged.

Every column that carries meaning is NOT NULL. A forward factor observation
whose version, capture identity, source version or evidence time is missing is
not a partially-complete row to be backfilled later -- it is a row that must
never have been written, so the database refuses it rather than accepting a
default.

Rollback is deliberately not an unconditional drop. Observations are
append-only business facts, and dropping a populated table would destroy them.
`downgrade` therefore drops the table only when it is empty, which is the state
this migration ships in (LIVE_CAPTURE_ENABLED is false, so nothing has been
captured). If rows exist, downgrade refuses and the documented path is the
forward-compatible one: disable the writer, leave the table and its rows in
place, and roll the application back without the schema. See
MIGRATION_AND_ROLLBACK.md in the F1R-B review package.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0071_forward_ah_factor_observation"
down_revision: str | None = "0070_notification_delivery_routing"
branch_labels: str | None = None
depends_on: str | None = None

_TABLE = "forward_ah_factor_observations"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("observation_id", sa.String(64), primary_key=True),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("record_kind", sa.String(64), nullable=False),
        sa.Column("batch_key", sa.String(255), nullable=False),
        sa.Column("evaluation_id", sa.String(128), nullable=False),
        sa.Column("attempt_id", sa.String(128), nullable=False),
        sa.Column("fixture_id", sa.String(128), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("factor_id", sa.String(64), nullable=False),
        sa.Column("factor_version", sa.String(128), nullable=False),
        sa.Column("factor_status", sa.String(48), nullable=False),
        sa.Column("participated", sa.Boolean(), nullable=False),
        sa.Column("applied_weight", sa.String(64), nullable=False),
        sa.Column("signed_score", sa.String(64), nullable=True),
        sa.Column("factor_inputs", sa.JSON(), nullable=False),
        sa.Column("evidence_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_capture_id", sa.String(255), nullable=False),
        sa.Column("source_capture_sha256", sa.String(64), nullable=False),
        sa.Column("source_version", sa.String(255), nullable=False),
        sa.Column("factor_input_hash", sa.String(64), nullable=False),
        sa.Column("factor_verdict_hash", sa.String(64), nullable=False),
        sa.Column(
            "supersedes_observation_id",
            sa.String(64),
            sa.ForeignKey(f"{_TABLE}.observation_id"),
            nullable=True,
        ),
        sa.Column("revision_reason", sa.String(255), nullable=True),
        sa.CheckConstraint(
            "factor_id in ('F3_REST_FITNESS', 'F5_RECENT_AH_COVER', "
            "'F6_H2H', 'F9_TRUE_XG')",
            name="ck_forward_ah_factor_observation_factor_id",
        ),
        sa.CheckConstraint(
            "market = 'ASIAN_HANDICAP'",
            name="ck_forward_ah_factor_observation_market",
        ),
        sa.CheckConstraint(
            "evidence_time_utc < evaluated_at_utc",
            name="ck_forward_ah_factor_observation_pit",
        ),
        # A scoreless status may not carry a number, and a participating factor
        # must. Absence is not zero and not neutral.
        sa.CheckConstraint(
            "(participated = true and signed_score is not null) or "
            "(participated = false and signed_score is null)",
            name="ck_forward_ah_factor_observation_score_presence",
        ),
        sa.CheckConstraint(
            "(participated = true) = (factor_status = 'PARTICIPATED')",
            name="ck_forward_ah_factor_observation_status_agrees",
        ),
        # A non-participating factor applied none of its declared weight.
        sa.CheckConstraint(
            "participated = true or applied_weight = '0'",
            name="ck_forward_ah_factor_observation_zero_weight_when_absent",
        ),
        sa.CheckConstraint(
            "(supersedes_observation_id is null) = (revision_reason is null)",
            name="ck_forward_ah_factor_observation_revision_pairing",
        ),
        sa.CheckConstraint(
            "supersedes_observation_id is null or "
            "supersedes_observation_id <> observation_id",
            name="ck_forward_ah_factor_observation_no_self_supersession",
        ),
    )
    # Partial, so a correction may append against the same attempt: only the
    # rows that supersede nothing are unique per factor.
    op.create_index(
        "uq_forward_ah_factor_observation_original_per_attempt",
        _TABLE,
        ["evaluation_id", "attempt_id", "fixture_id", "market", "factor_id",
         "evaluated_at_utc"],
        unique=True,
        postgresql_where=sa.text("supersedes_observation_id is null"),
        sqlite_where=sa.text("supersedes_observation_id is null"),
    )
    op.create_index(
        "ix_forward_ah_factor_observation_batch", _TABLE, ["batch_key"]
    )
    op.create_index(
        "ix_forward_ah_factor_observation_fixture",
        _TABLE,
        ["fixture_id", "evaluated_at_utc"],
    )
    op.create_index(
        "ix_forward_ah_factor_observation_supersedes",
        _TABLE,
        ["supersedes_observation_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        # Already absent: a repeated downgrade is a no-op, not a failure.
        return
    table = sa.table(_TABLE, sa.column("observation_id"))
    rows = bind.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
    if rows:
        raise RuntimeError(
            "FORWARD_AH_FACTOR_OBSERVATION_DOWNGRADE_WOULD_DESTROY_FACTS:"
            f"rows={rows}; use the forward-compatible disable path instead"
        )
    op.drop_index("ix_forward_ah_factor_observation_supersedes", table_name=_TABLE)
    op.drop_index(
        "uq_forward_ah_factor_observation_original_per_attempt", table_name=_TABLE
    )
    op.drop_index("ix_forward_ah_factor_observation_fixture", table_name=_TABLE)
    op.drop_index("ix_forward_ah_factor_observation_batch", table_name=_TABLE)
    op.drop_table(_TABLE)
