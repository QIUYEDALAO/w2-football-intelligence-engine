from __future__ import annotations

from datetime import UTC, datetime

from scripts.audit_sc21_materialization_prerequisites import build_audit
from sqlalchemy import create_engine

from w2.infrastructure.database import Base


def test_empty_materialization_audit_fails_closed(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        "scripts.audit_sc21_materialization_prerequisites.create_engine",
        lambda: engine,
    )

    payload = build_audit(
        start=datetime(2026, 8, 14, tzinfo=UTC),
        end=datetime(2026, 8, 22, tzinfo=UTC),
    )

    assert payload["provider_calls"] == 0
    assert payload["database_writes"] == 0
    assert payload["rating"]["new_snapshot_candidate_count"] == 0
    assert payload["team_value"]["materialization_status"] == (
        "IDENTITY_OR_ROSTER_PREREQUISITES_MISSING"
    )
    assert payload["team_value"]["write_authorized"] is False
