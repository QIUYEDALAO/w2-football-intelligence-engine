from __future__ import annotations

from typing import Any

from alembic.ddl.postgresql import PostgresqlImpl
from sqlalchemy import Column, MetaData, PrimaryKeyConstraint, String, Table

VERSION_NUM_LENGTH = 64


def build_version_table(
    *,
    version_table: str,
    version_table_schema: str | None,
    version_table_pk: bool,
) -> Table:
    table = Table(
        version_table,
        MetaData(),
        Column("version_num", String(VERSION_NUM_LENGTH), nullable=False),
        schema=version_table_schema,
    )
    if version_table_pk:
        table.append_constraint(
            PrimaryKeyConstraint("version_num", name=f"{version_table}_pkc")
        )
    return table


class W2PostgresqlImpl(PostgresqlImpl):
    __dialect__ = "postgresql"

    def version_table_impl(
        self,
        *,
        version_table: str,
        version_table_schema: str | None,
        version_table_pk: bool,
        **kw: Any,
    ) -> Table:
        del kw
        return build_version_table(
            version_table=version_table,
            version_table_schema=version_table_schema,
            version_table_pk=version_table_pk,
        )
