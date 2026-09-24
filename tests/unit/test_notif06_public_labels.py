from __future__ import annotations

from w2.identity.public_competition_labels import public_competition_labels
from w2.identity.public_team_labels import reviewed_public_team_labels
from w2.prematch.candidate_notifications import (
    DAILY_CANDIDATE_LIST,
    _competition_zh_name,
    render_bark_message,
)


def test_competition_labels_cover_all_28_leagues() -> None:
    labels = public_competition_labels()
    assert len(labels) >= 28
    # 7 个此前显示英文代号的新联赛
    assert labels["germany_2_bundesliga"] == "德乙"
    assert labels["denmark_superliga"] == "丹超"
    assert labels["austria_bundesliga"] == "奥甲"
    assert labels["netherlands_eerste_divisie"] == "荷乙"
    assert labels["croatia_hnl"] == "克甲"
    assert labels["italy_serie_b"] == "意乙"
    assert labels["belgium_jupiler_pro_league"] == "比甲"
    # 老联赛仍中文
    assert labels["premier_league"] == "英超"
    assert labels["england_championship"] == "英冠"
    assert labels["spain_segunda_division"] == "西乙"


def test_competition_zh_name_falls_back_to_id_when_missing() -> None:
    assert _competition_zh_name("germany_2_bundesliga") == "德乙"
    assert _competition_zh_name("no_such_league") == "no_such_league"
    assert _competition_zh_name(None) == "未知联赛"


def test_reviewed_team_labels_include_bayern_and_union() -> None:
    labels = reviewed_public_team_labels()
    assert labels.get("w2:team:api_football:157") == "拜仁慕尼黑"
    assert labels.get("w2:team:api_football:182") == "柏林联合"


def test_daily_candidate_list_title_uses_design_copy() -> None:
    payload = {
        "event_type": DAILY_CANDIDATE_LIST,
        "football_day": "2026-09-18",
        "match_count": 28,
        "matches": [],
        "dashboard_url": "",
    }
    rendered = render_bark_message(payload)
    assert rendered["title"] == "[今日候选] 9月18日 共 28 场待评估"
