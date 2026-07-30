from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
    LineupConfirmedEventModel,
)
from w2.infrastructure.persistence.matchday_intake_models import MatchdayFixtureIdentityModel
from w2.lineups.pair_projection import project_exact_eval_02b_pairs

NOW = datetime(2026, 8, 1, 10, tzinfo=UTC)
EVENT_AT = NOW + timedelta(hours=1)
KICKOFF = NOW + timedelta(hours=2)
STATES = {
    "WIN": 0.40,
    "HALF_WIN": 0.10,
    "PUSH": 0.10,
    "HALF_LOSS": 0.10,
    "LOSS": 0.30,
}


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    MatchdayFixtureIdentityModel.__table__.create(engine)
    DynamicPrematchEvaluationModel.__table__.create(engine)
    LineupConfirmedEventModel.__table__.create(engine)
    return engine


def _fixture(*, fixture_id: str = "fixture-1") -> MatchdayFixtureIdentityModel:
    return MatchdayFixtureIdentityModel(
        fixture_id=fixture_id,
        provider="api_football",
        provider_fixture_id="1001",
        competition_id="competition-1",
        provider_league_id="39",
        season="2026",
        kickoff_utc=KICKOFF,
        fixture_status="NS",
        home_provider_team_id="home",
        away_provider_team_id="away",
        team_identity_status="READY",
        raw_payload_sha256="a" * 64,
        captured_at=NOW,
        identity_hash="b" * 64,
        payload={},
    )


def _event(
    *,
    event_id: str = "lineup:lineup-hash",
    lineup_hash: str = "lineup-hash",
) -> LineupConfirmedEventModel:
    payload = {
        "schema_version": "w2.lineup_confirmed_event.v2",
        "fixture_id": "fixture-1",
        "competition_id": "competition-1",
        "season": "2026",
        "captured_at": EVENT_AT.isoformat(),
        "checkpoint": "LINEUP_CONFIRMED",
        "lineup_input_hash": lineup_hash,
    }
    return LineupConfirmedEventModel(
        event_id=event_id,
        fixture_id="fixture-1",
        lineup_input_hash=lineup_hash,
        captured_at=EVENT_AT,
        checkpoint="LINEUP_CONFIRMED",
        payload=payload,
    )


def _evaluation(
    evaluation_id: str,
    *,
    capture_at: datetime,
    lineup_hash: str | None,
    market: str = "ASIAN_HANDICAP",
    selection: str = "HOME",
    exact_line: float = -0.25,
    bookmaker_id: str = "book-1",
    provider: str = "api_football",
    state: str = "ANALYSIS_PICK_ACTIVE",
    schema_version: str = "w2.dynamic_quote_evaluation.v2",
    distribution: dict[str, float] | None = None,
) -> DynamicPrematchEvaluationModel:
    payload = {
        "schema_version": schema_version,
        "evaluation_id": evaluation_id,
        "fixture_id": "fixture-1",
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
        "evaluated_at": capture_at.isoformat(),
        "capture_at": capture_at.isoformat(),
        "model_settlement_distribution": distribution or STATES,
    }
    return DynamicPrematchEvaluationModel(
        evaluation_id=evaluation_id,
        identity_hash=f"{evaluation_id:0<64}"[:64],
        fixture_id="fixture-1",
        market=market,
        selection=selection,
        checkpoint="capture",
        capture_id=f"capture-{evaluation_id}",
        quote_identity_hash=f"quote-{evaluation_id}",
        model_input_hash=f"model-{evaluation_id}",
        lineup_input_hash=lineup_hash,
        evaluated_at=capture_at,
        capture_at=capture_at,
        original_state=state,
        payload=payload,
    )


def _persist_valid_pair(engine) -> None:
    with Session(engine) as session:
        session.add_all(
            [
                _fixture(),
                _event(),
                _evaluation(
                    "pre",
                    capture_at=EVENT_AT - timedelta(minutes=1),
                    lineup_hash=None,
                ),
                _evaluation(
                    "post",
                    capture_at=EVENT_AT,
                    lineup_hash="lineup-hash",
                ),
            ]
        )
        session.commit()


def test_projector_derives_one_deterministic_exact_pair_without_writes() -> None:
    engine = _engine()
    _persist_valid_pair(engine)
    with Session(engine) as session:
        counts_before = (
            session.query(DynamicPrematchEvaluationModel).count(),
            session.query(LineupConfirmedEventModel).count(),
        )

    first = project_exact_eval_02b_pairs(engine)
    second = project_exact_eval_02b_pairs(engine)

    assert first == second
    assert len(first.pairs) == 1
    pair = first.pairs[0]
    assert pair.identity.as_dict() == {
        "canonical_fixture_id": "fixture-1",
        "competition_id": "competition-1",
        "season_id": "2026",
        "provider_id": "api_football",
        "bookmaker_id": "book-1",
        "market": "ASIAN_HANDICAP",
        "selection": "HOME",
        "exact_line": -0.25,
        "pre_evaluation_id": "pre",
        "post_evaluation_id": "post",
    }
    assert len(pair.identity_hash) == 64
    assert pair.baseline_distribution == STATES
    assert pair.candidate_distribution == STATES
    with Session(engine) as session:
        assert counts_before == (
            session.query(DynamicPrematchEvaluationModel).count(),
            session.query(LineupConfirmedEventModel).count(),
        )


def test_projector_selects_last_pre_and_first_post_at_frozen_boundaries() -> None:
    engine = _engine()
    with Session(engine) as session:
        session.add_all(
            [
                _fixture(),
                _event(),
                _evaluation(
                    "pre-old",
                    capture_at=EVENT_AT - timedelta(minutes=2),
                    lineup_hash=None,
                ),
                _evaluation(
                    "pre-last",
                    capture_at=EVENT_AT - timedelta(microseconds=1),
                    lineup_hash=None,
                ),
                _evaluation(
                    "post-first",
                    capture_at=EVENT_AT,
                    lineup_hash="lineup-hash",
                ),
                _evaluation(
                    "post-later",
                    capture_at=EVENT_AT + timedelta(microseconds=1),
                    lineup_hash="lineup-hash",
                ),
            ]
        )
        session.commit()

    pair = project_exact_eval_02b_pairs(engine).pairs[0]

    assert pair.identity.pre_evaluation_id == "pre-last"
    assert pair.identity.post_evaluation_id == "post-first"


def test_projector_fails_closed_for_cross_quote_identity() -> None:
    for field, value in (
        ("bookmaker_id", "book-2"),
        ("provider", "other-provider"),
        ("selection", "AWAY"),
        ("exact_line", -0.5),
    ):
        engine = _engine()
        post_kwargs = {
            "bookmaker_id": "book-1",
            "provider": "api_football",
            "selection": "HOME",
            "exact_line": -0.25,
        }
        post_kwargs[field] = value
        with Session(engine) as session:
            session.add_all(
                [
                    _fixture(),
                    _event(),
                    _evaluation(
                        "pre",
                        capture_at=EVENT_AT - timedelta(minutes=1),
                        lineup_hash=None,
                    ),
                    _evaluation(
                        "post",
                        capture_at=EVENT_AT,
                        lineup_hash="lineup-hash",
                        **post_kwargs,
                    ),
                ]
            )
            session.commit()

        projection = project_exact_eval_02b_pairs(engine)

        assert not projection.pairs


def test_projector_requires_v2_valid_state_distribution_and_lineup_hash_roles() -> None:
    invalid_rows = (
        {"schema_version": "w2.dynamic_quote_evaluation.v1"},
        {"state": "NOT_READY_MODEL_INPUT"},
        {"state": "SUPERSEDED"},
        {"distribution": {**STATES, "WIN": 0.41}},
    )
    for override in invalid_rows:
        engine = _engine()
        with Session(engine) as session:
            session.add_all(
                [
                    _fixture(),
                    _event(),
                    _evaluation(
                        "pre",
                        capture_at=EVENT_AT - timedelta(minutes=1),
                        lineup_hash=None,
                    ),
                    _evaluation(
                        "post",
                        capture_at=EVENT_AT,
                        lineup_hash="lineup-hash",
                        **override,
                    ),
                ]
            )
            session.commit()
        assert not project_exact_eval_02b_pairs(engine).pairs

    engine = _engine()
    with Session(engine) as session:
        session.add_all(
            [
                _fixture(),
                _event(),
                _evaluation(
                    "pre",
                    capture_at=EVENT_AT - timedelta(minutes=1),
                    lineup_hash="lineup-hash",
                ),
                _evaluation("post", capture_at=EVENT_AT, lineup_hash=None),
            ]
        )
        session.commit()
    assert not project_exact_eval_02b_pairs(engine).pairs


def test_projector_requires_exactly_one_authoritative_event() -> None:
    for event_count in (0, 2):
        engine = _engine()
        rows = [
            _fixture(),
            _evaluation(
                "pre",
                capture_at=EVENT_AT - timedelta(minutes=1),
                lineup_hash=None,
            ),
            _evaluation("post", capture_at=EVENT_AT, lineup_hash="lineup-hash"),
        ]
        if event_count:
            rows.extend(
                [
                    _event(),
                    _event(event_id="lineup:other", lineup_hash="other"),
                ][:event_count]
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


def test_projector_blocks_multiple_exact_scopes_for_one_fixture_market() -> None:
    engine = _engine()
    with Session(engine) as session:
        session.add_all([_fixture(), _event()])
        for suffix, selection in (("home", "HOME"), ("away", "AWAY")):
            session.add(
                _evaluation(
                    f"pre-{suffix}",
                    capture_at=EVENT_AT - timedelta(minutes=1),
                    lineup_hash=None,
                    selection=selection,
                )
            )
            session.add(
                _evaluation(
                    f"post-{suffix}",
                    capture_at=EVENT_AT,
                    lineup_hash="lineup-hash",
                    selection=selection,
                )
            )
        session.commit()

    projection = project_exact_eval_02b_pairs(engine)

    assert not projection.pairs
    assert {
        (item.market, item.reason) for item in projection.exclusions
    } == {("ASIAN_HANDICAP", "BLOCKED_EXACT_PRE_POST_PAIR_MISSING_OR_AMBIGUOUS")}
