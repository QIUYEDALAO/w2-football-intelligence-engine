from __future__ import annotations

from w2.dashboard.day_view_projection import project_day_view_card
from w2.tracking.day_view_capture_index import DayViewCaptureSummary


def test_projection_uses_explicit_summary_without_spreading_capture() -> None:
    summary = DayViewCaptureSummary(
        fixture_id="1",
        captured_at="2026-07-16T09:00:00Z",
        kickoff_utc="2026-07-16T10:00:00Z",
        capture_hash="hash",
        decision_tier="WATCH",
        data_status="READY",
        lifecycle_status="DRAFT",
        outcome_tracked=False,
        lock_eligible=False,
        recommendation_id=None,
        reason_code=None,
        primary_blocker=None,
        primary_blocker_layer=None,
        action=None,
        next_eval_at=None,
        provider_budget_status="OK",
        pick=None,
        non_pick=None,
        current_odds={},
        analysis_readiness={},
        data_refresh={},
        compact_provenance={},
        direction_scorelines=(),
        scoreline_readiness={},
        audit_estimate_id=None,
        source="frozen_forward_capture",
    )
    card = project_day_view_card({"fixture_id": "1", "home_team_name": "A"}, summary)
    assert card["audit_capture_hash"] == "hash"
    assert card["home_team_name"] == "A"


def test_dayview_path_does_not_spread_raw_capture() -> None:
    import inspect

    from w2.dashboard import day_view_projection

    source = inspect.getsource(day_view_projection)
    assert "dict(capture)" not in source
    assert "**dict(capture)" not in source
