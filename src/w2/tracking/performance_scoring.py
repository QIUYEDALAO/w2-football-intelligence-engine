from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

BOOTSTRAP_ITERATIONS = 1000
BOOTSTRAP_SEED = 7


def probability_vector(
    record: Mapping[str, Any],
    key: str,
) -> tuple[float, float, float] | None:
    identity = record.get("probability_identity")
    if not isinstance(identity, Mapping):
        return None
    raw_value = identity.get(key)
    if not isinstance(raw_value, Mapping):
        return None
    raw: Mapping[str, Any] = raw_value
    one_x_two = raw.get("one_x_two")
    if isinstance(one_x_two, Mapping):
        probabilities = one_x_two.get("probabilities")
        raw = probabilities if isinstance(probabilities, Mapping) else one_x_two
    values = tuple(_number(raw.get(name)) for name in ("HOME", "DRAW", "AWAY"))
    if any(value is None for value in values):
        return None
    vector = tuple(float(value) for value in values if value is not None)
    if len(vector) != 3 or any(value <= 0 or value >= 1 for value in vector):
        return None
    total = sum(vector)
    if abs(total - 1.0) > 0.02:
        return None
    return tuple(value / total for value in vector)  # type: ignore[return-value]


def log_loss(probabilities: tuple[float, float, float], actual: int) -> float:
    return -math.log(max(probabilities[actual], 1e-15))


def brier(probabilities: tuple[float, float, float], actual: int) -> float:
    return sum(
        (value - (1.0 if index == actual else 0.0)) ** 2
        for index, value in enumerate(probabilities)
    )


def rps(probabilities: tuple[float, float, float], actual: int) -> float:
    observed = (1.0 if actual == 0 else 0.0, 1.0 if actual <= 1 else 0.0)
    forecast = (probabilities[0], probabilities[0] + probabilities[1])
    return (
        sum(
            (left - right) ** 2
            for left, right in zip(forecast, observed, strict=True)
        )
        / 2
    )


def reliability_bins(
    observations: Sequence[tuple[tuple[float, float, float], int]],
) -> list[dict[str, Any]]:
    buckets: dict[int, list[tuple[float, bool]]] = defaultdict(list)
    for probabilities, actual in observations:
        confidence = max(probabilities)
        predicted = probabilities.index(confidence)
        buckets[min(9, int(confidence * 10))].append(
            (confidence, predicted == actual)
        )
    rows: list[dict[str, Any]] = []
    for index in range(10):
        items = buckets.get(index, [])
        rows.append(
            {
                "lower": index / 10,
                "upper": (index + 1) / 10,
                "count": len(items),
                "mean_confidence": (
                    sum(confidence for confidence, _ in items) / len(items)
                    if items
                    else None
                ),
                "accuracy": (
                    sum(hit for _, hit in items) / len(items) if items else None
                ),
            }
        )
    return rows


def ece(
    observations: Sequence[tuple[tuple[float, float, float], int]],
) -> float | None:
    if not observations:
        return None
    total = len(observations)
    return float(
        sum(
        row["count"]
        / total
        * abs(float(row["mean_confidence"]) - float(row["accuracy"]))
        for row in reliability_bins(observations)
        if row["count"]
        )
    )


def paired_bootstrap(pairs: Sequence[tuple[float, float]]) -> dict[str, Any]:
    if len(pairs) < 2:
        return {"status": "INSUFFICIENT", "sample_count": len(pairs)}
    rng = random.Random(BOOTSTRAP_SEED)  # noqa: S311 - deterministic evaluation
    deltas: list[float] = []
    for _ in range(BOOTSTRAP_ITERATIONS):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        deltas.append(sum(model - market for model, market in sample) / len(sample))
    deltas.sort()
    return {
        "status": "AVAILABLE",
        "sample_count": len(pairs),
        "metric": "model_minus_market_log_loss",
        "delta": sum(model - market for model, market in pairs) / len(pairs),
        "ci95": [deltas[24], deltas[974]],
        "iterations": BOOTSTRAP_ITERATIONS,
        "seed": BOOTSTRAP_SEED,
    }


def bootstrap_ci(values: Sequence[float]) -> list[float] | None:
    if len(values) < 2:
        return None
    rng = random.Random(BOOTSTRAP_SEED)  # noqa: S311 - deterministic evaluation
    means = sorted(
        sum(values[rng.randrange(len(values))] for _ in values) / len(values)
        for _ in range(BOOTSTRAP_ITERATIONS)
    )
    return [means[24], means[974]]


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
