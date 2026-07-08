from __future__ import annotations

import w2.reporting.report_generator as report_generator
from w2.reporting import render_report
from w2.reporting.match_decision import MatchDecision


def _payload(*matches: dict[str, object]) -> dict[str, object]:
    return {
        "selected_football_day": "2026-06-30",
        "generated_at": "2026-06-30T23:40:00Z",
        "environment": "staging",
        "all": list(matches),
    }


def _formal_match() -> dict[str, object]:
    return {
        "fixture_id": "f1",
        "kickoff_utc": "2026-06-30T20:00:00Z",
        "competition_name": "世界杯",
        "home_team_name": "France",
        "away_team_name": "Sweden",
        "status": "NS",
        "recommendation": {
            "tier": "FORMAL",
            "formal_recommendation": True,
            "market": "ASIAN_HANDICAP",
            "selection": "HOME_AH",
            "line": -1.25,
            "odds": 1.93,
            "expected_value": 0.041,
        },
        "formal_recommendation": True,
        "current_odds": {
            "ah": {
                "display_line_cn": "主队 -1.25",
            },
        },
        "pricing_shadow": {
            "status": "READY",
            "independent_signal_count": 5,
            "team_score": {"home": 73, "away": 58},
            "fair_ah": -1.5,
            "market_ah": -1.25,
            "edge_ah": 0.25,
            "beats_market": False,
        },
        "scoreline_reference": {
            "direction_top3": [
                {
                    "scoreline": "2-0",
                    "probability": 0.17,
                    "probability_label": "17%",
                    "source": "formal_simulation_direction_top3",
                },
                {
                    "scoreline": "3-1",
                    "probability": 0.12,
                    "probability_label": "12%",
                    "source": "formal_simulation_direction_top3",
                },
                {
                    "scoreline": "2-1",
                    "probability": 0.11,
                    "probability_label": "11%",
                    "source": "formal_simulation_direction_top3",
                },
            ],
        },
        "market_timeline": {
            "status": "READY",
            "source": "market_timeline_snapshots",
            "label": "盘口时间线 · 参照 · 未验证",
            "verified": False,
            "direction_allowed": False,
            "open": {
                "line": -1.0,
                "home_price": 1.9,
                "away_price": 2.0,
                "as_of": "2026-06-30T10:00:00Z",
            },
            "current": {
                "line": -1.25,
                "home_price": 1.93,
                "away_price": 1.97,
                "as_of": "2026-06-30T19:00:00Z",
            },
            "as_of": "2026-06-30T19:00:00Z",
            "pattern": "ONE_WAY",
        },
        "data_refresh": {
            "odds_status": "READY",
            "lineups_status": "READY",
            "xg_status": "READY",
            "last_success": "2026-06-30T19:05:00Z",
        },
    }


def _non_formal_match() -> dict[str, object]:
    return {
        "fixture_id": "f2",
        "kickoff_utc": "2026-06-30T22:00:00Z",
        "competition_name": "世界杯",
        "home_team_name": "Mexico",
        "away_team_name": "Ecuador",
        "status": "NS",
        "recommendation": {"tier": "WATCH", "market": "ASIAN_HANDICAP"},
        "formal_recommendation": False,
        "pricing_shadow": {
            "status": "READY",
            "independent_signal_count": 5,
            "fair_ah": -0.25,
            "market_ah": -0.25,
            "edge_ah": 0,
            "beats_market": False,
        },
        "scoreline_reference": {
            "direction_top3": [],
            "top_scorelines": [{"scoreline": "1-1", "probability_label": "14%"}],
        },
        "market_timeline": {
            "status": "PARTIAL",
            "source": "market_timeline_snapshots",
            "label": "盘口时间线 · 参照 · 未验证",
            "verified": False,
            "direction_allowed": False,
            "open": {"line": -0.25, "as_of": "2026-06-30T12:00:00Z"},
            "current": {"line": -0.25, "as_of": "2026-06-30T12:00:00Z"},
            "as_of": "2026-06-30T12:00:00Z",
            "pattern": "INSUFFICIENT",
        },
        "data_refresh": {
            "odds_status": "READY",
            "lineups_status": "PARTIAL",
            "xg_status": "READY",
            "last_success": "2026-06-30T12:05:00Z",
        },
    }


def test_render_markdown_includes_environment_policy_summary() -> None:
    report = render_report(_payload(_non_formal_match()), output_format="markdown")

    assert "环境策略：" in report
    assert "environment：staging" in report
    assert "policy：staging_B" in report
    assert "ANALYSIS_PICK=display_track_replay_only" in report
    assert "staging-only" in report
    assert "分析参考" in report
    assert "非稳赢" in report
    assert "稳赢" not in report.replace("非稳赢", "")


def test_render_html_includes_production_environment_policy_summary() -> None:
    payload = _payload(_non_formal_match())
    payload["environment"] = "production"

    report = render_report(payload, output_format="html")

    assert "policy production_B" in report
    assert "ANALYSIS_PICK 非正式可动作" in report
    assert "production 仅 RECOMMEND 可锁" in report


def _non_formal_with_blockers(
    *,
    fixture_id: str,
    formal_blockers: list[str] | None = None,
    analysis_blockers: list[str] | None = None,
    missing_sources: list[str] | None = None,
    tier: str = "ANALYSIS_PICK",
) -> dict[str, object]:
    match = _non_formal_match()
    match["fixture_id"] = fixture_id
    match["home_team_name"] = f"Home {fixture_id}"
    match["away_team_name"] = f"Away {fixture_id}"
    match["recommendation"] = {
        "tier": tier,
        "market": "ASIAN_HANDICAP",
        "selection": "HOME_AH",
        "line": -0.75,
        "odds": 1.91,
    }
    shadow = dict(match["pricing_shadow"])  # type: ignore[arg-type]
    shadow["formal_blockers"] = formal_blockers or []
    shadow["missing_independent_sources"] = missing_sources or []
    match["pricing_shadow"] = shadow
    match["analysis_readiness"] = {"blockers": analysis_blockers or []}
    return match


def test_render_report_outputs_formal_direction_scorelines_and_as_of() -> None:
    report = render_report(_payload(_formal_match()), report_type="final", output_format="markdown")

    assert "# W2 足球日报告 · 2026-06-30 · 临场最终" in report
    assert "场次 1 · 正式推荐 1 · 临场锁定 · as-of 07-01 07:40" in report
    assert "状态：正式推荐" in report
    assert "推荐：全场让球，看 France -1.25 @1.93" in report
    assert "推荐比分（与主推一致 · 高方差仅参考）：2-0 17% · 3-1 12% · 2-1 11%" in report
    assert "盘口走势（参照 · 未验证）" in report
    assert "as-of：" in report


def test_render_report_hides_scorelines_for_non_formal_matches() -> None:
    report = render_report(
        _payload(_non_formal_match()),
        report_type="morning",
        output_format="text",
    )

    assert "W2 足球日报告 · 2026-06-30 · 早间预览" in report
    assert "场次 1 · 正式推荐 0 · 暂定 · 会变 · as-of 07-01 07:40" in report
    assert "状态：观察" in report
    assert "正式推荐判定摘要：" in report
    assert "今日正式推荐数量：0" in report
    assert "推荐比分" not in report
    assert "1-1 14%" not in report


def test_render_report_suppresses_non_formal_ah_direction_fields() -> None:
    match = _non_formal_with_blockers(
        fixture_id="egypt",
        formal_blockers=["AH_EV_BELOW_FORMAL_THRESHOLD"],
    )
    match["home_team_name"] = "Australia"
    match["away_team_name"] = "Egypt"
    match["recommendation"] = {
        "tier": "ANALYSIS_PICK",
        "market": "ASIAN_HANDICAP",
        "selection": "AWAY_AH",
        "selection_label_cn": "客队方向 0.25",
        "line": "0.25",
        "odds": "2.00",
        "reasons": ["客队方向 0.25"],
    }

    html = render_report(_payload(match), output_format="html")
    markdown = render_report(_payload(match), output_format="markdown")

    for output in (html, markdown):
        assert "客队方向 0.25" not in output
        assert "AWAY_AH" not in output
        assert "2.00" not in output
        assert "推荐：全场让球" not in output
        assert "AH_EV_BELOW_FORMAL_THRESHOLD" in output


def test_render_report_keeps_invalid_formal_payload_only_as_diagnostic() -> None:
    match = _formal_match()
    match["formal_recommendation"] = True
    match["recommendation"] = {
        "tier": "FORMAL",
        "market": "ASIAN_HANDICAP",
        "selection": "AWAY_AH",
        "selection_label_cn": "客队方向 0.25",
        "line": "0.25",
    }

    html = render_report(_payload(match), output_format="html")
    text = render_report(_payload(match), output_format="text")

    assert "推荐：全场让球" not in html
    assert "推荐：全场让球" not in text
    assert "INVALID: AWAY_AH" in html
    assert "INVALID: 0.25" in html
    assert "客队方向 0.25" not in html


def test_render_report_does_not_emit_formal_lines_for_invalid_formal_payload() -> None:
    match = _formal_match()
    match["recommendation"] = {
        "tier": "FORMAL",
        "market": "ASIAN_HANDICAP",
        "selection": "UNKNOWN",
        "line": 2.5,
        "odds": 1.87,
    }

    report = render_report(_payload(match), output_format="text")

    assert "状态：观察（正式推荐信息缺失）" in report
    assert "说明：正式推荐信息缺失，当前不输出方向。" in report
    assert "推荐：全场让球" not in report
    assert "推荐比分" not in report
    assert "方向未识别" not in report
    assert "全场让球，看 方向未识别" not in report


def test_render_report_does_not_emit_formal_lines_for_missing_formal_ev() -> None:
    match = _formal_match()
    recommendation = dict(match["recommendation"])  # type: ignore[arg-type]
    recommendation.pop("expected_value")
    match["recommendation"] = recommendation

    report = render_report(_payload(match), output_format="text")

    assert "状态：观察（正式推荐EV字段不完整）" in report
    assert "推荐：全场让球" not in report
    assert "推荐比分" not in report


def test_render_report_hides_scoreline_line_when_formal_direction_top3_missing() -> None:
    match = _formal_match()
    match["scoreline_reference"] = {"direction_top3": []}

    report = render_report(_payload(match), output_format="text")

    assert "状态：正式推荐" in report
    assert "推荐比分" not in report
    assert "暂无" not in report


def test_render_report_hides_scoreline_line_when_direction_top3_is_malformed() -> None:
    match = _formal_match()
    match["scoreline_reference"] = {"direction_top3": [{"probability": 0.1}]}

    report = render_report(_payload(match), output_format="text")

    assert "状态：正式推荐" in report
    assert "推荐比分" not in report
    assert "暂无" not in report


def test_render_report_separates_market_not_ready_from_data_insufficient() -> None:
    data_match = _non_formal_match()
    data_match["pricing_shadow"] = {"status": "READY", "independent_signal_count": 2}
    market_match = _non_formal_match()
    market_match["pricing_shadow"] = {
        "status": "READY",
        "independent_signal_count": 5,
        "fair_ah": -1.0,
        "canonical_ah_market_blocker": "AH_MAINLINE_AMBIGUOUS",
    }

    report = render_report(_payload(data_match, market_match), output_format="text")

    assert "状态：数据不足（独立信号不足）" in report
    assert "状态：盘口未就绪" in report
    assert "全场让球主盘口不明确" in report


def test_render_report_uses_payload_as_of_when_match_as_of_is_missing() -> None:
    match = _non_formal_match()
    match["data_refresh"] = {}
    match["market_timeline"] = {"status": "INSUFFICIENT"}

    report = render_report(_payload(match), output_format="text")

    assert "as-of：07-01 07:40" in report
    assert "as-of：未知" not in report


def test_render_report_requires_payload_as_of_for_determinism() -> None:
    payload = _payload(_non_formal_match())
    payload.pop("generated_at")

    try:
        render_report(payload, output_format="text")
    except ValueError as exc:
        assert str(exc) == "dashboard payload missing generated_at/as_of"
    else:
        raise AssertionError("expected missing as-of error")


def test_render_report_is_deterministic_for_same_input() -> None:
    payload = _payload(_formal_match(), _non_formal_match())

    assert render_report(payload, output_format="text") == render_report(
        payload,
        output_format="text",
    )


def test_render_report_rejects_forbidden_terms() -> None:
    match = _formal_match()
    match["competition_name"] = "必中杯"

    try:
        render_report(_payload(match), output_format="text")
    except ValueError as exc:
        assert "forbidden term" in str(exc)
    else:
        raise AssertionError("expected forbidden term guard")


def test_render_html_empty_day_has_header_and_no_forbidden_terms() -> None:
    report = render_report(_payload(), output_format="html")

    assert "<!doctype html>" in report
    assert "W2 足球日报告 · 2026-06-30 · 临场最终" in report
    assert "场次 0 · 正式推荐 0" in report
    assert "场次 0 · 正式 0 · 观察 0 · 数据不足 0 · 盘口未就绪 0 · 已锁定 0" in report
    assert "已结算" in report
    assert "观察中" in report
    assert "0/30" in report
    assert "已结算推荐：观察中 0/30" in report
    assert "今日正式推荐：0" in report
    assert "当前无 FORMAL + recommendation_id + future kickoff" in report
    assert "推荐：全场让球" not in report
    assert "命中率" not in report
    assert "方向未识别" not in report


def test_render_html_adds_settled_recommendation_fact_table_with_clv() -> None:
    payload = _payload(_non_formal_match())
    payload["locked_recommendation_snapshots"] = [
        {
            "source": "recommendation_lock_model",
            "lock_id": "lock-1",
            "recommendation_id": "rec-1",
            "fixture_id": "f-settled",
            "teams": "Portugal vs Croatia",
            "kickoff_utc": "2026-07-03T23:00:00Z",
            "recommendation_market": "ASIAN_HANDICAP",
            "recommendation_selection": "HOME_AH",
            "recommendation_line": -0.25,
            "recommendation_odds": 1.91,
        }
    ]
    payload["settlement_history"] = [
        {
            "source": "settlement_model",
            "settlement_id": "settle-1",
            "recommendation_id": "rec-1",
            "lock_id": "lock-1",
            "fixture_id": "f-settled",
            "status": "SETTLED",
            "result": "1-0",
            "settled_at": "2026-07-04T01:15:00Z",
            "closing_decimal_odds": 1.84,
            "clv_decimal": -0.07,
        }
    ]

    report = render_report(payload, output_format="html")

    assert "已结算推荐（观察中）" in report
    assert "已结算推荐：观察中 1/30" in report
    assert "CLV" in report
    assert "f-settled" in report
    assert "Portugal vs Croatia" in report
    assert "rec-1" in report
    assert "lock-1" in report
    assert "1.84" in report
    assert "-0.07" in report
    assert "settlement_model" in report
    assert "命中率" not in report


def test_render_html_reads_settlement_tables_from_audit_export_payload() -> None:
    payload = _payload()
    payload["audit_export"] = {
        "tables": {
            "locked_recommendation_snapshots": [
                {
                    "lock_id": "lock-2",
                    "recommendation_id": "rec-2",
                    "fixture_id": "f-audit",
                    "snapshot_payload_json": {
                        "home_team_name": "Argentina",
                        "away_team_name": "France",
                        "kickoff_utc": "2026-07-04T21:00:00Z",
                        "recommendation": {
                            "market": "ASIAN_HANDICAP",
                            "selection": "AWAY_AH",
                            "line": 0.5,
                            "odds": 1.88,
                        },
                    },
                }
            ],
            "settlement_history": [
                {
                    "settlement_id": "settle-2",
                    "recommendation_id": "rec-2",
                    "lock_id": "lock-2",
                    "fixture_id": "f-audit",
                    "outcome": "PUSH",
                    "settled_at": "2026-07-05T00:00:00Z",
                    "closing_odds": 1.9,
                }
            ],
        }
    }

    report = render_report(payload, output_format="html")

    assert "已结算推荐：观察中 1/30" in report
    assert "Argentina vs France" in report
    assert "AWAY_AH" in report
    assert "0.5" in report
    assert "1.88" in report
    assert "0.02" in report


def test_render_html_uses_dash_when_clv_is_not_yet_available() -> None:
    payload = _payload()
    payload["locked_recommendation_snapshots"] = [
        {
            "lock_id": "lock-no-close",
            "recommendation_id": "rec-no-close",
            "fixture_id": "f-no-close",
            "teams": "Colombia vs Ghana",
            "recommendation_market": "ASIAN_HANDICAP",
            "recommendation_selection": "AWAY_AH",
            "recommendation_line": 1.25,
            "recommendation_odds": 1.86,
        }
    ]
    payload["settlement_history"] = [
        {
            "settlement_id": "settle-no-close",
            "recommendation_id": "rec-no-close",
            "lock_id": "lock-no-close",
            "fixture_id": "f-no-close",
            "status": "OBSERVING",
        }
    ]

    report = render_report(payload, output_format="html")

    assert "已结算推荐：观察中 1/30" in report
    assert "<th>CLV</th>" in report
    assert "<td>—</td>" in report


def test_render_html_settlement_panel_keeps_forbidden_guard() -> None:
    payload = _payload()
    payload["settlement_history"] = [
        {
            "settlement_id": "settle-forbidden",
            "fixture_id": "f-bad",
            "result": "命中率",
        }
    ]

    try:
        render_report(payload, output_format="html")
    except ValueError as exc:
        assert "forbidden term" in str(exc)
    else:
        raise AssertionError("expected forbidden term guard")


def test_render_html_orders_formal_cards_first_without_redecision() -> None:
    matches = []
    for index in range(50):
        match = _formal_match() if index in {7, 31} else _non_formal_match()
        match = dict(match)
        match["fixture_id"] = f"f-{index}"
        match["home_team_name"] = f"Home {index}"
        match["away_team_name"] = f"Away {index}"
        matches.append(match)

    report = render_report(_payload(*matches), output_format="html")

    first_formal = report.index('class="match-card formal"')
    first_watch = report.index('class="match-card watch"')
    assert first_formal < first_watch
    assert report.count('class="match-card') == 50
    assert "推荐：全场让球，看 Home 7" in report
    assert "场次 50 · 正式 2 · 观察 48 · 数据不足 0 · 盘口未就绪 0 · 已锁定 0" in report
    assert "方向未识别" not in report
    assert "命中率" not in report


def test_render_html_uses_one_decision_per_match_for_scorelines(monkeypatch) -> None:
    calls = 0
    original_decide = report_generator.decide_match

    def counting_decide(match: dict[str, object]) -> MatchDecision:
        nonlocal calls
        calls += 1
        return original_decide(match)

    monkeypatch.setattr(report_generator, "decide_match", counting_decide)

    report = report_generator.render_report(
        _payload(_formal_match(), _non_formal_match()),
        output_format="html",
    )

    assert "推荐比分" in report
    assert calls == 2


def test_render_html_no_formal_day_does_not_fake_recommendations_or_scorelines() -> None:
    report = render_report(
        _payload(_non_formal_match(), _non_formal_match()),
        output_format="html",
    )

    assert "状态：观察" in report
    assert "场次 2 · 正式 0 · 观察 2 · 数据不足 0 · 盘口未就绪 0 · 已锁定 0" in report
    assert "正式推荐表" in report
    assert "非 FORMAL 判定表" in report
    assert "今日正式推荐：0" in report
    assert "推荐：全场让球" not in report
    assert "推荐比分" not in report
    assert "1-1 14%" not in report
    assert "方向未识别" not in report


def test_render_html_uses_explanatory_dashboard_headers_and_legend() -> None:
    report = render_report(_payload(_non_formal_match()), output_format="html")

    assert ">市场盘</span>" in report
    assert ">差距</span>" in report
    assert ">信号</span>" in report
    assert ">数据时间</span>" in report
    assert ">盘</span>" not in report
    assert ">差</span>" not in report
    assert ">ISC</span>" not in report
    assert ">as-of</span>" not in report
    assert "市场盘为主队视角，负数=主队让球" in report
    assert "差距=市场盘−模型公平盘" in report


def test_render_html_data_gap_badge_names_missing_inputs() -> None:
    match = _non_formal_with_blockers(
        fixture_id="missing",
        analysis_blockers=["MISSING_LINEUPS"],
        missing_sources=["h2h"],
    )
    data_refresh = dict(match["data_refresh"])  # type: ignore[arg-type]
    data_refresh["odds_status"] = "PROVIDER_EMPTY"
    data_refresh["xg_status"] = "INSUFFICIENT_HISTORY"
    match["data_refresh"] = data_refresh

    report = render_report(_payload(match), output_format="html")

    assert "数据未齐：赔率/盘口、首发、xG" in report
    assert "缺失：赔率/盘口、首发、xG" in report
    assert "缺失：赔率/盘口、首发、xG、H2H" not in report
    assert "MISSING_LINEUPS" in report
    assert "H2H 无历史，国家队比赛常见，不阻塞" in report


def test_render_html_h2h_missing_alone_is_not_data_gap_for_national_teams() -> None:
    match = _non_formal_with_blockers(
        fixture_id="h2h-only",
        missing_sources=["h2h"],
    )
    match["data_refresh"] = {
        "odds_status": "READY",
        "lineups_status": "READY",
        "xg_status": "READY",
    }
    match["analysis_readiness"] = {"blockers": []}

    report = render_report(_payload(match), output_format="html")

    assert "数据未齐：" not in report
    assert "缺失：H2H" not in report
    assert "MISSING_H2H" in report
    assert "H2H 无历史，国家队比赛常见，不阻塞" in report


def test_render_html_locked_match_suppresses_stale_data_gap_badge() -> None:
    match = _non_formal_with_blockers(
        fixture_id="started",
        analysis_blockers=["MISSING_LINEUPS"],
        missing_sources=["h2h"],
    )
    match["status"] = "LIVE"

    report = render_report(_payload(match), output_format="html")

    assert "赛前判断已锁定" in report
    assert "数据未齐：" not in report
    assert '<span class="dq">数据未齐' not in report
    assert "MISSING_LINEUPS" in report
    assert "H2H 无历史，国家队比赛常见，不阻塞" in report


def test_render_html_locked_match_labels_data_time_as_closing_snapshot() -> None:
    match = _non_formal_with_blockers(
        fixture_id="started",
        analysis_blockers=["MISSING_LINEUPS"],
    )
    match["status"] = "LIVE"
    match["market_timeline"] = {
        "status": "READY",
        "pattern": "STABLE",
        "as_of": "2026-06-30T17:12:00Z",
    }

    report = render_report(_payload(match), output_format="html")

    assert "收盘快照 01:12" in report
    assert "赛前收盘前最后一次可用快照" in report
    assert "数据未齐：" not in report


def test_render_html_non_formal_decision_table_explains_blockers() -> None:
    no_formal_payload = _non_formal_with_blockers(fixture_id="no-formal")
    no_formal_payload.update(
        {
            "decision_tier": "WATCH",
            "data_status": "PARTIAL",
            "missing_fields": ["xg"],
            "stale_fields": ["odds"],
            "lifecycle_status": "DRAFT",
            "outcome_tracked": False,
            "lock_eligible": False,
            "reason_code": "EDGE_INSUFFICIENT",
            "action": "盯价格变动",
            "next_eval_at": "2026-07-01T03:30:00Z",
            "provider_budget_status": "AVAILABLE",
        }
    )
    shadow = dict(no_formal_payload["pricing_shadow"])  # type: ignore[arg-type]
    shadow.update(
        {
            "fair_ah": -1.0,
            "market_ah": -0.5,
            "edge_ah": 0.5,
            "formal_blockers": [],
            "missing_independent_sources": [],
        }
    )
    no_formal_payload["pricing_shadow"] = shadow

    report = render_report(
        _payload(
            _non_formal_with_blockers(
                fixture_id="ev",
                formal_blockers=["AH_EV_BELOW_FORMAL_THRESHOLD"],
            ),
            _non_formal_with_blockers(
                fixture_id="lineups",
                analysis_blockers=["MISSING_LINEUPS"],
            ),
            _non_formal_with_blockers(
                fixture_id="h2h",
                missing_sources=["h2h"],
            ),
            _non_formal_with_blockers(
                fixture_id="switch",
                formal_blockers=["W2_FORMAL_RECOMMENDATION_ENABLED=false"],
            ),
            no_formal_payload,
        ),
        output_format="html",
    )

    assert "非 FORMAL 判定表" in report
    assert "decision_tier" in report
    assert "missing_fields" in report
    assert "stale_fields" in report
    assert "provider_budget_status" in report
    assert "EDGE_INSUFFICIENT" in report
    assert "盯价格变动" in report
    assert "AVAILABLE" in report
    assert "blocker_codes" in report
    assert "AH_EV_BELOW_FORMAL_THRESHOLD" in report
    assert "让球结算期望未达正式推荐阈值" in report
    assert "MISSING_LINEUPS" in report
    assert "首发未返回" in report
    assert "h2h" in report
    assert "H2H 无历史，国家队比赛常见，不阻塞" in report
    assert "W2_FORMAL_RECOMMENDATION_ENABLED=false" in report
    assert "正式推荐开关未开启" in report
    assert "NO_FORMAL_RECOMMENDATION_PAYLOAD" in report
    assert "推荐：全场让球" not in report
    assert "推荐比分" not in report
    assert "命中率" not in report
    assert "方向未识别" not in report


def test_render_html_shows_stale_materialized_ah_mainline_with_review_badge() -> None:
    match = _non_formal_match()
    match["pricing_shadow"] = {
        **match["pricing_shadow"],  # type: ignore[dict-item]
        "fair_ah": -0.25,
        "market_ah": -2.5,
        "edge_ah": -2.25,
        "materialized_market_ah": -2.5,
        "selector_market_ah": -1.0,
        "mainline_materialization_blocker": "AH_MAINLINE_STALE_MATERIALIZATION",
        "canonical_ah_market_blocker": "AH_MAINLINE_STALE_MATERIALIZATION",
        "formal_blockers": ["AH_MAINLINE_STALE_MATERIALIZATION"],
    }
    match["current_odds"] = {
        "ah": {
            "display_line_cn": "主队 -1",
            "home_line": "-1",
            "away_line": "1",
        }
    }

    report = render_report(_payload(match), output_format="html")

    assert "盘口未就绪" in report
    assert "AH_MAINLINE_STALE_MATERIALIZATION" in report
    assert "主线物化待复核" in report
    assert "主线待复核" in report
    assert ">-2.5<span" in report
    assert ">-2.25<" in report
    assert "状态原因已记录" not in report


def test_render_html_does_not_emit_generic_reason_fallback() -> None:
    match = _non_formal_match()
    match["pricing_shadow"] = {
        **match["pricing_shadow"],  # type: ignore[dict-item]
        "canonical_ah_market_blocker": "AH_MAINLINE_JUMP_REQUIRES_PRIMARY_CONFIRMATION",
        "formal_blockers": ["AH_MAINLINE_JUMP_REQUIRES_PRIMARY_CONFIRMATION"],
    }

    report = render_report(_payload(match), output_format="html")

    assert "盘口跳线需要多庄或连续时间桶确认" in report
    assert "状态原因已记录" not in report


def test_render_markdown_includes_formal_decision_summary_with_blocker_counts() -> None:
    report = render_report(
        _payload(
            _non_formal_with_blockers(
                fixture_id="ev",
                formal_blockers=["AH_EV_BELOW_FORMAL_THRESHOLD"],
            ),
            _non_formal_with_blockers(
                fixture_id="lineups",
                analysis_blockers=["MISSING_LINEUPS"],
            ),
        ),
        output_format="markdown",
    )

    assert "正式推荐判定摘要：" in report
    assert "今日正式推荐数量：0" in report
    assert "lock eligible 数量：0" in report
    assert "AH_EV_BELOW_FORMAL_THRESHOLD=1" in report
    assert "MISSING_LINEUPS=1" in report


def test_render_report_rejects_added_forbidden_terms() -> None:
    match = _formal_match()
    match["competition_name"] = "可买杯"

    try:
        render_report(_payload(match), output_format="text")
    except ValueError as exc:
        assert "forbidden term" in str(exc)
    else:
        raise AssertionError("expected forbidden term guard")


def test_render_report_rejects_unrecognized_direction_text_anywhere_visible() -> None:
    match = _non_formal_match()
    match["competition_name"] = "方向未识别杯"

    try:
        render_report(_payload(match), output_format="text")
    except ValueError as exc:
        assert "forbidden term" in str(exc)
    else:
        raise AssertionError("expected forbidden term guard")
