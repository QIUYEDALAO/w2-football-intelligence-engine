from __future__ import annotations

from w2.reporting import render_report


def _payload(*matches: dict[str, object]) -> dict[str, object]:
    return {
        "selected_football_day": "2026-06-30",
        "generated_at": "2026-06-30T23:40:00Z",
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
    assert "推荐比分" not in report
    assert "1-1 14%" not in report


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

    assert "状态：观察（正式推荐字段不完整）" in report
    assert "说明：正式推荐字段不完整，当前不输出方向。" in report
    assert "推荐：" not in report
    assert "推荐比分" not in report
    assert "方向未识别" not in report
    assert "全场让球，看 方向未识别" not in report


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
