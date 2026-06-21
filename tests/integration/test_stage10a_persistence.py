from __future__ import annotations

from w2.infrastructure.database import Base


def test_stage10a_read_api_tables_registered() -> None:
    expected = {
        "api_request_audit",
        "read_model_checkpoint",
        "operational_metric_snapshot",
    }
    assert expected.issubset(Base.metadata.tables)
