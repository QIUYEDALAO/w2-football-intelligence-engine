from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import (
    CURRENT_SERIALIZER_VERSION,
    HashDomain,
    canonical_sha256,
)
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
    DynamicPrematchSupersessionModel,
    LineupConfirmedEventModel,
)
from w2.infrastructure.persistence.matchday_intake_models import MatchdayFixtureIdentityModel
from w2.prematch.lifecycle import (
    DYNAMIC_EVALUATION_V2_SCHEMA,
    DYNAMIC_EVALUATION_V3_SCHEMA,
    MODEL_FORECAST_DENOMINATOR_SCOPE,
    DynamicEvaluationInput,
    DynamicEvaluationLedger,
    DynamicEvaluationState,
    LineupConfirmedEvent,
    classify_evaluation,
    select_t30_validation_snapshot,
)
from w2.prematch.repository import (
    DynamicPrematchRepository,
    project_exact_eval_02b_pairs,
)

NOW = datetime(2026, 7, 22, 12, tzinfo=UTC)
PAIR_NOW = datetime(2026, 8, 1, 10, tzinfo=UTC)
PAIR_EVENT_AT = PAIR_NOW + timedelta(hours=1)
PAIR_KICKOFF = PAIR_NOW + timedelta(hours=2)
PAIR_STATES = {
    "WIN": 0.40,
    "HALF_WIN": 0.10,
    "PUSH": 0.10,
    "HALF_LOSS": 0.10,
    "LOSS": 0.30,
}


def test_denominator_evaluation_persists_real_write_time_and_gate_attribution() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    version = classify_evaluation(
        DynamicEvaluationInput(
            fixture_id="1494246",
            market="TOTALS",
            selection="UNRESOLVED",
            exact_line=None,
            bookmaker_id=None,
            capture_id=None,
            quote_identity_hash=None,
            model_input_hash="model",
            evaluated_at=NOW,
            checkpoint="T-30m_VALIDATION_LOCK",
            source_observations_present=False,
            quote_fresh=False,
            model_ready=True,
            # declared so this test keeps isolating quote and mainline attribution;
            # the calibration gate has its own tests
            calibration_status="PRODUCTION_VALIDATED",
            market_probability_ready=False,
            schema_version=DYNAMIC_EVALUATION_V3_SCHEMA,
            competition_id="113",
            season="2026",
            provider="api_football",
            denominator_scope=MODEL_FORECAST_DENOMINATOR_SCOPE,
        )
    )

    persisted, created = DynamicPrematchRepository(engine).append_evaluation(version)

    assert created is True
    assert persisted.recorded_at is not None
    assert persisted.recorded_at > persisted.evaluated_at
    assert persisted.first_failed_gate == "MAINLINE_PARSED"
    assert persisted.all_failed_gates == (
        "MAINLINE_PARSED",
        "BOOKMAKER_DEPTH",
        "QUOTE_FRESH",
        "EVALUATION_COMPLETE",
    )
    with Session(engine) as session:
        row = session.get(DynamicPrematchEvaluationModel, persisted.evaluation_id)
        assert row is not None
        assert row.recorded_at is not None
        assert row.gate_results == persisted.gate_results


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
        # A well-formed evaluation now declares where its probability came from.
        # Tests about the EV gates say so explicitly; the calibration gate itself
        # is covered by its own tests below.
        "calibration_status": "PRODUCTION_VALIDATED",
    }
    values.update(overrides)
    return DynamicEvaluationInput(**values)  # type: ignore[arg-type]


def _lineup_event(**overrides: object) -> LineupConfirmedEvent:
    values = {
        "fixture_id": "fixture-1",
        "competition_id": "competition-1",
        "season": "2026",
        "captured_at": NOW,
        "lineup_input_hash": "lineup-1",
        "home_starters": 11,
        "away_starters": 11,
        "home_lineup_identity_hash": "home",
        "away_lineup_identity_hash": "away",
        "source_capture_id": "capture-lineup-1",
        "raw_sha256": "a" * 64,
    }
    values.update(overrides)
    return LineupConfirmedEvent(**values)  # type: ignore[arg-type]


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
    version = classify_evaluation(_evaluation(capture_id=blocker, ev=ev, delta=delta, ev_se=ev_se))
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


def test_v2_persists_exact_identity_and_five_state_distribution() -> None:
    distribution = {
        "WIN": 0.48,
        "HALF_WIN": 0.10,
        "PUSH": 0.02,
        "HALF_LOSS": 0.10,
        "LOSS": 0.30,
    }
    version = classify_evaluation(
        _evaluation(
            capture_id="v2",
            ev=0.08,
            delta=0.06,
            ev_se=0.02,
            schema_version=DYNAMIC_EVALUATION_V2_SCHEMA,
            competition_id="competition-1",
            season="2026",
            provider="api_football",
            model_settlement_distribution=distribution,
        )
    )

    payload = version.as_dict()
    assert payload["schema_version"] == DYNAMIC_EVALUATION_V2_SCHEMA
    assert payload["competition_id"] == "competition-1"
    assert payload["season"] == "2026"
    assert payload["provider"] == "api_football"
    assert payload["lineup_input_hash"] is None
    assert payload["model_settlement_distribution"] == distribution
    changed_provider = classify_evaluation(
        _evaluation(
            capture_id="v2",
            ev=0.08,
            delta=0.06,
            ev_se=0.02,
            schema_version=DYNAMIC_EVALUATION_V2_SCHEMA,
            competition_id="competition-1",
            season="2026",
            provider="other",
            model_settlement_distribution=distribution,
        )
    )
    assert changed_provider.identity_hash != version.identity_hash


@pytest.mark.parametrize(
    "distribution",
    [
        {
            "WIN": 0.48,
            "HALF_WIN": 0.10,
            "PUSH": 0.02,
            "HALF_LOSS": 0.10,
            "LOSS": 0.30000001,
        },
        {
            "WIN": float("nan"),
            "HALF_WIN": 0.10,
            "PUSH": 0.02,
            "HALF_LOSS": 0.10,
            "LOSS": 0.30,
        },
        {"WIN": 1.0},
    ],
)
def test_v2_distribution_fails_closed_at_one_e_minus_nine(
    distribution: dict[str, float],
) -> None:
    with pytest.raises(
        ValueError,
        match="DYNAMIC_EVALUATION_V2_DISTRIBUTION_INVALID",
    ):
        classify_evaluation(
            _evaluation(
                capture_id="v2-invalid",
                ev=0.08,
                delta=0.06,
                ev_se=0.02,
                schema_version=DYNAMIC_EVALUATION_V2_SCHEMA,
                competition_id="competition-1",
                season="2026",
                provider="api_football",
                model_settlement_distribution=distribution,
            )
        )


def test_lineup_event_invalidates_old_input_until_post_lineup_quote() -> None:
    ledger = DynamicEvaluationLedger()
    ledger.append(_evaluation(capture_id="before", ev=0.08, delta=0.06, ev_se=0.02))
    confirmed_at = NOW + timedelta(minutes=1)
    event = LineupConfirmedEvent(
        fixture_id="fixture-1",
        competition_id="competition-1",
        season="2026",
        captured_at=confirmed_at,
        lineup_input_hash="lineup-1",
        home_starters=11,
        away_starters=11,
        home_lineup_identity_hash="home",
        away_lineup_identity_hash="away",
        source_capture_id="capture-lineup-1",
        raw_sha256="a" * 64,
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
            competition_id="competition-1",
            season="2026",
            captured_at=NOW,
            lineup_input_hash="lineup-incomplete",
            home_starters=10,
            away_starters=11,
            home_lineup_identity_hash="home",
            away_lineup_identity_hash="away",
            source_capture_id="capture-lineup-incomplete",
            raw_sha256="b" * 64,
        )


def test_lineup_event_v2_append_is_idempotent_and_preserves_first_observation() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = DynamicPrematchRepository(engine)
    first = _lineup_event()

    stored, inserted = repository.append_lineup_event(first)
    reobserved, replay_inserted = repository.append_lineup_event(
        _lineup_event(
            captured_at=NOW + timedelta(minutes=5),
            source_capture_id="capture-lineup-2",
            raw_sha256="b" * 64,
        )
    )

    assert inserted is True
    assert replay_inserted is False
    assert stored == first
    assert reobserved == first
    assert reobserved.captured_at == NOW
    assert reobserved.source_capture_id == "capture-lineup-1"
    with Session(engine) as session:
        row = session.scalar(select(LineupConfirmedEventModel))
    assert row is not None
    assert row.payload == first.as_dict()
    assert row.payload["schema_version"] == "w2.lineup_confirmed_event.v2"
    assert row.payload["numeric_adjustment_enabled"] is False


def test_lineup_event_append_rejects_payload_and_lineup_corrections() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = DynamicPrematchRepository(engine)
    repository.append_lineup_event(_lineup_event())

    with pytest.raises(ValueError, match="LINEUP_EVENT_PAYLOAD_CONFLICT"):
        repository.append_lineup_event(_lineup_event(season="2027"))
    with pytest.raises(ValueError, match="LINEUP_CONFIRMATION_CONFLICT"):
        repository.append_lineup_event(_lineup_event(lineup_input_hash="lineup-2"))

    with Session(engine) as session:
        assert session.query(LineupConfirmedEventModel).count() == 1


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
    assert [row["original_state"] for row in lifecycle["versions"]] == [
        "ANALYSIS_PICK_ACTIVE",
        "NO_EDGE_CURRENT",
    ]

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


def _pair_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _pair_fixture(
    *,
    fixture_id: str = "pair-fixture-1",
    provider_fixture_id: str = "1001",
) -> MatchdayFixtureIdentityModel:
    return MatchdayFixtureIdentityModel(
        fixture_id=fixture_id,
        provider="api_football",
        provider_fixture_id=provider_fixture_id,
        competition_id="competition-1",
        provider_league_id="39",
        season="2026",
        kickoff_utc=PAIR_KICKOFF,
        fixture_status="NS",
        home_provider_team_id="home",
        away_provider_team_id="away",
        team_identity_status="READY",
        raw_payload_sha256="a" * 64,
        captured_at=PAIR_NOW,
        identity_hash=f"fixture-{fixture_id}",
        payload={},
    )


def _pair_event(
    *,
    event_id: str = "lineup:lineup-hash",
    lineup_hash: str = "lineup-hash",
    fixture_id: str = "pair-fixture-1",
) -> LineupConfirmedEventModel:
    return LineupConfirmedEventModel(
        event_id=event_id,
        fixture_id=fixture_id,
        lineup_input_hash=lineup_hash,
        captured_at=PAIR_EVENT_AT,
        checkpoint="LINEUP_CONFIRMED",
        payload={
            "schema_version": "w2.lineup_confirmed_event.v2",
            "fixture_id": fixture_id,
            "competition_id": "competition-1",
            "season": "2026",
            "captured_at": PAIR_EVENT_AT.isoformat(),
            "checkpoint": "LINEUP_CONFIRMED",
            "lineup_input_hash": lineup_hash,
        },
    )


def _pair_evaluation(
    evaluation_id: str,
    *,
    capture_at: datetime,
    lineup_hash: str | None,
    evaluated_at: datetime | None = None,
    fixture_id: str = "pair-fixture-1",
    market: str = "ASIAN_HANDICAP",
    selection: str = "HOME",
    exact_line: float = -0.25,
    bookmaker_id: str = "book-1",
    provider: str = "api_football",
    state: str = "ANALYSIS_PICK_ACTIVE",
    schema_version: str = "w2.dynamic_quote_evaluation.v2",
    distribution: dict[str, float] | None = None,
) -> DynamicPrematchEvaluationModel:
    evaluated = evaluated_at or capture_at
    payload = {
        "schema_version": schema_version,
        "evaluation_id": evaluation_id,
        "fixture_id": fixture_id,
        "competition_id": "competition-1",
        "season": "2026",
        "provider": provider,
        "market": market,
        "selection": selection,
        "exact_line": exact_line,
        "bookmaker_id": bookmaker_id,
        "capture_id": f"capture-{evaluation_id}",
        "quote_identity_hash": f"quote-{evaluation_id}",
        "lineup_input_hash": lineup_hash,
        "evaluated_at": evaluated.isoformat(),
        "capture_at": capture_at.isoformat(),
        "model_settlement_distribution": distribution or PAIR_STATES,
    }
    return DynamicPrematchEvaluationModel(
        evaluation_id=evaluation_id,
        identity_hash=f"{evaluation_id:0<64}"[:64],
        fixture_id=fixture_id,
        market=market,
        selection=selection,
        checkpoint="capture",
        capture_id=f"capture-{evaluation_id}",
        quote_identity_hash=f"quote-{evaluation_id}",
        model_input_hash=f"model-{evaluation_id}",
        lineup_input_hash=lineup_hash,
        evaluated_at=evaluated,
        capture_at=capture_at,
        original_state=state,
        payload=payload,
    )


def _persist_pair(engine) -> None:  # type: ignore[no-untyped-def]
    with Session(engine) as session:
        session.add_all(
            [
                _pair_fixture(),
                _pair_event(),
                _pair_evaluation(
                    "pair-pre",
                    capture_at=PAIR_EVENT_AT - timedelta(minutes=1),
                    lineup_hash=None,
                ),
                _pair_evaluation(
                    "pair-post",
                    capture_at=PAIR_EVENT_AT,
                    lineup_hash="lineup-hash",
                ),
            ]
        )
        session.commit()


def test_exact_pair_projector_is_deterministic_and_read_only() -> None:
    engine = _pair_engine()
    _persist_pair(engine)
    with Session(engine) as session:
        counts = (
            session.query(DynamicPrematchEvaluationModel).count(),
            session.query(LineupConfirmedEventModel).count(),
        )

    first = project_exact_eval_02b_pairs(engine)
    second = project_exact_eval_02b_pairs(engine)

    assert first == second
    assert first.schema_version == "w2.eval_02b_exact_pair_projection.v2"
    assert len(first.pairs) == 1
    pair = first.pairs[0]
    assert pair.identity.canonical_fixture_id == "pair-fixture-1"
    assert pair.identity.pre_evaluation_id == "pair-pre"
    assert pair.identity.post_evaluation_id == "pair-post"
    assert pair.hash_domain == HashDomain.EVAL_02B_PAIR_IDENTITY.value
    assert pair.serializer_version == CURRENT_SERIALIZER_VERSION.value
    assert pair.identity_hash == canonical_sha256(
        pair.identity.as_dict(), domain=HashDomain.EVAL_02B_PAIR_IDENTITY
    )
    assert pair.baseline_distribution == PAIR_STATES
    assert pair.candidate_distribution == PAIR_STATES
    assert pair.pre_superseded_by_evaluation_id is None
    assert pair.post_superseded_by_evaluation_id is None
    with Session(engine) as session:
        assert counts == (
            session.query(DynamicPrematchEvaluationModel).count(),
            session.query(LineupConfirmedEventModel).count(),
        )


def test_exact_pair_projector_selects_last_pre_and_first_post() -> None:
    engine = _pair_engine()
    with Session(engine) as session:
        session.add_all(
            [
                _pair_fixture(),
                _pair_event(),
                _pair_evaluation(
                    "pre-old",
                    capture_at=PAIR_EVENT_AT - timedelta(minutes=2),
                    lineup_hash=None,
                ),
                _pair_evaluation(
                    "pre-last",
                    capture_at=PAIR_EVENT_AT - timedelta(microseconds=1),
                    lineup_hash=None,
                ),
                _pair_evaluation(
                    "post-first",
                    capture_at=PAIR_EVENT_AT,
                    lineup_hash="lineup-hash",
                ),
                _pair_evaluation(
                    "post-later",
                    capture_at=PAIR_EVENT_AT + timedelta(microseconds=1),
                    lineup_hash="lineup-hash",
                ),
            ]
        )
        session.commit()

    pair = project_exact_eval_02b_pairs(engine).pairs[0]

    assert pair.identity.pre_evaluation_id == "pre-last"
    assert pair.identity.post_evaluation_id == "post-first"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("bookmaker_id", "book-2"),
        ("provider", "other-provider"),
        ("selection", "AWAY"),
        ("exact_line", -0.5),
    ],
)
def test_exact_pair_projector_rejects_cross_quote_identity(
    field: str,
    value: object,
) -> None:
    engine = _pair_engine()
    post = {
        "bookmaker_id": "book-1",
        "provider": "api_football",
        "selection": "HOME",
        "exact_line": -0.25,
    }
    post[field] = value
    with Session(engine) as session:
        session.add_all(
            [
                _pair_fixture(),
                _pair_event(),
                _pair_evaluation(
                    "pre",
                    capture_at=PAIR_EVENT_AT - timedelta(minutes=1),
                    lineup_hash=None,
                ),
                _pair_evaluation(
                    "post",
                    capture_at=PAIR_EVENT_AT,
                    lineup_hash="lineup-hash",
                    **post,
                ),
            ]
        )
        session.commit()

    assert not project_exact_eval_02b_pairs(engine).pairs


@pytest.mark.parametrize(
    "override",
    [
        {"schema_version": "w2.dynamic_quote_evaluation.v1"},
        {"state": "NOT_READY_MODEL_INPUT"},
        {"state": "SUPERSEDED"},
        {"distribution": {**PAIR_STATES, "WIN": 0.41}},
    ],
)
def test_exact_pair_projector_requires_valid_v2_original_evidence(
    override: dict[str, object],
) -> None:
    engine = _pair_engine()
    with Session(engine) as session:
        session.add_all(
            [
                _pair_fixture(),
                _pair_event(),
                _pair_evaluation(
                    "pre",
                    capture_at=PAIR_EVENT_AT - timedelta(minutes=1),
                    lineup_hash=None,
                ),
                _pair_evaluation(
                    "post",
                    capture_at=PAIR_EVENT_AT,
                    lineup_hash="lineup-hash",
                    **override,
                ),
            ]
        )
        session.commit()

    assert not project_exact_eval_02b_pairs(engine).pairs


@pytest.mark.parametrize("event_count", [0, 2])
def test_exact_pair_projector_requires_one_authoritative_event(event_count: int) -> None:
    engine = _pair_engine()
    rows = [
        _pair_fixture(),
        _pair_evaluation(
            "pre",
            capture_at=PAIR_EVENT_AT - timedelta(minutes=1),
            lineup_hash=None,
        ),
        _pair_evaluation(
            "post",
            capture_at=PAIR_EVENT_AT,
            lineup_hash="lineup-hash",
        ),
    ]
    if event_count:
        rows.extend(
            [
                _pair_event(),
                _pair_event(event_id="lineup:other", lineup_hash="other"),
            ]
        )
    with Session(engine) as session:
        session.add_all(rows)
        session.commit()

    projection = project_exact_eval_02b_pairs(engine)

    assert not projection.pairs
    expected = (
        "BLOCKED_LINEUP_EVENT_MISSING"
        if event_count == 0
        else "BLOCKED_LINEUP_EVENT_CONFLICT"
    )
    assert expected in {item.reason for item in projection.exclusions}


def test_exact_pair_projector_blocks_multiple_scopes_per_fixture_market() -> None:
    engine = _pair_engine()
    with Session(engine) as session:
        session.add_all([_pair_fixture(), _pair_event()])
        for suffix, selection in (("home", "HOME"), ("away", "AWAY")):
            session.add(
                _pair_evaluation(
                    f"pre-{suffix}",
                    capture_at=PAIR_EVENT_AT - timedelta(minutes=1),
                    lineup_hash=None,
                    selection=selection,
                )
            )
            session.add(
                _pair_evaluation(
                    f"post-{suffix}",
                    capture_at=PAIR_EVENT_AT,
                    lineup_hash="lineup-hash",
                    selection=selection,
                )
            )
        session.commit()

    assert not project_exact_eval_02b_pairs(engine).pairs


def test_exact_pair_projector_resolves_production_fixture_alias() -> None:
    engine = _pair_engine()
    with Session(engine) as session:
        session.add_all(
            [
                _pair_fixture(
                    fixture_id="api_football:1001",
                    provider_fixture_id="1001",
                ),
                _pair_event(fixture_id="1001"),
                _pair_evaluation(
                    "pre-alias",
                    fixture_id="1001",
                    capture_at=PAIR_EVENT_AT - timedelta(minutes=1),
                    lineup_hash=None,
                ),
                _pair_evaluation(
                    "post-alias",
                    fixture_id="1001",
                    capture_at=PAIR_EVENT_AT,
                    lineup_hash="lineup-hash",
                ),
            ]
        )
        session.commit()

    pair = project_exact_eval_02b_pairs(engine).pairs[0]

    assert pair.identity.canonical_fixture_id == "api_football:1001"


def test_exact_pair_projector_rejects_ambiguous_fixture_alias() -> None:
    engine = _pair_engine()
    with Session(engine) as session:
        session.add_all(
            [
                _pair_fixture(
                    fixture_id="api_football:1001",
                    provider_fixture_id="1001",
                ),
                _pair_fixture(fixture_id="1001", provider_fixture_id="2002"),
                _pair_event(fixture_id="1001"),
                _pair_evaluation(
                    "pre-ambiguous",
                    fixture_id="1001",
                    capture_at=PAIR_EVENT_AT - timedelta(minutes=1),
                    lineup_hash=None,
                ),
                _pair_evaluation(
                    "post-ambiguous",
                    fixture_id="1001",
                    capture_at=PAIR_EVENT_AT,
                    lineup_hash="lineup-hash",
                ),
            ]
        )
        session.commit()

    projection = project_exact_eval_02b_pairs(engine)

    assert not projection.pairs
    assert "BLOCKED_FIXTURE_IDENTITY_CONFLICT" in {
        item.reason for item in projection.exclusions
    }


def test_exact_pair_projector_keeps_superseded_original_history() -> None:
    engine = _pair_engine()
    _persist_pair(engine)
    with Session(engine) as session:
        session.add(
            DynamicPrematchSupersessionModel(
                superseded_evaluation_id="pair-pre",
                superseded_by_evaluation_id="pair-post",
                fixture_id="pair-fixture-1",
                market="ASIAN_HANDICAP",
                reason="NEW_CAPTURE_OR_MODEL_INPUT",
                created_at=PAIR_EVENT_AT,
            )
        )
        session.commit()

    pair = project_exact_eval_02b_pairs(engine).pairs[0]

    assert pair.pre_superseded_by_evaluation_id == "pair-post"
    assert pair.post_superseded_by_evaluation_id is None


def test_exact_pair_projector_pre_eligibility_uses_capture_time_only() -> None:
    engine = _pair_engine()
    with Session(engine) as session:
        session.add_all(
            [
                _pair_fixture(),
                _pair_event(),
                _pair_evaluation(
                    "pre-processed-late",
                    capture_at=PAIR_EVENT_AT - timedelta(minutes=1),
                    evaluated_at=PAIR_EVENT_AT + timedelta(minutes=1),
                    lineup_hash=None,
                ),
                _pair_evaluation(
                    "post",
                    capture_at=PAIR_EVENT_AT,
                    lineup_hash="lineup-hash",
                ),
            ]
        )
        session.commit()

    pair = project_exact_eval_02b_pairs(engine).pairs[0]

    assert pair.identity.pre_evaluation_id == "pre-processed-late"


def test_exact_pair_projector_orders_pre_by_capture_before_processing_time() -> None:
    engine = _pair_engine()
    with Session(engine) as session:
        session.add_all(
            [
                _pair_fixture(),
                _pair_event(),
                _pair_evaluation(
                    "pre-newer-capture",
                    capture_at=PAIR_EVENT_AT - timedelta(minutes=1),
                    evaluated_at=PAIR_EVENT_AT - timedelta(minutes=10),
                    lineup_hash=None,
                ),
                _pair_evaluation(
                    "pre-older-processed-later",
                    capture_at=PAIR_EVENT_AT - timedelta(minutes=2),
                    evaluated_at=PAIR_EVENT_AT + timedelta(minutes=1),
                    lineup_hash=None,
                ),
                _pair_evaluation(
                    "post",
                    capture_at=PAIR_EVENT_AT,
                    lineup_hash="lineup-hash",
                ),
            ]
        )
        session.commit()

    pair = project_exact_eval_02b_pairs(engine).pairs[0]

    assert pair.identity.pre_evaluation_id == "pre-newer-capture"
