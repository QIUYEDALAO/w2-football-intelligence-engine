from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import String

import w2.infrastructure.persistence  # noqa: F401
from w2.config import get_settings
from w2.infrastructure.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Alembic's default version_num is VARCHAR(32) but our revision IDs
# (e.g. "0003_create_stage4_ingestion_foundation") exceed 32 characters.
# Configure String(64) for the version table column to match our naming.
VERSION_TABLE_KW = {"version_num": String(64)}


def run_migrations_offline() -> None:
    url = get_settings().database_url.get_secret_value()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        version_table_kwargs=VERSION_TABLE_KW,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from w2.infrastructure.database import create_engine

    connectable = create_engine()
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_kwargs=VERSION_TABLE_KW,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
