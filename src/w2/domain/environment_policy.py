from __future__ import annotations

from typing import Any

POLICY_VERSION = "w2.environment_policy.v1"
SOURCE = "w2.domain.environment_policy"


def build_environment_policy_stamp(environment: str) -> dict[str, Any]:
    """Build a side-effect-free policy stamp for public W2 outputs."""
    env = str(environment or "staging").strip().lower() or "staging"
    is_production = env == "production"
    if is_production:
        return {
            "environment": env,
            "policy_version": POLICY_VERSION,
            "lock_policy": {
                "name": "production_B",
                "lock_eligible_policy": "recommend_only",
                "production_action_allowed": True,
                "production_action_allowed_tiers": ["RECOMMEND"],
                "analysis_pick_label": "分析参考·非稳赢；production 动作需 RECOMMEND",
                "staging_only": False,
            },
            "actionability": {
                "ANALYSIS_PICK": "display_track_replay_only",
                "RECOMMEND": "production_action_candidate",
            },
            "disclaimer": "ANALYSIS_PICK 非正式可动作；production 仅 RECOMMEND 可锁",
            "source": SOURCE,
        }
    return {
        "environment": env,
        "policy_version": POLICY_VERSION,
        "lock_policy": {
            "name": "staging_A",
            "lock_eligible_policy": "completeness_gate",
            "production_action_allowed": False,
            "production_action_allowed_tiers": [],
            "analysis_pick_label": "分析参考·非稳赢",
            "staging_only": True,
        },
        "actionability": {
            "ANALYSIS_PICK": "display_track_replay_only",
            "RECOMMEND": "production_action_candidate",
        },
        "disclaimer": "staging-only；分析参考·非稳赢；非 production 可动作推荐",
        "source": SOURCE,
    }
