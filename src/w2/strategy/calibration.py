from __future__ import annotations

from dataclasses import dataclass
from math import log

CALIBRATION_VERSION = "w2.formal.lambda_baseline_prior.v1"
CALIBRATION_STATUS = "BASELINE_PRIOR"
MAX_LINEUP_AH_DELTA = 0.25
MAX_LINEUP_TOTALS_DELTA = 0.30


@dataclass(frozen=True, kw_only=True)
class LambdaCalibrationParams:
    home_advantage_goals: float = 0.12
    elo_gap_weight: float = 0.28
    squad_value_log_weight: float = 0.18
    lineup_adjustment_weight: float = 0.08
    dixon_coles_rho: float = 0.0
    minimum_lambda: float = 0.15
    maximum_lambda: float = 4.25
    minimum_total_goals: float = 1.35
    maximum_total_goals: float = 4.40


@dataclass(frozen=True, kw_only=True)
class LambdaCalibrationOutput:
    calibration_version: str
    calibration_status: str
    lambda_home: float
    lambda_away: float
    params: dict[str, float]
    input_weights: dict[str, float]


def calibrate_lambdas(
    *,
    home_xg_for: float,
    home_xg_against: float,
    away_xg_for: float,
    away_xg_against: float,
    home_elo: float | None,
    away_elo: float | None,
    home_squad_value_eur: float | None,
    away_squad_value_eur: float | None,
    lineup_strength_adjustment: float = 0.0,
    lineup_ah_adjustment: float = 0.0,
    lineup_totals_adjustment: float = 0.0,
    lineup_ah_evidence_enabled: bool = False,
    lineup_totals_evidence_enabled: bool = False,
    apply_home_advantage: bool = True,
    params: LambdaCalibrationParams | None = None,
) -> LambdaCalibrationOutput:
    params = params or LambdaCalibrationParams()
    base_home = (float(home_xg_for) + float(away_xg_against)) / 2.0
    base_away = (float(away_xg_for) + float(home_xg_against)) / 2.0
    total = _clamp(
        base_home + base_away,
        minimum=params.minimum_total_goals,
        maximum=params.maximum_total_goals,
    )
    raw_delta = base_home - base_away
    elo_delta = 0.0
    if home_elo is not None and away_elo is not None:
        elo_delta = ((float(home_elo) - float(away_elo)) / 400.0) * params.elo_gap_weight
    value_delta = 0.0
    if (
        home_squad_value_eur is not None
        and away_squad_value_eur is not None
        and home_squad_value_eur > 0
        and away_squad_value_eur > 0
    ):
        value_delta = log(float(home_squad_value_eur) / float(away_squad_value_eur)) * (
            params.squad_value_log_weight
        )
    applied_home_advantage_goals = (
        params.home_advantage_goals if apply_home_advantage else 0.0
    )
    adjusted_delta = (
        raw_delta
        + applied_home_advantage_goals
        + elo_delta
        + value_delta
        + float(lineup_strength_adjustment) * params.lineup_adjustment_weight
    )
    if lineup_ah_evidence_enabled:
        adjusted_delta += _symmetric_clamp(lineup_ah_adjustment, MAX_LINEUP_AH_DELTA)
    if lineup_totals_evidence_enabled:
        total = _clamp(
            total + _symmetric_clamp(lineup_totals_adjustment, MAX_LINEUP_TOTALS_DELTA),
            minimum=params.minimum_total_goals,
            maximum=params.maximum_total_goals,
        )
    lambda_home = (total + adjusted_delta) / 2.0
    lambda_away = (total - adjusted_delta) / 2.0
    lambda_home = _clamp(
        lambda_home,
        minimum=params.minimum_lambda,
        maximum=params.maximum_lambda,
    )
    lambda_away = _clamp(
        lambda_away,
        minimum=params.minimum_lambda,
        maximum=params.maximum_lambda,
    )
    return LambdaCalibrationOutput(
        calibration_version=CALIBRATION_VERSION,
        calibration_status=CALIBRATION_STATUS,
        lambda_home=round(lambda_home, 6),
        lambda_away=round(lambda_away, 6),
        params={
            "home_advantage_goals": params.home_advantage_goals,
            "applied_home_advantage_goals": applied_home_advantage_goals,
            "elo_gap_weight": params.elo_gap_weight,
            "squad_value_log_weight": params.squad_value_log_weight,
            "lineup_adjustment_weight": params.lineup_adjustment_weight,
            "lineup_ah_delta_cap": MAX_LINEUP_AH_DELTA,
            "lineup_totals_delta_cap": MAX_LINEUP_TOTALS_DELTA,
            "dixon_coles_rho": params.dixon_coles_rho,
            "minimum_lambda": params.minimum_lambda,
            "maximum_lambda": params.maximum_lambda,
            "minimum_total_goals": params.minimum_total_goals,
            "maximum_total_goals": params.maximum_total_goals,
        },
        input_weights={
            "xg": 1.0,
            "elo": params.elo_gap_weight,
            "squad_value": params.squad_value_log_weight,
            "lineups": params.lineup_adjustment_weight,
            "lineup_ah_enabled": float(lineup_ah_evidence_enabled),
            "lineup_totals_enabled": float(lineup_totals_evidence_enabled),
        },
    )


def _clamp(value: float, *, minimum: float, maximum: float) -> float:
    return min(max(float(value), minimum), maximum)


def _symmetric_clamp(value: float, cap: float) -> float:
    return min(max(float(value), -cap), cap)
