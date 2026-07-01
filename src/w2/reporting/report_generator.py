from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from w2.reporting.match_decision import MatchDecision, MatchDecisionState, decide_match

ReportFormat = Literal["markdown", "text"]
ReportType = Literal["morning", "final"]

_BEIJING = ZoneInfo("Asia/Shanghai")
_FORBIDDEN_TERMS = (
    "命中率",
    "胜率",
    "ROI",
    "必中",
    "可买",
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
    payload_as_of = _payload_as_of(payload)
    lines = [
        _report_title(payload, options),
        _report_subtitle(
            matches=matches,
            formal_count=formal_count,
            options=options,
            payload_as_of=payload_as_of,
        ),
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
        score_line = _score_line(match)
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
    return "说明：盘口差距未达正式推荐阈值，当前只观察。"


def _score_line(match: dict[str, Any]) -> str | None:
    if decide_match(match).state != MatchDecisionState.FORMAL:
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
        side = "方向未识别"
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
