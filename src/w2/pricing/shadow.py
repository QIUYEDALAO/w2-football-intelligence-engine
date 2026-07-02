from __future__ import annotations

from typing import Any

from w2.pricing.scale import DEFAULT_FACTOR_SCALE_PARAMS
from w2.pricing.supremacy import fair_handicap_from_supremacy
from w2.pricing.team_score import independent_team_scores
from w2.pricing.value_vs_market import edge, market_lines, pricing_status
from w2.strategy.simulate import READY, SimulationOutput

PRICING_SHADOW_VERSION = "w2.s1.shadow.v1"
UNCALIBRATED_STATUS = "RULE_BASED_UNCALIBRATED"
INSUFFICIENT_FACTORS_STATUS = "INSUFFICIENT_INDEPENDENT_FACTORS"


def build_pricing_shadow(
    *,
    fixture_id: str,
    feature_contributions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    current_odds: dict[str, Any] | None = None,
    simulation: SimulationOutput | dict[str, Any] | None = None,
) -> dict[str, Any]:
    team_scores = independent_team_scores(
        feature_contributions=feature_contributions,
    )
    lines = market_lines(current_odds)
    simulation_payload = _simulation_payload(simulation)
    simulation_status = str(simulation_payload.get("status") or "NOT_RUN")
    if team_scores["independent_signal_count"] == 0:
        fair_ah = None
        fair_ou = None
        edge_ah = None
        edge_ou = None
        status = INSUFFICIENT_FACTORS_STATUS
    elif simulation_status == READY:
        fair_ah = _number(simulation_payload.get("fair_ah"))
        fair_ou = _number(simulation_payload.get("fair_ou"))
        edge_ah = edge(fair_ah, lines["market_ah"])
        edge_ou = edge(fair_ou, lines["market_ou"])
        status = "SIMULATION_READY"
    else:
        fair_ah = fair_handicap_from_supremacy(
            team_scores["home_score"],
            team_scores["away_score"],
        )
        fair_ou = None
        edge_ah = edge(fair_ah, lines["market_ah"])
        edge_ou = None
        status = pricing_status(
            coverage=team_scores["coverage"],
            edge_ah=edge_ah,
            edge_ou=edge_ou,
        )
    return {
        "fixture_id": fixture_id,
        "status": status,
        "model_version": PRICING_SHADOW_VERSION,
        "calibration_version": str(
            simulation_payload.get("calibration_version") or "UNVALIDATED"
        ),
        "factors": team_scores["factors"],
        "team_score": {
            "home": team_scores["home_score"],
            "away": team_scores["away_score"],
        },
        "team_score_audit": {
            "weight_sum_used": team_scores["weight_sum_used"],
            "weight_sum_possible": team_scores["weight_sum_possible"],
            "factor_count_used": team_scores["factor_count_used"],
        },
        "factor_scale": team_scores["factor_scale"],
        "factor_scale_version": DEFAULT_FACTOR_SCALE_PARAMS.version,
        "fair_ah": fair_ah,
        "fair_ou": fair_ou,
        "market_ah": lines["market_ah"],
        "market_ou": lines["market_ou"],
        "edge_ah": edge_ah,
        "edge_ou": edge_ou,
        "coverage": team_scores["coverage"],
        "coverage_note": (
            "coverage includes xG-derived proxy factors; ISC is authoritative for independence"
        ),
        "independent_signal_count": team_scores["independent_signal_count"],
        "independent_signal_groups": team_scores["independent_signal_groups"],
        "xg_derived_factor_count": team_scores["xg_derived_factor_count"],
        "missing_independent_sources": team_scores["missing_independent_sources"],
        "factor_source_summary": team_scores["factor_source_summary"],
        "asof_market_snapshot_id": None,
        "devig_method": None,
        "settlement_outcome": None,
        "beats_market": False,
        "formal_enabled": False,
        "candidate_enabled": False,
        "simulation": simulation_payload or None,
        "simulation_model_version": simulation_payload.get("model_version"),
        "simulation_calibration_version": simulation_payload.get("calibration_version"),
        "simulation_status": simulation_status,
        "formal_eligible": False,
        "s2_gate": {
            "n_min": 200,
            "beats_market": False,
        },
    }


def _simulation_payload(simulation: SimulationOutput | dict[str, Any] | None) -> dict[str, Any]:
    if simulation is None:
        return {}
    if isinstance(simulation, SimulationOutput):
        return simulation.as_dict()
    return simulation if isinstance(simulation, dict) else {}


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
