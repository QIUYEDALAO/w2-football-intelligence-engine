from __future__ import annotations

import w2.infrastructure.persistence  # noqa: F401
from w2.infrastructure.database import Base


def test_stage5_tables_are_registered() -> None:
    for table in [
        "dataset_sources",
        "dataset_versions",
        "dataset_artifacts",
        "label_references",
        "asof_samples",
        "data_quality_runs",
    ]:
        assert table in Base.metadata.tables
