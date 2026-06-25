from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROADMAP = ROOT / "docs/W2_MASTER_ROADMAP.md"
STATUS = ROOT / "reports/W2_ROADMAP_STATUS.json"
HANDOFF = ROOT / "reports/W2_CURRENT_HANDOFF.md"


def test_master_roadmap_exists_and_lists_all_phases_and_gates() -> None:
    text = ROADMAP.read_text(encoding="utf-8")

    for index in range(16):
        assert f"阶段 {index}" in text
    for index in range(7):
        assert f"Gate {index}" in text


def test_master_roadmap_contains_boundary_and_data_flow_rules() -> None:
    text = ROADMAP.read_text(encoding="utf-8")

    required = [
        "W1 只负责历史参考",
        "W2 才是未来世界杯、五大联赛和其他一级联赛共用的生产系统",
        "RAW\n→ NORMALIZED\n→ FEATURE\n→ PREDICTION/STRATEGY",
        "实时盘口采集必须与其他任务并行立即开始",
        "Gate 3 之前禁止继续调模型",
        "Gate 4 之前禁止生成正式推荐",
        "Gate 5 之前禁止替换生产系统",
        "禁止把市场反解概率叫作独立推荐优势",
        "禁止用 closing odds 回测早期预测",
    ]
    for required_text in required:
        assert required_text in text


def test_handoff_references_roadmap_and_status_sources() -> None:
    text = HANDOFF.read_text(encoding="utf-8")

    assert "master_roadmap_path: docs/W2_MASTER_ROADMAP.md" in text
    assert "master_roadmap_version: 1" in text
    assert "roadmap_status_path: reports/W2_ROADMAP_STATUS.json" in text
    assert "execution_package_is_not_master_phase: true" in text
    assert "## 0.1 权威文件层级" in text


def test_roadmap_status_contains_complete_phase_and_gate_matrix() -> None:
    payload = json.loads(STATUS.read_text(encoding="utf-8"))

    assert payload["roadmap_version"] == 2
    assert set(payload["phases"]) == {str(index) for index in range(16)}
    assert set(payload["gates"]) == {str(index) for index in range(7)}
    for phase in payload["phases"].values():
        assert phase["status"] in {
            "NOT_STARTED",
            "PARTIAL",
            "IN_PROGRESS",
            "BLOCKED",
            "COMPLETE",
            "UNVERIFIED",
        }
        assert isinstance(phase["evidence"], list)
        assert isinstance(phase["blockers"], list)
        assert isinstance(phase["next_actions"], list)


def test_roadmap_status_preserves_gate_safety_boundaries() -> None:
    payload = json.loads(STATUS.read_text(encoding="utf-8"))

    assert payload["candidate"] is False
    assert payload["formal_recommendation"] is False
    assert payload["gates"]["0"]["status"] in {"PARTIAL", "UNVERIFIED"}
    assert payload["gates"]["4"]["status"] == "OPEN"
    assert payload["gates"]["5"]["status"] == "OPEN"
    assert payload["gates"]["6"]["status"] == "NOT_READY"
    assert "Stage7I-R1B2" in {
        item["name"] for item in payload["active_execution_packages"]
    }
