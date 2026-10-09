"""D1（指令书，2026-10-10）：巡检报告体积治理 + 报告轮转 单测。

轮转逻辑住在**生成的 wrapper**里（`ops/host/w2-update-v3-monitor` 的 heredoc），
所以这里不重写一份实现来测——而是把生成器产出的真实正文取出来执行，防「实现了
但转义写坏」这一类只在生产才露馅的回归（本任务实施中已真实踩过一次）。
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MONITOR = ROOT / "ops" / "host" / "w2-v3-readonly-monitor.py"
WRAPPER_SRC = ROOT / "ops" / "host" / "w2-update-v3-monitor"

_ROTATE_RE = re.compile(r"^rotate_reports\(\).*?\n\}\n", re.S | re.M)


def _load_monitor():
    spec = importlib.util.spec_from_file_location("v3_monitor_trim", MONITOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


monitor = _load_monitor()


def _wrapper_text() -> str:
    """取出生成器里 wrapper 的正文，按生成时同样的规则还原转义（`\\$` → `$`）。"""
    src = WRAPPER_SRC.read_text(encoding="utf-8")
    match = re.search(r'cat > "\$temporary/wrapper" <<EOF\n(.*?)\nEOF\n', src, re.S)
    assert match is not None, "未能在生成器中定位 wrapper heredoc"
    return match.group(1).replace("\\$", "$")


def test_report_payload_keeps_judgement_fields_verbatim() -> None:
    """禁删字段：issues / 哨兵判定输入 / 状态结论 必须逐字保留。"""
    state = {
        "issues": ["AH_CHANNEL_UNREACHABLE:ah_rows=101:max_score=0.028881", "CHECKPOINT_FAILED"],
        "schema": "0093_asof_fixture_calendar_read",
        "real_event_status": "BLOCKED_PIPELINE",
        "ah_channel_today": [{"ah_rows": 101, "max_score": 0.0288812}],
        "pinnacle_compliant_coverage": [{"due_n": 24, "compliant_n": 0}],
        "provider_quota_live": {"remaining": 1234},
        "totals": list(range(50)),
    }
    payload = monitor.report_payload(state)

    assert payload["issues"] == state["issues"]
    assert payload["ah_channel_today"] == state["ah_channel_today"]
    assert payload["pinnacle_compliant_coverage"] == state["pinnacle_compliant_coverage"]
    assert payload["provider_quota_live"] == state["provider_quota_live"]
    assert payload["real_event_status"] == "BLOCKED_PIPELINE"
    # 未列入治理清单的列表：长度与顺序不变
    assert payload["totals"] == list(range(50))
    # 治理只作用于序列化视图：内存 state 未被改动
    assert "shown" not in state.get("totals", [])


def test_report_payload_caps_details_and_truncates_with_digest() -> None:
    """明细封顶 + 长文本截断，且截断保留 length/sha256（截断不等于丢证据）。"""
    blob = "x" * 5000
    state = {
        "commands": [
            {"command": f"c{i}", "exit": 0, "stdout": blob, "stderr": ""} for i in range(61)
        ],
        "decisions": [
            {"fixture_id": str(i), "fixture_identity": {"blob": blob}} for i in range(302)
        ],
    }
    payload = monitor.report_payload(state)

    assert payload["commands"]["shown"] == monitor.REPORT_MAX_DETAIL_ROWS
    assert payload["commands"]["total"] == 61
    assert payload["decisions"]["shown"] == monitor.REPORT_MAX_DETAIL_ROWS
    assert payload["decisions"]["total"] == 302

    stdout = payload["commands"]["rows"][0]["stdout"]
    assert stdout["truncated"] is True
    assert stdout["len"] == 5000
    assert len(stdout["sha256"]) == 64
    assert len(stdout["head"].encode("utf-8")) <= monitor.REPORT_MAX_CMD_OUTPUT_BYTES

    # 原 state 的列表未被截断（哨兵判定仍用全量）
    assert len(state["commands"]) == 61
    assert len(state["decisions"]) == 302


def test_report_payload_short_text_is_untouched() -> None:
    """未超限的字符串原样返回——不改变既有消费者看到的类型。"""
    payload = monitor.report_payload({"commands": [{"stdout": "short", "exit": 0}]})
    assert payload["commands"]["rows"][0]["stdout"] == "short"


def test_rotation_three_tier_boundaries(tmp_path: Path) -> None:
    """轮转三档：最近 48 份保留原文 / 48 份之后 7 天以内 gzip / 7 天以上删除。"""
    reports = tmp_path / "v3-monitor"
    reports.mkdir()
    body = _ROTATE_RE.search(_wrapper_text())
    assert body is not None, "生成的 wrapper 里未找到 rotate_reports"
    script = tmp_path / "rotate.sh"
    script.write_text(
        'set -uo pipefail\nreport_root="' + str(reports) + '"\n' + body.group(0)
        + "\nrotate_reports; echo ROTATE_RC=$?\n",
        encoding="utf-8",
    )

    now = time.time()
    for i in range(60):
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.localtime(now - i * 300))
        for suffix in (".json", ".stdout"):
            (reports / f"{stamp}-{i}{suffix}").write_text(
                "{}" if suffix == ".json" else "log", encoding="utf-8"
            )
        stamp_ts = now - i * 300
        os.utime(reports / f"{stamp}-{i}.json", (stamp_ts, stamp_ts))
    stale = reports / "20260101T000000Z-999.json"
    stale.write_text("{}", encoding="utf-8")
    old_ts = now - 8 * 86400
    os.utime(stale, (old_ts, old_ts))

    result = subprocess.run(["bash", str(script)], capture_output=True, text=True)
    assert "ROTATE_RC=0" in result.stdout, result.stderr
    assert not stale.exists(), "7 天以上必须删除"
    assert len(list(reports.glob("[0-9]*.json"))) == 48, "最近 48 份必须保留原文"
    assert len(list(reports.glob("[0-9]*.json.gz"))) == 12, "其余必须 gzip 归档"


def test_rotation_failure_does_not_abort_main_flow() -> None:
    """轮转失败不得阻断巡检主流程：契约层面的静态锁。

    生成的 wrapper 必须在**产出落盘并取到 result 之后**才轮转，且以
    `rotate_reports || ...` 形式吞掉失败；最终 `exit "$result"` 只反映巡检结论。
    """
    text = _wrapper_text()
    rotate_call = text.index("rotate_reports ||")
    exit_line = text.index('exit "$result"')
    result_line = text.index("result=$?")
    assert result_line < rotate_call < exit_line, "轮转必须晚于取 result、早于 exit"
    assert 'exit "$result"' in text
    # 轮转不得以任何形式改写 result
    rotate_segment = text[rotate_call:exit_line]
    assert "result=" not in rotate_segment
