"""AH/OU F9+F6 softmax selection — frozen model parameters from task 5/6 research.

This is the production decision core that replaces the old weighted
``factor_score`` AH direction and the ``bookmaker_intent`` OU view. It contains
only the frozen softmax arithmetic plus the frozen model JSON (loaded from
``config/models/ah_ou/``). Feature construction (F9 snapshot + F6 meeting
history -> the 14/22-dim feature dict) lives in ``ah_ou_features``.

Frozen semantics (do not change without a new version + unseen window):
* AH direction follows the market (``market_home_cover_p >= 0.5``); the factor
  only scores the selected side. Selection = ``|q-0.5| * support >= cutoff``.
* OU only recommends OVER; selection = ``factor_over_share - market_over_q >= threshold``.
"""
from __future__ import annotations

import json
import math
from collections.abc import Mapping
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from w2.domain.odds import settle_total_goals

AH_MODEL_PATH = Path("config/models/ah_ou/xg_f9_f6_validation_selected_model.json")
OU_MODEL_PATH = Path("config/models/ah_ou/ou_xg_f9_f6_over_value_candidate.json")


def _model_path(relative: Path) -> Path:
    candidates = (Path.cwd() / relative, Path(__file__).resolve().parents[3] / relative)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"AH_OU_MODEL_NOT_FOUND: {relative}")


@lru_cache(maxsize=1)
def load_ah_model() -> dict[str, Any]:
    return json.loads(_model_path(AH_MODEL_PATH).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_ou_model() -> dict[str, Any]:
    return json.loads(_model_path(OU_MODEL_PATH).read_text(encoding="utf-8"))


def _has(value: Any) -> bool:
    return value is not None and value != ""


def ah_feature_vector(features: Mapping[str, Any]) -> list[float]:
    """14-dim goal-margin feature vector, order frozen in the model JSON."""
    def f(key: str) -> float:
        return float(features[key])

    venue = f("f6_same_venue") if _has(features.get("f6_same_venue")) else f("f6_score")
    return [
        f("f9_score"), f("f6_shrunk"), f("f6_n") / 10,
        f("f9_home_xgf"), f("f9_home_xga"), f("f9_away_xgf"), f("f9_away_xga"),
        f("f6_recent3"), f("f6_decay365"), f("f6_decay730"), venue,
        f("f6_same_venue_n") / 10, f("f6_last_diff"), math.log1p(f("f6_last_age_days")) / 8,
    ]


def ou_feature_vector(features: Mapping[str, Any]) -> list[float]:
    """22-dim total-goals vector: first 14 shared with AH, then 8 total-goal F6."""
    def f(key: str) -> float:
        return float(features[key])

    total_venue = (
        f("f6_total_same_venue")
        if _has(features.get("f6_total_same_venue"))
        else f("f6_total_mean")
    )
    return [
        *ah_feature_vector(features),
        f("f6_total_mean"), f("f6_total_recent3"), f("f6_total_decay365"),
        f("f6_total_decay730"), total_venue, f("f6_total_same_venue_n") / 10,
        f("f6_total_last"), math.log1p(f("f6_total_last_age_days")) / 8,
    ]


def _softmax_classes(vector: list[float], model: Mapping[str, Any]) -> list[float]:
    mean, scale = model["scaler_mean"], model["scaler_scale"]
    normalized = [(value - center) / spread for value, center, spread in zip(vector, mean, scale)]
    logits = [
        intercept + sum(weight * value for weight, value in zip(weights, normalized))
        for intercept, weights in zip(model["softmax_intercept"], model["softmax_coefficients"])
    ]
    peak = max(logits)
    exponential = [math.exp(value - peak) for value in logits]
    total = sum(exponential)
    return [value / total for value in exponential]


def ah_home_cover_p(features: Mapping[str, Any], home_line: float) -> float:
    model = load_ah_model()
    probabilities = _softmax_classes(ah_feature_vector(features), model)
    return sum(
        probability
        for probability, klass in zip(probabilities, model["classes"])
        if klass + home_line > 0
    )


def ah_select(
    features: Mapping[str, Any],
    *,
    home_line: float,
    home_odds: float,
    away_odds: float,
) -> dict[str, Any]:
    model = load_ah_model()
    q = (1 / home_odds) / ((1 / home_odds) + (1 / away_odds))
    factor = ah_home_cover_p(features, home_line)
    home = q >= 0.5
    support = factor if home else 1 - factor
    score = abs(q - 0.5) * support
    return {
        "side": "HOME" if home else "AWAY",
        "factor_home_cover_p": factor,
        "market_home_cover_p": q,
        "score": score,
        "selected": score >= model["selection_cutoff"] - 1e-14,
    }


def ou_factor_share(features: Mapping[str, Any], line: float) -> float:
    model = load_ou_model()
    probabilities = _softmax_classes(ou_feature_vector(features), model)
    weights = {"WIN": 1.0, "HALF_WIN": 0.5, "PUSH": 0.0, "HALF_LOSS": -0.5, "LOSS": -1.0}
    signed = [
        (probability, weights[settle_total_goals(int(klass), "OVER", Decimal(str(line))).value])
        for probability, klass in zip(probabilities, model["classes"])
    ]
    gain = sum(probability * weight for probability, weight in signed if weight > 0)
    loss = sum(-probability * weight for probability, weight in signed if weight < 0)
    return gain / (gain + loss)


def ou_select(
    features: Mapping[str, Any],
    *,
    line: float,
    over_odds: float,
    under_odds: float,
) -> dict[str, Any]:
    model = load_ou_model()
    factor = ou_factor_share(features, line)
    q = (1 / over_odds) / ((1 / over_odds) + (1 / under_odds))
    edge = factor - q
    return {
        "factor_over_share": factor,
        "market_over_q": q,
        "edge": edge,
        "selected": edge >= model["threshold"],
    }
