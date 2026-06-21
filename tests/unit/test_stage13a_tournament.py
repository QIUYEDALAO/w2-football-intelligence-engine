from __future__ import annotations

from datetime import UTC
from pathlib import Path

from w2.operations.tournament import (
    ContextValidationStatus,
    build_importance_context,
    build_match_context,
    build_operations_plan,
    load_tournament_profile,
)

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "config/competitions/world_cup_2026.v1.json"


def test_world_cup_profile_schema_and_strategy_unavailable() -> None:
    profile = load_tournament_profile(PROFILE)
    assert profile.competition_id == "world_cup_2026"
    assert profile.strategy_version == "NOT_AVAILABLE_GATE4"
    assert len(profile.groups) == 12
    assert profile.knockout_rounds[-1].penalties_enabled is True
    assert profile.freeze_policy["upgrade_requires_new_version"] is True


def test_group_knockout_and_result_semantics() -> None:
    profile = load_tournament_profile(PROFILE)
    group = next(stage for stage in profile.stages if stage.stage_id == "group")
    knockout = next(stage for stage in profile.stages if stage.stage_id == "knockout")
    assert group.result_semantics == "90_MINUTES_ONLY"
    assert "EXTRA_TIME" in knockout.result_semantics
    assert "PENALTIES" in knockout.result_semantics


def test_phase_plan_and_neutral_site_context() -> None:
    profile = load_tournament_profile(PROFILE)
    row = {
        "fixture_uuid": "fixture-demo",
        "competition": "WorldCup2026",
        "match_date": "2026-06-20",
        "neutral_site": True,
    }
    match = build_match_context(row, profile)
    assert match.kickoff_utc.tzinfo == UTC
    assert match.neutral_site is True
    plan = build_operations_plan(profile, [row])
    assert len(plan) == 1
    assert len(plan[0]["phase_plan"]) == len(profile.operations_schedule.collection_phases)
    assert plan[0]["watch_skip_lock_windows"][0]["phase"] == "T-24h"


def test_importance_context_is_explanatory_only() -> None:
    profile = load_tournament_profile(PROFILE)
    match = build_match_context(
        {
            "fixture_uuid": "fixture-demo",
            "competition": "WorldCup2026",
            "match_date": "2026-06-20",
            "neutral_site": False,
        },
        profile,
    )
    context = build_importance_context(match)
    assert context.validation_status == ContextValidationStatus.EXPLANATORY_ONLY_UNVALIDATED
    assert context.model_feature_enabled is False
