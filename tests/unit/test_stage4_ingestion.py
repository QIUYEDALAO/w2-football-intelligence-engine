from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from w2.domain.enums import MarketType
from w2.ingestion.freshness import FreshnessEvaluator
from w2.ingestion.ports import API_FOOTBALL_ENDPOINTS, ProviderRequest
from w2.ingestion.quota import QuotaManager, QuotaPolicy
from w2.ingestion.raw_store import RawPayloadStore, payload_sha256
from w2.ingestion.retry import CircuitBreaker, CircuitOpenError, RetryPolicy, call_with_retry
from w2.ingestion.scheduler import SNAPSHOT_PHASES, build_snapshot_schedule
from w2.ingestion.service import IngestionService
from w2.normalization.api_football import ApiFootballNormalizer, parse_datetime
from w2.providers.api_football import ApiFootballClient, LiveNetworkDisabledError

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "fixtures/provider/api_football/offline_gate2_fixture.json"
CAPTURED_AT = datetime(2026, 6, 22, 1, 0, tzinfo=UTC)


def load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_each_api_football_endpoint_adapter_parses_fixture_shape() -> None:
    client = ApiFootballClient()
    payload = {"response": [{"synthetic": True}]}
    for endpoint in API_FOOTBALL_ENDPOINTS:
        assert client.parse_fixture(endpoint, payload) == [{"synthetic": True}]


def test_network_is_disabled_without_explicit_live_and_stage4_blocks_live() -> None:
    client = ApiFootballClient()
    with pytest.raises(LiveNetworkDisabledError):
        client.fetch(ProviderRequest(endpoint="fixtures", params={}))
    with pytest.raises(LiveNetworkDisabledError):
        ApiFootballClient(allow_live=True).fetch(
            ProviderRequest(endpoint="fixtures", params={}, live=True)
        )


def test_retry_backoff_and_circuit_breaker() -> None:
    calls = {"count": 0}
    delays: list[float] = []

    def flaky() -> str:
        calls["count"] += 1
        if calls["count"] < 2:
            raise TimeoutError("synthetic timeout")
        return "ok"

    result = call_with_retry(
        flaky,
        RetryPolicy(max_attempts=3, base_delay_seconds=1, multiplier=2),
        CircuitBreaker(failure_threshold=3),
        sleep=delays.append,
    )
    assert result == "ok"
    assert delays == [1]

    breaker = CircuitBreaker(failure_threshold=1)
    with pytest.raises(CircuitOpenError):
        call_with_retry(lambda: (_ for _ in ()).throw(TimeoutError()), RetryPolicy(), breaker)
    with pytest.raises(CircuitOpenError):
        breaker.before_call()


def test_raw_payload_hash_and_append_only_idempotency() -> None:
    store = RawPayloadStore()
    payload = {"response": [{"id": 1}]}
    first = store.save(
        provider="api_football",
        endpoint="fixtures",
        payload=payload,
        captured_at=CAPTURED_AT,
    )
    second = store.save(
        provider="api_football",
        endpoint="fixtures",
        payload=payload,
        captured_at=CAPTURED_AT,
    )
    assert first.reference.sha256 == payload_sha256(payload)
    assert first.reference.id == second.reference.id
    assert store.count() == 1
    with pytest.raises(TypeError):
        first.payload["changed"] = True


def test_quota_priority_and_degrade_rules_are_configured() -> None:
    manager = QuotaManager(
        QuotaPolicy(daily_limit=2, reserve_for_high_priority=1, degrade_after_remaining=1)
    )
    assert manager.allow("fixtures", priority=1)
    assert not manager.allow("statistics", priority=9)
    assert manager.allow("odds", priority=1)
    assert not manager.allow("fixtures", priority=1)


def test_snapshot_scheduler_phases_and_closing() -> None:
    kickoff = datetime(2026, 6, 22, 18, 0, tzinfo=UTC)
    jobs = build_snapshot_schedule("fixture-1", kickoff)
    assert [job.phase for job in jobs] == list(SNAPSHOT_PHASES)
    assert jobs[0].scheduled_for == kickoff - timedelta(hours=72)
    assert jobs[-1].phase == "Closing"
    assert jobs[-1].closing is True


def test_normalizer_preserves_bookmakers_and_market_canonicalization() -> None:
    payload = load_fixture()
    odds_payload = payload["odds"]
    normalized = ApiFootballNormalizer().normalize_odds_payload(
        odds_payload,  # type: ignore[arg-type]
        captured_at=CAPTURED_AT,
    )
    bookmaker_ids = {item.bookmaker_id for item in normalized.odds_observations}
    assert len(bookmaker_ids) == 2
    assert {item.market for item in normalized.odds_observations} == {
        MarketType.ONE_X_TWO,
        MarketType.TOTALS,
        MarketType.ASIAN_HANDICAP,
        MarketType.BTTS,
    }
    assert all(item.decimal_odds > Decimal("1") for item in normalized.odds_observations)


def test_pre_match_odds_after_kickoff_are_rejected() -> None:
    payload = load_fixture()
    with pytest.raises(ValueError):
        ApiFootballNormalizer().normalize_odds_payload(
            payload["odds"],  # type: ignore[arg-type]
            captured_at=parse_datetime("2026-06-22T19:00:00+00:00"),
        )


def test_raw_normalized_feature_replay_idempotency_and_freshness() -> None:
    payload = load_fixture()
    service = IngestionService(freshness_evaluator=FreshnessEvaluator(threshold_seconds=60))
    first = service.replay_api_football_payload(
        endpoint="odds",
        payload=payload["odds"],  # type: ignore[arg-type]
        captured_at=CAPTURED_AT,
        now=parse_datetime("2026-06-22T02:00:00+00:00"),
    )
    replay = service.replay_api_football_payload(
        endpoint="odds",
        payload=payload["odds"],  # type: ignore[arg-type]
        captured_at=CAPTURED_AT,
        now=parse_datetime("2026-06-22T02:00:00+00:00"),
    )
    assert first.raw.reference.sha256 == replay.raw.reference.sha256
    assert len(first.odds_observations) == 4
    assert replay.odds_observations == []
    assert first.gate2_status == "PROVISIONAL"
    assert first.freshness_alerts


def test_first_seen_opening_and_closing_semantics_are_not_conflated() -> None:
    jobs = build_snapshot_schedule("fixture-1", datetime(2026, 6, 22, 18, 0, tzinfo=UTC))
    assert jobs[0].phase == "T-72h"
    assert jobs[0].closing is False
    assert jobs[-1].phase == "Closing"
    assert jobs[-1].closing is True
