from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from typing import Any, Literal
from zoneinfo import ZoneInfo

from w2.reporting.match_decision import MatchDecision, MatchDecisionState, decide_match

ReportFormat = Literal["markdown", "text", "html"]
ReportType = Literal["morning", "final"]

_BEIJING = ZoneInfo("Asia/Shanghai")
_FORBIDDEN_TERMS = (
    "命中率",
    "胜率",
    "ROI",
    "必中",
    "必胜",
    "稳赢",
    "稳赚",
    "可买",
    "方向未识别",
    "正式推荐字段不完整",
    "庄家开错",
    "照这个买",
    "跟庄",
)


@dataclass(frozen=True)
class ReportOptions:
    report_type: ReportType = "final"
    output_format: ReportFormat = "markdown"


def render_report(
    payload: dict[str, Any],
    *,
    report_type: ReportType = "final",
    output_format: ReportFormat = "markdown",
) -> str:
    options = ReportOptions(report_type=report_type, output_format=output_format)
    matches = [item for item in _list(payload.get("all")) if isinstance(item, dict)]
    decisions = [decide_match(match) for match in matches]
    formal_count = sum(1 for decision in decisions if decision.state == MatchDecisionState.FORMAL)
    state_counts = _state_counts(decisions)
    payload_as_of = _payload_as_of(payload)
    if output_format == "html":
        return _render_html_report(
            payload,
            matches=matches,
            decisions=decisions,
            formal_count=formal_count,
            state_counts=state_counts,
            options=options,
            payload_as_of=payload_as_of,
        )
    lines = [
        _report_title(payload, options),
        _report_subtitle(
            matches=matches,
            formal_count=formal_count,
            options=options,
            payload_as_of=payload_as_of,
        ),
        "",
        *_formal_decision_summary_lines(matches, decisions, payload_as_of=payload_as_of),
        "",
    ]
    for index, match in enumerate(matches):
        lines.extend(
            _render_match(
                match,
                decisions[index],
                options=options,
                payload_as_of=payload_as_of,
            )
        )
        lines.append("")
    text = "\n".join(lines).rstrip() + "\n"
    _assert_safe_report_text(text)
    return text


HTML_RENDERER_VERSION = "w2.html_dashboard.v5"

_TERMINAL_CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: #0a0e14; color: #c9d5e3; font-size: 12.5px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Microsoft YaHei", sans-serif; }
main { max-width: 1360px; margin: 0 auto; padding: 0 12px 28px; }
.ko, .n, .ao, .evt, .chip .n, .statusline { font-family: ui-monospace, SFMono-Regular,
  Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; }
.topbar { position: sticky; top: 0; z-index: 9; background: #0d1320;
  border-bottom: 1px solid #1b2534; margin: 0 -12px 6px; padding: 5px 12px 6px;
  display: flex; flex-direction: column; gap: 4px; }
.tb1 { display: flex; flex-wrap: wrap; gap: 3px 12px; align-items: baseline; }
h1 { margin: 0; font-size: 13.5px; font-weight: 600; color: #e8f0fa; }
.asof { color: #5d7290; font-size: 11px; }
.statusline { color: #5d7290; font-size: 11px; }
.tools { display: flex; gap: 5px; flex-wrap: wrap; align-items: center; }
.chip { border: 1px solid #243349; background: #111a29; color: #8ea4c0; border-radius: 3px;
  padding: 1px 8px; font-size: 11.5px; cursor: pointer; font-family: inherit; }
.chip.on { border-color: #2f6df6; color: #dce9ff; background: #14233f; }
.chip .n { color: #e8f0fa; font-weight: 600; margin-left: 4px; }
.chip.settled { border-color: #3d5a43; background: #101b16; cursor: default; }
.chip.settled .obs { color: #8da18f; margin-left: 5px; }
input[type=search], select { background: #0f1726; border: 1px solid #243349; color: #c9d5e3;
  border-radius: 3px; padding: 2px 7px; font-size: 11.5px; font-family: inherit; }
#cards { display: grid; gap: 0; border: 1px solid #141d2b; border-radius: 3px;
  overflow: hidden; }
.g { display: grid; gap: 8px; align-items: baseline; min-width: 0;
  grid-template-columns: 72px 44px minmax(190px, 1.2fr) 66px minmax(150px, 1fr)
    60px 60px 36px 64px 46px; }
.hdr { padding: 4px 10px; background: #0d1320; border-bottom: 1px solid #1b2534;
  color: #44546b; font-size: 10.5px; }
.hdr span { white-space: nowrap; overflow: hidden; }
.match-card { border-left: 3px solid #2a3548; background: #0e1522; padding: 3px 10px;
  min-width: 0; }
.match-card:nth-child(odd) { background: #0c121c; }
.ko { color: #8ea4c0; font-size: 11.5px; white-space: nowrap; }
.lg { color: #5d7290; font-size: 11px; white-space: nowrap; overflow: hidden; }
.tm { color: #dce6f2; font-weight: 600; font-size: 12.5px; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
.rs { color: #64788f; font-size: 11px; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
.pt { color: #64788f; font-size: 11px; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }
.ao { color: #44546b; font-size: 10.5px; white-space: nowrap; text-align: right; }
.n { color: #aebfd4; font-size: 11.5px; white-space: nowrap; text-align: right; }
.dq { color: #e2b04a; font-size: 10.5px; margin-left: 6px; }
.ah-review { display: inline-block; margin-left: 3px; color: #e2b04a;
  font-size: 10px; vertical-align: 1px; }
.badge { display: inline-block; font-size: 10.5px; font-weight: 500; border-radius: 2px;
  padding: 0 6px; justify-self: start; }
.b-formal { background: #123726; color: #43e59a; }
.b-watch { background: #182234; color: #8ea4c0; }
.b-data_insufficient { background: #33270f; color: #e2b04a; }
.b-market_not_ready { background: #331616; color: #e57373; }
.b-locked { background: #221c3d; color: #a89bf0; }
.match-card.formal { border-left-color: #22c07e; background: #0d1a17; padding: 5px 10px; }
.match-card.formal:nth-child(odd) { background: #0d1a17; }
.match-card.formal .tm { color: #eafff5; }
.rec { margin: 2px 0 0; display: flex; gap: 12px; align-items: baseline; min-width: 0;
  overflow: hidden; }
.rt { color: #43e59a; font-size: 13px; font-weight: 600; white-space: nowrap; }
.evt { color: #43e59a; font-size: 12px; font-weight: 600; white-space: nowrap; }
.rx { color: #7fa895; font-size: 11px; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; flex: 1; min-width: 0; }
.match-card.locked { border-left-color: #8a7bf7; }
.match-card.data_insufficient { border-left-color: #d9a13c; }
.match-card.market_not_ready { border-left-color: #d95c5c; }
.empty { color: #5d7290; border: 1px dashed #243349; border-radius: 3px; padding: 14px;
  text-align: center; }
details.debug { border: 1px solid #141d2b; border-radius: 3px; background: #0d1320;
  margin: 8px 0; }
details.debug summary { cursor: pointer; padding: 6px 10px; color: #8ea4c0;
  font-size: 11.5px; }
.decision-section h2 { margin: 0; padding: 8px 10px 3px; font-size: 12.5px; color: #dce6f2; }
.decision-section p { margin: 0; padding: 0 10px 8px; color: #5d7290; font-size: 11.5px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 11.5px;
  font-variant-numeric: tabular-nums; }
th, td { padding: 4px 7px; border-top: 1px solid #17202f; text-align: left;
  vertical-align: top; line-height: 1.4; }
th { color: #5d7290; background: #0d1320; white-space: nowrap; font-weight: 500; }
footer { margin-top: 16px; color: #4d6076; font-size: 10.5px; line-height: 1.6;
  border-top: 1px solid #17202f; padding-top: 8px; }
.hide { display: none; }
@media (max-width: 900px) {
  .g { grid-template-columns: 64px minmax(0, 1.4fr) 60px minmax(0, 1fr) 52px 36px; }
  .lg, .pt, .ao, .n-market, .hdr .h-lg, .hdr .h-pt, .hdr .h-ao, .hdr .h-market {
    display: none; }
}
"""

_TERMINAL_JS = """
(function () {
  var cards = [].slice.call(document.querySelectorAll(".match-card"));
  var grid = document.getElementById("cards");
  var chips = [].slice.call(document.querySelectorAll(".chip[data-state]"));
  var q = document.getElementById("q");
  var lg = document.getElementById("lg");
  var srt = document.getElementById("srt");
  var stateFilter = "ALL";
  function num(card, key) {
    var value = parseFloat(card.getAttribute(key));
    return isNaN(value) ? null : value;
  }
  function apply() {
    var term = q && q.value ? q.value.toLowerCase() : "";
    var league = lg && lg.value ? lg.value : "";
    cards.forEach(function (card) {
      var okState = stateFilter === "ALL" || card.getAttribute("data-state") === stateFilter;
      var okLeague = !league || card.getAttribute("data-league") === league;
      var okTerm = !term || (card.getAttribute("data-teams") || "").indexOf(term) >= 0;
      card.classList.toggle("hide", !(okState && okLeague && okTerm));
    });
  }
  function resort() {
    if (!grid || !srt) { return; }
    var mode = srt.value;
    var sorted = cards.slice().sort(function (a, b) {
      var fa = a.getAttribute("data-state") === "FORMAL" ? 0 : 1;
      var fb = b.getAttribute("data-state") === "FORMAL" ? 0 : 1;
      if (mode === "ko") {
        return (a.getAttribute("data-ko") || "").localeCompare(b.getAttribute("data-ko") || "");
      }
      if (mode === "edge") {
        return Math.abs(num(b, "data-edge") || 0) - Math.abs(num(a, "data-edge") || 0);
      }
      if (fa !== fb) { return fa - fb; }
      var ea = num(a, "data-ev");
      var eb = num(b, "data-ev");
      if (ea === null && eb === null) {
        return (a.getAttribute("data-ko") || "").localeCompare(b.getAttribute("data-ko") || "");
      }
      return (eb === null ? -1 : eb) - (ea === null ? -1 : ea);
    });
    sorted.forEach(function (card) { grid.appendChild(card); });
  }
  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      stateFilter = chip.getAttribute("data-state");
      chips.forEach(function (other) { other.classList.toggle("on", other === chip); });
      apply();
    });
  });
  if (q) { q.addEventListener("input", apply); }
  if (lg) { lg.addEventListener("change", apply); }
  if (srt) { srt.addEventListener("change", resort); }
})();
"""

_STATE_CHIP_LABELS: tuple[tuple[MatchDecisionState, str], ...] = (
    (MatchDecisionState.FORMAL, "正式"),
    (MatchDecisionState.WATCH, "观察"),
    (MatchDecisionState.DATA_INSUFFICIENT, "数据不足"),
    (MatchDecisionState.MARKET_NOT_READY, "盘口未就绪"),
    (MatchDecisionState.LOCKED, "已锁定"),
)
_SETTLEMENT_OBSERVING_SAMPLE_TARGET = 30


def _render_html_report(
    payload: dict[str, Any],
    *,
    matches: list[dict[str, Any]],
    decisions: list[MatchDecision],
    formal_count: int,
    state_counts: dict[MatchDecisionState, int],
    options: ReportOptions,
    payload_as_of: str,
) -> str:
    def _order_key(item: tuple[int, tuple[dict[str, Any], MatchDecision]]) -> tuple[Any, ...]:
        index, (match, decision) = item
        if decision.state == MatchDecisionState.FORMAL:
            ev = _number(_dict(match.get("recommendation")).get("expected_value"))
            return (0, -(ev if ev is not None else 0.0), index)
        return (1, 0.0, index)

    ordered = sorted(enumerate(zip(matches, decisions, strict=True)), key=_order_key)
    text_options = ReportOptions(report_type=options.report_type, output_format="text")
    cards = [
        _html_match_card(
            match,
            decision,
            text_options=text_options,
            payload_as_of=payload_as_of,
        )
        for _, (match, decision) in ordered
    ]
    header_row = (
        '<div class="g hdr">'
        "<span>时间</span>"
        '<span class="h-lg">联赛</span>'
        "<span>对阵</span>"
        "<span>状态</span>"
        "<span>原因</span>"
        '<span class="h-market" style="text-align:right">盘</span>'
        '<span style="text-align:right">差</span>'
        '<span style="text-align:right">ISC</span>'
        '<span class="h-pt">走势·参照</span>'
        '<span class="h-ao" style="text-align:right">as-of</span>'
        "</div>"
    )
    cards_html = (
        header_row + "".join(cards) if cards else '<p class="empty">本足球日无场次。</p>'
    )
    leagues: list[str] = []
    for match in matches:
        name = _competition(match)
        if name not in leagues:
            leagues.append(name)
    league_options = "".join(
        f'<option value="{escape(name)}">{escape(name)}</option>' for name in leagues
    )
    title = _report_title(payload, ReportOptions(options.report_type, "text"))
    subtitle = _report_subtitle(
        matches=matches,
        formal_count=formal_count,
        options=options,
        payload_as_of=payload_as_of,
    )
    state_summary = _html_state_summary(state_counts)
    state_chips = "".join(
        f'<button class="chip" data-state="{state.value}">'
        f'{label}<span class="n">{state_counts[state]}</span></button>'
        for state, label in _STATE_CHIP_LABELS
    )
    settled_rows = _settled_recommendation_rows(payload)
    settlement_tile = (
        '<span class="chip settled" title="观察中口径，只读 settlement_history 与 lock 快照">'
        f'已结算<span class="obs">观察中</span>'
        f'<span class="n">{len(settled_rows)}/{_SETTLEMENT_OBSERVING_SAMPLE_TARGET}</span>'
        "</span>"
    )
    formal_table = _html_formal_recommendation_table(
        matches,
        decisions,
        payload_as_of=payload_as_of,
    )
    non_formal_table = _html_non_formal_decision_table(matches, decisions)
    settled_table = _html_settled_recommendation_table(settled_rows)
    generated = _time_label(payload_as_of)
    data_profile = str(payload.get("data_profile") or "")
    profile_suffix = f" · data_profile {escape(data_profile)}" if data_profile else ""
    html = (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta name="w2-renderer" content="{HTML_RENDERER_VERSION}">\n'
        f"<title>{escape(title)}</title>\n"
        f"<style>{_TERMINAL_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        "<main>\n"
        '<div class="topbar">'
        '<div class="tb1">'
        f"<h1>{escape(title)}</h1>"
        f'<span class="asof">{escape(subtitle)}</span>'
        f'<span class="statusline">{escape(state_summary)}{profile_suffix}</span>'
        "</div>"
        '<div class="tools">'
        '<button class="chip on" data-state="ALL">全部</button>'
        f"{state_chips}"
        f"{settlement_tile}"
        '<input type="search" id="q" placeholder="搜索球队">'
        f'<select id="lg"><option value="">全部联赛</option>{league_options}</select>'
        '<select id="srt">'
        '<option value="smart">正式优先 · EV 降序</option>'
        '<option value="ko">开球时间</option>'
        '<option value="edge">差距绝对值</option>'
        "</select>"
        "</div>"
        "</div>\n"
        f'<section id="cards">{cards_html}</section>\n'
        '<details class="debug"><summary>正式推荐表（审计明细）</summary>'
        f"{formal_table}</details>\n"
        '<details class="debug"><summary>非 FORMAL 判定表（blocker 解释）</summary>'
        f"{non_formal_table}</details>\n"
        '<details class="debug"><summary>已结算推荐（观察中）</summary>'
        f"{settled_table}</details>\n"
        "<footer>"
        f"生成时间：{escape(generated)} · 只读报告 · 数据来自 dashboard payload · "
        f"renderer {HTML_RENDERER_VERSION}<br>"
        "盘口走势仅作参照、未验证，不构成方向；"
        "非 FORMAL 场次不显示推荐方向与比分参考；"
        "已结算区为观察中事实表。"
        "</footer>\n"
        "</main>\n"
        f"<script>{_TERMINAL_JS}</script>\n"
        "</body>\n"
        "</html>\n"
    )
    _assert_safe_report_text(html)
    return html


def _html_match_card(
    match: dict[str, Any],
    decision: MatchDecision,
    *,
    text_options: ReportOptions,
    payload_as_of: str,
) -> str:
    lines = _render_match(match, decision, options=text_options, payload_as_of=payload_as_of)
    state_class = decision.state.value.lower()
    shadow = _dict(match.get("pricing_shadow"))
    recommendation = _dict(match.get("recommendation"))
    is_formal = decision.state == MatchDecisionState.FORMAL
    ev = _number(recommendation.get("expected_value")) if is_formal else None
    edge = _number(shadow.get("edge_ah"))
    ev_attr = "" if ev is None else f"{ev:.6f}"
    edge_attr = "" if edge is None else f"{edge:.4f}"
    attrs = (
        f' data-state="{escape(decision.state.value)}"'
        f' data-league="{escape(_competition(match))}"'
        f' data-teams="{escape(_teams(match).lower())}"'
        f' data-ev="{ev_attr}"'
        f' data-edge="{edge_attr}"'
        f' data-ko="{escape(str(match.get("kickoff_utc") or ""))}"'
    )
    status_line = lines[1]
    rec_line: str | None = None
    core_parts: list[str] = []
    meta_parts: list[str] = []
    for line in lines[2:]:
        if line.startswith("推荐："):
            rec_line = line
        elif line.startswith(("我们的盘", "推荐比分")):
            core_parts.append(line)
        else:
            meta_parts.append(line)
    tooltip = escape(" ｜ ".join([status_line, *meta_parts]))
    market_cell = _market_display_cell(match)
    edge_cell = _edge_display_cell(match)
    signal_count = shadow.get("independent_signal_count")
    isc_cell = escape(str(signal_count)) if signal_count is not None else "—"
    timeline = _dict(match.get("market_timeline"))
    pattern_cell = (
        escape(_pattern_label(str(timeline.get("pattern") or "INSUFFICIENT")))
        if timeline
        else "—"
    )
    as_of_cell = escape(_as_of(match, payload_as_of=payload_as_of)[-5:])
    reason = escape(_reason_cn(decision.reason))
    flag = _data_quality_flag(match)
    row = (
        '<div class="g">'
        f'<span class="ko">{escape(_kickoff_label(match))}</span>'
        f'<span class="lg">{escape(_competition(match))}</span>'
        f'<span class="tm">{escape(_teams(match))}</span>'
        f'<span class="badge b-{state_class}">{escape(decision.label_cn)}</span>'
        f'<span class="rs">{reason}{flag}</span>'
        f'<span class="n n-market">{market_cell}</span>'
        f'<span class="n">{edge_cell}</span>'
        f'<span class="n">{isc_cell}</span>'
        f'<span class="pt">{pattern_cell}</span>'
        f'<span class="ao">{as_of_cell}</span>'
        "</div>"
    )
    parts = [row]
    if is_formal and rec_line is not None:
        ev_tag = f'<span class="evt">EV {ev * 100:+.1f}%</span>' if ev is not None else ""
        core_text = (
            f'<span class="rx">{escape(" ｜ ".join(core_parts))}</span>' if core_parts else ""
        )
        parts.append(
            f'<p class="rec"><span class="rt">{escape(rec_line)}</span>{ev_tag}{core_text}</p>'
        )
    return (
        f'<article class="match-card {state_class}"{attrs} title="{tooltip}">'
        f'{"".join(parts)}</article>'
    )


def _number_cell(value: Any, *, signed: bool = False) -> str:
    numeric = _number(value)
    if numeric is None:
        return "—"
    return escape(_signed_line(numeric) if signed else _line_value(numeric))


def _market_ready_for_display(match: dict[str, Any]) -> bool:
    return not _has_stale_mainline_diagnostic(match)


def _has_stale_mainline_diagnostic(match: dict[str, Any]) -> bool:
    shadow = _dict(match.get("pricing_shadow"))
    stale = "AH_MAINLINE_STALE_MATERIALIZATION"
    blockers = [
        shadow.get("mainline_materialization_blocker"),
        shadow.get("canonical_ah_market_blocker"),
        *list(_list(shadow.get("formal_blockers"))),
    ]
    canonical = _dict(shadow.get("canonical_ah_market"))
    blockers.append(canonical.get("blocker"))
    return stale in {str(item) for item in blockers if item}


def _market_display_cell(match: dict[str, Any]) -> str:
    shadow = _dict(match.get("pricing_shadow"))
    cell = _number_cell(shadow.get("market_ah"))
    if cell != "—" and _has_stale_mainline_diagnostic(match):
        cell += '<span class="ah-review" title="主线待复核">!</span>'
    return cell


def _edge_display_cell(match: dict[str, Any]) -> str:
    shadow = _dict(match.get("pricing_shadow"))
    return _number_cell(shadow.get("edge_ah"), signed=True)


def _data_quality_flag(match: dict[str, Any]) -> str:
    refresh = _dict(match.get("data_refresh"))
    statuses = (
        refresh.get("odds_status"),
        refresh.get("lineups_status"),
        refresh.get("xg_status"),
    )
    if all(str(status or "") == "READY" for status in statuses):
        return ""
    return '<span class="dq">数据未齐</span>'


def _state_counts(decisions: list[MatchDecision]) -> dict[MatchDecisionState, int]:
    return {
        state: sum(1 for decision in decisions if decision.state == state)
        for state in MatchDecisionState
    }


def _html_state_summary(state_counts: dict[MatchDecisionState, int]) -> str:
    return (
        f"场次 {sum(state_counts.values())} · "
        f"正式 {state_counts[MatchDecisionState.FORMAL]} · "
        f"观察 {state_counts[MatchDecisionState.WATCH]} · "
        f"数据不足 {state_counts[MatchDecisionState.DATA_INSUFFICIENT]} · "
        f"盘口未就绪 {state_counts[MatchDecisionState.MARKET_NOT_READY]} · "
        f"已锁定 {state_counts[MatchDecisionState.LOCKED]}"
    )


def _formal_decision_summary_lines(
    matches: list[dict[str, Any]],
    decisions: list[MatchDecision],
    *,
    payload_as_of: str,
) -> list[str]:
    formal_count = sum(1 for decision in decisions if decision.state == MatchDecisionState.FORMAL)
    lock_eligible = sum(
        1
        for match, decision in zip(matches, decisions, strict=True)
        if decision.state == MatchDecisionState.FORMAL
        and _recommendation_id(match)
        and _kickoff_after_as_of(match, payload_as_of)
    )
    blocker_counts = _blocker_counts(matches, decisions)
    blocker_text = "无" if not blocker_counts else " · ".join(
        f"{code}={count}" for code, count in sorted(blocker_counts.items())
    )
    return [
        "正式推荐判定摘要：",
        f"- 今日正式推荐数量：{formal_count}",
        f"- lock eligible 数量：{lock_eligible}",
        f"- 主要 blocker 统计：{blocker_text}",
    ]


def _html_formal_recommendation_table(
    matches: list[dict[str, Any]],
    decisions: list[MatchDecision],
    *,
    payload_as_of: str,
) -> str:
    rows = [
        _formal_table_row(match, payload_as_of=payload_as_of)
        for match, decision in zip(matches, decisions, strict=True)
        if decision.state == MatchDecisionState.FORMAL
    ]
    lock_eligible_count = sum(1 for row in rows if row[-1] == "true")
    if not rows:
        return (
            '<section class="decision-section">'
            "<h2>正式推荐表</h2>"
            "<p>今日正式推荐：0</p>"
            "<p>当前无 FORMAL + recommendation_id + future kickoff</p>"
            "</section>"
        )
    headers = (
        "fixture_id",
        "kickoff",
        "match",
        "market",
        "selection",
        "line",
        "odds",
        "expected_value / risk_adjusted_ev",
        "ev_se",
        "recommendation_id",
        "lock_eligible",
    )
    return (
        '<section class="decision-section">'
        "<h2>正式推荐表</h2>"
        f"<p>今日正式推荐：{len(rows)} · lock eligible：{lock_eligible_count}</p>"
        f'<div class="table-wrap">{_html_table(headers, rows)}</div>'
        "</section>"
    )


def _html_non_formal_decision_table(
    matches: list[dict[str, Any]],
    decisions: list[MatchDecision],
) -> str:
    rows = [
        _non_formal_table_row(match, decision)
        for match, decision in zip(matches, decisions, strict=True)
        if decision.state != MatchDecisionState.FORMAL
    ]
    if not rows:
        return (
            '<section class="decision-section">'
            "<h2>非 FORMAL 判定表</h2>"
            "<p>无非 FORMAL 场次。</p>"
            "</section>"
        )
    headers = (
        "fixture_id",
        "match",
        "current_state",
        "recommendation.tier",
        "formal_recommendation",
        "recommendation_id / id",
        "market",
        "selection",
        "line",
        "odds",
        "fair_ah",
        "market_ah",
        "edge_ah",
        "expected_value / risk_adjusted_ev",
        "ev_se",
        "pricing_shadow.formal_blockers",
        "analysis_readiness.blockers",
        "independent_signal_count",
        "missing_independent_sources",
        "blocker_codes",
        "explanation_cn",
    )
    return (
        '<section class="decision-section">'
        "<h2>非 FORMAL 判定表</h2>"
        f"<p>非 FORMAL 场次：{len(rows)}</p>"
        f'<div class="table-wrap">{_html_table(headers, rows)}</div>'
        "</section>"
    )


def _html_settled_recommendation_table(rows: list[dict[str, str]]) -> str:
    count_text = f"观察中 {len(rows)}/{_SETTLEMENT_OBSERVING_SAMPLE_TARGET}"
    if not rows:
        return (
            '<section class="decision-section">'
            "<h2>已结算推荐</h2>"
            f"<p>已结算推荐：{count_text}</p>"
            "</section>"
        )
    headers = (
        "fixture_id",
        "kickoff",
        "match",
        "recommendation_id",
        "lock_id",
        "market",
        "selection",
        "line",
        "odds",
        "closing_odds",
        "CLV",
        "result",
        "settlement_status",
        "settled_at",
        "source",
    )
    table_rows = [tuple(row.get(header, "") for header in headers) for row in rows]
    return (
        '<section class="decision-section">'
        "<h2>已结算推荐</h2>"
        f"<p>已结算推荐：{count_text}</p>"
        f'<div class="table-wrap">{_html_table(headers, table_rows)}</div>'
        "</section>"
    )


def _settled_recommendation_rows(payload: dict[str, Any]) -> list[dict[str, str]]:
    settlements = _audit_table_rows(payload, "settlement_history")
    locks = _audit_table_rows(payload, "locked_recommendation_snapshots")
    locks_by_lock_id = {
        str(lock.get("lock_id")): lock
        for lock in locks
        if lock.get("lock_id") not in {None, ""}
    }
    locks_by_recommendation_id = {
        str(lock.get("recommendation_id")): lock
        for lock in locks
        if lock.get("recommendation_id") not in {None, ""}
    }
    locks_by_fixture_id = {
        str(lock.get("fixture_id")): lock
        for lock in locks
        if lock.get("fixture_id") not in {None, ""}
    }
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for settlement in settlements:
        fixture_id = _text(settlement.get("fixture_id"))
        recommendation_id = _text(settlement.get("recommendation_id"))
        lock_id = _text(settlement.get("lock_id"))
        key = (
            _text(settlement.get("settlement_id")),
            lock_id,
            recommendation_id,
            _text(settlement.get("settled_at")),
        )
        if key in seen:
            continue
        seen.add(key)
        lock = (
            locks_by_lock_id.get(lock_id)
            or locks_by_recommendation_id.get(recommendation_id)
            or locks_by_fixture_id.get(fixture_id)
            or {}
        )
        snapshot = _json_dict(lock.get("snapshot_payload_json"))
        raw_settlement = _json_dict(settlement.get("raw_settlement_json"))
        recommendation = _dict(snapshot.get("recommendation"))
        locked_odds = _first_present(
            lock,
            recommendation,
            "recommendation_odds",
            "odds",
        )
        closing_odds = _first_present(
            settlement,
            raw_settlement,
            "closing_odds",
            "closing_decimal_odds",
            "closing_price",
        )
        clv = _first_present(settlement, raw_settlement, "clv", "clv_decimal")
        rows.append(
            {
                "fixture_id": _text(
                    fixture_id or lock.get("fixture_id") or snapshot.get("fixture_id")
                ),
                "kickoff": _time_label(
                    lock.get("kickoff_utc")
                    or snapshot.get("kickoff_utc")
                    or settlement.get("kickoff_utc")
                ),
                "match": _settled_match_label(settlement, lock, snapshot),
                "recommendation_id": _text(recommendation_id or lock.get("recommendation_id")),
                "lock_id": _text(lock_id or lock.get("lock_id")),
                "market": _text(
                    _first_present(
                        lock,
                        recommendation,
                        "recommendation_market",
                        "market",
                    )
                ),
                "selection": _text(
                    _first_present(
                        lock,
                        recommendation,
                        "recommendation_selection",
                        "selection",
                    )
                ),
                "line": _format_optional_number(
                    _first_present(lock, recommendation, "recommendation_line", "line")
                ),
                "odds": _format_optional_number(locked_odds, digits=2),
                "closing_odds": _format_optional_number(closing_odds, digits=2),
                "CLV": _clv_text(clv, locked_odds=locked_odds, closing_odds=closing_odds),
                "result": _text(settlement.get("result") or raw_settlement.get("result")),
                "settlement_status": _text(
                    settlement.get("status")
                    or settlement.get("outcome")
                    or raw_settlement.get("status")
                    or raw_settlement.get("outcome")
                ),
                "settled_at": _time_label(
                    settlement.get("settled_at") or raw_settlement.get("settled_at")
                ),
                "source": _text(settlement.get("source")),
            }
        )
    return rows


def _audit_table_rows(payload: dict[str, Any], table_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    candidates: list[Any] = [
        payload.get(table_name),
        _dict(payload.get("audit_tables")).get(table_name),
        _dict(payload.get("tables")).get(table_name),
        _dict(payload.get("audit_export")).get(table_name),
        _dict(_dict(payload.get("audit_export")).get("tables")).get(table_name),
    ]
    for candidate in candidates:
        for row in _list(candidate):
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _first_present(
    primary: dict[str, Any],
    secondary: dict[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        if key in primary and primary.get(key) not in {None, ""}:
            return primary.get(key)
        if key in secondary and secondary.get(key) not in {None, ""}:
            return secondary.get(key)
    return None


def _settled_match_label(
    settlement: dict[str, Any],
    lock: dict[str, Any],
    snapshot: dict[str, Any],
) -> str:
    for value in (settlement.get("teams"), lock.get("teams"), snapshot.get("teams")):
        if isinstance(value, str) and value.strip():
            return value
    home = snapshot.get("home_team_name") or lock.get("home_team_name")
    away = snapshot.get("away_team_name") or lock.get("away_team_name")
    if home or away:
        return f"{home or '主队'} vs {away or '客队'}"
    return ""


def _clv_text(clv: Any, *, locked_odds: Any, closing_odds: Any) -> str:
    value = _number(clv)
    if value is None:
        locked = _number(locked_odds)
        closing = _number(closing_odds)
        if locked is None or closing is None:
            return "—"
        value = closing - locked
    return _format_number(value, digits=4)


def _formal_table_row(match: dict[str, Any], *, payload_as_of: str) -> tuple[str, ...]:
    recommendation = _dict(match.get("recommendation"))
    return (
        _text(match.get("fixture_id")),
        _kickoff_label(match),
        _teams(match),
        _text(recommendation.get("market")),
        _text(recommendation.get("selection")),
        _format_optional_number(recommendation.get("line")),
        _format_optional_number(recommendation.get("odds"), digits=2),
        _ev_text(recommendation),
        _format_optional_number(recommendation.get("ev_se")),
        _recommendation_id(match),
        (
            "true"
            if _recommendation_id(match) and _kickoff_after_as_of(match, payload_as_of)
            else "false"
        ),
    )


def _non_formal_table_row(match: dict[str, Any], decision: MatchDecision) -> tuple[str, ...]:
    recommendation = _dict(match.get("recommendation"))
    shadow = _dict(match.get("pricing_shadow"))
    analysis = _dict(match.get("analysis_readiness"))
    invalid_formal = _has_formal_recommendation_intent(match) and (
        decision.state != MatchDecisionState.FORMAL
    )
    return (
        _text(match.get("fixture_id")),
        _teams(match),
        _current_state(match, decision),
        _text(recommendation.get("tier")),
        str(match.get("formal_recommendation") is True).lower(),
        _recommendation_id(match),
        _text(recommendation.get("market")),
        _diagnostic_recommendation_field(
            recommendation,
            "selection",
            invalid_formal=invalid_formal,
        ),
        _diagnostic_recommendation_field(recommendation, "line", invalid_formal=invalid_formal),
        _diagnostic_recommendation_field(
            recommendation,
            "odds",
            invalid_formal=invalid_formal,
            digits=2,
        ),
        _format_optional_number(shadow.get("fair_ah")),
        _format_optional_number(shadow.get("market_ah")),
        _format_optional_number(shadow.get("edge_ah")),
        _ev_text(recommendation),
        _format_optional_number(recommendation.get("ev_se")),
        _join_codes(shadow.get("formal_blockers")),
        _join_codes(analysis.get("blockers")),
        _text(shadow.get("independent_signal_count")),
        _join_codes(shadow.get("missing_independent_sources")),
        _join_codes(_blocker_codes(match, decision)),
        _explanation_cn(match, decision),
    )


def _diagnostic_recommendation_field(
    recommendation: dict[str, Any],
    key: str,
    *,
    invalid_formal: bool,
    digits: int = 4,
) -> str:
    if not invalid_formal:
        return ""
    value = recommendation.get(key)
    if value is None:
        return ""
    if key in {"line", "odds"}:
        text = _format_optional_number(value, digits=digits)
    else:
        text = _text(value)
    return f"INVALID: {text}" if text else ""


def _html_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _blocker_counts(
    matches: list[dict[str, Any]],
    decisions: list[MatchDecision],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match, decision in zip(matches, decisions, strict=True):
        if decision.state == MatchDecisionState.FORMAL:
            continue
        for code in _blocker_codes(match, decision):
            counts[code] = counts.get(code, 0) + 1
    return counts


def _blocker_codes(match: dict[str, Any], decision: MatchDecision) -> list[str]:
    shadow = _dict(match.get("pricing_shadow"))
    analysis = _dict(match.get("analysis_readiness"))
    codes: list[str] = []
    for item in _list(shadow.get("formal_blockers")):
        if isinstance(item, str) and item:
            codes.append(item)
    for item in _list(analysis.get("blockers")):
        if isinstance(item, str) and item:
            codes.append(item)
    missing_sources = {
        str(item).lower()
        for item in _list(shadow.get("missing_independent_sources"))
    }
    if "h2h" in missing_sources:
        codes.append("MISSING_H2H")
    if decision.reason and decision.reason not in codes:
        codes.append(decision.reason)
    return codes


def _explanation_cn(match: dict[str, Any], decision: MatchDecision) -> str:
    messages: list[str] = []
    for code in _blocker_codes(match, decision):
        message = _blocker_explanation_cn(code)
        if message not in messages:
            messages.append(message)
    return "；".join(messages) if messages else "未形成正式推荐，当前只观察"


def _blocker_explanation_cn(code: str) -> str:
    return {
        "AH_EV_BELOW_FORMAL_THRESHOLD": "让球结算期望未达正式推荐阈值",
        "EV_IMPLAUSIBLY_HIGH": "EV 异常偏高，保守拦截",
        "AH_FAIR_MARKET_GAP_TOO_WIDE": "模型公平盘与市场盘分歧过大",
        "AH_MAINLINE_CONSENSUS_CONFLICT": "主盘口与庄家共识冲突",
        "AH_MAINLINE_STALE_MATERIALIZATION": "盘口物化陈旧，等待重建",
        "EV_WITHIN_UNCERTAINTY_BAND": "EV 未超过不确定性缓冲带",
        "EV_UNCERTAINTY_MISSING": "EV 不确定度缺失，保守观察",
        "MISSING_LINEUPS": "首发未返回",
        "MISSING_H2H": "H2H 独立信号缺失",
        "W2_FORMAL_RECOMMENDATION_ENABLED=false": "正式推荐开关未开启",
        "MARKET_NOT_READY": "盘口未就绪",
        "DATA_INSUFFICIENT": "独立信号不足",
        "INSUFFICIENT_INDEPENDENT_FACTORS": "独立信号不足",
        "INDEPENDENT_SIGNAL_COUNT_BELOW_MINIMUM": "独立信号不足",
        "MISSING_MARKET_AH": "盘口未就绪",
        "MISSING_AH_MARKET": "盘口未就绪",
        "MISSING_ODDS": "赔率未就绪",
        "AH_MAINLINE_AMBIGUOUS": "全场让球主盘口不明确",
        "AH_PRIMARY_MAINLINE_MISSING": "缺少可确认的全场让球主盘口",
        "AH_MAINLINE_JUMP_REQUIRES_PRIMARY_CONFIRMATION": "盘口跳线需要多庄或连续时间桶确认",
        "AH_MARKET_LINE_MAGNITUDE_MISMATCH": "让球盘口幅度不一致",
        "AH_MARKET_HOME_LINE_MAGNITUDE_MISMATCH": "主队让球盘口幅度不一致",
        "AH_MARKET_ABS_LINE_MISMATCH": "让球盘口绝对值不一致",
        "AH_MARKET_LINE_SIDE_MISMATCH": "让球盘口方向不一致",
        "RECOMMENDATION_DIRECTION_INCONSISTENT": "推荐方向与盘口差距不一致",
        "NO_FORMAL_RECOMMENDATION_PAYLOAD": "未形成正式推荐，当前只观察",
        "EDGE_BELOW_FORMAL_THRESHOLD": "盘口差距未达正式推荐阈值",
        "INVALID_FORMAL_RECOMMENDATION_PAYLOAD": "正式推荐信息缺失，当前不输出方向",
        "INVALID_FORMAL_EV_PAYLOAD": "正式推荐EV字段不完整，当前不输出方向",
    }.get(code, f"未映射原因：{code}")


def _current_state(match: dict[str, Any], decision: MatchDecision) -> str:
    if decision.state != MatchDecisionState.WATCH:
        return decision.state.value
    recommendation = _dict(match.get("recommendation"))
    tier = str(recommendation.get("tier") or "").upper()
    return tier if tier else MatchDecisionState.WATCH.value


def _has_formal_recommendation_intent(match: dict[str, Any]) -> bool:
    recommendation = _dict(match.get("recommendation"))
    return (
        match.get("formal_recommendation") is True
        or str(recommendation.get("tier") or "").upper() == "FORMAL"
        or recommendation.get("formal_recommendation") is True
    )


def _recommendation_id(match: dict[str, Any]) -> str:
    recommendation = _dict(match.get("recommendation"))
    return _text(recommendation.get("recommendation_id") or recommendation.get("id"))


def _ev_text(recommendation: dict[str, Any]) -> str:
    value = recommendation.get("expected_value")
    if _number(value) is None:
        value = recommendation.get("risk_adjusted_ev")
    return _format_optional_number(value)


def _format_optional_number(value: Any, *, digits: int = 4) -> str:
    return "" if _number(value) is None else _format_number(value, digits=digits)


def _join_codes(value: Any) -> str:
    return " / ".join(str(item) for item in _list(value) if str(item))


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _kickoff_after_as_of(match: dict[str, Any], payload_as_of: str) -> bool:
    kickoff = _parse_time(match.get("kickoff_utc"))
    as_of = _parse_time(payload_as_of)
    return kickoff is not None and as_of is not None and kickoff > as_of


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _report_title(payload: dict[str, Any], options: ReportOptions) -> str:
    football_day = (
        payload.get("selected_football_day")
        or payload.get("selected_date")
        or payload.get("date")
        or "未知足球日"
    )
    suffix = "早间预览" if options.report_type == "morning" else "临场最终"
    title = f"W2 足球日报告 · {football_day} · {suffix}"
    return f"# {title}" if options.output_format == "markdown" else title


def _report_subtitle(
    *,
    matches: list[dict[str, Any]],
    formal_count: int,
    options: ReportOptions,
    payload_as_of: str,
) -> str:
    note = "暂定 · 会变" if options.report_type == "morning" else "临场锁定"
    as_of = _time_label(payload_as_of)
    return f"场次 {len(matches)} · 正式推荐 {formal_count} · {note} · as-of {as_of}"


def _render_match(
    match: dict[str, Any],
    decision: MatchDecision,
    *,
    options: ReportOptions,
    payload_as_of: str,
) -> list[str]:
    prefix = "## " if options.output_format == "markdown" else ""
    lines = [
        f"{prefix}{_kickoff_label(match)} · {_competition(match)} · {_teams(match)}",
        f"状态：{decision.label_cn}（{_reason_cn(decision.reason)}）",
    ]
    if decision.state == MatchDecisionState.FORMAL:
        lines.extend(_formal_lines(match))
        score_line = _score_line(match, decision)
        if score_line is not None:
            lines.append(score_line)
    elif decision.state == MatchDecisionState.LOCKED:
        lines.append(_locked_line(match))
    else:
        lines.append(_non_formal_line(match, decision))
    lines.append(_market_line(match))
    lines.append(_data_line(match))
    lines.append(f"as-of：{_as_of(match, payload_as_of=payload_as_of)}")
    return lines


def _formal_lines(match: dict[str, Any]) -> list[str]:
    recommendation = _dict(match.get("recommendation"))
    shadow = _dict(match.get("pricing_shadow"))
    return [
        f"推荐：{_recommendation_text(match, recommendation)}",
        f"我们的盘：{_line_value(shadow.get('fair_ah'))}；市场盘：{_market_display(match)}；差距：{_edge_text(shadow.get('edge_ah'))}（待校准）",
    ]


def _locked_line(match: dict[str, Any]) -> str:
    locked = _dict(match.get("locked_pre_match_recommendation"))
    if locked:
        return "赛前锁定：赛前正式推荐已锁定，复盘只读取锁定快照。"
    return "赛前锁定：未找到赛前正式推荐快照。"


def _non_formal_line(match: dict[str, Any], decision: MatchDecision) -> str:
    shadow = _dict(match.get("pricing_shadow"))
    if decision.state == MatchDecisionState.DATA_INSUFFICIENT:
        count = shadow.get("independent_signal_count")
        signal_count = count if count is not None else "未知"
        return f"说明：独立信号不足，当前不输出方向。独立信号数：{signal_count}。"
    if decision.state == MatchDecisionState.MARKET_NOT_READY:
        return f"说明：盘口未就绪，{_reason_cn(decision.reason)}，当前不输出方向。"
    if decision.reason == "INVALID_FORMAL_RECOMMENDATION_PAYLOAD":
        return "说明：正式推荐信息缺失，当前不输出方向。"
    if decision.reason == "INVALID_FORMAL_EV_PAYLOAD":
        return "说明：正式推荐EV字段不完整，当前不输出方向。"
    if decision.reason == "NO_FORMAL_RECOMMENDATION_PAYLOAD":
        return "说明：未形成正式推荐，当前只观察。"
    return "说明：盘口差距未达正式推荐阈值，当前只观察。"


def _score_line(match: dict[str, Any], decision: MatchDecision) -> str | None:
    if decision.state != MatchDecisionState.FORMAL:
        return None
    reference = _dict(match.get("scoreline_reference"))
    rows = [item for item in _list(reference.get("direction_top3")) if isinstance(item, dict)]
    if not rows:
        return None
    parts = []
    for item in rows[:3]:
        scoreline = item.get("scoreline")
        label = item.get("probability_label") or _probability_label(item.get("probability"))
        if scoreline:
            parts.append(f"{scoreline} {label}" if label else str(scoreline))
    if not parts:
        return None
    return f"推荐比分（与主推一致 · 高方差仅参考）：{' · '.join(parts)}。"


def _market_line(match: dict[str, Any]) -> str:
    timeline = _dict(match.get("market_timeline"))
    if not timeline:
        return "盘口走势（参照 · 未验证）：暂无时间线。"
    opening = _timeline_point(timeline.get("open"))
    current = _timeline_point(timeline.get("current"))
    pattern = _pattern_label(str(timeline.get("pattern") or "INSUFFICIENT"))
    if opening and current:
        return f"盘口走势（参照 · 未验证）：开盘 {opening} → 现在 {current}（{pattern}）。"
    return f"盘口走势（参照 · 未验证）：{pattern}。"


def _data_line(match: dict[str, Any]) -> str:
    refresh = _dict(match.get("data_refresh"))
    parts = [
        f"赔率{_status_cn(refresh.get('odds_status'))}",
        f"首发{_status_cn(refresh.get('lineups_status'))}",
        f"xG{_status_cn(refresh.get('xg_status'))}",
    ]
    return "数据：" + " · ".join(parts)


def _recommendation_text(match: dict[str, Any], recommendation: dict[str, Any]) -> str:
    selection = str(recommendation.get("selection") or "")
    line = recommendation.get("line")
    odds = recommendation.get("odds")
    home = str(match.get("home_team_name") or "主队")
    away = str(match.get("away_team_name") or "客队")
    if selection == "HOME_AH":
        side = home
    elif selection == "AWAY_AH":
        side = away
    else:
        raise ValueError("formal recommendation missing valid AH selection")
    odds_text = f" @{_format_number(odds, digits=2)}" if _number(odds) is not None else ""
    return f"全场让球，看 {side} {_signed_line(line)}{odds_text}"


def _market_display(match: dict[str, Any]) -> str:
    if not _market_ready_for_display(match):
        return "盘口未就绪"
    current = _dict(match.get("current_odds"))
    ah = _dict(current.get("ah"))
    display = ah.get("display_line_cn")
    if isinstance(display, str) and display:
        return display
    shadow = _dict(match.get("pricing_shadow"))
    return _line_value(shadow.get("market_ah"))


def _timeline_point(value: Any) -> str | None:
    point = _dict(value)
    if not point:
        return None
    line = _line_value(point.get("line"))
    home_price = _number(point.get("home_price"))
    away_price = _number(point.get("away_price"))
    as_of = _time_label(point.get("as_of"))
    price = ""
    if home_price is not None and away_price is not None:
        price = f"@{_format_number(home_price, digits=2)}/{_format_number(away_price, digits=2)}"
    return f"{line}{price} as-of {as_of}"


def _kickoff_label(match: dict[str, Any]) -> str:
    return _time_label(match.get("kickoff_utc"))


def _time_label(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "未知"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(_BEIJING).strftime("%m-%d %H:%M")


def _payload_as_of(payload: dict[str, Any]) -> str:
    value = (
        payload.get("generated_at")
        or payload.get("as_of")
        or payload.get("asof")
        or payload.get("build_time")
    )
    if not isinstance(value, str) or not value.strip():
        raise ValueError("dashboard payload missing generated_at/as_of")
    return value


def _as_of(match: dict[str, Any], *, payload_as_of: str) -> str:
    refresh = _dict(match.get("data_refresh"))
    timeline = _dict(match.get("market_timeline"))
    payload_value = (
        refresh.get("last_success")
        or refresh.get("as_of")
        or timeline.get("as_of")
        or match.get("generated_at")
        or payload_as_of
    )
    return _time_label(payload_value)


def _competition(match: dict[str, Any]) -> str:
    return str(match.get("competition_name") or "未知赛事")


def _teams(match: dict[str, Any]) -> str:
    return f"{match.get('home_team_name') or '主队'} vs {match.get('away_team_name') or '客队'}"


def _edge_text(value: Any) -> str:
    numeric = _number(value)
    if numeric is None:
        return "未知"
    return _signed_line(numeric)


def _line_value(value: Any) -> str:
    numeric = _number(value)
    if numeric is None:
        return "未知"
    if abs(numeric) < 1e-9:
        return "0"
    return _signed_line(numeric)


def _signed_line(value: Any) -> str:
    numeric = _number(value)
    if numeric is None:
        return "未知"
    if abs(numeric) < 1e-9:
        return "0"
    sign = "+" if numeric > 0 else ""
    return f"{sign}{_format_number(numeric)}"


def _format_number(value: Any, *, digits: int = 2) -> str:
    numeric = _number(value)
    if numeric is None:
        return "未知"
    text = f"{numeric:.{digits}f}"
    return text.rstrip("0").rstrip(".")


def _probability_label(value: Any) -> str | None:
    numeric = _number(value)
    if numeric is None:
        return None
    if numeric > 1:
        numeric /= 100
    return f"{round(numeric * 100)}%"


def _status_cn(value: Any) -> str:
    status = str(value or "UNKNOWN")
    return {
        "READY": "已就绪",
        "PARTIAL": "部分就绪",
        "WAITING": "等待中",
        "PROVIDER_EMPTY": "未返回",
        "INSUFFICIENT_HISTORY": "样本不足",
        "UNKNOWN": "未知",
    }.get(status, status)


def _pattern_label(pattern: str) -> str:
    return {
        "STABLE": "死守线",
        "ONE_WAY": "单边变化",
        "JUMP_LINE": "跳线",
        "EARLY_DROP_LATE_REBOUND": "早降晚升",
        "INSUFFICIENT": "样本不足",
    }.get(pattern, "样本不足")


def _reason_cn(reason: str) -> str:
    return {
        "MATCH_STARTED_OR_SETTLEMENT_PRESENT": "比赛已开始或进入复盘",
        "MISSING_PRICING_SHADOW": "缺少独立评分",
        "INSUFFICIENT_INDEPENDENT_FACTORS": "独立信号不足",
        "INDEPENDENT_SIGNAL_COUNT_BELOW_MINIMUM": "独立信号不足",
        "MISSING_MARKET_AH": "缺少全场让球市场盘",
        "AH_MAINLINE_AMBIGUOUS": "全场让球主盘口不明确",
        "AH_PRIMARY_MAINLINE_MISSING": "缺少可确认的全场让球主盘口",
        "AH_MAINLINE_CONSENSUS_CONFLICT": "全场让球主盘口与庄家共识冲突",
        "AH_MAINLINE_STALE_MATERIALIZATION": "主线物化待复核",
        "AH_MAINLINE_JUMP_REQUIRES_PRIMARY_CONFIRMATION": "盘口跳线需要多庄或连续时间桶确认",
        "AH_MARKET_LINE_MAGNITUDE_MISMATCH": "让球盘口幅度不一致",
        "AH_MARKET_HOME_LINE_MAGNITUDE_MISMATCH": "主队让球盘口幅度不一致",
        "AH_MARKET_ABS_LINE_MISMATCH": "让球盘口绝对值不一致",
        "AH_MARKET_LINE_SIDE_MISMATCH": "让球盘口方向不一致",
        "MISSING_ODDS": "赔率未就绪",
        "MISSING_AH_MARKET": "缺少全场让球市场盘",
        "AH_FAIR_MARKET_GAP_TOO_WIDE": "模拟公平盘与市场盘分歧过大",
        "EV_IMPLAUSIBLY_HIGH": "EV 异常偏高，保守拦截",
        "EDGE_BELOW_FORMAL_THRESHOLD": "盘口差距未达正式推荐阈值",
        "MISSING_FAIR_AH": "缺少模拟公平让球盘",
        "RECOMMENDATION_DIRECTION_INCONSISTENT": "推荐方向与盘口差距不一致",
        "INVALID_FORMAL_RECOMMENDATION_PAYLOAD": "正式推荐信息缺失",
        "INVALID_FORMAL_EV_PAYLOAD": "正式推荐EV字段不完整",
        "NO_FORMAL_RECOMMENDATION_PAYLOAD": "未形成正式推荐",
        "FORMAL_REPORTABLE": "达到报告正式推荐条件",
    }.get(reason, f"未映射原因：{reason}")


def _assert_safe_report_text(text: str) -> None:
    for term in _FORBIDDEN_TERMS:
        if term in text:
            raise ValueError(f"report contains forbidden term: {term}")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None
