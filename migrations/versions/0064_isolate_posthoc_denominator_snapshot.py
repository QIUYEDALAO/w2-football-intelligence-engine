"""isolate the post-hoc denominator snapshot from the official funnel

Revision ID: 0064_isolate_posthoc_denominator_snapshot
Revises: 0063_model_forecast_capture_policy_identity

The first denominator population was written by a single sweep -- 158 rows
stamped within roughly an hour, 86 of them inside four minutes -- so each row
holds the market state at scan time rather than at the checkpoint it claims.

Fixture 1494246 shows the damage plainly: it passed all six gates and evaluated
five times, yet its rows read "zero bookmakers, mainline parse failed", because
the sweep reached it nine minutes after kickoff when live odds had already
stopped.

The rows are kept -- they are a real record of a real scan -- but moved to their
own scope so no pass-rate can be computed from them by accident.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0064_isolate_posthoc_denominator_snapshot"
down_revision: str | None = "0063_model_forecast_capture_policy_identity"
branch_labels: str | None = None
depends_on: str | None = None

TABLE = "dynamic_prematch_evaluations"
SWEEP_SCOPE = "MODEL_FORECAST_CAPTURE_MARKET_V1"
LEGACY_SCOPE = "LEGACY_POSTHOC_DENOMINATOR_SNAPSHOT_V1"

_ISOLATE = sa.text(
    """
    UPDATE dynamic_prematch_evaluations
    SET denominator_scope = :legacy_scope
    WHERE denominator_scope = :sweep_scope
    """
).bindparams(legacy_scope=LEGACY_SCOPE, sweep_scope=SWEEP_SCOPE)

_RESTORE = sa.text(
    """
    UPDATE dynamic_prematch_evaluations
    SET denominator_scope = :sweep_scope
    WHERE denominator_scope = :legacy_scope
    """
).bindparams(legacy_scope=LEGACY_SCOPE, sweep_scope=SWEEP_SCOPE)


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("measurement_semantics", sa.String(64), nullable=True),
    )
    op.add_column(
        TABLE,
        sa.Column("official_funnel_eligible", sa.Boolean(), nullable=True),
    )
    op.add_column(TABLE, sa.Column("exclusion_reason", sa.String(128), nullable=True))
    op.add_column(TABLE, sa.Column("evaluation_policy_version", sa.String(64), nullable=True))
    op.add_column(TABLE, sa.Column("evaluation_slot_id", sa.String(64), nullable=True))

    # Mark before renaming the scope so no window exists where the rows look
    # official but carry no semantics.
    op.execute(
        sa.text(
            """
            UPDATE dynamic_prematch_evaluations
            SET measurement_semantics = 'POSTHOC_CURRENT_STATE_SNAPSHOT',
                official_funnel_eligible = false,
                exclusion_reason = 'NO_CHECKPOINT_TIME_BINDING'
            WHERE denominator_scope = :sweep_scope
            """
        ).bindparams(sweep_scope=SWEEP_SCOPE)
    )
    op.execute(_ISOLATE)


def downgrade() -> None:
    op.execute(_RESTORE)
    op.drop_column(TABLE, "evaluation_slot_id")
    op.drop_column(TABLE, "evaluation_policy_version")
    op.drop_column(TABLE, "exclusion_reason")
    op.drop_column(TABLE, "official_funnel_eligible")
    op.drop_column(TABLE, "measurement_semantics")
