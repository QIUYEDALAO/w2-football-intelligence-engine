from __future__ import annotations

from w2.infrastructure import persistence as _persistence
from w2.infrastructure.database import Base


def test_stage11a_tables_are_registered() -> None:
    assert _persistence.OperationalAlertModel is not None
    expected_tables = {
        "operational_alert",
        "slo_evaluation",
        "backup_run",
        "restore_run",
        "security_audit_event",
    }
    assert expected_tables.issubset(Base.metadata.tables)
