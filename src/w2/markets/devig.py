from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from math import exp, log


class DevigMethod(StrEnum):
    PROPORTIONAL = "PROPORTIONAL"
    SHIN = "SHIN"
    POWER = "POWER"
    LOGARITHMIC = "LOGARITHMIC"


@dataclass(frozen=True, kw_only=True)
class DevigResult:
    method: DevigMethod
    probabilities: dict[str, float]
    overround: float
    diagnostics: tuple[str, ...] = ()


def _validate_decimal_odds(odds: dict[str, Decimal]) -> dict[str, float]:
    if len(odds) < 2:
        raise ValueError("devig requires at least two outcomes")
    cleaned: dict[str, float] = {}
    for selection, price in odds.items():
        value = float(price)
        if value <= 1.0:
            raise ValueError(f"invalid decimal odds for {selection}: {price}")
        cleaned[selection] = value
    return cleaned


def _normalize(values: dict[str, float]) -> dict[str, float]:
    total = sum(values.values())
    if total <= 0:
        raise ValueError("cannot normalize non-positive probabilities")
    normalized = {key: max(value / total, 1e-12) for key, value in values.items()}
    correction = sum(normalized.values())
    return {key: value / correction for key, value in normalized.items()}


def _power(implied: dict[str, float]) -> dict[str, float]:
    low = 0.01
    high = 10.0
    for _ in range(80):
        mid = (low + high) / 2
        total = sum(value**mid for value in implied.values())
        if total > 1.0:
            low = mid
        else:
            high = mid
    exponent = (low + high) / 2
    return _normalize({key: value**exponent for key, value in implied.items()})


def _shin(implied: dict[str, float]) -> dict[str, float]:
    overround = max(sum(implied.values()) - 1.0, 0.0)
    if overround == 0:
        return _normalize(implied)
    insider = min(overround / max(len(implied) - 1, 1), 0.20)
    adjusted = {
        key: max(value - insider * value * (1.0 - value), 1e-12)
        for key, value in implied.items()
    }
    return _normalize(adjusted)


def _logarithmic(implied: dict[str, float]) -> dict[str, float]:
    logs = {key: log(value) for key, value in implied.items()}
    low = -20.0
    high = 20.0
    for _ in range(80):
        mid = (low + high) / 2
        total = sum(exp(value - mid) for value in logs.values())
        if total > 1.0:
            low = mid
        else:
            high = mid
    shift = (low + high) / 2
    return _normalize({key: exp(value - shift) for key, value in logs.items()})


def devig(odds: dict[str, Decimal], method: DevigMethod) -> DevigResult:
    decimal_odds = _validate_decimal_odds(odds)
    implied = {key: 1.0 / value for key, value in decimal_odds.items()}
    overround = sum(implied.values())
    diagnostics: list[str] = []
    try:
        if method == DevigMethod.PROPORTIONAL:
            probabilities = _normalize(implied)
        elif method == DevigMethod.SHIN:
            probabilities = _shin(implied)
        elif method == DevigMethod.POWER:
            probabilities = _power(implied)
        elif method == DevigMethod.LOGARITHMIC:
            probabilities = _logarithmic(implied)
        else:
            raise ValueError(f"unsupported devig method {method}")
    except (OverflowError, ValueError) as exc:
        diagnostics.append(f"DEVIG_FAILED:{exc}")
        probabilities = _normalize(implied)
    probability_sum = sum(probabilities.values())
    if abs(probability_sum - 1.0) > 1e-9:
        diagnostics.append(f"PROBABILITY_SUM_ADJUSTED:{probability_sum:.12f}")
        probabilities = _normalize(probabilities)
    return DevigResult(
        method=method,
        probabilities=probabilities,
        overround=overround,
        diagnostics=tuple(diagnostics),
    )
