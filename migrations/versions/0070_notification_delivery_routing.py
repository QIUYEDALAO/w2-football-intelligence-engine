"""widen notification delivery status for routed events

Revision ID: 0070_notification_delivery_routing
Revises: 0069_outcome_ledger_run_state

Delivery routing writes DIGEST_PENDING, DIGESTED and SUPPRESSED so that an
event withheld from the phone stays inspectable in the outbox instead of
being dropped. The 0068 check constraint predates that and admits only the
four delivery states, so every routed row failed with a CheckViolation and
fell back to being pushed.
"""

from __future__ import annotations

from alembic import op

revision: str = "0070_notification_delivery_routing"
down_revision: str | None = "0069_outcome_ledger_run_state"
branch_labels: str | None = None
depends_on: str | None = None

_CONSTRAINT = "ck_candidate_notification_delivery_status"
_TABLE = "candidate_notification_outbox"
_OLD = "delivery_status in ('PENDING', 'RETRY_PENDING', 'DELIVERED', 'FAILED')"
_NEW = (
    "delivery_status in ('PENDING', 'RETRY_PENDING', 'DELIVERED', 'FAILED', "
    "'DIGEST_PENDING', 'DIGESTED', 'SUPPRESSED')"
)


def upgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_constraint(_CONSTRAINT, type_="check")
        batch.create_check_constraint(_CONSTRAINT, _NEW)


def downgrade() -> None:
    # Routed rows carry states the narrow constraint rejects; returning them to
    # PENDING is what the old shape means, and a re-routed row lands there again.
    op.execute(
        "UPDATE candidate_notification_outbox SET delivery_status = 'PENDING' "  # noqa: S608
        "WHERE delivery_status IN ('DIGEST_PENDING', 'DIGESTED', 'SUPPRESSED')"
    )
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_constraint(_CONSTRAINT, type_="check")
        batch.create_check_constraint(_CONSTRAINT, _OLD)
