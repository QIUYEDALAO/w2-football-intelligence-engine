from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from w2.backtest.replay import (
    AsOfDataRepository,
    EventOrderingPolicy,
    FeatureBuildStep,
    ModelLoadStep,
    PredictionStep,
    ReplayEvent,
    ReplayEventType,
    ReplayLedger,
    assert_fixture_split_integrity,
    chronological_holdout,
    expanding_window,
    rolling_window,
    stable_hash,
    walk_forward,
)
from w2.domain.enums import SettlementOutcome
from w2.domain.odds import settle_asian_handicap

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def event(event_id: str, sequence: int, fixture_id: str = "fixture") -> ReplayEvent:
    return ReplayEvent(
        event_id=event_id,
        fixture_id=fixture_id,
        event_time=NOW,
        event_type=ReplayEventType.PREDICTION,
        sequence=sequence,
    )


def test_event_ordering_and_deterministic_hash() -> None:
    ordered = EventOrderingPolicy().order([event("b", 1), event("a", 1), event("c", 0)])
    assert [item.event_id for item in ordered] == ["c", "a", "b"]
    assert stable_hash({"b": 2, "a": 1}) == stable_hash({"a": 1, "b": 2})


def test_future_and_closing_leakage_guards() -> None:
    repo = AsOfDataRepository(
        {
            "fixture": {
                "kickoff_utc": NOW.isoformat(),
                "snapshot_semantics": "CAPTURED_AT",
                "prediction_phase": "T-1h",
                "features": {},
            },
            "closing": {
                "kickoff_utc": NOW.isoformat(),
                "snapshot_semantics": "CLOSING",
                "prediction_phase": "T-1h",
                "features": {},
            },
        }
    )
    with pytest.raises(ValueError):
        repo.read_as_of("fixture", NOW + timedelta(minutes=1))
    with pytest.raises(ValueError):
        repo.read_as_of("closing", NOW - timedelta(hours=1))
    with pytest.raises(ValueError):
        FeatureBuildStep().run({"features": {"home_goals": 1}})


def test_version_mismatch_prediction_and_idempotent_ledger() -> None:
    with pytest.raises(ValueError):
        ModelLoadStep().run(model_version="wrong", expected_version="stage7.v1")
    with pytest.raises(ValueError):
        PredictionStep().run({"HOME": 0.4, "DRAW": 0.4, "AWAY": 0.3})
    ledger = ReplayLedger()
    replay_event = event("prediction", 1)
    ledger.append_once(replay_event, {"decision": "WATCH"})
    ledger.append_once(replay_event, {"decision": "WATCH"})
    assert len(ledger.records) == 1


def test_splitters_and_fixture_split_guard() -> None:
    fixtures = [f"f{i}" for i in range(20)]
    assert chronological_holdout(fixtures)["test"]
    assert rolling_window(fixtures, train_size=5, test_size=3)
    assert expanding_window(fixtures, min_train_size=5, test_size=3)
    assert walk_forward(fixtures, initial_train_size=5, step_size=3)
    with pytest.raises(ValueError):
        assert_fixture_split_integrity(
            {"s1": "fixture", "s2": "fixture"},
            {"s1": "train", "s2": "test"},
        )


def test_ah_settlement_functional_replay() -> None:
    assert settle_asian_handicap(1, 1, "HOME", Decimal("-0.25")) == SettlementOutcome.HALF_LOSS
