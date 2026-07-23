from __future__ import annotations

import os
import tempfile
from pathlib import Path

from sqlalchemy import create_engine

from w2.competitions.seed import seed_competition_runtime_authority
from w2.infrastructure.database import Base
from w2.infrastructure.persistence import league_models  # noqa: F401


def pytest_configure() -> None:
    root = Path(tempfile.mkdtemp(prefix="w2-pytest-competition-db-"))
    database_url = f"sqlite+pysqlite:///{root / 'authority.db'}"
    os.environ["W2_DATABASE_URL"] = database_url
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    report = seed_competition_runtime_authority(
        engine,
        environment="test",
        updated_by="pytest-first-install-seed",
    )
    if report.conflicts:
        raise RuntimeError(";".join(report.conflicts))

    # Tests frequently swap W2_DATABASE_URL after collection. Ensure each isolated
    # test database receives the same first-install seed before Registry reads it.
    from w2.competitions import registry as registry_module

    production_create_engine = registry_module.create_engine

    def test_authority_engine():  # type: ignore[no-untyped-def]
        isolated_engine = production_create_engine()
        Base.metadata.create_all(isolated_engine)
        isolated_report = seed_competition_runtime_authority(
            isolated_engine,
            environment="test",
            updated_by="pytest-isolated-db-first-install-seed",
        )
        if isolated_report.conflicts:
            raise RuntimeError(";".join(isolated_report.conflicts))
        return isolated_engine

    registry_module.create_engine = test_authority_engine
