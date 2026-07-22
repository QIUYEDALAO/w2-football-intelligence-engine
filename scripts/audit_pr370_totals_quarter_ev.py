#!/usr/bin/env python3
"""Independently recompute the surviving PR #370 totals-quarter EV."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from w2.api.frozen_analysis import read_frozen_analysis_artifact
from w2.infrastructure.database import create_engine
from w2.markets.value_engine import expected_value, settlement_distribution_totals
from w2.strategy.simulate import _exact_score_matrix

FIXTURE_ID = "1494222"
EXPECTED = {
    "model_probability": 0.596063,
    "market_probability": 0.494565,
    "probability_delta": 0.101498,
    "expected_value": 0.214444,
    "ev_se": 0.093216,
}
TOLERANCE = 0.000006


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day-view-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    return parser.parse_args()


def _hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _number(value: Any) -> float:
    return float(Decimal(str(value)))


def _close(name: str, observed: float | None) -> None:
    if observed is None or abs(observed - EXPECTED[name]) > TOLERANCE:
        raise ValueError(f"TOTALS_QUARTER_LINE_EV_RECOMPUTE_MISMATCH:{name}:{observed}")


def main() -> int:
    args = _args()
    day_view = json.loads(args.day_view_json.read_text(encoding="utf-8"))
    card = next(
        (
            item
            for item in day_view.get("cards", [])
            if isinstance(item, dict) and str(item.get("fixture_id")) == FIXTURE_ID
        ),
        None,
    )
    if not isinstance(card, dict):
        raise ValueError("TOTALS_QUARTER_PICK_FIXTURE_MISSING")
    v3 = card.get("recommendation_decision_v3") or {}
    pick = v3.get("selected_candidate") or {}
    model = pick.get("model_probability") or {}
    quote = pick.get("quote_identity") or {}
    quotes = quote.get("quotes") or {}
    over = quotes.get("over") or {}
    under = quotes.get("under") or {}
    if (
        v3.get("outcome") != "ANALYSIS_PICK"
        or pick.get("market") != "TOTALS"
        or pick.get("selection") != "OVER"
        or str(pick.get("line")) != "2.75"
        or abs(_number(pick.get("odds")) - 1.86) > 0.000001
        or not over
        or not under
    ):
        raise ValueError("TOTALS_QUARTER_PICK_CONTRACT_MISMATCH")

    distribution = model.get("settlement_distribution") or {}
    probabilities = {
        "P(total<=2)_LOSS": _number(distribution.get("LOSS")),
        "P(total=3)_HALF_WIN": _number(distribution.get("HALF_WIN")),
        "P(total>=4)_WIN": _number(distribution.get("WIN")),
        "PUSH": _number(distribution.get("PUSH", 0)),
        "HALF_LOSS": _number(distribution.get("HALF_LOSS", 0)),
    }
    artifact = read_frozen_analysis_artifact(create_engine(), FIXTURE_ID)
    analysis_card = artifact.payload.get("analysis_card") or {}
    simulation = analysis_card.get("simulation") or {}
    if not simulation:
        raise ValueError("TOTALS_QUARTER_FROZEN_SIMULATION_MISSING")
    calibration = simulation.get("calibration") or {}
    home = _number(simulation.get("lambda_home"))
    away = _number(simulation.get("lambda_away"))
    price = Decimal("1.86")
    matrix = {
        score: Decimal(str(probability))
        for score, probability in _exact_score_matrix(
            home,
            away,
            rho=_number((calibration.get("params") or {}).get("dixon_coles_rho") or 0),
            max_goals=12,
        ).items()
    }
    recomputed = settlement_distribution_totals(matrix, selection="OVER", line=Decimal("2.75"))
    recomputed_payload = recomputed.as_dict()
    recomputed_ev = float(expected_value(price, recomputed))
    displayed_ev = _number(model.get("expected_value"))
    displayed_probability = _number(model.get("effective_probability"))
    market_probability_payload = (pick.get("market_probability") or {}).get("devig", {})
    market_probability = _number(market_probability_payload.get("OVER"))
    displayed_delta = _number(pick.get("probability_delta"))
    ev_se = _number(model.get("ev_se"))
    for name, value in (
        ("model_probability", displayed_probability),
        ("market_probability", market_probability),
        ("probability_delta", displayed_delta),
        ("expected_value", displayed_ev),
        ("ev_se", ev_se),
    ):
        _close(name, value)
    if abs(recomputed_ev - displayed_ev) > TOLERANCE:
        raise ValueError(f"TOTALS_QUARTER_LINE_EV_RECOMPUTE_MISMATCH:formula:{recomputed_ev}")

    payload = {
        "schema_version": "w2.pr370.totals_quarter_ev_audit.v1",
        "status": "PASS",
        "fixture_id": FIXTURE_ID,
        "selection": "OVER",
        "line": "2.75",
        "decimal_odds": "1.86",
        "quarter_settlement": {
            "total<=2": {"outcome": "LOSS", "profit": -1.0},
            "total=3": {"outcome": "HALF_WIN", "profit": 0.43},
            "total>=4": {"outcome": "WIN", "profit": 0.86},
        },
        "probabilities": probabilities,
        "probability_sum": round(sum(probabilities.values()), 12),
        "recomputed_settlement_distribution": recomputed_payload,
        "recomputed_ev": recomputed_ev,
        "displayed": {
            "model_probability": displayed_probability,
            "market_probability": market_probability,
            "probability_delta": displayed_delta,
            "expected_value": displayed_ev,
            "ev_se": ev_se,
        },
        "expected": EXPECTED,
        "tolerance": TOLERANCE,
        "simulation": {
            "artifact_hash": artifact.artifact_hash,
            "artifact_source_hash": artifact.source_hash,
            "matrix_hash": _hash({str(key): str(value) for key, value in matrix.items()}),
            "lambda_home": home,
            "lambda_away": away,
            "lambda_sigma_home": simulation.get("lambda_sigma_home"),
            "lambda_sigma_away": simulation.get("lambda_sigma_away"),
            "uncertainty_method": calibration.get("lambda_uncertainty_method"),
            "uncertainty_input_hash": _hash(
                simulation.get("input_manifest") or simulation.get("inputs") or {}
            ),
        },
        "quote_identity": {
            "execution_bookmaker": over.get("bookmaker_name"),
            "selected_over_price": over.get("decimal_odds"),
            "opposite_under_price": under.get("decimal_odds"),
            "capture_id": over.get("capture_id"),
            "raw_payload_sha256": over.get("raw_payload_sha256"),
            "quote_identity_hash": quote.get("quote_identity_hash"),
        },
        "warnings": ["EV_PLAUSIBILITY_REVIEW", "ANALYSIS_ONLY_FORMAL_DISABLED"],
        "formal": "DISABLED",
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
