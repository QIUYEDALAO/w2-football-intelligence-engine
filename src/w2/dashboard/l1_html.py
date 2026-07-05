from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from typing import Any

from w2.dashboard.l1_view import build_boss_dashboard_l1
from w2.domain.enums import DecisionTier

_FORBIDDEN_TERMS = ("稳赢", "必中", "保证", "包赢")


def render_boss_dashboard_l1_html(day_view: Mapping[str, Any]) -> str:
    model = build_boss_dashboard_l1(day_view)
    counts = _mapping(model.get("counts"))
    freshness = _mapping(model.get("freshness"))
    sections = _mapping(model.get("sections"))
    html = "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>W2 今日比赛日</title>",
            f"<style>{_CSS}</style>",
            "</head>",
            "<body>",
            "<main>",
            _header(model, counts, freshness),
            _notice(model, counts, freshness),
            _section(
                "可锁审批 / 正式可锁",
                _card_list(sections.get("lock_eligible_recommendations")),
                empty_text=_empty_lock_text(model),
            ),
            _section("分析推荐", _card_list(sections.get("analysis_picks"))),
            _section("重点观察", _card_list(sections.get("watchlist"))),
            _section("未就绪", _card_list(sections.get("not_ready"))),
            _section("跳过", _card_list(sections.get("skipped"))),
            _reason_summary(sections.get("reason_summary")),
            _details(model),
            "</main>",
            "</body>",
            "</html>",
        ]
    )
    _assert_safe_html(html)
    return html


def _header(
    model: Mapping[str, Any],
    counts: Mapping[str, Any],
    freshness: Mapping[str, Any],
) -> str:
    lock_label = _lock_metric_label(model)
    return "\n".join(
        [
            "<header>",
            "<h1>W2 今日比赛日</h1>",
            '<div class="meta">',
            f"<span>环境：{_e(model.get('environment'))}</span>",
            f"<span>比赛日：{_e(model.get('football_day'))}</span>",
            f"<span>更新时间：{_e(model.get('generated_at'))}</span>",
            "<span>下一次刷新："
            f"{_e(freshness.get('next_refresh_tick') or '等待下一次刷新')}</span>",
            "</div>",
            '<div class="counts">',
            _metric(lock_label, counts.get("lock_eligible")),
            _metric("分析推荐", counts.get("analysis_pick")),
            _metric("观察", counts.get("watch")),
            _metric("未就绪", counts.get("not_ready")),
            _metric("数据陈旧", counts.get("stale")),
            _metric("跳过", counts.get("skip")),
            "</div>",
            "</header>",
        ]
    )


def _notice(
    model: Mapping[str, Any],
    counts: Mapping[str, Any],
    freshness: Mapping[str, Any],
) -> str:
    provider_budget_status = str(freshness.get("provider_budget_status") or "").upper()
    messages = [_e(model.get("headline"))]
    empty_lock_text = _empty_lock_text(model)
    if provider_budget_status == "EXHAUSTED":
        messages.append("provider 预算耗尽，等待下一 tick 或预算恢复")
    if _int(counts.get("total")) == 0:
        messages.append("今日暂无比赛")
    if _int(counts.get("lock_eligible")) == 0:
        messages.append(empty_lock_text)
    return '<section class="notice">' + "".join(
        f"<p>{message}</p>" for message in dict.fromkeys(messages) if message
    ) + "</section>"


def _section(title: str, cards: list[Mapping[str, Any]], *, empty_text: str = "") -> str:
    body = "".join(_card(card) for card in cards)
    if not body and empty_text:
        body = f'<p class="empty">{_e(empty_text)}</p>'
    return f'<section class="panel"><h2>{_e(title)}</h2><div class="cards">{body}</div></section>'


def _card(card: Mapping[str, Any]) -> str:
    market_line = " · ".join(
        item
        for item in (
            _optional_text(card.get("market")),
            _optional_text(card.get("selection")),
            _optional_text(card.get("line")),
            _optional_text(card.get("odds")),
        )
        if item
    )
    disclaimer = _optional_text(card.get("disclaimer"))
    if card.get("decision_tier") == DecisionTier.ANALYSIS_PICK.value:
        disclaimer = "分析参考·非稳赢；production 动作需 RECOMMEND"
    fallback = _optional_text(card.get("action")) or "等待下一次刷新"
    badges = [
        item
        for item in (
            "staging-only" if card.get("staging_only") is True else None,
            _optional_text(card.get("action_label")),
        )
        if item
    ]
    return "\n".join(
        [
            '<article class="card">',
            f"<h3>{_e(card.get('match'))}</h3>",
            '<div class="card-meta">',
            f"<span>{_e(card.get('kickoff_utc'))}</span>",
            f"<span>{_e(card.get('decision_tier'))}</span>",
            f"<span>{_e(card.get('data_status'))}</span>",
            *(f"<span>{_e(badge)}</span>" for badge in badges),
            "</div>",
            f"<p>{_e(card.get('one_liner') or fallback)}</p>",
            f'<p class="market">{_e(market_line)}</p>' if market_line else "",
            f'<p class="disclaimer">{_e(disclaimer)}</p>' if disclaimer else "",
            '<details><summary>技术细节</summary>',
            "<dl>",
            f"<dt>fixture_id</dt><dd>{_e(card.get('fixture_id'))}</dd>",
            f"<dt>reason_code</dt><dd>{_e(card.get('reason_code'))}</dd>",
            f"<dt>action</dt><dd>{_e(card.get('action'))}</dd>",
            f"<dt>next_eval_at</dt><dd>{_e(card.get('next_eval_at'))}</dd>",
            "</dl>",
            "</details>",
            "</article>",
        ]
    )


def _reason_summary(value: Any) -> str:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        rows: list[Mapping[str, Any]] = []
    else:
        rows = [item for item in value if isinstance(item, Mapping)]
    if not rows:
        return (
            '<section class="panel"><h2>主要未出原因</h2>'
            '<p class="empty">暂无主要未出原因</p></section>'
        )
    items = "".join(
        f"<li>{_e(row.get('reason_code'))}：{_e(row.get('count'))}</li>" for row in rows
    )
    return f'<section class="panel"><h2>主要未出原因</h2><ul>{items}</ul></section>'


def _details(model: Mapping[str, Any]) -> str:
    freshness = _mapping(model.get("freshness"))
    return "\n".join(
        [
            '<details class="debug">',
            "<summary>技术细节</summary>",
            "<dl>",
            f"<dt>provider_budget_status</dt><dd>{_e(freshness.get('provider_budget_status'))}</dd>",
            f"<dt>last_refresh</dt><dd>{_e(freshness.get('last_refresh'))}</dd>",
            f"<dt>next_refresh_tick</dt><dd>{_e(freshness.get('next_refresh_tick'))}</dd>",
            "</dl>",
            "</details>",
        ]
    )


def _metric(label: str, value: Any) -> str:
    return f'<div class="metric"><span>{_e(label)}</span><strong>{_e(_int(value))}</strong></div>'


def _lock_metric_label(model: Mapping[str, Any]) -> str:
    return "正式可锁" if model.get("environment") == "production" else "可锁审批"


def _empty_lock_text(model: Mapping[str, Any]) -> str:
    if model.get("environment") == "production":
        return "当前无正式可锁推荐"
    return "当前无可锁审批候选"


def _card_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _e(value: Any) -> str:
    if value is None:
        return ""
    return escape(str(value), quote=True)


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _assert_safe_html(html: str) -> None:
    normalized = html.replace("非稳赢", "")
    for term in _FORBIDDEN_TERMS:
        if term in normalized:
            raise ValueError(f"L1 HTML contains forbidden term: {term}")
    hidden_terms = ("raw payload", "provider_request_hash", "lambda", "blocker_codes")
    for term in hidden_terms:
        if term in html:
            raise ValueError(f"L1 HTML leaked diagnostic term: {term}")


_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; background: #f6f7f9; color: #17202a;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Microsoft YaHei", sans-serif; }
main { max-width: 1120px; margin: 0 auto; padding: 20px; }
header { background: #ffffff; border: 1px solid #d9dde5; border-radius: 6px; padding: 16px; }
h1 { margin: 0 0 8px; font-size: 24px; }
.meta { display: flex; flex-wrap: wrap; gap: 10px 18px; color: #607086; font-size: 13px; }
.counts { display: grid; grid-template-columns: repeat(6, minmax(100px, 1fr));
  gap: 8px; margin-top: 14px; }
.metric { background: #eef2f7; border-radius: 6px; padding: 10px; }
.metric span { display: block; color: #607086; font-size: 12px; }
.metric strong { display: block; margin-top: 4px; font-size: 22px; }
.notice, .panel { margin-top: 12px; background: #ffffff; border: 1px solid #d9dde5;
  border-radius: 6px; padding: 14px; }
.notice p { margin: 0 0 6px; font-weight: 600; }
.panel h2 { margin: 0 0 10px; font-size: 17px; }
.cards { display: grid; gap: 10px; }
.card { border: 1px solid #dfe3eb; border-radius: 6px; padding: 12px; background: #fbfcfe; }
.card h3 { margin: 0 0 8px; font-size: 16px; }
.card-meta { display: flex; flex-wrap: wrap; gap: 8px; color: #607086; font-size: 12px; }
.card p { margin: 8px 0 0; line-height: 1.45; }
.market { color: #3b566f; }
.disclaimer { color: #7a4f00; font-weight: 600; }
.empty { color: #607086; margin: 0; }
details { margin-top: 10px; color: #607086; }
summary { cursor: pointer; }
dl { display: grid; grid-template-columns: 120px minmax(0, 1fr); gap: 4px 10px; margin: 8px 0 0; }
dt { color: #607086; }
dd { margin: 0; overflow-wrap: anywhere; }
ul { margin: 0; padding-left: 20px; }
@media (max-width: 760px) {
  main { padding: 12px; }
  .counts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
"""
