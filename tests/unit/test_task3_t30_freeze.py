"""Task 3 T-30 same-window capture freeze: fail-closed + policy + replay tests.

Covers the phase-2 rectification requirements:

1. real ANALYSIS_READY chain -> T-30 model freeze -> same-window quote reference;
2. neutral_site strict fail-closed (missing / None / 0 / 1 / str / bad source /
   bad policy version / bad as_of / simulation-vs-ledger conflict);
3. lambda sigma strict fail-closed (missing / non-numeric / negative / NaN / Inf);
4. T-30 window boundaries (T-35 / T-25 / before / after / post-kickoff / tz);
5. quote reference fail-closed (incomplete / bad market / bad odds / state /
   identity);
6. identity / idempotency (same input no second row; conflicting payload fails);
7. real 0.12 vs 0.30 parameter-level replay;
8. result isolation (capture is byte-identical with or without a settled result).
"""
from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.future_refresh_models import (
    TeamXgMatchModel,
    TeamXgRollingSnapshotModel,
)
from w2.infrastructure.persistence.model_forecast_models import (
    ModelForecastCaptureDataVersionModel,
    ModelForecastCaptureModel,
    ModelForecastOutcomeModel,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.models.dixon_coles import one_x_two_from_matrix
from w2.strategy.calibration import LambdaCalibrationParams, calibrate_lambdas
from w2.strategy.simulate import _exact_score_matrix_with_uncertainty
from w2.tracking.model_forecast_ledger import (
    T30_CAPTURE_POLICY,
    T30_CHECKPOINT,
    T30_HORIZON,
    ModelForecastLedgerError,
    ModelForecastLedgerRepository,
    freeze_t30_capture,
)

NOW = datetime(2026, 8, 14, 0, 0, tzinfo=UTC)
KICKOFF = NOW + timedelta(hours=12)
T30_CAPTURED_AT = KICKOFF - timedelta(minutes=30)

NEUTRAL_SITE_RESOLUTION = {
    "neutral_site": False,
    "neutral_site_resolution_source": "DEFAULT_NON_NEUTRAL_POLICY",
    "neutral_site_policy_version": "w2.neutral_site_policy.v1",
    "neutral_site_as_of": NOW.isoformat(),
    "neutral_site_status": "READY",
}


def _repository(tmp_path: Path) -> ModelForecastLedgerRepository:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 't30.db'}")
    TeamXgMatchModel.__table__.create(engine)
    TeamXgRollingSnapshotModel.__table__.create(engine)
    ModelForecastCaptureModel.__table__.create(engine)
    ModelForecastCaptureDataVersionModel.__table__.create(engine)
    ModelForecastOutcomeModel.__table__.create(engine)
    ResultModel.__table__.create(engine)
    return ModelForecastLedgerRepository(engine)


def _seed_xg(repository: ModelForecastLedgerRepository) -> None:
    with Session(repository.engine) as session:
        for team_id, opponent, xg_for, xg_against in (
            ("10", "20", 1.2, 0.8),
            ("20", "10", 0.8, 1.2),
        ):
            for index in range(3):
                session.add(
                    TeamXgMatchModel(
                        id=f"history-{index}:{team_id}",
                        fixture_id=f"history-{index}",
                        team_id=team_id,
                        opponent_team_id=opponent,
                        kickoff_at=NOW - timedelta(days=4 - index),
                        captured_at=NOW - timedelta(days=3 - index),
                        xg_for=xg_for,
                        xg_against=xg_against,
                        goals_for=1,
                        goals_against=0,
                        raw_payload_sha256=f"{index + 1}" * 64,
                        source_system="api_football_statistics",
                        candidate=False,
                        formal_recommendation=False,
                    )
                )
            session.add(
                TeamXgRollingSnapshotModel(
                    snapshot_id=f"{team_id}:fixture-1",
                    team_id=team_id,
                    as_of_fixture_id="fixture-1",
                    as_of_time=NOW,
                    match_count=3,
                    rolling_xg_for=xg_for,
                    rolling_xg_against=xg_against,
                    rolling_goals_for=1.0,
                    rolling_goals_against=0.0,
                    regression_index=0.0,
                    source_system="team_xg_match",
                    candidate=False,
                    formal_recommendation=False,
                )
            )
        session.commit()


def _simulation() -> dict[str, Any]:
    return {
        "status": "READY",
        "model_version": "w2.formal.exact_dc_poisson.v1",
        "calibration_version": "w2.calibration.v1",
        "calibration_status": "BASELINE_PRIOR",
        "lambda_sigma_home": 0.5,
        "lambda_sigma_away": 0.4,
        "calibration": {
            "simulation_input_hash": "f" * 64,
            "lambda_uncertainty_method": "empirical_xg_standard_error.v2_latest_five",
            "lambda_uncertainty_status": "ANALYSIS_READY",
        },
        "input_readiness": {
            "neutral_site": False,
            "lambda_uncertainty_input_hash": "g" * 64,
        },
        "score_matrix_summary": {
            "home_win": 0.5,
            "draw": 0.2,
            "away_win": 0.3,
            "score_matrix_hash": "9" * 64,
            "distribution": [
                {"home_goals": 0, "away_goals": 0, "probability": 0.2},
                {"home_goals": 1, "away_goals": 0, "probability": 0.5},
                {"home_goals": 0, "away_goals": 1, "probability": 0.3},
            ],
        },
        "ah_probabilities": {
            "ladder": [
                {
                    "home_line": -0.5,
                    "home_settlement_distribution": {
                        "WIN": 0.5, "HALF_WIN": 0.0, "PUSH": 0.0,
                        "HALF_LOSS": 0.0, "LOSS": 0.5,
                    },
                    "away_settlement_distribution": {
                        "WIN": 0.5, "HALF_WIN": 0.0, "PUSH": 0.0,
                        "HALF_LOSS": 0.0, "LOSS": 0.5,
                    },
                }
            ]
        },
        "ou_probabilities": {"ladder": [{"line": 2.5}]},
    }


def _day_view(*, simulation: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "cards": [
            {
                "fixture_id": "fixture-1",
                "competition_id": "premier_league",
                "kickoff_utc": KICKOFF.isoformat(),
                "decision_tier": "NOT_READY",
                "outcome_tracked": False,
                "neutral_site_resolution": dict(NEUTRAL_SITE_RESOLUTION),
                "frozen_artifact_provenance": {
                    "artifact_hash": "c" * 64,
                    "source_hash": "d" * 64,
                    "fixture_identity": {
                        "fixture_id": "fixture-1",
                        "competition_id": "premier_league",
                        "kickoff_utc": KICKOFF.isoformat(),
                        "home_team_id": "10",
                        "away_team_id": "20",
                    },
                    "input_manifest": {"simulation_sha256": "e" * 64},
                },
                "simulation": {"status": "READY", "simulation": simulation or _simulation()},
            }
        ]
    }


def _market_snapshot(**overrides: Any) -> dict[str, Any]:
    from w2.tracking.model_forecast_ledger import select_t30_market_reference
    quote_time = datetime.fromisoformat(str(overrides.get("as_of", T30_CAPTURED_AT.isoformat())))
    if not KICKOFF - timedelta(minutes=35) <= quote_time <= KICKOFF - timedelta(minutes=25):
        quote_time = T30_CAPTURED_AT
    rows = []
    for side, line, odds in (("HOME", "-0.5", "1.90"), ("AWAY", "0.5", "1.95")):
        rows.append({
            "fixture_id": "fixture-1", "provider": "api-football",
            "bookmaker_id": "4", "bookmaker_name": "Pinnacle",
            "canonical_market": "ASIAN_HANDICAP", "raw_market_label": "Asian Handicap",
            "selection": side, "line": line, "decimal_odds": odds,
            "captured_at": quote_time.isoformat(),
            "observation_id": side, "capture_id": "capture-1",
            "raw_payload_sha256": "a" * 64, "source_revision": "future-refresh.v1",
            "live": False, "suspended": False,
        })
    snapshot = select_t30_market_reference(
        rows, fixture_id="fixture-1", kickoff=KICKOFF, captured_at=quote_time,
    )
    assert snapshot is not None
    if "as_of" in overrides:
        overrides["as_of"] = (
            datetime.fromisoformat(str(overrides["as_of"]))
            .astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z")
        )
    snapshot.update(overrides)
    return snapshot


def _mutated_card(mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    day_view = _day_view()
    card = day_view["cards"][0]
    mutator(card)
    return day_view


def _simulation_of(card: dict[str, Any]) -> dict[str, Any]:
    return card["simulation"]["simulation"]


# --------------------------------------------------------------------------- #
# 1. real chain -> T-30 freeze -> same-window quote reference
# --------------------------------------------------------------------------- #
def test_storage_t30_freeze_produces_capture(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_xg(repository)

    result = freeze_t30_capture(
        _day_view(),
        repository=repository,
        market_snapshots={"fixture-1": _market_snapshot()},
        captured_at=T30_CAPTURED_AT,
        dry_run=False,
        write_db=True,
    )

    assert result["provider_calls"] == 0
    assert result["window_eligible_count"] == 1
    assert result["model_eligible_count"] == 1
    assert result["model_forecast_capture_count"] == 1
    assert result["blocked_count"] == 0

    with Session(repository.engine) as session:
        capture = session.scalars(select(ModelForecastCaptureModel)).one()
        payload = capture.payload

    assert capture.capture_policy == T30_CAPTURE_POLICY
    assert capture.horizon_id == T30_HORIZON
    assert payload["checkpoint"] == T30_CHECKPOINT
    assert payload["model_as_of"] == T30_CAPTURED_AT.astimezone(UTC).isoformat().replace(
        "+00:00", "Z"
    )
    assert payload["decision_evaluated_at"] == payload["model_as_of"]
    ref = payload["t30_market_reference"]
    assert ref["market"] == "ASIAN_HANDICAP"
    assert ref["home_price"] == 1.90
    assert ref["away_price"] == 1.95
    assert ref["source_hash"] == _market_snapshot()["source_hash"]
    # 完整 7 项输入真实持久化并参与 hash
    assert payload["four_field_xg_identity"]["four_fields"]["home_xg_for"] is not None
    assert payload["neutral_site"] is False
    assert payload["lambda_sigma_home"] == 0.5


# --------------------------------------------------------------------------- #
# 2. neutral_site strict fail-closed
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("mutator", "expected_blocker"),
    [
        (lambda c: c.update(neutral_site_resolution=None),
         "NOT_ESTIMABLE_NEUTRAL_SITE_RESOLUTION"),
        (lambda c: c["neutral_site_resolution"].pop("neutral_site"),
         "NOT_ESTIMABLE_NEUTRAL_SITE_VALUE"),
        (lambda c: c["neutral_site_resolution"].update(neutral_site=None),
         "NOT_ESTIMABLE_NEUTRAL_SITE_TYPE"),
        (lambda c: c["neutral_site_resolution"].update(neutral_site=0),
         "NOT_ESTIMABLE_NEUTRAL_SITE_TYPE"),
        (lambda c: c["neutral_site_resolution"].update(neutral_site=1),
         "NOT_ESTIMABLE_NEUTRAL_SITE_TYPE"),
        (lambda c: c["neutral_site_resolution"].update(neutral_site=""),
         "NOT_ESTIMABLE_NEUTRAL_SITE_TYPE"),
        (lambda c: c["neutral_site_resolution"].update(neutral_site="false"),
         "NOT_ESTIMABLE_NEUTRAL_SITE_TYPE"),
        (lambda c: c["neutral_site_resolution"].update(neutral_site="true"),
         "NOT_ESTIMABLE_NEUTRAL_SITE_TYPE"),
        (lambda c: c["neutral_site_resolution"].pop("neutral_site_resolution_source"),
         "NOT_ESTIMABLE_NEUTRAL_SITE_SOURCE"),
        (lambda c: c["neutral_site_resolution"].update(
            neutral_site_resolution_source="MADE_UP"
        ), "NOT_ESTIMABLE_NEUTRAL_SITE_SOURCE"),
        (lambda c: c["neutral_site_resolution"].pop("neutral_site_policy_version"),
         "NOT_ESTIMABLE_NEUTRAL_SITE_POLICY_VERSION"),
        (lambda c: c["neutral_site_resolution"].update(
            neutral_site_policy_version="w2.neutral_site_policy.v2"
        ), "NOT_ESTIMABLE_NEUTRAL_SITE_POLICY_VERSION"),
        (lambda c: c["neutral_site_resolution"].pop("neutral_site_as_of"),
         "NOT_ESTIMABLE_NEUTRAL_SITE_AS_OF"),
        (lambda c: c["neutral_site_resolution"].update(neutral_site_as_of="not-a-date"),
         "NOT_ESTIMABLE_NEUTRAL_SITE_AS_OF"),
        (lambda c: c["neutral_site_resolution"].update(
            neutral_site_as_of=(KICKOFF + timedelta(minutes=1)).isoformat()
        ), "NOT_ESTIMABLE_NEUTRAL_SITE_AS_OF_POST_KICKOFF"),
        (lambda c: c["neutral_site_resolution"].update(neutral_site_status="UNKNOWN"),
         "NOT_ESTIMABLE_NEUTRAL_SITE_STATUS"),
        (lambda c: _simulation_of(c)["input_readiness"].update(neutral_site=True),
         "NOT_ESTIMABLE_NEUTRAL_SITE_CONSISTENCY"),
    ],
)
def test_neutral_site_fails_closed(
    tmp_path: Path, mutator: Callable[[dict[str, Any]], None], expected_blocker: str
) -> None:
    repository = _repository(tmp_path)
    _seed_xg(repository)

    result = freeze_t30_capture(
        _mutated_card(mutator),
        repository=repository,
        market_snapshots={"fixture-1": _market_snapshot()},
        captured_at=T30_CAPTURED_AT,
        dry_run=False,
        write_db=True,
    )

    assert result["model_eligible_count"] == 0
    assert result["model_forecast_capture_count"] == 0
    assert result["blocked_reasons"] == [
        {"fixture_id": "fixture-1", "blocker": expected_blocker}
    ]


# --------------------------------------------------------------------------- #
# 3. lambda sigma strict fail-closed
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("mutator", "expected_blocker"),
    [
        (lambda c: _simulation_of(c).pop("lambda_sigma_home"),
         "NOT_ESTIMABLE_LAMBDA_SIGMA_MISSING"),
        (lambda c: _simulation_of(c).pop("lambda_sigma_away"),
         "NOT_ESTIMABLE_LAMBDA_SIGMA_MISSING"),
        (lambda c: _simulation_of(c).update(lambda_sigma_home="0.5"),
         "NOT_ESTIMABLE_LAMBDA_SIGMA_NON_NUMERIC"),
        (lambda c: _simulation_of(c).update(lambda_sigma_home=-0.1),
         "NOT_ESTIMABLE_LAMBDA_SIGMA_NEGATIVE"),
        (lambda c: _simulation_of(c).update(lambda_sigma_home=float("nan")),
         "NOT_ESTIMABLE_LAMBDA_SIGMA_NON_FINITE"),
        (lambda c: _simulation_of(c).update(lambda_sigma_home=float("inf")),
         "NOT_ESTIMABLE_LAMBDA_SIGMA_NON_FINITE"),
        (lambda c: _simulation_of(c)["calibration"].update(
            lambda_uncertainty_status="XG_UNCERTAINTY_SAMPLE_INSUFFICIENT"
        ), "NOT_ESTIMABLE_LAMBDA_UNCERTAINTY_STATUS"),
        (lambda c: _simulation_of(c)["calibration"].update(
            lambda_uncertainty_status="READY"
        ), "NOT_ESTIMABLE_LAMBDA_UNCERTAINTY_STATUS"),
        (lambda c: _simulation_of(c)["calibration"].update(
            lambda_uncertainty_method="none"
        ), "NOT_ESTIMABLE_LAMBDA_UNCERTAINTY_METHOD"),
        (lambda c: _simulation_of(c)["input_readiness"].pop(
            "lambda_uncertainty_input_hash"
        ), "NOT_ESTIMABLE_LAMBDA_UNCERTAINTY_INPUT_HASH"),
    ],
)
def test_lambda_sigma_fails_closed(
    tmp_path: Path, mutator: Callable[[dict[str, Any]], None], expected_blocker: str
) -> None:
    repository = _repository(tmp_path)
    _seed_xg(repository)

    result = freeze_t30_capture(
        _mutated_card(mutator),
        repository=repository,
        market_snapshots={"fixture-1": _market_snapshot()},
        captured_at=T30_CAPTURED_AT,
        dry_run=False,
        write_db=True,
    )

    assert result["model_eligible_count"] == 0
    assert result["model_forecast_capture_count"] == 0
    assert result["blocked_reasons"] == [
        {"fixture_id": "fixture-1", "blocker": expected_blocker}
    ]


# --------------------------------------------------------------------------- #
# 4. T-30 window boundaries
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("captured_at", "eligible"),
    [
        (KICKOFF - timedelta(minutes=35), True),   # T-35 left edge (inclusive)
        (KICKOFF - timedelta(minutes=25), True),   # T-25 right edge (inclusive)
        (KICKOFF - timedelta(minutes=36), False),  # before T-35
        (KICKOFF - timedelta(minutes=24), False),  # after T-25
        (KICKOFF + timedelta(minutes=1), False),   # post kickoff
        # same UTC instant expressed in a different timezone offset
        ((KICKOFF - timedelta(minutes=30)).astimezone(timezone(timedelta(hours=2))), True),
    ],
)
def test_t30_window_boundaries(
    tmp_path: Path, captured_at: datetime, eligible: bool
) -> None:
    repository = _repository(tmp_path)
    _seed_xg(repository)

    result = freeze_t30_capture(
        _day_view(),
        repository=repository,
        market_snapshots={"fixture-1": _market_snapshot(as_of=captured_at.isoformat())},
        captured_at=captured_at,
        dry_run=False,
        write_db=True,
    )

    if eligible:
        assert result["model_forecast_capture_count"] == 1
    else:
        assert result["model_forecast_capture_count"] == 0


def test_t30_naive_datetime_rejected(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_xg(repository)

    with pytest.raises(ModelForecastLedgerError):
        freeze_t30_capture(
            _day_view(),
            repository=repository,
            market_snapshots={"fixture-1": _market_snapshot()},
            captured_at=T30_CAPTURED_AT.replace(tzinfo=None),
            dry_run=False,
            write_db=True,
        )


# --------------------------------------------------------------------------- #
# 5. quote reference fail-closed
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "snapshot",
    [
        {},                                                  # missing
        _market_snapshot(market="TOTALS"),                   # wrong market
        _market_snapshot(home_price=None),                   # incomplete
        _market_snapshot(away_price=None),                   # incomplete
        _market_snapshot(home_price=1.0),                    # odds <= 1
        _market_snapshot(away_price=0.9),                    # odds <= 1
        _market_snapshot(as_of=(KICKOFF - timedelta(minutes=10)).isoformat()),  # outside window
        _market_snapshot(as_of=(KICKOFF + timedelta(minutes=1)).isoformat()),   # post kickoff
        _market_snapshot(live=True),                         # live
        _market_snapshot(suspended=True),                    # suspended
        _market_snapshot(source_hash=None),                  # missing identity
    ],
)
def test_t30_quote_reference_fails_closed(tmp_path: Path, snapshot: dict[str, Any]) -> None:
    repository = _repository(tmp_path)
    _seed_xg(repository)

    result = freeze_t30_capture(
        _day_view(),
        repository=repository,
        market_snapshots={"fixture-1": snapshot},
        captured_at=T30_CAPTURED_AT,
        dry_run=False,
        write_db=True,
    )

    assert result["model_eligible_count"] == 0
    assert result["model_forecast_capture_count"] == 0
    assert result["blocked_count"] == 1


def test_t30_missing_market_snapshot_fails_closed(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_xg(repository)

    result = freeze_t30_capture(
        _day_view(),
        repository=repository,
        market_snapshots={},  # no snapshot for fixture-1
        captured_at=T30_CAPTURED_AT,
        dry_run=False,
        write_db=True,
    )

    assert result["model_forecast_capture_count"] == 0
    assert result["blocked_reasons"] == [
        {"fixture_id": "fixture-1", "blocker": "NOT_ESTIMABLE_T30_QUOTE_MISSING"}
    ]


# --------------------------------------------------------------------------- #
# 6. identity / idempotency
# --------------------------------------------------------------------------- #
def test_t30_rerun_same_input_is_idempotent(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_xg(repository)

    first = freeze_t30_capture(
        _day_view(),
        repository=repository,
        market_snapshots={"fixture-1": _market_snapshot()},
        captured_at=T30_CAPTURED_AT,
        dry_run=False,
        write_db=True,
    )
    second = freeze_t30_capture(
        _day_view(),
        repository=repository,
        market_snapshots={"fixture-1": _market_snapshot()},
        captured_at=T30_CAPTURED_AT,
        dry_run=False,
        write_db=True,
    )

    assert first["model_forecast_capture_count"] == 1
    assert second["model_forecast_capture_count"] == 0
    assert second["already_captured_count"] == 1

    with Session(repository.engine) as session:
        assert len(session.scalars(select(ModelForecastCaptureModel)).all()) == 1


def test_t30_same_identity_different_payload_fails_closed(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_xg(repository)

    freeze_t30_capture(
        _day_view(),
        repository=repository,
        market_snapshots={"fixture-1": _market_snapshot()},
        captured_at=T30_CAPTURED_AT,
        dry_run=False,
        write_db=True,
    )

    # Same relational identity (fixture, model family, version, policy, horizon)
    # but a different payload (different quote) must fail closed, not overwrite.
    mutated = _day_view()
    mutated["cards"][0]["simulation"]["simulation"]["score_matrix_summary"]["home_win"] = 0.6
    mutated["cards"][0]["simulation"]["simulation"]["score_matrix_summary"]["away_win"] = 0.2

    with pytest.raises(ModelForecastLedgerError):
        freeze_t30_capture(
            mutated,
            repository=repository,
            market_snapshots={"fixture-1": _market_snapshot()},
            captured_at=T30_CAPTURED_AT,
            dry_run=False,
            write_db=True,
        )


def test_first_eligible_and_t30_policies_coexist(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_xg(repository)

    # A FIRST_ELIGIBLE capture and a T-30 capture for the same fixture are two
    # distinct tracks (different policy/horizon), so both may exist.
    from w2.tracking.model_forecast_ledger import run_model_forecast_capture

    run_model_forecast_capture(
        _day_view(),
        repository=repository,
        captured_at=NOW,
        dry_run=False,
        write_db=True,
    )
    freeze_t30_capture(
        _day_view(),
        repository=repository,
        market_snapshots={"fixture-1": _market_snapshot()},
        captured_at=T30_CAPTURED_AT,
        dry_run=False,
        write_db=True,
    )

    with Session(repository.engine) as session:
        policies = set(
            session.scalars(select(ModelForecastCaptureModel.capture_policy)).all()
        )
    assert policies == {"FIRST_ELIGIBLE_FREEZE_IMMUTABLE", T30_CAPTURE_POLICY}


# --------------------------------------------------------------------------- #
# 7. real 0.12 vs 0.30 parameter-level replay
# --------------------------------------------------------------------------- #
def test_real_012_vs_030_parameter_level_replay() -> None:
    inputs = dict(
        home_xg_for=1.9,
        home_xg_against=0.7,
        away_xg_for=0.8,
        away_xg_against=1.5,
        home_elo=None,
        away_elo=None,
        home_squad_value_eur=None,
        away_squad_value_eur=None,
    )
    cal_030 = calibrate_lambdas(
        **inputs,
        apply_home_advantage=True,
        params=LambdaCalibrationParams(home_advantage_goals=0.30),
    )
    cal_012 = calibrate_lambdas(
        **inputs,
        apply_home_advantage=True,
        params=LambdaCalibrationParams(home_advantage_goals=0.12),
    )

    # Parameter-level, not a probability offset: the home/away lambda deltas are
    # exactly (0.30 - 0.12) / 2, symmetric.
    assert math.isclose(cal_030.lambda_home - cal_012.lambda_home, 0.09, abs_tol=1e-9)
    assert math.isclose(cal_030.lambda_away - cal_012.lambda_away, -0.09, abs_tol=1e-9)

    def _matrix(cal) -> dict[tuple[int, int], float]:
        return _exact_score_matrix_with_uncertainty(
            cal.lambda_home,
            cal.lambda_away,
            sigma_home=0.0,
            sigma_away=0.0,
            rho=0.0,
            max_goals=10,
        )

    matrix_030 = _matrix(cal_030)
    matrix_012 = _matrix(cal_012)
    prob_030 = one_x_two_from_matrix(matrix_030)
    prob_012 = one_x_two_from_matrix(matrix_012)

    # Different, and hashes recompute deterministically.
    assert prob_030 != prob_012
    import hashlib
    import json

    def _matrix_hash(matrix: dict[tuple[int, int], float]) -> str:
        encoded = json.dumps(
            {f"{h}:{a}": round(p, 12) for (h, a), p in sorted(matrix.items())},
            sort_keys=True,
        )
        return hashlib.sha256(encoded.encode()).hexdigest()

    assert _matrix_hash(matrix_030) != _matrix_hash(matrix_012)
    # Recompute is deterministic.
    assert _matrix_hash(matrix_030) == _matrix_hash(matrix_030)


# --------------------------------------------------------------------------- #
# 8. result isolation
# --------------------------------------------------------------------------- #
def test_capture_is_byte_identical_with_or_without_result(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _seed_xg(repository)

    def _capture_payload() -> dict[str, Any]:
        result = freeze_t30_capture(
            _day_view(),
            repository=repository,
            market_snapshots={"fixture-1": _market_snapshot()},
            captured_at=T30_CAPTURED_AT,
            dry_run=True,
            write_db=False,
        )
        return dict(result["captures"][0])

    without_result = _capture_payload()

    # Insert a settled result; capture must not consult it.
    with Session(repository.engine) as session:
        session.add(
            ResultModel(
                fixture_id="fixture-1",
                home_goals=2,
                away_goals=1,
                result_status="FT",
                confirmed_at=KICKOFF + timedelta(hours=2),
                source_payload_sha256="s" * 64,
                result_hash="r" * 64,
            )
        )
        session.commit()

    with_result = _capture_payload()

    assert without_result == with_result


@pytest.mark.parametrize('field,value', [
    ('provider', 'Bet365'), ('bookmaker_name', 'Bet365'), ('line', None),
    ('line', float('nan')), ('line', 0.1), ('home_price', float('inf')),
    ('selection_policy', 'unknown'), ('fixture_id', 'other'), ('source_hash', '0' * 64),
])
def test_t30_quote_identity_tampering_fails_closed(tmp_path, field, value):
    repository = _repository(tmp_path)
    _seed_xg(repository)
    result = repository.freeze_t30(
        _day_view(), market_snapshots={'fixture-1': _market_snapshot(**{field: value})},
        captured_at=T30_CAPTURED_AT,
    )
    assert result['model_forecast_capture_count'] == 0
    assert result['blocked_count'] == 1


def test_development_track_excluded_from_recommendation_opportunities(tmp_path):
    repository = _repository(tmp_path)
    _seed_xg(repository)
    repository.freeze_t30(
        _day_view(), market_snapshots={'fixture-1': _market_snapshot()},
        captured_at=T30_CAPTURED_AT, dry_run=False, write_db=True,
    )
    assert repository.opportunity_capture_seeds('fixture-1') == ()
    assert repository.denominator_capture_seeds() == ()
