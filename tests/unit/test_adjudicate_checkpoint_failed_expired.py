from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "adjudicate_checkpoint_failed_expired.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("adjudicate_checkpoint_failed_expired", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_fetch_query_excludes_already_marked(monkeypatch) -> None:
    """D3 幂等：fetch 查询加 NOT LIKE '%EXPIRED_FIXTURE_FT%'，已标记行不再重复打标。"""
    mod = _load()
    captured: dict[str, str] = {}

    def fake_sql(query: str) -> str:
        captured["q"] = query
        return "[]"

    monkeypatch.setattr(mod, "sql", fake_sql)
    rows = mod.fetch_expired_failed()
    assert rows == []
    assert "NOT LIKE '%EXPIRED_FIXTURE_FT%'" in captured["q"]


def test_build_updates_empty_rows_no_statements() -> None:
    """D3 幂等：fetch 过滤后无行 → dry-run 0 可处置。"""
    mod = _load()
    statements, records = mod.build_updates([], "tester")
    assert statements == []
    assert records == []
