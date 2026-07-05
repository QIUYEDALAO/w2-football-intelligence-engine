from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from w2.matchday.orchestrator import build_matchday_controlled_run_plan

NOW = datetime(2026, 7, 5, 0, 0, tzinfo=UTC)
KICKOFF = NOW + timedelta(hours=25)


def _fixture(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "fixture_id": "fixture-1",
        "kickoff_utc": KICKOFF,
        "market": "ASIAN_HANDICAP",
        "line": "-0.25",
        "odds": "1.95",
    }
    payload.update(overrides)
    return payload


def _plan(
    *,
    fixtures: list[dict[str, object]] | None = None,
    environment: str = "staging",
    approve_provider_calls: bool = False,
    approve_db_writes: bool = False,
    approve_lock_write: bool = False,
    approve_settlement_write: bool = False,
) -> dict[str, object]:
    return build_matchday_controlled_run_plan(
        football_day=date(2026, 7, 5),
        environment=environment,
        as_of=NOW,
        fixtures=fixtures if fixtures is not None else [_fixture()],
        approve_provider_calls=approve_provider_calls,
        approve_db_writes=approve_db_writes,
        approve_lock_write=approve_lock_write,
        approve_settlement_write=approve_settlement_write,
        provider_allowed_endpoints=("status", "fixtures", "odds", "lineups"),
    )


def test_controlled_run_without_approvals_fails_closed() -> None:
    plan = _plan()

    assert plan["status"] == "APPROVAL_REQUIRED"
    assert plan["provider_calls"] == 0
    assert plan["db_writes"] == 0
    assert plan["would_enqueue"] is False
    assert plan["would_call_provider"] is False
    assert plan["would_write_db"] is False
    assert plan["would_write_lock"] is False
    assert plan["would_write_settlement"] is False
    assert plan["environment_policy"]["lock_policy"]["name"] == "staging_A"  # type: ignore[index]


def test_projected_provider_calls_require_provider_and_db_approval() -> None:
    plan = _plan()

    assert plan["projected_provider_calls"] > 0  # type: ignore[operator]
    assert plan["provider_call_approval_required"] is True
    assert plan["db_write_approval_required"] is True
    assert "PROVIDER_CALLS" in plan["required_approvals"]  # type: ignore[operator]
    assert "DB_WRITE" in plan["required_approvals"]  # type: ignore[operator]


def test_provider_approval_does_not_execute_provider_in_this_pr() -> None:
    plan = _plan(approve_provider_calls=True, approve_db_writes=True)

    assert plan["required_approvals"] == []
    assert plan["status"] == "EXECUTION_DEFERRED"
    assert plan["execution_plan"]["execution_deferred"] is True  # type: ignore[index]
    assert plan["execution_plan"]["would_execute"] is False  # type: ignore[index]
    assert plan["would_call_provider"] is False
    assert plan["provider_calls"] == 0


def test_lock_candidate_requires_lock_approval_without_writing_lock() -> None:
    plan = _plan(
        fixtures=[
            _fixture(
                recommendation_id="rec-1",
                lineups_available=True,
                xg_available=True,
                ratings_available=True,
                team_value_available=True,
            ),
        ],
        approve_provider_calls=True,
        approve_db_writes=True,
    )

    assert plan["lock_write_approval_required"] is True
    assert "STAGING_FORMAL_LOCK_CAPTURE_WRITE" in plan["required_approvals"]  # type: ignore[operator]
    assert plan["lock_candidates"] != []
    assert plan["would_write_lock"] is False


def test_production_analysis_pick_remains_not_lock_eligible() -> None:
    plan = _plan(
        environment="production",
        fixtures=[
            _fixture(
                recommendation_id="rec-1",
                lineups_available=True,
                xg_available=True,
                ratings_available=True,
                team_value_available=True,
            ),
        ],
    )
    fixture = plan["fixtures"][0]  # type: ignore[index]

    assert fixture["decision_tier"] == "ANALYSIS_PICK"
    assert fixture["lock_eligible"] is False
    assert plan["lock_candidates"] == []
    assert plan["environment_policy"]["lock_policy"]["name"] == "production_B"  # type: ignore[index]


def test_empty_controlled_run_has_no_required_approvals_or_side_effects() -> None:
    plan = _plan(fixtures=[])

    assert plan["projected_provider_calls"] == 0
    assert plan["required_approvals"] == []
    assert plan["provider_calls"] == 0
    assert plan["db_writes"] == 0
    assert plan["would_enqueue"] is False
    assert plan["settlement_write_approval_required"] is False
    assert plan["would_write_settlement"] is False
