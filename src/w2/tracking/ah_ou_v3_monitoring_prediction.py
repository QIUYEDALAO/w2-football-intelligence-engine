"""Observation of the existing frozen model; no scoring or fitting changes."""

from collections.abc import Mapping
from typing import Any

from w2.strategy.ah_ou_softmax import (
    _softmax_classes,
    ah_feature_vector,
    load_ah_model,
    load_ou_model,
    ou_feature_vector,
)


def monitoring_class_probabilities(
    features: Mapping[str, Any], market: str
) -> list[dict[str, Any]]:
    if market == "ASIAN_HANDICAP":
        model, vector = load_ah_model(), ah_feature_vector(features)
    elif market == "TOTALS":
        model, vector = load_ou_model(), ou_feature_vector(features)
    else:
        raise ValueError("V3_MONITORING_MARKET_INVALID")
    return [
        {"class": klass, "probability": probability}
        for klass, probability in zip(
            model["classes"], _softmax_classes(vector, model), strict=True)
    ]
