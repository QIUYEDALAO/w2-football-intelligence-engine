from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from w2.domain.enums import SettlementOutcome
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.markets.historical_dataset import (
    ah_walk_forward,
    detect_snapshot_semantics,
    normalize_api_football_odds_payload,
    normalize_w1_local_odds,
    normalize_w1_snapshot_jsonl,
    phase_coverage,
    validate_observations,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/gate3"


def test_w1_local_odds_are_closing_only_and_not_captured_at() -> None:
    path = FIXTURES / "w1_local_odds_sample.csv"
    observations = normalize_w1_local_odds(path)

    assert observations
    assert {item.snapshot_semantics for item in observations} == {"CLOSING"}
    assert all(item.captured_at is None for item in observations)
    assert detect_snapshot_semantics(path, [item.__dict__ for item in observations]) == "CLOSING"


def test_w1_snapshot_jsonl_deduplicates_and_quarantines_post_kickoff_rows() -> None:
    observations = normalize_w1_snapshot_jsonl(FIXTURES / "w1_snapshot_sample.jsonl")

    assert len(observations) == 3
    semantics = {item.snapshot_semantics for item in observations}
    assert "CAPTURED_AT" in semantics
    assert "INVALID_OR_UNUSABLE" in semantics
    assert validate_observations(observations)["status"] == "PASS"


def test_api_payload_adapter_requires_explicit_captured_at_not_mtime() -> None:
    observations = normalize_api_football_odds_payload(
        FIXTURES / "api_odds_sample.json",
        captured_at=None,
        kickoff_utc="2026-06-20T12:00:00Z",
    )

    assert observations
    assert {item.snapshot_semantics for item in observations} == {"INVALID_OR_UNUSABLE"}
    assert all(item.captured_at is None for item in observations)


def test_phase_coverage_excludes_closing_from_t24() -> None:
    closing = normalize_w1_local_odds(FIXTURES / "w1_local_odds_sample.csv")
    captured = normalize_w1_snapshot_jsonl(FIXTURES / "w1_snapshot_sample.jsonl")
    coverage = phase_coverage(closing + captured)

    assert coverage["excluded_closing_leakage_count"] == 0
    assert coverage["phases"]["T-24h"]["observation_count"] == 0
    assert coverage["phases"]["T-1h"]["observation_count"] > 0
    assert coverage["phases"]["Closing"]["observation_count"] > 0


def test_ah_and_ou_quarter_settlement_semantics() -> None:
    assert settle_asian_handicap(3, 0, "HOME", Decimal("-2.75")) == SettlementOutcome.HALF_WIN
    assert settle_asian_handicap(3, 0, "AWAY", Decimal("2.75")) == SettlementOutcome.HALF_LOSS
    assert settle_asian_handicap(2, 0, "AWAY", Decimal("2")) == SettlementOutcome.PUSH
    assert settle_total_goals(3, "OVER", Decimal("2.75")) == SettlementOutcome.HALF_WIN
    assert settle_total_goals(3, "UNDER", Decimal("3.25")) == SettlementOutcome.HALF_WIN


def test_no_result_ah_returns_real_no_data_blocker() -> None:
    observations = normalize_w1_snapshot_jsonl(FIXTURES / "w1_snapshot_sample.jsonl")
    output = ah_walk_forward(observations)

    assert output["status"] == "NO_USABLE_INTERNAL_HISTORICAL_AH_DATA"
    assert output["fixture_count"] == 0
    assert output["candidate"] is False
    assert output["formal_recommendation"] is False
