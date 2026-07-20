from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from w2.markets.devig import DevigMethod, devig

MARKET_SCORE_BASELINE_SCHEMA = "w2.market_score_baseline.v1"
SOLVER_VERSION = "w2.market_score_baseline.grid_poisson.v1"
RESIDUAL_POLICY = "UNVALIDATED_NO_PRE_REGISTERED_THRESHOLD"


@dataclass(frozen=True, kw_only=True)
class MarketScoreBaselineV1:
    schema_version: str
    status: str
    provider_fixture_id: str
    bookmaker_id: str | None
    captured_at: str | None
    input_quote_ids: list[str]
    input_quote_hashes: list[str]
    devig_probabilities: dict[str, dict[str, float]]
    fitted_parameters: dict[str, float] | None
    fitted_score_matrix_hash: str | None
    residuals_by_market: dict[str, float]
    max_residual: float | None
    optimizer_status: str
    residual_policy: str
    blockers: list[str]
    baseline_hash: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_market_score_baseline(
    quotes: list[Mapping[str, Any]],
    *,
    entry_checkpoint: str,
) -> dict[str, Any]:
    blockers = _batch_blockers(quotes, entry_checkpoint=entry_checkpoint)
    quote_ids = sorted(
        str(row.get("observation_id") or "") for row in quotes if row.get("observation_id")
    )
    quote_hashes = sorted(
        str(row.get("quote_identity_hash") or row.get("source_sha256") or "")
        for row in quotes
    )
    if blockers:
        return _baseline(
            status=_status_for_blockers(blockers),
            quotes=quotes,
            quote_ids=quote_ids,
            quote_hashes=quote_hashes,
            devig_probabilities={},
            fitted_parameters=None,
            residuals_by_market={},
            optimizer_status="NOT_RUN",
            blockers=blockers,
        )
    devigged = _devig_by_market(quotes)
    if set(devigged) != {"1X2", "AH", "OU"}:
        missing = sorted({"1X2", "AH", "OU"} - set(devigged))
        status = "INSUFFICIENT_MARKET_DIMENSIONS" if set(devigged) == {"AH"} else "INCOMPLETE"
        return _baseline(
            status=status,
            quotes=quotes,
            quote_ids=quote_ids,
            quote_hashes=quote_hashes,
            devig_probabilities=devigged,
            fitted_parameters=None,
            residuals_by_market={},
            optimizer_status="NOT_RUN",
            blockers=[f"MISSING_{item}" for item in missing],
        )
    fit = _fit_score_matrix(devigged)
    return _baseline(
        status="UNVALIDATED",
        quotes=quotes,
        quote_ids=quote_ids,
        quote_hashes=quote_hashes,
        devig_probabilities=devigged,
        fitted_parameters=fit["parameters"],
        residuals_by_market=fit["residuals_by_market"],
        optimizer_status=fit["optimizer_status"],
        blockers=["MARKET_BASELINE_RESIDUAL_THRESHOLD_UNVALIDATED"],
    )


def _baseline(
    *,
    status: str,
    quotes: list[Mapping[str, Any]],
    quote_ids: list[str],
    quote_hashes: list[str],
    devig_probabilities: dict[str, dict[str, float]],
    fitted_parameters: dict[str, float] | None,
    residuals_by_market: dict[str, float],
    optimizer_status: str,
    blockers: list[str],
) -> dict[str, Any]:
    matrix_hash = (
        _hash({"parameters": fitted_parameters, "solver": SOLVER_VERSION})
        if fitted_parameters
        else None
    )
    payload: dict[str, Any] = {
        "schema_version": MARKET_SCORE_BASELINE_SCHEMA,
        "status": status,
        "provider_fixture_id": _same_text(quotes, "provider_fixture_id"),
        "bookmaker_id": _same_text(quotes, "bookmaker_id"),
        "captured_at": _same_text(quotes, "captured_at"),
        "input_quote_ids": quote_ids,
        "input_quote_hashes": quote_hashes,
        "devig_probabilities": devig_probabilities,
        "fitted_parameters": fitted_parameters,
        "fitted_score_matrix_hash": matrix_hash,
        "residuals_by_market": residuals_by_market,
        "max_residual": max(residuals_by_market.values()) if residuals_by_market else None,
        "optimizer_status": optimizer_status,
        "residual_policy": RESIDUAL_POLICY,
        "blockers": sorted(set(blockers)),
    }
    payload["baseline_hash"] = _hash(payload)
    return MarketScoreBaselineV1(**payload).as_dict()


def _batch_blockers(quotes: list[Mapping[str, Any]], *, entry_checkpoint: str) -> list[str]:
    if not quotes:
        return ["INCOMPLETE"]
    blockers: list[str] = []
    for field, blocker in (
        ("provider_fixture_id", "FIXTURE_IDENTITY_INCOMPLETE"),
        ("bookmaker_id", "BOOKMAKER_MISMATCH"),
        ("captured_at", "CAPTURED_AT_MISMATCH"),
    ):
        values = {str(row.get(field) or "") for row in quotes}
        if len(values) != 1 or "" in values:
            blockers.append(blocker)
    if any(row.get("live") is True for row in quotes):
        blockers.append("LIVE_QUOTE")
    if any(row.get("suspended") is True for row in quotes):
        blockers.append("SUSPENDED_QUOTE")
    if any(not str(row.get("source_sha256") or "") for row in quotes):
        blockers.append("SOURCE_HASH_MISSING")
    captured = _same_text(quotes, "captured_at")
    if captured and captured > entry_checkpoint:
        blockers.append("POST_ENTRY_CHECKPOINT")
    return blockers


def _devig_by_market(quotes: list[Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, dict[str, Decimal]] = {}
    for row in quotes:
        market = str(row.get("market") or "")
        selection = str(row.get("selection") or "")
        odds = _decimal(row.get("decimal_odds"))
        if market and selection and odds is not None:
            grouped.setdefault(market, {})[selection] = odds
    result: dict[str, dict[str, float]] = {}
    expected_sizes = {"1X2": 3, "AH": 2, "OU": 2}
    for market, prices in grouped.items():
        if len(prices) == expected_sizes.get(market):
            result[market] = {
                key: round(value, 6)
                for key, value in devig(prices, DevigMethod.PROPORTIONAL).probabilities.items()
            }
    return result


def _fit_score_matrix(devigged: Mapping[str, Mapping[str, float]]) -> dict[str, Any]:
    best: tuple[float, float, float] | None = None
    best_residuals: dict[str, float] = {}
    for home_step in range(8, 33):
        for away_step in range(8, 33):
            home = home_step / 10
            away = away_step / 10
            implied = _market_probabilities(home, away)
            residuals = {
                market: round(
                    max(abs(implied[market][key] - float(target[key])) for key in target),
                    6,
                )
                for market, target in devigged.items()
            }
            score = max(residuals.values())
            if best is None or score < best[0]:
                best = (score, home, away)
                best_residuals = residuals
    assert best is not None
    return {
        "parameters": {
            "lambda_home": round(best[1], 4),
            "lambda_away": round(best[2], 4),
            "optimizer": "DETERMINISTIC_GRID_SEARCH",
            "bounds": "0.8..3.2 step 0.1",
            "tolerance": 0.0,
            "iteration_limit": 625,
            "rounding": 6,
            "solver_version": SOLVER_VERSION,
        },
        "residuals_by_market": best_residuals,
        "optimizer_status": "CONVERGED_DIAGNOSTIC",
    }


def _market_probabilities(home_lambda: float, away_lambda: float) -> dict[str, dict[str, float]]:
    matrix = {}
    for home in range(8):
        for away in range(8):
            matrix[(home, away)] = _poisson(home_lambda, home) * _poisson(away_lambda, away)
    total = sum(matrix.values())
    normalized = {score: value / total for score, value in matrix.items()}
    home_prob = sum(value for (h, a), value in normalized.items() if h > a)
    draw = sum(value for (h, a), value in normalized.items() if h == a)
    away_prob = sum(value for (h, a), value in normalized.items() if h < a)
    over = sum(value for (h, a), value in normalized.items() if h + a > 2.5)
    under = 1 - over
    ah_home = sum(value for (h, a), value in normalized.items() if h > a)
    ah_away = 1 - ah_home
    return {
        "1X2": {"HOME": home_prob, "DRAW": draw, "AWAY": away_prob},
        "AH": {"HOME": ah_home, "AWAY": ah_away},
        "OU": {"OVER": over, "UNDER": under},
    }


def _poisson(expected: float, goals: int) -> float:
    return math.exp(-expected) * expected**goals / math.factorial(goals)


def _status_for_blockers(blockers: list[str]) -> str:
    if "BOOKMAKER_MISMATCH" in blockers:
        return "INCOMPLETE"
    if "CAPTURED_AT_MISMATCH" in blockers:
        return "INCOMPLETE"
    return "INCOMPLETE"


def _same_text(quotes: list[Mapping[str, Any]], key: str) -> str | None:
    values = {str(row.get(key) or "") for row in quotes}
    return next(iter(values)) if len(values) == 1 and "" not in values else None


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()
