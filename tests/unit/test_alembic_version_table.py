from __future__ import annotations

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

import w2.infrastructure.alembic_version  # noqa: F401
from w2.infrastructure.alembic_version import VERSION_NUM_LENGTH, W2PostgresqlImpl


def test_postgresql_alembic_version_table_uses_w2_width() -> None:
    context = MigrationContext.configure(dialect_name="postgresql")

    assert isinstance(context.impl, W2PostgresqlImpl)
    version_num = context._version.c.version_num
    assert getattr(version_num.type, "length", None) == VERSION_NUM_LENGTH
    assert version_num.nullable is False
    assert list(context._version.primary_key.columns) == [version_num]


def test_revision_ids_fit_w2_version_table_width() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    lengths = [len(revision.revision) for revision in script.walk_revisions()]

    assert lengths
    assert max(lengths) > 32
    assert max(lengths) <= VERSION_NUM_LENGTH


def test_env_no_longer_uses_ignored_version_table_kwargs() -> None:
    text = open("migrations/env.py", encoding="utf-8").read()

    assert "version_table_kwargs" not in text
