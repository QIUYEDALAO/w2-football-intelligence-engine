"""指令书 G（2026-10-10）：xG 补采「零调用」的可观测性与空转治理。

G1 的根因定位被**日志本身**挡住了：`w2-xg-refresh` 只在 statistics!=0 时打印每联赛行
（`[ "$2" != "0" ] && echo "  $comp statistics=$2 rows=$3 blockers=$4"`），于是
「24 个窗口全部 statistics_calls=0」在日志里只剩 `rc=0`，真实 blocker
（`BACKFILL_QUOTA_GUARD`：当日 provider 剩余 771 < backfill_stop=int(7500×0.15)=1125）
完全不可见。同时 24 个联赛逐个空跑 ~55s（每个都要载入 6.4 万条 raw fixture），
即 E1 验收所指的「空烧」。

本文件用结构性断言钉死两条修法（ops 脚本无 python 入口，故按源码口径断言，
与 tests/unit/test_w2_release.py 的做法一致）。
"""

from __future__ import annotations

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "ops" / "host"
REFRESH = SCRIPTS / "w2-xg-refresh"
WINDOW = SCRIPTS / "w2-xg-backfill-window"


def test_refresh_always_prints_blockers_even_with_zero_calls() -> None:
    """零调用必须留痕：不得再用 `[ "$2" != "0" ] && echo` 把 blocker 吞掉。"""
    source = REFRESH.read_text(encoding="utf-8")

    assert '[ "$2" != "0" ] && echo "  $comp statistics=' not in source
    assert 'echo "  $comp statistics=$2 rows=$3 blockers=$4"' in source
    # 额度让位必须单列成机器可读 marker（上层据此提前结束窗口）
    assert "XG_REFRESH_QUOTA_GUARDED" in source
    for blocker in (
        "BACKFILL_QUOTA_GUARD",
        "QUOTA_BELOW_RESERVE",
        "QUOTA_CRITICAL_CORE_ONLY",
        "DAILY_QUOTA_EXHAUSTED",
    ):
        assert blocker in source, blocker


def test_refresh_distinguishes_quota_deferral_from_no_new_work() -> None:
    """「额度让位」与「无新可采」都表现为 calls=0，必须区分并可上报。"""
    source = REFRESH.read_text(encoding="utf-8")

    assert "XG_REFRESH_QUOTA_GUARDED_ALL" in source
    assert "XG_REFRESH_NO_CALLS" in source
    # 额度让位是按设计的正常让位，不是失败：保持 exit 0（不改变 systemd 单元语义）
    assert "exit 137" in source and "exit 2" in source  # 既有分档不被破坏
    assert "quota_guarded=${quota_guarded}" in source


def test_window_stops_early_on_quota_guard_instead_of_burning_all_competitions() -> None:
    """额度是当日累计口径 ⇒ 同一窗口内余下联赛必然同样被挡，必须提前结束（治空烧）。"""
    source = WINDOW.read_text(encoding="utf-8")

    assert "quota_guarded=0" in source
    assert "*XG_REFRESH_QUOTA_GUARDED*" in source
    assert "quota_guarded=1" in source
    assert "break" in source
    assert "quota_guarded=$quota_guarded" in source


def test_window_captures_refresh_output_to_inspect_marker() -> None:
    """marker 来自被调用脚本的 stdout ⇒ 执行器必须先捕获再透传，否则无法据以决策。"""
    source = WINDOW.read_text(encoding="utf-8")

    assert 'refresh_out="$(W2_XG_REFRESH_COMPETITIONS="$comp"' in source
    assert "printf '%s\\n' \"$refresh_out\"" in source
