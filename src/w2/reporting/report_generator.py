from __future__ import annotations

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
    ordered = sorted(
        enumerate(zip(matches, decisions, strict=True)),
        key=lambda item: (
            0 if item[1][1].state == MatchDecisionState.FORMAL else 1,
            item[0],
        ),
    )
    cards = []
    text_options = ReportOptions(report_type=options.report_type, output_format="text")
    for _, (match, decision) in ordered:
        lines = _render_match(
            match,
            decision,
            options=text_options,
            payload_as_of=payload_as_of,
        )
        state_class = decision.state.value.lower()
        title = escape(lines[0])
        body = "\n".join(f"<p>{escape(line)}</p>" for line in lines[1:])
        cards.append(
            f'<article class="match-card {state_class}" '
            f'data-state="{escape(decision.state.value)}">'
            f"<h2>{title}</h2>{body}</article>"
        )
    title = _report_title(payload, ReportOptions(options.report_type, "text"))
    subtitle = _report_subtitle(
        matches=matches,
        formal_count=formal_count,
        options=options,
        payload_as_of=payload_as_of,
    )
    state_summary = _html_state_summary(state_counts)
    formal_table = _html_formal_recommendation_table(
        matches,
        decisions,
        payload_as_of=payload_as_of,
    )
    non_formal_table = _html_non_formal_decision_table(matches, decisions)
    generated = _time_label(payload_as_of)
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    body {{ margin: 0; background: #f6f7f9; color: #17202a; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 32px 20px 48px; }}
    header {{ margin-bottom: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    .subtitle, .state-summary {{ margin: 0; color: #52606d; }}
    .state-summary {{ margin-top: 8px; font-weight: 600; }}
    .decision-section {{
      margin: 18px 0;
      border: 1px solid #d6dbe1;
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }}
    .decision-section h2 {{
      margin: 0;
      padding: 14px 16px 6px;
      font-size: 18px;
      letter-spacing: 0;
    }}
    .decision-section p {{ margin: 0; padding: 0 16px 14px; color: #52606d; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{
      padding: 9px 10px;
      border-top: 1px solid #e4e7eb;
      text-align: left;
      vertical-align: top;
    }}
    th {{ white-space: nowrap; background: #f2f4f7; color: #344054; }}
    td {{ line-height: 1.45; }}
    .grid {{ display: grid; gap: 14px; }}
    .match-card {{
      border: 1px solid #d6dbe1;
      border-radius: 8px;
      background: #fff;
      padding: 18px;
    }}
    .match-card.formal {{ border-color: #0f766e; box-shadow: inset 4px 0 0 #0f766e; }}
    .match-card h2 {{ margin: 0 0 12px; font-size: 18px; letter-spacing: 0; }}
    .match-card p {{ margin: 7px 0; line-height: 1.55; }}
    footer {{ margin-top: 18px; color: #697586; font-size: 13px; }}
    @media (prefers-color-scheme: dark) {{
      body {{ background: #111827; color: #e5e7eb; }}
      .subtitle, .state-summary, footer {{ color: #aeb7c2; }}
      .match-card {{ background: #1f2937; border-color: #374151; }}
      .decision-section {{ background: #1f2937; border-color: #374151; }}
      .decision-section p {{ color: #aeb7c2; }}
      th {{ background: #111827; color: #d1d5db; }}
      th, td {{ border-color: #374151; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{escape(title)}</h1>
      <p class="subtitle">{escape(subtitle)}</p>
      <p class="state-summary">{escape(state_summary)}</p>
    </header>
    {formal_table}
    {non_formal_table}
    <section class="grid">
      {''.join(cards)}
    </section>
    <footer>生成时间：{escape(generated)} · 只读报告 · 数据来自 dashboard payload</footer>
  </main>
</body>
</html>
"""
    _assert_safe_report_text(html)
    return html


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
    return (
        _text(match.get("fixture_id")),
        _teams(match),
        _current_state(match, decision),
        _text(recommendation.get("tier")),
        str(match.get("formal_recommendation") is True).lower(),
        _recommendation_id(match),
        _text(recommendation.get("market")),
        _text(recommendation.get("selection")),
        _format_optional_number(recommendation.get("line")),
        _format_optional_number(recommendation.get("odds"), digits=2),
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
        "RECOMMENDATION_DIRECTION_INCONSISTENT": "推荐方向与盘口差距不一致",
        "NO_FORMAL_RECOMMENDATION_PAYLOAD": "未形成正式推荐，当前只观察",
        "EDGE_BELOW_FORMAL_THRESHOLD": "盘口差距未达正式推荐阈值",
        "INVALID_FORMAL_RECOMMENDATION_PAYLOAD": "正式推荐信息缺失，当前不输出方向",
        "INVALID_FORMAL_EV_PAYLOAD": "正式推荐EV字段不完整，当前不输出方向",
    }.get(code, "未形成正式推荐，当前只观察")


def _current_state(match: dict[str, Any], decision: MatchDecision) -> str:
    if decision.state != MatchDecisionState.WATCH:
        return decision.state.value
    recommendation = _dict(match.get("recommendation"))
    tier = str(recommendation.get("tier") or "").upper()
    return tier if tier else MatchDecisionState.WATCH.value


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
        "EDGE_BELOW_FORMAL_THRESHOLD": "盘口差距未达正式推荐阈值",
        "MISSING_FAIR_AH": "缺少模拟公平让球盘",
        "RECOMMENDATION_DIRECTION_INCONSISTENT": "推荐方向与盘口差距不一致",
        "INVALID_FORMAL_RECOMMENDATION_PAYLOAD": "正式推荐信息缺失",
        "INVALID_FORMAL_EV_PAYLOAD": "正式推荐EV字段不完整",
        "NO_FORMAL_RECOMMENDATION_PAYLOAD": "未形成正式推荐",
        "FORMAL_REPORTABLE": "达到报告正式推荐条件",
    }.get(reason, "状态原因已记录")


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
