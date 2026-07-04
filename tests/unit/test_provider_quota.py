from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from w2.api.repository import ReadModelService
from w2.ingestion.quota_budget import independent_signal_quota_decision
from w2.providers.quota import (
    api_football_quota_policy,
    parse_api_football_quota,
    provider_daily_hard_cap_decision,
    quota_guard_decision,
)

NOW = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)


class ProviderStatusRepository:
    def __init__(self, remaining_quota: Any) -> None:
        self.remaining_quota = remaining_quota

    def dashboard_provider(self) -> dict[str, Any]:
        return {
            "provider": "api_football",
            "status": "READY",
            "remaining_quota": self.remaining_quota,
            "credential_status": "PRESENT",
            "last_request_status": 200,
        }


def test_daily_and_burst_are_separated() -> None:
    quota = parse_api_football_quota(
        headers={
            "x-ratelimit-remaining": "299",
            "x-ratelimit-requests-remaining": "6774",
        },
        payload={},
        observed_at=NOW,
    )

    assert quota.daily_remaining == 6774
    assert quota.burst_remaining == 299
    assert quota.daily_source == "x-ratelimit-requests-remaining"
    assert quota.burst_source == "x-ratelimit-remaining"


def test_daily_below_reserve_can_be_detected_with_burst_present() -> None:
    quota = parse_api_football_quota(
        headers={
            "x-ratelimit-requests-remaining": "1499",
            "x-ratelimit-remaining": "299",
        },
        payload={},
        observed_at=NOW,
    )

    assert quota.daily_remaining == 1499
    assert quota.burst_remaining == 299


def test_burst_only_does_not_fill_daily_quota() -> None:
    quota = parse_api_football_quota(
        headers={"x-ratelimit-remaining": "299"},
        payload={},
        observed_at=NOW,
    )

    assert quota.daily_remaining is None
    assert quota.burst_remaining == 299
    assert quota.daily_source is None


def test_header_order_does_not_change_daily_and_burst_meaning() -> None:
    first = parse_api_football_quota(
        headers={
            "x-ratelimit-remaining": "299",
            "x-apisports-requests-remaining": "6774",
        },
        payload={},
        observed_at=NOW,
    )
    second = parse_api_football_quota(
        headers={
            "x-apisports-requests-remaining": "6774",
            "x-ratelimit-remaining": "299",
        },
        payload={},
        observed_at=NOW,
    )

    assert first == second


def test_status_payload_can_supply_daily_quota() -> None:
    quota = parse_api_football_quota(
        headers={"x-ratelimit-remaining": "299"},
        payload={"response": {"requests": {"remaining": "6774"}}},
        observed_at=NOW,
    )

    assert quota.daily_remaining == 6774
    assert quota.daily_source == "response.requests.remaining"
    assert quota.burst_remaining == 299


def test_header_limit_is_parsed_on_the_same_basis_as_remaining() -> None:
    quota = parse_api_football_quota(
        headers={
            "x-ratelimit-requests-remaining": "90",
            "x-ratelimit-requests-limit": "100",
        },
        payload={},
        observed_at=NOW,
    )

    assert quota.daily_remaining == 90
    assert quota.daily_limit == 100
    assert quota.daily_source == "x-ratelimit-requests-remaining"
    assert quota.daily_limit_source == "x-ratelimit-requests-limit"


def test_status_payload_can_supply_daily_limit() -> None:
    quota = parse_api_football_quota(
        headers={"x-ratelimit-remaining": "299"},
        payload={"response": {"requests": {"remaining": "90", "limit": "100"}}},
        observed_at=NOW,
    )

    assert quota.daily_remaining == 90
    assert quota.daily_limit == 100
    assert quota.daily_source == "response.requests.remaining"
    assert quota.daily_limit_source == "response.requests.limit"
    assert quota.burst_remaining == 299


def test_api_football_quota_policy_freezes_w2_default_budget() -> None:
    policy = api_football_quota_policy(6774)

    assert policy["daily_budget"] == 7500
    assert policy["reserve_bucket"] == 1500
    assert policy["available_after_reserve"] == 5274
    assert policy["reserve_locked"] is False
    assert policy["upgrade_evaluation_daily_budget"] == 75000
    assert policy["upgrade_enabled"] is False


def test_api_football_quota_policy_handles_unknown_remaining_quota() -> None:
    for remaining_quota in (None,):
        policy = api_football_quota_policy(remaining_quota)

        assert policy["daily_budget"] == 7500
        assert policy["reserve_bucket"] == 1500
        assert policy["available_after_reserve"] is None
        assert policy["reserve_locked"] is None
        assert policy["upgrade_evaluation_daily_budget"] == 75000
        assert policy["upgrade_enabled"] is False


def test_invalid_remaining_quota_values_parse_as_unknown() -> None:
    unknown = parse_api_football_quota(
        headers={"x-ratelimit-requests-remaining": "UNKNOWN"},
        payload={},
        observed_at=NOW,
    )
    empty = parse_api_football_quota(
        headers={"x-ratelimit-requests-remaining": ""},
        payload={},
        observed_at=NOW,
    )

    assert unknown.daily_remaining is None
    assert empty.daily_remaining is None
    assert api_football_quota_policy(unknown.daily_remaining)["reserve_locked"] is None
    assert api_football_quota_policy(empty.daily_remaining)["available_after_reserve"] is None


def test_provider_status_handles_unknown_empty_and_null_remaining_quota() -> None:
    for raw_remaining_quota in ("UNKNOWN", "", None):
        service = ReadModelService(
            repository=ProviderStatusRepository(raw_remaining_quota)  # type: ignore[arg-type]
        )

        status = service.provider_status()

        assert status["remaining_quota"] is None
        assert status["quota_policy"]["available_after_reserve"] is None
        assert status["quota_policy"]["reserve_locked"] is None


def test_quota_guard_blocks_backfill_before_it_reaches_live_reserve() -> None:
    decision = quota_guard_decision(remaining_quota=1499, task_type="xg_backfill")

    assert decision["allowed"] is False
    assert decision["blocker"] == "BACKFILL_QUOTA_GUARD"
    assert decision["mode"] == "BACKFILL_STOPPED"
    assert decision["reserve_locked"] is True


def test_quota_guard_keeps_core_matchday_tasks_available_at_low_quota() -> None:
    assert quota_guard_decision(remaining_quota=700, task_type="odds")["allowed"] is True
    assert quota_guard_decision(remaining_quota=700, task_type="lineups")["allowed"] is True

    blocked = quota_guard_decision(remaining_quota=700, task_type="statistics")
    assert blocked["allowed"] is False
    assert blocked["blocker"] == "QUOTA_CRITICAL_CORE_ONLY"
    assert blocked["mode"] == "CORE_ONLY"


def test_quota_guard_blocks_unknown_or_exhausted_quota() -> None:
    assert quota_guard_decision(remaining_quota=None, task_type="odds")["blocker"] == (
        "DAILY_QUOTA_UNKNOWN"
    )
    assert quota_guard_decision(remaining_quota=0, task_type="lineups")["blocker"] == (
        "DAILY_QUOTA_EXHAUSTED"
    )


def test_provider_daily_hard_cap_blocks_before_exceeding_reserve() -> None:
    decision = provider_daily_hard_cap_decision(
        actual_calls_today=6000,
        planned_calls=100,
        daily_cap=7500,
        reserve_bucket=1500,
    )

    assert decision["allowed"] is False
    assert decision["blocker"] == "PROVIDER_RESERVE_PROTECTED"
    assert decision["projected_total"] == 6100
    assert decision["remaining_after_plan"] == 1400


def test_provider_daily_hard_cap_blocks_exhaustion() -> None:
    decision = provider_daily_hard_cap_decision(
        actual_calls_today=7495,
        planned_calls=10,
        daily_cap=7500,
        reserve_bucket=0,
    )

    assert decision["allowed"] is False
    assert decision["blocker"] == "DAILY_PROVIDER_HARD_CAP_EXCEEDED"


def test_independent_signal_budget_allows_only_prematch_when_quota_unknown() -> None:
    assert independent_signal_quota_decision(
        remaining_quota=None,
        task_type="prematch_odds",
    )["allowed"] is True
    blocked = independent_signal_quota_decision(
        remaining_quota="UNKNOWN",
        task_type="team_fixture_history_backfill",
    )

    assert blocked["allowed"] is False
    assert blocked["reason"] == "DAILY_QUOTA_UNKNOWN"


def test_independent_signal_budget_protects_reserve_and_core_only_thresholds() -> None:
    for task_type in (
        "team_fixture_history_backfill",
        "h2h_backfill",
        "squad_value_mapping",
        "ratings_backfill",
    ):
        assert independent_signal_quota_decision(
            remaining_quota=1499,
            task_type=task_type,
        )["allowed"] is False
        critical = independent_signal_quota_decision(
            remaining_quota=749,
            task_type=task_type,
        )
        assert critical["allowed"] is False
        assert critical["mode"] == "CORE_ONLY"

    assert independent_signal_quota_decision(
        remaining_quota=749,
        task_type="prematch_lineups",
    )["allowed"] is True
    assert independent_signal_quota_decision(
        remaining_quota=6774,
        task_type="h2h_backfill",
    )["allowed"] is True
