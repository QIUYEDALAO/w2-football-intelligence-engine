"""create FootyStats shadow pilot bypass tables (指令书 I 任务 A)

Revision ID: 0094_footystats_shadow
Revises: 0093_asof_fixture_calendar_read

Additive. Five new tables only: ``fs_request_log``、``fs_raw_payload``、
``fs_league_season``、``fs_team``、``fs_fixture``。没有任何既有表、列、索引或
约束被触碰，因此生产 fixture / team 身份、既有 hash 与其历史语义全部不变。

为什么是旁路表而不是复用生产表：FootyStats 的 league-season id、球队 id、
比赛 id 都是**Provider 侧身份**，与 api_football 的 id 不是同一个域。把它们硬塞
进生产表就等于在生产身份域里引入第二套取值；``fs_fixture.matched_fixture_id``
指向既有生产 ``fixture_id``，未命中时留空，绝不另造一个 canonical fixture。

DDL 由 ``Base.metadata`` 生成（同 0015 的做法），表定义只有一份，
不存在「模型与迁移各写一遍」的漂移源。

``downgrade`` 不在有数据时无条件 drop：影子试点的原始 payload 是取证材料，
破坏它是数据丢失。有行时拒绝并给出可解释的失败，而不是静默清空。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

import w2.infrastructure.persistence  # noqa: F401
import w2.quant_research.footystats_shadow_models  # noqa: F401
from w2.infrastructure.database import Base

revision: str = "0094_footystats_shadow"
down_revision: str | None = "0093_asof_fixture_calendar_read"
branch_labels: str | None = None
depends_on: str | None = None

FOOTYSTATS_SHADOW_TABLES = {
    "fs_request_log",
    "fs_raw_payload",
    "fs_league_season",
    "fs_team",
    "fs_fixture",
}


def _selected() -> list[sa.Table]:
    return [
        table
        for table in Base.metadata.sorted_tables
        if table.name in FOOTYSTATS_SHADOW_TABLES
    ]


def upgrade() -> None:
    bind = op.get_bind()
    for table in _selected():
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    present = set(inspector.get_table_names())
    populated: dict[str, int] = {}
    for table in _selected():
        if table.name not in present:
            continue
        count = bind.execute(
            sa.select(sa.func.count()).select_from(sa.table(table.name))
        ).scalar_one()
        if count:
            populated[table.name] = int(count)
    if populated:
        raise RuntimeError(
            "FOOTYSTATS_SHADOW_DOWNGRADE_WOULD_DESTROY_CAPTURED_PAYLOADS:"
            f"{populated}; 影子试点数据是取证材料，请改用「停写 + 保留表」的前向兼容路径"
        )
    for table in reversed(_selected()):
        table.drop(bind=bind, checkfirst=True)
