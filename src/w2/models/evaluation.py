from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class EvaluationRow:
    fixture_id: str
    actual: str
    probabilities: dict[str, float]
    competition: str
    season: str
    neutral_site: bool


def log_loss(rows: list[EvaluationRow]) -> float:
    return sum(-math.log(max(row.probabilities[row.actual], 1e-12)) for row in rows) / len(rows)


def brier(rows: list[EvaluationRow]) -> float:
    return sum(
        sum(
            (row.probabilities[key] - (1.0 if row.actual == key else 0.0)) ** 2
            for key in ("HOME", "DRAW", "AWAY")
        )
        for row in rows
    ) / len(rows)


def rps(rows: list[EvaluationRow]) -> float:
    order = ("HOME", "DRAW", "AWAY")
    total = 0.0
    for row in rows:
        predicted = 0.0
        actual = 0.0
        score = 0.0
        for key in order[:-1]:
            predicted += row.probabilities[key]
            actual += 1.0 if row.actual == key else 0.0
            score += (predicted - actual) ** 2
        total += score / 2
    return total / len(rows)


def reliability(rows: list[EvaluationRow], bins: int = 10) -> list[dict[str, float]]:
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    for row in rows:
        prediction, confidence = max(row.probabilities.items(), key=lambda item: item[1])
        buckets[min(int(confidence * bins), bins - 1)].append(
            (confidence, prediction == row.actual)
        )
    output: list[dict[str, float]] = []
    for index, bucket in enumerate(buckets):
        if bucket:
            output.append(
                {
                    "bin": float(index),
                    "count": float(len(bucket)),
                    "confidence": sum(item[0] for item in bucket) / len(bucket),
                    "accuracy": sum(1.0 for item in bucket if item[1]) / len(bucket),
                    "weight": len(bucket) / len(rows),
                }
            )
    return output


def ece(rows: list[EvaluationRow]) -> float:
    return sum(
        item["weight"] * abs(item["accuracy"] - item["confidence"])
        for item in reliability(rows)
    )


def metrics(rows: list[EvaluationRow]) -> dict[str, float]:
    return {
        "log_loss": round(log_loss(rows), 6),
        "rps": round(rps(rows), 6),
        "brier": round(brier(rows), 6),
        "ece": round(ece(rows), 6),
    }


def paired_bootstrap_delta(
    candidate_losses: list[float],
    baseline_losses: list[float],
    *,
    samples: int = 400,
    seed: int = 7,
) -> dict[str, float]:
    if len(candidate_losses) != len(baseline_losses):
        raise ValueError("paired bootstrap requires aligned rows")
    rng = random.Random(seed)  # noqa: S311 - deterministic evaluation bootstrap, not security.
    n = len(candidate_losses)
    deltas = []
    for _ in range(samples):
        total = 0.0
        for _ in range(n):
            index = rng.randrange(n)
            total += candidate_losses[index] - baseline_losses[index]
        deltas.append(total / n)
    deltas.sort()
    return {
        "mean_delta": round(sum(deltas) / len(deltas), 6),
        "ci_low": round(deltas[int(samples * 0.025)], 6),
        "ci_high": round(deltas[int(samples * 0.975) - 1], 6),
    }
