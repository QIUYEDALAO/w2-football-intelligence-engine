from __future__ import annotations

from w2.domain.environment_policy import build_environment_policy_stamp


def test_staging_policy_stamp_is_staging_only_non_production_actionable() -> None:
    stamp = build_environment_policy_stamp("staging")

    assert stamp["environment"] == "staging"
    assert stamp["policy_version"] == "w2.environment_policy.v1"
    assert stamp["lock_policy"]["name"] == "staging_A"
    assert stamp["lock_policy"]["staging_only"] is True
    assert stamp["lock_policy"]["production_action_allowed"] is False
    assert stamp["actionability"]["ANALYSIS_PICK"] == "display_track_replay_only"
    assert "staging-only" in stamp["disclaimer"]
    assert "分析参考" in stamp["disclaimer"]
    assert "非稳赢" in stamp["disclaimer"]


def test_production_policy_stamp_is_recommend_only() -> None:
    stamp = build_environment_policy_stamp("production")

    assert stamp["environment"] == "production"
    assert stamp["lock_policy"]["name"] == "production_B"
    assert stamp["lock_policy"]["lock_eligible_policy"] == "recommend_only"
    assert stamp["lock_policy"]["production_action_allowed"] is True
    assert stamp["lock_policy"]["production_action_allowed_tiers"] == ["RECOMMEND"]
    assert "ANALYSIS_PICK 非正式可动作" in stamp["disclaimer"]
    assert "production 仅 RECOMMEND 可锁" in stamp["disclaimer"]


def test_unknown_environment_fails_safe_to_non_production_policy() -> None:
    stamp = build_environment_policy_stamp("qa")

    assert stamp["environment"] == "qa"
    assert stamp["lock_policy"]["name"] == "staging_A"
    assert stamp["lock_policy"]["production_action_allowed"] is False
    assert stamp["lock_policy"]["staging_only"] is True
