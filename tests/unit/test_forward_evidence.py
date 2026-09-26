from __future__ import annotations

from contextlib import nullcontext
from dataclasses import make_dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.forward_evidence_models import (
    ForwardClockModel,
    RecommendationReviewLedgerModel,
)
from w2.infrastructure.persistence.model_forecast_models import ModelForecastCaptureModel
from w2.infrastructure.persistence.models import ResultModel
from w2.tracking.forward_evidence import (
    CLOCK_ID,
    T0,
    TRACK_D_FADE,
    VALIDATION_SIGNAL,
    append_forward_evidence_in_session,
    append_validation_signal_settlement_in_session,
    record_shadow_evidence_in_session,
    register_forward_clock,
    settle_track_d_validation_signals_in_session,
)


class _Rows:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows

    def all(self) -> list[SimpleNamespace]:
        return self.rows


class _Session:
    def __init__(
        self, *, capture: SimpleNamespace | None = None, quotes: list[SimpleNamespace] | None = None
    ) -> None:
        self.clock: ForwardClockModel | None = None
        self.capture = capture
        self.quotes = quotes or []
        self.events: dict[str, RecommendationReviewLedgerModel] = {}

    def get(self, model: type, key: str):
        if model is ForwardClockModel:
            return self.clock if key == CLOCK_ID else None
        if model is ModelForecastCaptureModel:
            return self.capture if key == "f" else None
        if model is RecommendationReviewLedgerModel:
            return self.events.get(key)
        raise AssertionError(model)

    def scalars(self, _query: object) -> _Rows:
        return _Rows(self.quotes)

    def scalar(self, _query: object):
        return next(
            (row for row in self.events.values() if row.event_type == "DECISION_SNAPSHOT"),
            None,
        )

    def add(self, row: object) -> None:
        if isinstance(row, ForwardClockModel):
            self.clock = row
        elif isinstance(row, RecommendationReviewLedgerModel):
            self.events[row.review_event_id] = row
        else:
            raise AssertionError(type(row))

    def flush(self) -> None:
        pass

    def begin_nested(self):
        return nullcontext()


def _version(at: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        evaluation_id="e",
        identity_hash="a" * 64,
        fixture_id="api_football:123",
        market="TOTALS",
        selection="OVER",
        exact_line=2.5,
        bookmaker_id="4",
        capture_id="c",
        quote_identity_hash="b" * 64,
        capture_at=at - timedelta(minutes=1),
        decimal_odds=1.9,
        model_forecast_capture_identity_hash="f",
        evaluated_at=at,
        evaluation_policy_version="candidate-eval.v2",
        calibration_identity="candidate-eval.v2",
        model_settlement_distribution={"WIN": 0.5},
        state=SimpleNamespace(value="NO_EDGE_CURRENT"),
        factor_decision_status="ADMITTED",
    )


def _capture(at: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        fixture_id="api_football:123",
        captured_at=at - timedelta(minutes=3),
        kickoff_utc=at + timedelta(hours=2),
        model_input_manifest_hash="m" * 64,
        payload={
            "simulation_replay": {
                "simulation": {
                    "lambda_home": 1.2,
                    "lambda_away": 1.0,
                    "calibration": {
                        "params": {"dixon_coles_rho": -0.08},
                        "simulation_input_hash": "i" * 64,
                    },
                }
            }
        },
    )


def _quotes(at: datetime) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            observation_id=side,
            provider_fixture_id="123",
            capture_id="c",
            canonical_market="TOTALS",
            canonical_selection=side,
            bookmaker_id="4",
            line="2.5",
            decimal_odds="1.9" if side == "OVER" else "2.0",
            captured_at=at - timedelta(minutes=1),
        )
        for side in ("OVER", "UNDER")
    ]


def test_clock_is_one_shot_and_cannot_precede_t0() -> None:
    session = _Session()
    with pytest.raises(ValueError, match="BEFORE_T0"):
        register_forward_clock(
            session, started_at=T0 - timedelta(seconds=1), code_revision="a" * 40
        )
    first = register_forward_clock(session, started_at=T0, code_revision="a" * 40)
    assert register_forward_clock(session, started_at=T0, code_revision="a" * 40) is first
    with pytest.raises(ValueError, match="ALREADY_STARTED"):
        register_forward_clock(
            session, started_at=T0 + timedelta(seconds=1), code_revision="a" * 40
        )


def test_new_evaluation_binds_both_quotes_and_model_parameters() -> None:
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)
    session = _Session(capture=_capture(at), quotes=_quotes(at))
    assert append_forward_evidence_in_session(session, _version(at)) is None
    register_forward_clock(session, started_at=T0, code_revision="a" * 40)
    row = append_forward_evidence_in_session(session, _version(at))
    assert row is not None and row.pit_status == "PROVABLE"
    assert row.payload["lambda_home"] == 1.2
    assert row.payload["rho"] == -0.08
    assert row.payload["quote_observation_ids"] == ["OVER", "UNDER"]
    assert (
        append_forward_evidence_in_session(session, _version(at)).review_event_id
        == row.review_event_id
    )
    assert len(session.events) == 1


def test_missing_or_mismatched_evidence_is_kept_but_not_pit_provable() -> None:
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)
    session = _Session(capture=_capture(at), quotes=_quotes(at)[:1])
    register_forward_clock(session, started_at=T0, code_revision="a" * 40)
    row = append_forward_evidence_in_session(session, _version(at))
    assert row is not None and row.pit_status == "PIT_UNPROVABLE"
    assert "QUOTE_PAIR_MISMATCH" in row.payload["exclusion_reasons"]
    assert row.payload["quote_pair_identity"] is None


def test_pre_clock_evaluations_are_never_backfilled() -> None:
    session = _Session()
    register_forward_clock(session, started_at=T0 + timedelta(hours=2), code_revision="a" * 40)
    assert append_forward_evidence_in_session(session, _version(T0 + timedelta(hours=1))) is None
    assert not session.events


def test_shadow_writer_logs_failure_without_aborting_evaluation(monkeypatch, caplog) -> None:
    def broken(_session, _version):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr("w2.tracking.forward_evidence.append_forward_evidence_in_session", broken)
    record_shadow_evidence_in_session(_Session(), _version(T0))
    assert "FORWARD_EVIDENCE_WRITE_FAILED evaluation_id=e" in caplog.text


def test_under_evaluation_creates_separate_pit_fade_decision_and_channel_settlement() -> None:
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)
    source = _version(at)
    source.selection = "UNDER"
    source.bookmaker_id = "36"
    source.decimal_odds = 1.98
    source.track_d_validation_signal = None
    source.model_settlement_distribution = {
        "WIN": 0.45, "HALF_WIN": 0.0, "PUSH": 0.0,
        "HALF_LOSS": 0.0, "LOSS": 0.55,
    }
    version_type = make_dataclass("UnderVersion", [(key, object) for key in vars(source)])
    version = version_type(**vars(source))
    quotes = [
        SimpleNamespace(
            observation_id=f"{bookmaker}-{side}",
            provider_fixture_id="123",
            capture_id="c",
            canonical_market="TOTALS",
            canonical_selection=side,
            bookmaker_id=bookmaker,
            line="2.5",
            decimal_odds=price,
            captured_at=at - timedelta(minutes=1),
        )
        for bookmaker, side, price in (
            ("36", "UNDER", "1.98"), ("36", "OVER", "1.92"),
            ("4", "UNDER", "1.90"), ("4", "OVER", "1.93"),
        )
    ]
    session = _Session(capture=_capture(at), quotes=quotes)
    register_forward_clock(session, started_at=T0, code_revision="a" * 40)

    record_shadow_evidence_in_session(session, version)

    rows = list(session.events.values())
    assert len(rows) == 2
    fade = next(row for row in rows if row.event_type == "DECISION_SNAPSHOT")
    assert fade.pit_status == "PROVABLE"
    assert fade.payload["candidate_kind"] == TRACK_D_FADE
    assert fade.payload["display_state"] == VALIDATION_SIGNAL
    assert fade.payload["official_recommendation"] is False
    assert fade.payload["original_selection"] == "UNDER"
    assert fade.payload["selection"] == "OVER"
    assert fade.payload["derived_from_evaluation_id"] == version.evaluation_id
    assert fade.payload["decimal_odds_channel"] == 1.92
    assert fade.payload["decimal_odds_pinnacle"] == 1.93
    assert fade.payload["channel_quote_identity"] == "36-OVER"
    assert fade.payload["pinnacle_quote_identity"]
    assert fade.payload["market_quote_identity"] == fade.payload["pinnacle_quote_identity"]
    assert fade.payload["source_quote_identity"] == version.quote_identity_hash
    assert fade.payload["track_d_validation_signal"]["fade_delta"] == 0.05

    settled = append_validation_signal_settlement_in_session(
        session,
        evaluation_id=version.evaluation_id,
        settlement="WIN",
        profit_units_channel=0.92,
        settled_at=at + timedelta(hours=3),
        home_goals=2,
        away_goals=1,
    )
    assert settled.payload["profit_units_channel"] == 0.92
    assert settled.payload["rebate_units_channel"] == pytest.approx(0.023)
    assert settled.payload["profit_units_channel_with_rebate"] == pytest.approx(0.943)


def test_pinnacle_cannot_be_used_as_fade_channel_price() -> None:
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)
    version = _version(at)
    version.selection = "OVER"
    version.bookmaker_id = "4"
    version.track_d_validation_signal = {"source_selection": "UNDER"}
    session = _Session(capture=_capture(at), quotes=_quotes(at))
    register_forward_clock(session, started_at=T0, code_revision="a" * 40)

    row = append_forward_evidence_in_session(
        session, version, _event_type="DECISION_SNAPSHOT"
    )

    assert row is not None
    assert row.payload["candidate_kind"] != TRACK_D_FADE
    assert "TRACK_D_CHANNEL_OR_MARKET_QUOTE_UNPROVABLE" in row.payload["exclusion_reasons"]


def test_result_materialization_settles_fade_at_frozen_channel_price() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[RecommendationReviewLedgerModel.__table__, ResultModel.__table__],
    )
    at = datetime(2026, 9, 26, 8, tzinfo=UTC)
    source = {
        "candidate_kind": TRACK_D_FADE,
        "fixture_id": "api_football:123",
        "market": "TOTALS",
        "selection": "OVER",
        "exact_line": "2.5",
        "decimal_odds_channel": 1.92,
        "market_quote_identity": "m" * 64,
        "channel_quote_identity": "36-OVER",
        "evaluated_at": at.isoformat(),
        "first_quote_captured_at": (at - timedelta(minutes=1)).isoformat(),
        "kickoff_utc": (at + timedelta(hours=2)).isoformat(),
    }
    with Session(engine) as session:
        session.add(RecommendationReviewLedgerModel(
            review_event_id="a" * 64,
            evaluation_id="e",
            event_type="DECISION_SNAPSHOT",
            evaluated_at=at,
            pit_status="PROVABLE",
            payload=source,
            payload_sha256="a" * 64,
            created_at=at,
        ))
        session.add(ResultModel(
            fixture_id="api_football:123",
            home_goals=2,
            away_goals=1,
            result_status="FT",
            confirmed_at=at + timedelta(hours=3),
            source_payload_sha256="b" * 64,
            result_hash="c" * 64,
        ))
        session.commit()

        assert settle_track_d_validation_signals_in_session(
            session, now=at + timedelta(hours=2, minutes=30)
        ) == {"signals": 1, "settled": 0}
        report = settle_track_d_validation_signals_in_session(
            session, now=at + timedelta(hours=3)
        )
        assert report == {"signals": 1, "settled": 1}
        settled = session.query(RecommendationReviewLedgerModel).filter_by(
            event_type="SETTLEMENT_OBSERVED"
        ).one()
        assert settled.payload["settlement"] == "WIN"
        assert settled.payload["profit_units_channel"] == pytest.approx(0.92)
        assert settled.payload["rebate_units_channel"] == pytest.approx(0.023)
        assert settled.payload["profit_units_channel_with_rebate"] == pytest.approx(0.943)
        session.commit()
        assert settle_track_d_validation_signals_in_session(
            session, now=at + timedelta(hours=4)
        ) == {"signals": 0, "settled": 0}
