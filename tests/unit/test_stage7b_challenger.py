from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from w2.models.challenger import (
    AuditSetFreeze,
    ChallengerFamily,
    ChallengerStatus,
    ForwardPredictionLedger,
    ForwardPredictionLock,
    stable_prediction_hash,
    validate_challenger_features,
)

NOW = datetime(2026, 6, 22, tzinfo=UTC)


def test_audit_set_freeze_and_hash_are_deterministic() -> None:
    first = AuditSetFreeze.from_fixture_ids(["b", "a"])
    second = AuditSetFreeze.from_fixture_ids(["a", "b"])
    assert first.status == "AUDIT_ONLY"
    assert first.fixture_ids == ("a", "b")
    assert first.manifest_sha256 == second.manifest_sha256


def test_market_fields_are_forbidden_for_challenger() -> None:
    validate_challenger_features({"elo_home": 1500.0, "elo_away": 1490.0})
    with pytest.raises(ValueError):
        validate_challenger_features({"market_probability_home": 0.5})


def test_forward_prediction_lock_append_only_and_kickoff_guard() -> None:
    prediction_hash = stable_prediction_hash(
        {"HOME": 0.34, "DRAW": 0.31, "AWAY": 0.35},
        "config",
    )
    lock = ForwardPredictionLock(
        fixture_id="fixture",
        kickoff_utc=NOW + timedelta(days=1),
        locked_at=NOW,
        as_of_time=NOW,
        data_cutoff=NOW,
        model_version="national_challenger_v1",
        prediction_hash=prediction_hash,
        decision=ChallengerStatus.WATCH,
    )
    ledger = ForwardPredictionLedger()
    ledger.append_lock(lock)
    with pytest.raises(ValueError):
        ledger.append_lock(lock)
    with pytest.raises(ValueError):
        ForwardPredictionLock(
            fixture_id="late",
            kickoff_utc=NOW,
            locked_at=NOW + timedelta(seconds=1),
            as_of_time=NOW + timedelta(seconds=1),
            data_cutoff=NOW,
            model_version="national_challenger_v1",
            prediction_hash=prediction_hash,
            decision=ChallengerStatus.WATCH,
        )


def test_challenger_family_contains_required_candidates() -> None:
    assert ChallengerFamily.REGULARIZED_MULTICLASS_LOGISTIC
    assert ChallengerFamily.GRADIENT_BOOSTING
    assert ChallengerFamily.ELO_POISSON_STACKING
    assert ChallengerFamily.CONSTRAINED_ENSEMBLE
