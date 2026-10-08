from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "adjudicate_fence_blocked_history.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("adjudicate_fence_blocked_history", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _row(task_id: str, blockers: list[str]) -> dict:
    return {
        "task_id": task_id,
        "stage": "task",
        "attempt": 1,
        "state": "DONE",
        "error": None,
        "updated_at": "2026-10-04T00:00:00Z",
        "stored_result_text": json.dumps(
            {
                "task_key": "checkpoint-refresh:brasileirao_serie_a:2026:abc",
                "status": "BLOCKED",
                "result": {"blockers": blockers},
            }
        ),
    }


def test_adjudicate_quota_protected_with_pass_evidence() -> None:
    mod = _load()
    pass_evidence = {"checkpoint-refresh:brasileirao_serie_a:2026": "2026-10-04T12:00:00Z"}
    verdict, apply = mod.adjudicate_row(
        _row("t1", ["PROVIDER_RESERVE_PROTECTED"]), pass_evidence, {}, set()
    )
    assert apply is True
    assert "额度保护" in verdict


def test_adjudicate_quota_protected_without_pass_evidence_skips() -> None:
    mod = _load()
    verdict, apply = mod.adjudicate_row(
        _row("t1", ["PROVIDER_RESERVE_PROTECTED"]), {}, {}, set()
    )
    assert apply is False  # 无后续 PASS 证据 → fail-closed


def test_adjudicate_claim_noise_applies() -> None:
    mod = _load()
    verdict, apply = mod.adjudicate_row(
        _row("t1", ["CHECKPOINT_CLAIM_TOKEN_MISMATCH"]), {}, {}, set()
    )
    assert apply is True
    assert "并发 claim" in verdict


def test_adjudicate_payload_missing_repaired_applies() -> None:
    mod = _load()
    fixture_status = {
        "api_football:1492390": [
            {"checkpoint": "T12_ODDS", "status": "CAPTURED", "scheduled_at": "2026-10-08T10:30:00Z"}
        ]
    }
    verdict, apply = mod.adjudicate_row(
        _row("t1", ["CHECKPOINT_FIXTURE_PAYLOAD_MISSING:1492390"]), {}, fixture_status, set()
    )
    assert apply is True
    assert "已修复" in verdict or "已过期" in verdict


def test_adjudicate_payload_missing_still_missing_skips() -> None:
    mod = _load()
    verdict, apply = mod.adjudicate_row(
        _row("t1", ["CHECKPOINT_FIXTURE_PAYLOAD_MISSING:1492390"]), {}, {}, set()
    )
    assert apply is False  # 仍缺且未完赛 → 不得处置（保持上浮）


def test_adjudicate_unknown_blocker_skips() -> None:
    mod = _load()
    verdict, apply = mod.adjudicate_row(_row("t1", ["ValueError"]), {}, {}, set())
    assert apply is False
    assert "未识别" in verdict


def test_build_updates_mixed_applies_and_skips() -> None:
    mod = _load()
    pass_evidence = {"checkpoint-refresh:brasileirao_serie_a:2026": "2026-10-04T12:00:00Z"}
    rows = [
        _row("t1", ["PROVIDER_RESERVE_PROTECTED"]),  # 可处置
        _row("t2", ["ValueError"]),  # skipped
        _row("t3", ["CHECKPOINT_CLAIM_TOKEN_MISMATCH"]),  # 可处置
    ]
    statements, records = mod.build_updates(
        rows, "tester", pass_evidence=pass_evidence, fixture_status={}, finished=set()
    )
    assert len(statements) == 2  # 只有 t1、t3 产出 UPDATE
    assert len(records) == 3
    skipped = [r for r in records if r.get("skipped")]
    assert [r["task_id"] for r in skipped] == ["t2"]
