from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROADMAP = ROOT / "docs/W2_MASTER_ROADMAP.md"


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
