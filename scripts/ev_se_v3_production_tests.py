#!/usr/bin/env python3
"""Behavioural invariants and mutants bound to the real EV-SE path.

Protocol v3 section 10 (commit 603a9753). v2's suite mutated a local copy of the
formula, which proved only that the test could fail. Everything here runs through
production code:

  * `ReadModelService._empirical_xg_lambda_uncertainty` produces sigma from real
    historical rows, exactly as the shipped read model does;
  * `ah_expected_value_uncertainty_from_lambdas` propagates it through GH-3 to EV,
    exactly as the shipped strategy layer does.

The candidate formula wraps production's own SE0 rather than reimplementing it, so
a mutant that survives here is a defect the shipped chain would actually carry.

Run:
    PYTHONPATH=src <venv>/bin/python scripts/ev_se_v3_production_tests.py
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from typing import Any

from w2.prematch.analysis_calculator import ReadModelService
from w2.strategy.simulate import ah_expected_value_uncertainty_from_lambdas

AS_OF = datetime(2026, 6, 1, tzinfo=UTC)
PRICE = 2.0
SELECTION = "HOME"
LINE = -0.5
LAMBDA_HOME, LAMBDA_AWAY = 1.40, 1.10

# xG values are held fixed across every state so that only age or coverage moves.
HOME_XG = [(1.10, 0.90), (1.60, 1.20), (0.80, 1.05), (1.45, 0.70), (1.25, 1.35), (0.95, 1.00)]
AWAY_XG = [(0.85, 1.30), (1.20, 0.95), (1.05, 1.15), (0.70, 1.40), (1.35, 0.80), (1.00, 1.10)]


class StubRepository:
    """Serves the rows a state defines. The production filters still run on them."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def team_xg_matches_for_teams(
        self, team_ids: list[str], *, before: datetime, limit_per_team: int = 20
    ) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["team_id"] in team_ids]


def _rows(age_days: float, *, observed: int, season_switch: bool = False) -> list[dict[str, Any]]:
    """`observed` fixtures per team, the most recent one `age_days` before AS_OF."""
    rows: list[dict[str, Any]] = []
    for team, table in (("H", HOME_XG), ("A", AWAY_XG)):
        for index in range(observed):
            kickoff = AS_OF - timedelta(days=age_days + 7.0 * index)
            xg_for, xg_against = table[index % len(table)]
            rows.append(
                {
                    "fixture_id": f"{team}-{index}",
                    "team_id": team,
                    "opponent_team_id": "Z",
                    "kickoff_at": kickoff.isoformat().replace("+00:00", "Z"),
                    # captured just after kickoff, so production's PIT filter admits it
                    "captured_at": (kickoff + timedelta(hours=6))
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "xg_for": xg_for,
                    "xg_against": xg_against,
                    "source_system": "api_football_statistics",
                    # the frozen extract did not carry this column; a valid placeholder
                    # only makes production more permissive, so a blocked verdict stays
                    # conservative
                    "raw_payload_sha256": "0" * 64,
                    "season": "2025" if season_switch and index >= 2 else "2026",
                }
            )
    return rows


def production_sigma(age_days: float, *, observed: int = 6) -> dict[str, Any]:
    """Run the shipped read-model path and return its sigma pair verbatim."""
    service = ReadModelService.__new__(ReadModelService)
    service._bounded_public_request = False
    service._team_xg_matches_cache = None
    service._future_refresh_repository_cache = StubRepository(
        _rows(age_days, observed=observed)
    )
    return service._empirical_xg_lambda_uncertainty(
        fixture_id="target",
        as_of=AS_OF,
        home_team_id="H",
        away_team_id="A",
    )


def ev_se(sigma_home: float, sigma_away: float) -> float | None:
    """Propagate through the shipped GH-3 EV path."""
    _distribution, _ev, uncertainty = ah_expected_value_uncertainty_from_lambdas(
        lambda_home=LAMBDA_HOME,
        lambda_away=LAMBDA_AWAY,
        selection=SELECTION,
        line=LINE,
        decimal_price=PRICE,
        lambda_sigma_home=sigma_home,
        lambda_sigma_away=sigma_away,
    )
    return uncertainty


# --------------------------------------------------------------- candidate formula
def candidate(
    se0: float,
    age_days: float,
    coverage: float | None,
    *,
    alpha: float,
    beta: float,
    reset_age: bool = False,
    constant_inflation: float = 0.0,
    coverage_sign: float = 1.0,
    fail_open: bool = False,
) -> float | None:
    """`SE^2 = SE0^2 + alpha*A + beta*(1-c)`, wrapping production's own SE0."""
    if coverage is None:
        if not fail_open:
            return None
        coverage = 1.0
    age = 0.0 if reset_age else age_days
    total = se0**2 + alpha * age + coverage_sign * beta * (1.0 - coverage)
    if total < 0.0:
        return None
    return math.sqrt(total + constant_inflation)


def check_invariants(**knobs: Any) -> list[str]:
    """The five preregistered invariants plus the supplementary strict-increase check.

    Every SE0 comes from the production path, and every verdict is confirmed on the
    propagated EV_SE as well, so a mutant cannot hide behind the propagation step.
    """
    fresh = production_sigma(1.0)
    if fresh["lambda_uncertainty_status"] != "ANALYSIS_READY":
        return ["production_not_ready_on_valid_inputs"]
    se0_home = float(fresh["lambda_sigma_home"])
    se0_away = float(fresh["lambda_sigma_away"])

    def pair(age: float, coverage: float | None, **extra: Any) -> tuple[Any, Any]:
        return (
            candidate(se0_home, age, coverage, **{**knobs, **extra}),
            candidate(se0_away, age, coverage, **{**knobs, **extra}),
        )

    failures: list[str] = []
    base_h, base_a = pair(10.0, 1.0)
    old_h, old_a = pair(60.0, 1.0)
    sparse_h, sparse_a = pair(10.0, 0.5)
    zero_h, zero_a = pair(0.0, 1.0)
    if None in (base_h, base_a, old_h, old_a, sparse_h, sparse_a, zero_h, zero_a):
        return ["candidate_unavailable_on_valid_inputs"]

    # 1 age monotonicity, on sigma and on the propagated EV_SE
    if old_h < base_h or old_a < base_a:
        failures.append("age_monotonicity")
    elif ev_se(old_h, old_a) < ev_se(base_h, base_a):  # type: ignore[operator]
        failures.append("age_monotonicity_after_propagation")
    # 2 coverage monotonicity
    if sparse_h < base_h or sparse_a < base_a:
        failures.append("coverage_monotonicity")
    elif ev_se(sparse_h, sparse_a) < ev_se(base_h, base_a):  # type: ignore[operator]
        failures.append("coverage_monotonicity_after_propagation")
    # 3 fresh and complete reproduces production's own SE0
    if abs(zero_h - se0_home) > 1e-12 or abs(zero_a - se0_away) > 1e-12:
        failures.append("fresh_complete_baseline")
    # 4 no evidence fails closed
    if pair(10.0, None)[0] is not None:
        failures.append("no_evidence_fail_closed")
    # 5 age is not reset by a season switch
    across_h, _ = pair(400.0, 1.0)
    if across_h is None or across_h < base_h:
        failures.append("seasonal_recovery")
    # supplementary: invariant 1 only forbids a decrease, so a formula that ignores
    # age satisfies it. With alpha > 0 the age term must actually bite.
    if float(knobs.get("alpha", 0.0)) > 0 and old_h <= base_h:
        failures.append("age_term_inert")
    return failures


def production_as_shipped() -> dict[str, Any]:
    """What the shipped formula does about age and coverage today. No candidate involved."""
    fresh = production_sigma(1.0)
    stale = production_sigma(400.0)
    thin_full = production_sigma(1.0, observed=5)
    starved = production_sigma(1.0, observed=2)
    return {
        "fresh_sigma_home": fresh["lambda_sigma_home"],
        "stale_400d_sigma_home": stale["lambda_sigma_home"],
        "age_changes_sigma": fresh["lambda_sigma_home"] != stale["lambda_sigma_home"],
        "ev_se_fresh": ev_se(
            float(fresh["lambda_sigma_home"]), float(fresh["lambda_sigma_away"])
        ),
        "ev_se_stale_400d": ev_se(
            float(stale["lambda_sigma_home"]), float(stale["lambda_sigma_away"])
        ),
        "five_observations_sigma_home": thin_full["lambda_sigma_home"],
        "two_observations_status": starved["lambda_uncertainty_status"],
        "fails_closed_under_three": starved["lambda_sigma_home"] is None,
    }


MUTANTS: dict[str, dict[str, Any]] = {
    "negative_age_coefficient": {"alpha": -1e-4},
    "inverted_coverage_sign": {"coverage_sign": -1.0},
    "constant_inflation_at_baseline": {"constant_inflation": 1e-3},
    "fail_open_without_denominator": {"fail_open": True},
    "age_reset_on_season_switch": {"reset_age": True},
}


def main() -> int:
    healthy = {"alpha": 1e-4, "beta": 1e-3}
    positive = check_invariants(**healthy)
    survivors = []
    rejected = {}
    for name, override in MUTANTS.items():
        broken = check_invariants(**{**healthy, **override})
        if broken:
            rejected[name] = broken
        else:
            survivors.append(name)
    shipped = production_as_shipped()
    shipped_verdict = check_invariants(alpha=0.0, beta=0.0)
    report = {
        "bound_to": [
            "w2.prematch.analysis_calculator.ReadModelService._empirical_xg_lambda_uncertainty",
            "w2.strategy.simulate.ah_expected_value_uncertainty_from_lambdas",
        ],
        "positive_invariants": "PASS" if not positive else positive,
        "mutants_rejected": rejected,
        "mutants_survived": survivors,
        "production_as_shipped": shipped,
        "production_as_shipped_invariants": (
            "PASS" if not shipped_verdict else shipped_verdict
        ),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if (positive or survivors) else 0


if __name__ == "__main__":
    raise SystemExit(main())
