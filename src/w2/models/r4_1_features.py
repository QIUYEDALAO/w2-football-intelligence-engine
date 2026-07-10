from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from w2.models.dixon_coles import one_x_two_from_matrix, tau_correction
from w2.models.fair_market_estimate import fair_lines_from_lambdas
from w2.models.independent import AsOfFeatureBuilder, MatchRecord

R4_1_WINDOW_MATCHES = 8
R4_1_TIME_DECAY_HALF_LIFE_DAYS = 365.0
R4_1_FEATURE_NAMES_BASE = (
    "intercept",
    "home_field",
    "attack_xg_for",
    "opponent_xg_against",
    "elo_gap",
)


@dataclass(frozen=True, kw_only=True)
class R4_1LambdaModel:
    coefficients: tuple[float, ...]
    feature_names: tuple[str, ...]
    l2: float
    iterations: int
    learning_rate: float


@dataclass(frozen=True, kw_only=True)
class R4_1Prediction:
    probabilities: dict[str, float]
    fair_ah: float
    fair_ou: float
    ah_probabilities: dict[str, float]
    ou_probabilities: dict[str, float]
    home_mu: float
    away_mu: float


def r4_1_offline_model_samples(
    *,
    fixtures: Sequence[Any],
    statistics_by_fixture: Mapping[str, Mapping[str, float]],
    min_history: int,
) -> list[Any]:
    from w2.backtest.free_tier_2024 import OfflineModelSample

    builders: dict[str, AsOfFeatureBuilder] = {}
    histories: dict[tuple[str, str], list[tuple[float, float]]] = {}
    samples: list[Any] = []
    for fixture in sorted(
        fixtures,
        key=lambda item: (item.kickoff_utc, item.competition_id, item.fixture_id),
    ):
        builder = builders.setdefault(fixture.competition_id, AsOfFeatureBuilder())
        match = match_record_from_fixture(fixture)
        proxy_features = builder.features(match)
        home_key = (fixture.competition_id, fixture.home_team)
        away_key = (fixture.competition_id, fixture.away_team)
        home_history = histories.get(home_key, [])
        away_history = histories.get(away_key, [])
        current_xg = statistics_by_fixture.get(fixture.fixture_id)
        if current_xg and len(home_history) >= min_history and len(away_history) >= min_history:
            true_features = dict(proxy_features)
            true_features.update(
                r4_1_strength_features(
                    competition_id=fixture.competition_id,
                    histories=histories,
                    home_key=home_key,
                    away_key=away_key,
                )
            )
            samples.append(
                OfflineModelSample(
                    fixture=fixture,
                    proxy_features=dict(proxy_features),
                    true_features=true_features,
                )
            )
        builder.update(match)
        if current_xg is not None:
            home_xg = current_xg.get(fixture.home_team)
            away_xg = current_xg.get(fixture.away_team)
            if home_xg is not None and away_xg is not None:
                histories.setdefault(home_key, []).append((float(home_xg), float(away_xg)))
                histories.setdefault(away_key, []).append((float(away_xg), float(home_xg)))
    return samples


def match_record_from_fixture(fixture: Any) -> MatchRecord:
    return MatchRecord(
        fixture_id=str(fixture.fixture_id),
        competition=str(fixture.competition_id),
        season=str(fixture.season),
        kickoff_utc=fixture.kickoff_utc,
        home_team=str(fixture.home_team),
        away_team=str(fixture.away_team),
        home_goals=int(fixture.home_goals),
        away_goals=int(fixture.away_goals),
        neutral_site=bool(fixture.neutral_site),
    )


def r4_1_strength_features(
    *,
    competition_id: str,
    histories: Mapping[tuple[str, str], Sequence[tuple[float, float]]],
    home_key: tuple[str, str],
    away_key: tuple[str, str],
) -> dict[str, float]:
    home_recent = list(histories[home_key])[-R4_1_WINDOW_MATCHES:]
    away_recent = list(histories[away_key])[-R4_1_WINDOW_MATCHES:]
    league_recent = [
        item
        for (league, _team), history in histories.items()
        if league == competition_id
        for item in list(history)[-R4_1_WINDOW_MATCHES:]
    ]
    league_for = _mean([item[0] for item in league_recent], default=1.25)
    league_against = _mean([item[1] for item in league_recent], default=1.25)
    home_for = _mean([item[0] for item in home_recent], default=league_for)
    home_against = _mean([item[1] for item in home_recent], default=league_against)
    away_for = _mean([item[0] for item in away_recent], default=league_for)
    away_against = _mean([item[1] for item in away_recent], default=league_against)
    return r4_1_strength_features_from_rolling(
        home_for=home_for,
        home_against=home_against,
        away_for=away_for,
        away_against=away_against,
        league_for=league_for,
        league_against=league_against,
    )


def r4_1_strength_features_from_rolling(
    *,
    home_for: float,
    home_against: float,
    away_for: float,
    away_against: float,
    league_for: float = 1.25,
    league_against: float = 1.25,
) -> dict[str, float]:
    home_attack = home_for * _safe_ratio(away_against, league_against)
    away_attack = away_for * _safe_ratio(home_against, league_against)
    home_defence = home_against * _safe_ratio(away_for, league_for)
    away_defence = away_against * _safe_ratio(home_for, league_for)
    return {
        "home_attack_strength": _clamp(home_attack, 0.25, 3.5),
        "away_attack_strength": _clamp(away_attack, 0.25, 3.5),
        "home_defence_strength": _clamp(home_defence, 0.25, 3.5),
        "away_defence_strength": _clamp(away_defence, 0.25, 3.5),
        "rolling_home_xg": round(home_for, 6),
        "rolling_away_xg": round(away_for, 6),
    }


def fit_r4_1_lambda_model(
    samples: Sequence[Any],
    *,
    min_sample: int,
) -> R4_1LambdaModel:
    if len(samples) < min_sample:
        return R4_1LambdaModel(
            coefficients=(math.log(1.25), 0.0, 0.0, 0.0, 0.0),
            feature_names=(
                *R4_1_FEATURE_NAMES_BASE,
                "dixon_coles_rho=0.00",
            ),
            l2=0.004,
            iterations=0,
            learning_rate=0.0,
        )
    ordered = sorted(samples, key=lambda s: (s.fixture.kickoff_utc, s.fixture.fixture_id))
    competitions = tuple(sorted({sample.fixture.competition_id for sample in ordered}))
    feature_names = (
        *R4_1_FEATURE_NAMES_BASE,
        *(f"home_field__{competition}" for competition in competitions),
    )
    beta = [math.log(1.25), 0.06, 0.08, 0.08, 0.04, *([0.0] * len(competitions))]
    learning_rate = 0.020
    l2 = 0.004
    cutoff = max(sample.fixture.kickoff_utc for sample in ordered)
    rows: list[tuple[list[float], float, float]] = []
    for sample in ordered:
        rows.extend(r4_1_goal_fit_rows(sample, competitions=competitions, cutoff=cutoff))
    total_weight = sum(weight for _, _, weight in rows) or 1.0
    for _ in range(1400):
        gradient = [0.0 for _ in beta]
        for features, goals, weight in rows:
            log_mu = _clamp(
                sum(coef * value for coef, value in zip(beta, features, strict=True)),
                -3.0,
                2.0,
            )
            mu = math.exp(log_mu)
            error = (mu - goals) * weight
            for index, value in enumerate(features):
                gradient[index] += error * value
        for index in range(len(beta)):
            penalty = 0.0 if index == 0 else l2 * beta[index]
            beta[index] -= learning_rate * (gradient[index] / total_weight + penalty)
    rho = fit_r4_1_rho(ordered, beta, competitions)
    return R4_1LambdaModel(
        coefficients=tuple(beta),
        feature_names=(*feature_names, f"dixon_coles_rho={rho:.2f}"),
        l2=l2,
        iterations=1400,
        learning_rate=learning_rate,
    )


def r4_1_goal_fit_rows(
    sample: Any,
    *,
    competitions: tuple[str, ...],
    cutoff: datetime,
) -> list[tuple[list[float], float, float]]:
    home_features, away_features = r4_1_feature_rows(sample, competitions)
    age_days = max((cutoff - sample.fixture.kickoff_utc).total_seconds() / 86400.0, 0.0)
    weight = 0.5 ** (age_days / R4_1_TIME_DECAY_HALF_LIFE_DAYS)
    return [
        (home_features, float(sample.fixture.home_goals), weight),
        (away_features, float(sample.fixture.away_goals), weight),
    ]


def r4_1_feature_rows(
    sample: Any,
    competitions: tuple[str, ...],
) -> tuple[list[float], list[float]]:
    fixture = sample.fixture
    features = sample.true_features
    elo_gap = float(features["elo_diff"]) / 400.0
    league_home = [
        1.0 if fixture.competition_id == competition else 0.0 for competition in competitions
    ]
    home_row = [
        1.0,
        float(features["home_field"]),
        float(features["home_attack_strength"]),
        float(features["away_defence_strength"]),
        elo_gap,
        *league_home,
    ]
    away_row = [
        1.0,
        0.0,
        float(features["away_attack_strength"]),
        float(features["home_defence_strength"]),
        -elo_gap,
        *([0.0] * len(competitions)),
    ]
    return home_row, away_row


def fit_r4_1_rho(
    samples: Sequence[Any],
    beta: Sequence[float],
    competitions: tuple[str, ...],
) -> float:
    best_rho = 0.0
    best_loss = float("inf")
    candidates = tuple(round(-0.20 + step * 0.01, 2) for step in range(41))
    for rho in candidates:
        loss = 0.0
        for sample in samples:
            home_mu, away_mu = r4_1_lambdas(sample, beta, competitions)
            probability = dc_score_probability(
                sample.fixture.home_goals,
                sample.fixture.away_goals,
                home_mu,
                away_mu,
                rho,
            )
            loss += -math.log(max(probability, 1e-12))
        if loss < best_loss:
            best_loss = loss
            best_rho = rho
    return best_rho


def r4_1_lambdas(
    sample: Any,
    coefficients: Sequence[float],
    competitions: tuple[str, ...],
) -> tuple[float, float]:
    home_row, away_row = r4_1_feature_rows(sample, competitions)
    return r4_1_lambdas_from_rows(
        home_row,
        away_row,
        coefficients=coefficients,
    )


def r4_1_lambdas_from_rows(
    home_row: Sequence[float],
    away_row: Sequence[float],
    *,
    coefficients: Sequence[float],
) -> tuple[float, float]:
    lambdas = []
    for row in (home_row, away_row):
        log_mu = _clamp(
            sum(coef * value for coef, value in zip(coefficients, row, strict=True)),
            -3.0,
            2.0,
        )
        lambdas.append(_clamp(math.exp(log_mu), 0.05, 4.25))
    return lambdas[0], lambdas[1]


def r4_1_predictions(
    samples: Sequence[Any],
    model: R4_1LambdaModel,
) -> list[dict[str, Any]]:
    from w2.backtest.free_tier_2024 import _prediction_row

    rows = []
    for sample in samples:
        prediction = predict_r4_1_sample(sample, model)
        rows.append(_prediction_row(fixture=sample.fixture, probabilities=prediction.probabilities))
    return rows


def predict_r4_1_sample(sample: Any, model: R4_1LambdaModel) -> R4_1Prediction:
    competitions = r4_1_competitions_from_feature_names(model.feature_names)
    coefficients = model.coefficients[: 5 + len(competitions)]
    home_mu, away_mu = r4_1_lambdas(sample, coefficients, competitions)
    return r4_1_prediction_from_lambdas(
        home_mu=home_mu,
        away_mu=away_mu,
        rho=rho_from_r4_1(model),
    )


def r4_1_prediction_from_feature_rows(
    *,
    home_row: Sequence[float],
    away_row: Sequence[float],
    coefficients: Sequence[float],
    rho: float,
    temperature: float,
) -> R4_1Prediction:
    home_mu, away_mu = r4_1_lambdas_from_rows(
        home_row,
        away_row,
        coefficients=coefficients,
    )
    raw = r4_1_prediction_from_lambdas(home_mu=home_mu, away_mu=away_mu, rho=rho)
    return R4_1Prediction(
        probabilities=temperature_scale_probabilities(raw.probabilities, temperature=temperature),
        fair_ah=raw.fair_ah,
        fair_ou=raw.fair_ou,
        ah_probabilities=raw.ah_probabilities,
        ou_probabilities=raw.ou_probabilities,
        home_mu=raw.home_mu,
        away_mu=raw.away_mu,
    )


def r4_1_prediction_from_lambdas(*, home_mu: float, away_mu: float, rho: float) -> R4_1Prediction:
    probabilities = dc_one_x_two(home_mu, away_mu, rho)
    fair_ah, fair_ou, ah_probabilities, ou_probabilities = fair_lines_from_lambdas(
        home_mu=home_mu,
        away_mu=away_mu,
        rho=rho,
    )
    return R4_1Prediction(
        probabilities=probabilities,
        fair_ah=fair_ah,
        fair_ou=fair_ou,
        ah_probabilities=ah_probabilities,
        ou_probabilities=ou_probabilities,
        home_mu=home_mu,
        away_mu=away_mu,
    )


def temperature_scale_probabilities(
    probabilities: Mapping[str, float],
    *,
    temperature: float,
) -> dict[str, float]:
    adjusted = {
        key: max(float(value), 1e-12) ** (1.0 / temperature) for key, value in probabilities.items()
    }
    total = sum(adjusted.values())
    if total <= 0:
        return {"HOME": 1 / 3, "DRAW": 1 / 3, "AWAY": 1 / 3}
    return {key: round(value / total, 8) for key, value in adjusted.items()}


def r4_1_competitions_from_feature_names(feature_names: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        name.removeprefix("home_field__")
        for name in feature_names
        if name.startswith("home_field__")
    )


def rho_from_r4_1(model: R4_1LambdaModel) -> float:
    for name in model.feature_names:
        if name.startswith("dixon_coles_rho="):
            return float(name.split("=", 1)[1])
    return 0.0


def dc_score_probability(
    home_goals: int,
    away_goals: int,
    home_mu: float,
    away_mu: float,
    rho: float,
) -> float:
    base = math.exp(-home_mu) * (home_mu**home_goals) / math.factorial(home_goals)
    base *= math.exp(-away_mu) * (away_mu**away_goals) / math.factorial(away_goals)
    return max(base * tau_correction(home_goals, away_goals, home_mu, away_mu, rho), 0.0)


def dc_one_x_two(
    home_mu: float,
    away_mu: float,
    rho: float,
    *,
    max_goals: int = 10,
) -> dict[str, float]:
    matrix = {
        (home, away): dc_score_probability(home, away, home_mu, away_mu, rho)
        for home in range(max_goals + 1)
        for away in range(max_goals + 1)
    }
    total = sum(matrix.values())
    if total <= 0:
        return {"HOME": 1 / 3, "DRAW": 1 / 3, "AWAY": 1 / 3}
    normalized = {score: probability / total for score, probability in matrix.items()}
    return one_x_two_from_matrix(normalized)


def _mean(values: Sequence[float], *, default: float) -> float:
    return sum(values) / len(values) if values else default


def _safe_ratio(value: float, denominator: float) -> float:
    return value / denominator if denominator > 0 else 1.0


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(float(value), lower), upper)
