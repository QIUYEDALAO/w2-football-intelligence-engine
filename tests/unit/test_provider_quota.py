from __future__ import annotations

from datetime import UTC, datetime

from w2.providers.quota import parse_api_football_quota

NOW = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)


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
