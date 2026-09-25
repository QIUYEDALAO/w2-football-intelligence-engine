from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from w2.infrastructure.persistence.forward_evidence_models import (
    ForwardClockModel,
    RecommendationReviewLedgerModel,
)
from w2.infrastructure.persistence.model_forecast_models import ModelForecastCaptureModel
from w2.tracking.forward_evidence import (
    CLOCK_ID,
    T0,
    append_forward_evidence_in_session,
    record_shadow_evidence_in_session,
    register_forward_clock,
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
