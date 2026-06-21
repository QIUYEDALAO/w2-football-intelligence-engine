from __future__ import annotations

from w2.infrastructure import persistence as _persistence
from w2.infrastructure.database import Base


def test_stage12a_tables_are_registered() -> None:
    assert _persistence.MigrationSourceAssetModel is not None
    expected_tables = {
        "migration_source_asset",
        "migration_dry_run",
        "migration_validation_record",
        "migration_quarantine_record",
        "shadow_run",
        "shadow_comparison_record",
    }
    assert expected_tables.issubset(Base.metadata.tables)
