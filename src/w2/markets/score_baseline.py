from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from w2.markets.devig import DevigMethod, devig
from w2.markets.settlement_probability import effective_settlement_probability
from w2.markets.value_engine import settlement_distribution_ah, settlement_distribution_totals

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
    actual_ah_line: str | None
    actual_ou_line: str | None
    devig_probabilities: dict[str, dict[str, float]]
    baseline_distributions: dict[str, dict[str, Any]]
    model_fair_odds: dict[str, dict[str, float]]
    market_fair_odds: dict[str, dict[str, float]]
    fitted_parameters: dict[str, float] | None
    fitted_score_matrix_hash: str | None
    zero_ev_residuals_by_market: dict[str, float]
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
    if set(devigged) != {"1X2", "ASIAN_HANDICAP", "TOTALS"}:
        missing = sorted({"1X2", "ASIAN_HANDICAP", "TOTALS"} - set(devigged))
        status = (
            "INSUFFICIENT_MARKET_DIMENSIONS"
            if set(devigged) == {"ASIAN_HANDICAP"}
            else "INCOMPLETE"
        )
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
    ah_line = _market_line(quotes, "ASIAN_HANDICAP")
    ou_line = _market_line(quotes, "TOTALS")
    if ah_line is None or ou_line is None:
        return _baseline(
            status="INCOMPLETE",
            quotes=quotes,
            quote_ids=quote_ids,
            quote_hashes=quote_hashes,
            devig_probabilities=devigged,
            fitted_parameters=None,
            residuals_by_market={},
            optimizer_status="NOT_RUN",
            blockers=["MISSING_ACTUAL_AH_LINE" if ah_line is None else "MISSING_ACTUAL_OU_LINE"],
        )
    fit = _fit_score_matrix(devigged, ah_line=ah_line, ou_line=ou_line)
    return _baseline(
        status="UNVALIDATED",
        quotes=quotes,
        quote_ids=quote_ids,
        quote_hashes=quote_hashes,
        devig_probabilities=devigged,
        baseline_distributions=fit["baseline_distributions"],
        model_fair_odds=fit["model_fair_odds"],
        market_fair_odds=fit["market_fair_odds"],
        fitted_parameters=fit["parameters"],
        residuals_by_market=fit["zero_ev_residuals_by_market"],
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
    baseline_distributions: dict[str, dict[str, Any]] | None = None,
    model_fair_odds: dict[str, dict[str, float]] | None = None,
    market_fair_odds: dict[str, dict[str, float]] | None = None,
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
        "actual_ah_line": _line_text(_market_line(quotes, "ASIAN_HANDICAP")),
        "actual_ou_line": _line_text(_market_line(quotes, "TOTALS")),
        "devig_probabilities": devig_probabilities,
        "baseline_distributions": baseline_distributions or {},
        "model_fair_odds": model_fair_odds or {},
        "market_fair_odds": market_fair_odds or {},
        "fitted_parameters": fitted_parameters,
        "fitted_score_matrix_hash": matrix_hash,
        "zero_ev_residuals_by_market": residuals_by_market,
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
        ("provider", "PROVIDER_MISMATCH"),
        ("source_snapshot_id", "SOURCE_SNAPSHOT_MISMATCH"),
        ("source_sha256", "SOURCE_HASH_MISMATCH"),
    ):
        values = {str(row.get(field) or "") for row in quotes}
        if len(values) != 1 or "" in values:
            blockers.append(blocker)
    if any(row.get("live") is True for row in quotes):
        blockers.append("LIVE_QUOTE")
    if any(row.get("suspended") is True for row in quotes):
        blockers.append("SUSPENDED_QUOTE")
    blockers.extend(_selection_blockers(quotes))
    captured = _same_text(quotes, "captured_at")
    captured_at = _parse_utc(captured)
    checkpoint = _parse_utc(entry_checkpoint)
    if captured_at is None or checkpoint is None:
        blockers.append("INVALID_TIMESTAMP")
    elif captured_at > checkpoint:
        blockers.append("POST_ENTRY_CHECKPOINT")
    return blockers


def _devig_by_market(quotes: list[Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, dict[str, Decimal]] = {}
    for row in quotes:
        market = _market(row.get("market"))
        selection = str(row.get("selection") or "")
        odds = _decimal(row.get("decimal_odds"))
        if market and selection and odds is not None:
            grouped.setdefault(market, {})[selection] = odds
    result: dict[str, dict[str, float]] = {}
    expected_sizes = {"1X2": 3, "ASIAN_HANDICAP": 2, "TOTALS": 2}
    for market, prices in grouped.items():
        if len(prices) == expected_sizes.get(market):
            result[market] = {
                key: round(value, 6)
                for key, value in devig(prices, DevigMethod.PROPORTIONAL).probabilities.items()
            }
    return result


def _fit_score_matrix(
    devigged: Mapping[str, Mapping[str, float]],
    *,
    ah_line: Decimal,
    ou_line: Decimal,
) -> dict[str, Any]:
    best: tuple[float, float, float] | None = None
    best_residuals: dict[str, float] = {}
    best_distributions: dict[str, dict[str, Any]] = {}
    best_model_fair: dict[str, dict[str, float]] = {}
    best_market_fair: dict[str, dict[str, float]] = {}
    for home_step in range(8, 33):
        for away_step in range(8, 33):
            home = home_step / 10
            away = away_step / 10
            implied, distributions = _market_probabilities(
                home,
                away,
                ah_line=ah_line,
                ou_line=ou_line,
            )
            model_fair = _model_fair_odds(implied, distributions)
            market_fair = _market_fair_odds(devigged)
            residuals = _zero_ev_residuals(implied, devigged, model_fair, market_fair)
            score = max(residuals.values())
            if best is None or score < best[0]:
                best = (score, home, away)
                best_residuals = residuals
                best_distributions = distributions
                best_model_fair = model_fair
                best_market_fair = market_fair
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
        "zero_ev_residuals_by_market": best_residuals,
        "model_fair_odds": best_model_fair,
        "market_fair_odds": best_market_fair,
        "baseline_distributions": best_distributions,
        "optimizer_status": "CONVERGED_DIAGNOSTIC",
    }


def _market_probabilities(
    home_lambda: float,
    away_lambda: float,
    *,
    ah_line: Decimal,
    ou_line: Decimal,
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, Any]]]:
    matrix: dict[tuple[int, int], Decimal] = {}
    for home in range(8):
        for away in range(8):
            probability = _poisson(home_lambda, home) * _poisson(away_lambda, away)
            matrix[(home, away)] = Decimal(str(probability))
    total = sum(matrix.values())
    normalized = {score: value / total for score, value in matrix.items()}
    home_prob = sum(value for (h, a), value in normalized.items() if h > a)
    draw = sum(value for (h, a), value in normalized.items() if h == a)
    away_prob = sum(value for (h, a), value in normalized.items() if h < a)
    ah_home_dist = _five_state(
        settlement_distribution_ah(normalized, selection="HOME", line=ah_line)
    )
    ah_away_dist = _five_state(
        settlement_distribution_ah(normalized, selection="AWAY", line=-ah_line)
    )
    ou_over_dist = _five_state(
        settlement_distribution_totals(normalized, selection="OVER", line=ou_line)
    )
    ou_under_dist = _five_state(
        settlement_distribution_totals(normalized, selection="UNDER", line=ou_line)
    )
    implied = {
        "1X2": {
            "HOME": float(home_prob),
            "DRAW": float(draw),
            "AWAY": float(away_prob),
        },
        "ASIAN_HANDICAP": {
            "HOME": effective_settlement_probability(ah_home_dist) or 0.0,
            "AWAY": effective_settlement_probability(ah_away_dist) or 0.0,
        },
        "TOTALS": {
            "OVER": effective_settlement_probability(ou_over_dist) or 0.0,
            "UNDER": effective_settlement_probability(ou_under_dist) or 0.0,
        },
    }
    return implied, {
        "ASIAN_HANDICAP": {"HOME": ah_home_dist, "AWAY": ah_away_dist},
        "TOTALS": {"OVER": ou_over_dist, "UNDER": ou_under_dist},
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


def _selection_blockers(quotes: list[Mapping[str, Any]]) -> list[str]:
    blockers: list[str] = []
    expected = {
        "1X2": {"HOME", "DRAW", "AWAY"},
        "ASIAN_HANDICAP": {"HOME", "AWAY"},
        "TOTALS": {"OVER", "UNDER"},
    }
    grouped: dict[str, list[str]] = {}
    for row in quotes:
        market = _market(row.get("market"))
        if market:
            grouped.setdefault(market, []).append(str(row.get("selection") or ""))
    for market, selections in grouped.items():
        if len(selections) != len(set(selections)):
            blockers.append(f"DUPLICATE_SELECTION_{market}")
        if set(selections) != expected.get(market, set()):
            blockers.append(f"SELECTION_SET_INCOMPLETE_{market}")
    return blockers


def _market_line(quotes: list[Mapping[str, Any]], market_name: str) -> Decimal | None:
    if market_name == "ASIAN_HANDICAP":
        home_lines = {
            _decimal(row.get("line"))
            for row in quotes
            if _market(row.get("market")) == market_name
            and str(row.get("selection") or "").upper() == "HOME"
            and row.get("line") not in {None, ""}
        }
        away_lines = {
            _decimal(row.get("line"))
            for row in quotes
            if _market(row.get("market")) == market_name
            and str(row.get("selection") or "").upper() == "AWAY"
            and row.get("line") not in {None, ""}
        }
        if len(home_lines) == 1 and len(away_lines) == 1:
            home_line = next(iter(home_lines))
            away_line = next(iter(away_lines))
            if home_line is not None and away_line is not None and home_line == -away_line:
                return home_line
        return None
    values = {
        _decimal(row.get("line"))
        for row in quotes
        if _market(row.get("market")) == market_name and row.get("line") not in {None, ""}
    }
    return next(iter(values)) if len(values) == 1 else None


def _line_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _market(value: object) -> str:
    text = str(value or "").upper()
    return {
        "AH": "ASIAN_HANDICAP",
        "ASIAN HANDICAP": "ASIAN_HANDICAP",
        "OU": "TOTALS",
        "OVER_UNDER": "TOTALS",
    }.get(text, text)


def _parse_utc(value: object) -> datetime | None:
    if value in {None, ""}:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _five_state(value: Any) -> dict[str, float]:
    raw = value.as_dict()
    return {
        "WIN": float(raw["full_win_probability"]),
        "HALF_WIN": float(raw["half_win_probability"]),
        "PUSH": float(raw["push_probability"]),
        "HALF_LOSS": float(raw["half_loss_probability"]),
        "LOSS": float(raw["full_loss_probability"]),
    }


def fair_decimal_odds(distribution: Mapping[str, Any]) -> float | None:
    win = _decimal(distribution.get("WIN"))
    half_win = _decimal(distribution.get("HALF_WIN"))
    half_loss = _decimal(distribution.get("HALF_LOSS"))
    loss = _decimal(distribution.get("LOSS"))
    if win is None or half_win is None or half_loss is None or loss is None:
        return None
    denominator = win + Decimal("0.5") * half_win
    if denominator <= 0:
        return None
    numerator = Decimal("0.5") * half_loss + loss
    return round(float(Decimal("1") + numerator / denominator), 6)


def _model_fair_odds(
    implied: Mapping[str, Mapping[str, float]],
    distributions: Mapping[str, Mapping[str, Mapping[str, float]]],
) -> dict[str, dict[str, float]]:
    output = {
        "1X2": {
            selection: round(1 / probability, 6)
            for selection, probability in implied["1X2"].items()
            if probability > 0
        }
    }
    for market in ("ASIAN_HANDICAP", "TOTALS"):
        output[market] = {}
        for selection, distribution in distributions[market].items():
            fair = fair_decimal_odds(distribution)
            if fair is not None:
                output[market][selection] = fair
    return output


def _market_fair_odds(devigged: Mapping[str, Mapping[str, float]]) -> dict[str, dict[str, float]]:
    return {
        market: {
            selection: round(1 / probability, 6)
            for selection, probability in probabilities.items()
            if probability > 0
        }
        for market, probabilities in devigged.items()
    }


def _zero_ev_residuals(
    implied: Mapping[str, Mapping[str, float]],
    devigged: Mapping[str, Mapping[str, float]],
    model_fair: Mapping[str, Mapping[str, float]],
    market_fair: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
    residuals = {
        "1X2": round(
            max(
                abs(implied["1X2"][selection] - float(devigged["1X2"][selection]))
                for selection in devigged["1X2"]
            ),
            6,
        )
    }
    for market in ("ASIAN_HANDICAP", "TOTALS"):
        residuals[market] = round(
            max(
                abs(float(model_fair[market][selection]) - float(market_fair[market][selection]))
                for selection in market_fair[market]
            ),
            6,
        )
    return residuals


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
