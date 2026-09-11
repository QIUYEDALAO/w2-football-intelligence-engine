from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_xg_ingest_guard_alarms_only_on_numeric_raw_materialization_loss() -> None:
    source = (ROOT / "ops/host/w2-xg-ingest-guard").read_text(encoding="utf-8")

    assert "s->>'value' IS NOT NULL" in source
    assert "coalesce(p.rows,0)<>2" in source
    assert "coalesce(p.teams,0)<>2" in source
    assert "coalesce(p.null_rows,0)<>0" in source
    assert "psql -XqAt '-F|'" in source
    assert "BEGIN READ ONLY;" in source
    assert "XG_INGEST_ALARM" in source
    assert "request_live" not in source
    assert "INSERT" not in source.upper()
    assert "UPDATE" not in source.upper()
    assert "DELETE" not in source.upper()


def test_xg_ingest_guard_timer_is_hourly_and_not_deployed_by_test() -> None:
    timer = (ROOT / "ops/host/w2-xg-ingest-guard.timer").read_text(encoding="utf-8")

    assert "OnCalendar=*-*-* *:10:00 UTC" in timer
    assert "Persistent=true" in timer
