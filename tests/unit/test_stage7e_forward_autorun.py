from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from w2.models.forward_autorun import (
    ForwardAutorunSettings,
    ForwardQuotaLedger,
    ForwardRuntimeGuard,
)


def test_autorun_settings_allow_only_local_or_staging() -> None:
    ForwardAutorunSettings(
        environment="local",
        autorun_enabled=True,
        network_enabled=True,
        deepseek_enabled=False,
        recommendation_enabled=False,
    ).validate()
    ForwardAutorunSettings(
        environment="staging",
        autorun_enabled=True,
        network_enabled=True,
        deepseek_enabled=False,
        recommendation_enabled=False,
    ).validate()
    with pytest.raises(ValueError, match="local or staging"):
        ForwardAutorunSettings(
            environment="production",
            autorun_enabled=True,
            network_enabled=True,
            deepseek_enabled=False,
            recommendation_enabled=False,
        ).validate()


def test_runtime_guard_rejects_deepseek_and_recommendation() -> None:
    with pytest.raises(ValueError, match="DeepSeek"):
        ForwardAutorunSettings(
            environment="local",
            autorun_enabled=True,
            network_enabled=True,
            deepseek_enabled=True,
            recommendation_enabled=False,
        ).validate()
    with pytest.raises(ValueError, match="recommendation"):
        ForwardAutorunSettings(
            environment="local",
            autorun_enabled=True,
            network_enabled=True,
            deepseek_enabled=False,
            recommendation_enabled=True,
        ).validate()


def test_quota_policy_uses_6000_daily_hard_limit_and_1500_reserve() -> None:
    settings = ForwardAutorunSettings(
        environment="local",
        autorun_enabled=True,
        network_enabled=True,
        deepseek_enabled=False,
        recommendation_enabled=False,
    )
    ledger = ForwardQuotaLedger(provider="api_football", usage_date=date(2026, 6, 22))
    assert ledger.available(settings, None) == 0
    assert ledger.available(settings, 1500) == 0
    assert ledger.available(settings, 2600) == 1000
    ledger.record(5900)
    assert ledger.available(settings, 7000) == 100


def test_quota_reset_uses_provider_reset_day() -> None:
    ledger = ForwardQuotaLedger(
        provider="api_football",
        usage_date=date(2026, 6, 21),
        requests_used=500,
    )
    ledger.reset_if_needed(datetime(2026, 6, 22, 1, 0, tzinfo=UTC))
    assert ledger.usage_date == date(2026, 6, 22)
    assert ledger.requests_used == 0


def test_circuit_breaker_and_no_overlap() -> None:
    settings = ForwardAutorunSettings(
        environment="local",
        autorun_enabled=True,
        network_enabled=True,
        deepseek_enabled=False,
        recommendation_enabled=False,
    )
    guard = ForwardRuntimeGuard(settings)
    assert guard.acquire() is True
    assert guard.acquire() is False
    guard.release()
    with pytest.raises(RuntimeError, match="HTTP_403"):
        guard.check_response(403, 7000)
