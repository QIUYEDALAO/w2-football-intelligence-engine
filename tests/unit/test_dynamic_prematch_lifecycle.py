from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine

from w2.infrastructure.database import Base
from w2.prematch.lifecycle import (
    DynamicEvaluationInput,
    DynamicEvaluationLedger,
    DynamicEvaluationState,
    LineupConfirmedEvent,
    classify_evaluation,
    select_t30_validation_snapshot,
)
from w2.prematch.repository import DynamicPrematchRepository

NOW = datetime(2026, 7, 22, 12, tzinfo=UTC)


def _evaluation(
    *,
    capture_id: str,
    ev: float,
    delta: float,
    ev_se: float,
    capture_at: datetime | None = None,
    **overrides: object,
) -> DynamicEvaluationInput:
    market_probability = 0.50
    values = {
        "fixture_id": "fixture-1",
        "market": "TOTALS",
        "selection": "OVER",
        "exact_line": 2.75,
        "bookmaker_id": "book-1",
        "capture_id": capture_id,
        "quote_identity_hash": f"quote-{capture_id}",
        "model_input_hash": "model-1",
        "evaluated_at": NOW,
        "checkpoint": "T-3h",
        "capture_at": capture_at or NOW,
        "model_probability": market_probability + delta,
        "market_probability": market_probability,
        "expected_value": ev,
        "ev_se": ev_se,
    }
    values.update(overrides)
    return DynamicEvaluationInput(**values)  # type: ignore[arg-type]


def test_new_capture_supersedes_old_and_same_capture_is_idempotent() -> None:
    ledger = DynamicEvaluationLedger()
    first = ledger.append(_evaluation(capture_id="c1", ev=0.08, delta=0.06, ev_se=0.02))
    assert first.state is DynamicEvaluationState.ANALYSIS_PICK_ACTIVE
    assert ledger.append(_evaluation(capture_id="c1", ev=0.08, delta=0.06, ev_se=0.02)) == first
    second = ledger.append(_evaluation(capture_id="c2", ev=0.01, delta=0.02, ev_se=0.03))
    assert second.state is DynamicEvaluationState.NO_EDGE_CURRENT
    payload = ledger.as_dict()
    assert len(payload["versions"]) == 2
    assert payload["versions"][0]["state"] == "SUPERSEDED"
    assert payload["versions"][1]["state"] == "NO_EDGE_CURRENT"


def test_no_edge_can_upgrade_and_active_can_become_stale() -> None:
    low = classify_evaluation(_evaluation(capture_id="c1", ev=0.02, delta=0.03, ev_se=0.01))
    high = classify_evaluation(_evaluation(capture_id="c2", ev=0.08, delta=0.07, ev_se=0.02))
    stale = classify_evaluation(
        _evaluation(capture_id="c3", ev=0.08, delta=0.07, ev_se=0.02, quote_fresh=False)
    )
    assert low.state is DynamicEvaluationState.NO_EDGE_CURRENT
    assert low.shortfall["delta"] == 0.02
    assert high.state is DynamicEvaluationState.ANALYSIS_PICK_ACTIVE
    assert stale.state is DynamicEvaluationState.STALE_PENDING_REFRESH


@pytest.mark.parametrize(
    ("ev", "delta", "ev_se", "blocker"),
    [
        (0.0, 0.06, -0.01, "EV_NOT_POSITIVE"),
        (0.05, 0.049, 0.01, "DELTA_BELOW_THRESHOLD"),
        (0.02, 0.06, 0.02, "EV_MINUS_SE_NOT_POSITIVE"),
    ],
)
def test_active_admission_requires_all_three_robust_gates(
    ev: float,
    delta: float,
    ev_se: float,
    blocker: str,
) -> None:
    version = classify_evaluation(
        _evaluation(capture_id=blocker, ev=ev, delta=delta, ev_se=ev_se)
    )
    assert version.state is DynamicEvaluationState.NO_EDGE_CURRENT
    assert blocker in version.blockers


@pytest.mark.parametrize(
    ("overrides", "expected_blocker"),
    [
        ({"identity_conflict": True}, "QUOTE_IDENTITY_CONFLICT"),
        ({"exact_quote_complete": False}, "PAIR_INCOMPLETE"),
        ({"model_input_hash": None}, "MODEL_OR_DEVIG_NOT_READY"),
    ],
)
def test_incomplete_quote_or_model_input_fails_closed(
    overrides: dict[str, object],
    expected_blocker: str,
) -> None:
    version = classify_evaluation(
        _evaluation(capture_id=expected_blocker, ev=0.08, delta=0.06, ev_se=0.02, **overrides)
    )
    assert version.state in {
        DynamicEvaluationState.NOT_READY_QUOTE_INCOMPLETE,
        DynamicEvaluationState.NOT_READY_MODEL_INPUT,
    }
    assert expected_blocker in version.blockers


def test_source_absent_has_public_copy_not_internal_term() -> None:
    version = classify_evaluation(
        _evaluation(
            capture_id="absent",
            ev=0.0,
            delta=0.0,
            ev_se=0.0,
            source_observations_present=False,
            exact_quote_complete=False,
            quote_identity_hash=None,
        )
    )
    assert version.state is DynamicEvaluationState.NOT_READY_SOURCE_ABSENT
    assert version.user_message == "当前采集窗口尚未取得完整盘口"
    assert version.next_action == "等待下一次受控采集"


def test_lineup_event_invalidates_old_input_until_post_lineup_quote() -> None:
    ledger = DynamicEvaluationLedger()
    ledger.append(_evaluation(capture_id="before", ev=0.08, delta=0.06, ev_se=0.02))
    confirmed_at = NOW + timedelta(minutes=1)
    event = LineupConfirmedEvent(
        fixture_id="fixture-1",
        captured_at=confirmed_at,
        lineup_input_hash="lineup-1",
        home_starters=11,
        away_starters=11,
        home_lineup_identity_hash="home",
        away_lineup_identity_hash="away",
    )
    ledger.confirm_lineup(event)
    pending = ledger.current_for("fixture-1", "TOTALS")
    assert pending is not None
    assert pending.state is DynamicEvaluationState.LINEUP_READY_MARKET_REFRESH_PENDING
    assert ledger.as_dict()["versions"][0]["supersession_reason"] == "LINEUP_INPUT_SUPERSEDED"

    after = ledger.append(
        _evaluation(
            capture_id="after",
            ev=0.04,
            delta=0.04,
            ev_se=0.02,
            evaluated_at=confirmed_at + timedelta(minutes=1),
            capture_at=confirmed_at + timedelta(minutes=1),
            lineup_confirmed_at=confirmed_at,
            lineup_input_hash="lineup-1",
            post_lineup_quote=True,
            model_input_hash="model-lineup-1",
        )
    )
    assert after.state is DynamicEvaluationState.NO_EDGE_CURRENT


def test_incomplete_confirmed_lineup_event_fails_closed() -> None:
    with pytest.raises(ValueError, match="STARTING_XI_INCOMPLETE"):
        LineupConfirmedEvent(
            fixture_id="fixture-1",
            captured_at=NOW,
            lineup_input_hash="lineup-incomplete",
            home_starters=10,
            away_starters=11,
            home_lineup_identity_hash="home",
            away_lineup_identity_hash="away",
        )


def test_t30_validation_is_time_selected_and_never_best_ev_selected() -> None:
    kickoff = NOW + timedelta(hours=2)
    snapshots = [
        {
            "capture_id": "closest-low-ev",
            "captured_at": kickoff - timedelta(minutes=30),
            "exact_quote_complete": True,
            "quote_fresh": True,
            "model_inputs_frozen": True,
            "expected_value": 0.01,
        },
        {
            "capture_id": "farther-high-ev",
            "captured_at": kickoff - timedelta(minutes=27),
            "exact_quote_complete": True,
            "quote_fresh": True,
            "model_inputs_frozen": True,
            "expected_value": 0.50,
        },
        {
            "capture_id": "post-kickoff",
            "captured_at": kickoff + timedelta(seconds=1),
            "exact_quote_complete": True,
            "quote_fresh": True,
            "model_inputs_frozen": True,
        },
    ]
    result = select_t30_validation_snapshot(snapshots, kickoff=kickoff)
    assert result.status == "READY"
    assert result.snapshot is not None
    assert result.snapshot["capture_id"] == "closest-low-ev"
    assert {item["reason"] for item in result.rejected} == {"POST_KICKOFF_REJECTED"}


def test_t30_excludes_outside_window_and_incomplete_inputs() -> None:
    kickoff = NOW + timedelta(hours=2)
    result = select_t30_validation_snapshot(
        [
            {
                "capture_id": "too-early",
                "captured_at": kickoff - timedelta(minutes=40),
                "exact_quote_complete": True,
                "quote_fresh": True,
                "model_inputs_frozen": True,
            },
            {
                "capture_id": "incomplete",
                "captured_at": kickoff - timedelta(minutes=30),
                "exact_quote_complete": False,
                "quote_fresh": True,
                "model_inputs_frozen": True,
            },
        ],
        kickoff=kickoff,
    )
    assert result.status == "LOCK_SNAPSHOT_UNAVAILABLE"
    assert result.snapshot is None
    assert {item["reason"] for item in result.rejected} == {
        "OUTSIDE_T30_WINDOW",
        "PAIR_INCOMPLETE",
    }


def test_db_lifecycle_is_append_only_and_t30_freezes_once() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = DynamicPrematchRepository(engine)
    first = classify_evaluation(_evaluation(capture_id="c1", ev=0.08, delta=0.06, ev_se=0.02))
    second = classify_evaluation(_evaluation(capture_id="c2", ev=0.01, delta=0.02, ev_se=0.03))
    assert repository.append_evaluation(first)[1]
    assert not repository.append_evaluation(first)[1]
    assert repository.append_evaluation(second)[1]
    lifecycle = repository.lifecycle("fixture-1")
    assert [row["state"] for row in lifecycle["versions"]] == ["SUPERSEDED", "NO_EDGE_CURRENT"]

    kickoff = NOW + timedelta(hours=2)
    lock = select_t30_validation_snapshot(
        [
            {
                "capture_id": "lock-1",
                "captured_at": kickoff - timedelta(minutes=30),
                "exact_quote_complete": True,
                "quote_fresh": True,
                "model_inputs_frozen": True,
            }
        ],
        kickoff=kickoff,
    )
    assert repository.freeze_t30_snapshot("fixture-1", lock)
    assert not repository.freeze_t30_snapshot("fixture-1", lock)
