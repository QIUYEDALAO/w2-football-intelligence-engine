from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "resolve_fence_uncertain.py"


def _load():
    spec = importlib.util.spec_from_file_location("resolve_fence_uncertain", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_build_updates_applies_only_actual_success() -> None:
    """实际成功行生成 UPDATE；实际失败行 skipped 不生成 UPDATE（fail-closed）。"""
    mod = _load()
    rows = [
        {
            "task_id": "t1",
            "stage": "task",
            "attempt": 1,
            "state": "SIDE_EFFECT_UNCERTAIN",
            "error": "UniqueViolation",
        },
        {
            "task_id": "t2",
            "stage": "task",
            "attempt": 1,
            "state": "SIDE_EFFECT_UNCERTAIN",
            "error": "SOME_UNKNOWN_ERROR",
        },
        {
            "task_id": "t3",
            "stage": "task",
            "attempt": 1,
            "state": "SIDE_EFFECT_UNCERTAIN",
            "error": None,
        },
    ]
    statements, records = mod.build_updates(rows, "tester")

    # 只有 t1（UniqueViolation）实际成功 → 1 条 UPDATE；APPLY_OK 用 len(statements) 计数。
    assert len(statements) == 1
    assert len(records) == 3
    skipped = [r for r in records if r.get("skipped")]
    assert len(skipped) == 2
    assert {r["task_id"] for r in skipped} == {"t2", "t3"}
    assert all(r["new_state"] == "SIDE_EFFECT_UNCERTAIN" for r in skipped)

    resolved = [r for r in records if not r.get("skipped")]
    assert [r["task_id"] for r in resolved] == ["t1"]
    assert resolved[0]["new_state"] == "RESOLVED"


def test_build_updates_no_skip_counts_all() -> None:
    """无实际失败时，statements == records（数字不变，无 skipped）。"""
    mod = _load()
    rows = [
        {
            "task_id": "t1",
            "stage": "task",
            "attempt": 1,
            "state": "SIDE_EFFECT_UNCERTAIN",
            "error": "UniqueViolation",
        },
        {
            "task_id": "t2",
            "stage": "task",
            "attempt": 1,
            "state": "SIDE_EFFECT_UNCERTAIN",
            "error": "STALE_ATTEMPTING_TIMEOUT",
        },
    ]
    statements, records = mod.build_updates(rows, "tester")
    assert len(statements) == 2
    assert len(records) == 2
    assert not any(r.get("skipped") for r in records)
