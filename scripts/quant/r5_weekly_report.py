"""Render a read-only weekly Markdown report from explicit, frozen JSON exports.

This command never opens a database or sends a notification. Missing evidence is
reported as such; it never becomes a zero or a successful gate.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _number(value: object) -> str:
    return (
        f"{value}"
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else "证据不足"
    )


def render_weekly_report(
    *,
    week: str,
    shadow: Mapping[str, Any],
    forward: Mapping[str, Any],
    drift: Mapping[str, Any],
) -> str:
    """Format supplied evidence; never infer missing counts or model decisions."""
    lines = [
        f"# W2 前向等待期周报 · {week}",
        "",
        "> 只读诊断；不构成前向验收、自动调参或生产切换依据。",
        "",
        "## Shadow 指标",
        "",
        "| 市场/轨道 | 样本 n | logloss | Brier | RPS | bias | 状态 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    metrics = shadow.get("metrics")
    if isinstance(metrics, Mapping) and metrics:
        for name, item in sorted(metrics.items()):
            row = item if isinstance(item, Mapping) else {}
            lines.append(
                f"| {name} | {_number(row.get('n'))} | {_number(row.get('logloss'))} | "
                f"{_number(row.get('brier'))} | {_number(row.get('rps'))} | "
                f"{_number(row.get('bias'))} | {row.get('status') or '证据不足'} |"
            )
    else:
        lines.append("| 证据不足 | — | — | — | — | — | 未提供 shadow 指标 |")
    lines += [
        "",
        "## 前向样本进度",
        "",
        f"- 当前模型身份：{forward.get('calibration_identity') or '证据不足'}",
        f"- 可证明 eligible：{_number(forward.get('eligible_count'))}",
        "- validation / test："
        f"{_number(forward.get('validation_count'))} / "
        f"{_number(forward.get('test_count'))}（各需 2500）",
        f"- 唯一 fixture：{_number(forward.get('fixture_count'))}",
        "",
        "## 排除计数",
        "",
    ]
    exclusions = forward.get("exclusions")
    if isinstance(exclusions, Mapping) and exclusions:
        lines += [f"- `{key}`：{_number(value)}" for key, value in sorted(exclusions.items())]
    else:
        lines.append("- 证据不足（未提供排除清单）")
    lines += ["", "## 漂移观测", ""]
    windows = drift.get("windows")
    if isinstance(windows, list) and windows:
        for item in windows:
            row = item if isinstance(item, Mapping) else {}
            lines.append(
                f"- {row.get('window_days', '?')} 天：n={_number(row.get('n'))}，"
                f"bias={_number(row.get('bias'))}，CUSUM={_number(row.get('cusum_zero_reference'))}，"
                f"{row.get('evidence') or '证据不足'}；仅提示人工复核"
            )
    else:
        lines.append("- 证据不足（未提供漂移窗口）")
    return "\n".join(lines) + "\n"


def _read(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week", required=True, help="ISO week label, e.g. 2026-W39")
    parser.add_argument("--shadow", required=True, type=Path)
    parser.add_argument("--forward", required=True, type=Path)
    parser.add_argument("--drift", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = render_weekly_report(
        week=args.week,
        shadow=_read(args.shadow),
        forward=_read(args.forward),
        drift=_read(args.drift),
    )
    args.output.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
