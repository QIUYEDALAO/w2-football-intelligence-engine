"""Same-line, read-only analysis evidence for AH and totals candidates."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from w2.markets.devig import DevigMethod, devig
from w2.markets.settlement_probability import effective_settlement_probability
from w2.markets.value_engine import (
    expected_value,
    settlement_distribution_ah,
    settlement_distribution_totals,
)
from w2.strategy.simulate import _exact_score_matrix

SCHEMA_VERSION = "w2.analysis_market_evidence.v1"
MIN_MARKET_ANCHOR_DIVERGENCE = 0.05
_KEYS = {"ASIAN_HANDICAP": ("ah", ("HOME", "AWAY")), "TOTALS": ("ou", ("OVER", "UNDER"))}


def build_analysis_market_evidence(
    *,
    fixture_id: str,
    competition_id: str,
    market: str,
    selection: object,
    line: object,
    quote_identity_audit: Mapping[str, Any] | None,
    simulation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Derive all comparison values from one authoritative two-sided quote pair."""
    key_and_sides = _KEYS.get(market)
    normalized_selection = _selection(market, selection)
    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "evidence_contract_version": "w2.analysis-market-evidence.v2",
        "fixture_id": fixture_id,
        "competition_id": competition_id,
        "market": market,
        "selection": normalized_selection,
        "line": _text(line),
        "quote_identity": {},
        "quote_evidence_status": "NOT_READY",
        "model_evidence_status": "NOT_READY",
        "direction_status": "NOT_READY",
        "quote_usage": "NONE",
        "ev_eligible": False,
        "formal_eligible": False,
        "lock_eligible": False,
        "market_probability": {},
        "model_probability": {"status": "NOT_READY"},
        "comparison": {"analysis_direction_allowed": False, "status": "NOT_READY"},
    }
    decimal_line = _decimal(line)
    if key_and_sides is None or decimal_line is None:
        return _finish(base, "UNSUPPORTED_OR_INCOMPLETE_MARKET")
    key, sides = key_and_sides
    audit = _mapping(_mapping(quote_identity_audit).get(key))
    quote_identity = {
        field: audit.get(field)
        for field in (
            "identity_status",
            "freshness_status",
            "provider",
            "bookmaker_id",
            "captured_at",
            "observation_ids",
        )
    }
    base["quote_identity"] = quote_identity
    base["quote_observation_ids"] = dict(_mapping(quote_identity.get("observation_ids")))
    quotes = _mapping(audit.get("quotes"))
    prices = {
        side: _decimal(_mapping(quotes.get(side.lower())).get("decimal_odds")) for side in sides
    }
    if (
        quote_identity["identity_status"] != "COMPLETE"
        or quote_identity["freshness_status"] != "COMPLETE"
        or any(price is None or price <= 1 for price in prices.values())
    ):
        return _finish(base, "AUTHORITATIVE_QUOTE_INCOMPLETE")
    base["quote_evidence_status"] = "READY"
    complete_prices = {side: price for side, price in prices.items() if price is not None}
    raw = {side: round(float(Decimal("1") / complete_prices[side]), 6) for side in sides}
    devigged = devig(complete_prices, DevigMethod.PROPORTIONAL)
    base["market_probability"] = {
        "raw_implied": raw,
        "overround": round(sum(raw.values()) - 1.0, 6),
        "devig": {side: round(devigged.probabilities[side], 6) for side in sides},
    }
    side_evidence = {
        side: _side_evidence(
            market=market,
            selection=side,
            line=decimal_line,
            price=complete_prices[side],
            market_probability=devigged.probabilities[side],
            simulation=simulation,
        )
        for side in sides
    }
    base["side_evidence"] = side_evidence
    all_model_ready = all(
        row["model_probability"].get("status") == "READY" for row in side_evidence.values()
    )
    if normalized_selection is None:
        base["quote_usage"] = "COMPARISON_ONLY"
        base["model_probability"] = {
            "status": "SIDE_EVIDENCE_AVAILABLE" if all_model_ready else "NOT_READY"
        }
        base["model_evidence_status"] = "READY" if all_model_ready else "NOT_READY"
        base["direction_status"] = "NO_DIRECTION_SELECTED" if all_model_ready else "NOT_READY"
        base["comparison"] = {
            "analysis_direction_allowed": False,
            "status": "NO_EDGE" if all_model_ready else "NOT_READY",
            "reason_code": "NO_DIRECTION_SELECTED",
        }
        return _finish(base, "NO_EDGE" if all_model_ready else "NOT_READY")
    selected_evidence = side_evidence[normalized_selection]
    model = selected_evidence["model_probability"]
    base["model_probability"] = model
    if model.get("status") != "READY":
        base["model_evidence_status"] = "NOT_READY"
        base["direction_status"] = "NOT_READY"
        base["comparison"] = {
            "analysis_direction_allowed": False,
            "status": "NOT_READY",
            "reason_code": model.get("reason_code") or "MODEL_EVIDENCE_NOT_READY",
        }
        return _finish(base, "NOT_READY")
    base["quote_usage"] = "EXECUTABLE"
    base["model_evidence_status"] = "READY"
    base["comparison"] = selected_evidence["comparison"]
    base["direction_status"] = str(base["comparison"].get("status") or "UNKNOWN")
    base["ev_eligible"] = bool(base["comparison"].get("analysis_direction_allowed"))
    return _finish(base, "COMPLETE")


def _side_evidence(
    *,
    market: str,
    selection: str,
    line: Decimal,
    price: Decimal,
    market_probability: float,
    simulation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    model = _model_evidence(market, selection, line, price, simulation)
    if model.get("status") != "READY":
        return {
            "model_probability": model,
            "comparison": {
                "analysis_direction_allowed": False,
                "status": "NOT_READY",
                "reason_code": model.get("reason_code") or "MODEL_EVIDENCE_INCOMPLETE",
            },
        }
    delta = round(float(model["effective_probability"]) - float(market_probability), 6)
    allowed = bool(model.get("expected_value", 0.0) > 0 and delta >= MIN_MARKET_ANCHOR_DIVERGENCE)
    return {
        "model_probability": model,
        "comparison": {
            "probability_delta": delta,
            "analysis_direction_allowed": allowed,
            "status": "READY" if allowed else "NO_EDGE",
            "reason_code": "MODEL_MARKET_EDGE_READY"
            if allowed
            else "MODEL_MARKET_EDGE_INSUFFICIENT",
        },
    }


def _model_evidence(
    market: str, selection: str, line: Decimal, price: Decimal, simulation: Mapping[str, Any] | None
) -> dict[str, Any]:
    sim = _mapping(simulation)
    home, away = _decimal(sim.get("lambda_home")), _decimal(sim.get("lambda_away"))
    if sim.get("status") != "READY" or home is None or away is None or home <= 0 or away <= 0:
        return {
            "status": "NOT_READY",
            "calibration_status": sim.get("calibration_status") or "UNKNOWN",
            "model_version": sim.get("model_version"),
            "calibration_version": sim.get("calibration_version"),
            "model_input_hash": _hash_mapping(sim.get("input_manifest") or sim.get("inputs") or {}),
        }
    sigma_home = _decimal(sim.get("lambda_sigma_home"))
    sigma_away = _decimal(sim.get("lambda_sigma_away"))
    calibration = _mapping(sim.get("calibration"))
    method = str(calibration.get("lambda_uncertainty_method") or "").lower()
    if (
        method in {"", "none"}
        or sigma_home is None
        or sigma_away is None
        or (sigma_home <= 0 and sigma_away <= 0)
    ):
        return {
            "status": "NOT_READY",
            "reason_code": "MODEL_UNCERTAINTY_NOT_READY",
            "calibration_status": sim.get("calibration_status") or "UNKNOWN",
            "model_version": sim.get("model_version"),
            "calibration_version": sim.get("calibration_version"),
            "model_input_hash": _hash_mapping(sim.get("input_manifest") or sim.get("inputs") or {}),
            "lambda_uncertainty_method": method or "none",
            "lambda_sigma_home": float(sigma_home) if sigma_home is not None else None,
            "lambda_sigma_away": float(sigma_away) if sigma_away is not None else None,
        }
    matrix = {
        score: Decimal(str(probability))
        for score, probability in _exact_score_matrix(
            float(home),
            float(away),
            rho=float(_mapping(calibration.get("params")).get("dixon_coles_rho") or 0.0),
            max_goals=12,
        ).items()
    }
    distribution = (
        settlement_distribution_ah(matrix, selection=selection, line=line)
        if market == "ASIAN_HANDICAP"
        else settlement_distribution_totals(matrix, selection=selection, line=line)
    )
    result = distribution.as_dict()
    settlement_distribution = {
        "WIN": float(result["full_win_probability"]),
        "HALF_WIN": float(result["half_win_probability"]),
        "PUSH": float(result["push_probability"]),
        "HALF_LOSS": float(result["half_loss_probability"]),
        "LOSS": float(result["full_loss_probability"]),
    }
    effective = effective_settlement_probability(settlement_distribution)
    if effective is None:
        return {"status": "NOT_READY", "reason_code": "INVALID_SETTLEMENT_DISTRIBUTION"}
    ev = float(expected_value(price, distribution))
    ev_se = _ev_uncertainty(
        market=market,
        selection=selection,
        line=line,
        price=price,
        lambda_home=home,
        lambda_away=away,
        sigma_home=sigma_home,
        sigma_away=sigma_away,
        rho=float(_mapping(calibration.get("params")).get("dixon_coles_rho") or 0.0),
    )
    if ev_se is None:
        return {
            "status": "NOT_READY",
            "reason_code": "MODEL_UNCERTAINTY_NOT_READY",
            "calibration_status": sim.get("calibration_status") or "UNKNOWN",
            "model_version": sim.get("model_version"),
            "calibration_version": sim.get("calibration_version"),
            "model_input_hash": _hash_mapping(sim.get("input_manifest") or sim.get("inputs") or {}),
            "lambda_uncertainty_method": method or "none",
            "lambda_sigma_home": float(sigma_home),
            "lambda_sigma_away": float(sigma_away),
        }
    return {
        "status": "READY",
        "calibration_status": sim.get("calibration_status") or "UNKNOWN",
        "model_version": sim.get("model_version"),
        "calibration_version": sim.get("calibration_version"),
        "model_input_hash": _hash_mapping(sim.get("input_manifest") or sim.get("inputs") or {}),
        "settlement_distribution": settlement_distribution,
        "effective_probability": effective,
        "expected_value": ev,
        "ev_se": ev_se,
        "lambda_uncertainty_method": method,
        "lambda_sigma_home": float(sigma_home),
        "lambda_sigma_away": float(sigma_away),
    }


def _ev_uncertainty(
    *,
    market: str,
    selection: str,
    line: Decimal,
    price: Decimal,
    lambda_home: Decimal,
    lambda_away: Decimal,
    sigma_home: Decimal,
    sigma_away: Decimal,
    rho: float,
) -> float | None:
    scenario_rows: list[tuple[Decimal, float]] = []
    for scenario_home, home_weight in _lambda_scenarios(lambda_home, sigma_home):
        for scenario_away, away_weight in _lambda_scenarios(lambda_away, sigma_away):
            matrix = {
                score: Decimal(str(probability))
                for score, probability in _exact_score_matrix(
                    float(scenario_home),
                    float(scenario_away),
                    rho=rho,
                    max_goals=12,
                ).items()
            }
            distribution = (
                settlement_distribution_ah(matrix, selection=selection, line=line)
                if market == "ASIAN_HANDICAP"
                else settlement_distribution_totals(matrix, selection=selection, line=line)
            )
            scenario_rows.append(
                (home_weight * away_weight, float(expected_value(price, distribution)))
            )
    total_weight = sum(weight for weight, _ in scenario_rows)
    if total_weight <= 0:
        return None
    mean = sum(weight * Decimal(str(ev)) for weight, ev in scenario_rows) / total_weight
    variance = sum(
        float(weight / total_weight) * ((float(ev) - float(mean)) ** 2)
        for weight, ev in scenario_rows
    )
    return round(math.sqrt(max(variance, 0.0)), 6)


def _lambda_scenarios(value: Decimal, sigma: Decimal) -> tuple[tuple[Decimal, Decimal], ...]:
    sigma = max(sigma, Decimal("0"))
    if sigma == 0:
        return ((value, Decimal("1")),)
    low = max(value - sigma, Decimal("0.01"))
    high = value + sigma
    return (
        (low, Decimal("0.25")),
        (value, Decimal("0.5")),
        (high, Decimal("0.25")),
    )


def _finish(payload: dict[str, Any], status: str) -> dict[str, Any]:
    payload["status"] = status
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    payload["evidence_hash"] = hashlib.sha256(encoded.encode()).hexdigest()
    return payload


def _hash_mapping(value: object) -> str | None:
    if not isinstance(value, Mapping) or not value:
        return None
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def _selection(market: str, value: object) -> str | None:
    raw = _text(value)
    if raw is None:
        return None
    text = raw.upper().replace("_AH", "").replace("_TOTALS", "")
    if market == "ASIAN_HANDICAP" and text.startswith(("HOME", "AWAY")):
        return "HOME" if text.startswith("HOME") else "AWAY"
    if market == "TOTALS" and text.startswith(("OVER", "UNDER")):
        return "OVER" if text.startswith("OVER") else "UNDER"
    return None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _text(value: object) -> str | None:
    return str(value) if value not in {None, ""} else None
