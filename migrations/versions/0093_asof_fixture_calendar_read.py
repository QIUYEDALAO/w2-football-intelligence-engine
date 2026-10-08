"""F1: AS-OF 读角色只读授权 matchday_fixture_identities 的赛程日历列（不含比分/raw）。

Revision ID: 0093_asof_fixture_calendar_read
Revises: 0092_t4_guard_direct_write
Create Date: 2026-10-08

F9 门「比赛日历最近 FT」对照基准从 canonical_team_match_history（xG 链自己的表，
断供时一起冻结导致假健康）改用 matchday_fixture_identities.fixture_status='FT'
（独立于 xG 采集）。该表对 quant_asof_reader_role 默认无授权（no privileges unless
granted），故此处按最小列级授权开放赛程日历列。

🔴 前瞻偏差防护：绝不授权 ``payload``（fixtures item 含 goals 比分）、
``raw_payload_sha256``、``identity_hash``、``endpoint_capture_id``。AS-OF 决策路径
只能读「何时开球 / 是否完赛 / 双方 w2 身份 / 采集时点」，绝不能读到比分或收盘价。
"""
from __future__ import annotations

from alembic import op

revision: str = "0093_asof_fixture_calendar_read"
down_revision: str | None = "0092_t4_guard_direct_write"
branch_labels: str | None = None
depends_on: str | None = None


def _postgres_only() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _postgres_only():
        return
    op.execute(
        """
        GRANT SELECT (fixture_id, provider_fixture_id, kickoff_utc, fixture_status,
                      home_w2_team_id, away_w2_team_id, captured_at)
          ON matchday_fixture_identities TO quant_asof_reader_role
        """
    )


def downgrade() -> None:
    if not _postgres_only():
        return
    op.execute(
        "REVOKE SELECT ON matchday_fixture_identities FROM quant_asof_reader_role"
    )
