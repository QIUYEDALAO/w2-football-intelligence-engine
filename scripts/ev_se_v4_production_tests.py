#!/usr/bin/env python3
"""Behavioural tests against the shipped EV-SE chain, mutants honestly classified.

Protocol v4 section 8 (commit 18f812b7).

v3 applied all five preregistered mutants to a local `candidate()` wrapper and
scored them as rejected. That was a violation of v3's own section 10, which said a
mutant that cannot be expressed against production must be reported as such and
never simulated. Production carries no age term, no coverage term and no season
logic, so three of the five have nothing to mutate there.

This file separates three things that v3 ran together:

  1. what the shipped chain actually does, measured, no candidate involved;
  2. mutants injected into the shipped chain itself by patching the real methods --
     these are scored, and the suite must kill them;
  3. the preregistered mutants that production cannot express, reported with the
     reason and explicitly NOT scored as passes;
  4. the research candidate formula, exercised and labelled as research code.

Run:
    PYTHONPATH=src <venv>/bin/python scripts/ev_se_v4_production_tests.py
"""
from __future__ import annotations

import json
import math
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from w2.prematch.analysis_calculator import ReadModelService
from w2.strategy.simulate import ah_expected_value_uncertainty_from_lambdas

AS_OF = datetime(2026, 6, 1, tzinfo=UTC)
LAMBDA_HOME, LAMBDA_AWAY = 1.40, 1.10
PRICE, SELECTION, LINE = 2.0, "HOME", -0.5

TIGHT = [1.00, 1.05, 0.95, 1.02, 0.98, 1.01, 0.99, 1.03]
WIDE = [0.30, 1.90, 0.45, 1.75, 0.60, 1.60, 0.75, 1.45]


class StubRepository:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def team_xg_matches_for_teams(
        self, team_ids: list[str], *, before: datetime, limit_per_team: int = 20
    ) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["team_id"] in team_ids]


def _rows(values: list[float], *, age_days: float, count: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for team in ("H", "A"):
        for index in range(count):
            kickoff = AS_OF - timedelta(days=age_days + 7.0 * index)
            value = values[index % len(values)]
            rows.append(
                {
                    "fixture_id": f"{team}-{index}",
                    "team_id": team,
                    "opponent_team_id": "Z",
                    "kickoff_at": kickoff.isoformat().replace("+00:00", "Z"),
                    "captured_at": (kickoff + timedelta(hours=6))
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "xg_for": value,
                    "xg_against": value * 0.9,
                    "source_system": "api_football_statistics",
                    # the frozen extract selected seven columns and omitted this one;
                    # a valid placeholder only makes production more permissive, so a
                    # blocked verdict stays conservative
                    "raw_payload_sha256": "0" * 64,
                }
            )
    return rows


def sigma(values: list[float], *, age_days: float = 10.0, count: int = 8) -> dict[str, Any]:
    service = ReadModelService.__new__(ReadModelService)
    service._bounded_public_request = False
    service._team_xg_matches_cache = None
    service._future_refresh_repository_cache = StubRepository(
        _rows(values, age_days=age_days, count=count)
    )
    return service._empirical_xg_lambda_uncertainty(
        fixture_id="target", as_of=AS_OF, home_team_id="H", away_team_id="A"
    )


def ev_se(home: float, away: float) -> float | None:
    _d, _ev, uncertainty = ah_expected_value_uncertainty_from_lambdas(
        lambda_home=LAMBDA_HOME, lambda_away=LAMBDA_AWAY, selection=SELECTION,
        line=LINE, decimal_price=PRICE,
        lambda_sigma_home=home, lambda_sigma_away=away,
    )
    return uncertainty


# ------------------------------------------- invariants production can actually hold
def production_invariants() -> list[str]:
    """Four properties the shipped chain genuinely has. Each one a mutant can break."""
    failures: list[str] = []
    base = sigma(TIGHT, count=8)
    if base["lambda_uncertainty_status"] != "ANALYSIS_READY":
        return ["production_not_ready_on_valid_inputs"]
    base_home = float(base["lambda_sigma_home"])

    # P1 fail closed below three observations
    starved = sigma(TIGHT, count=2)
    if starved["lambda_sigma_home"] is not None:
        failures.append("P1_fail_closed_under_three")

    # P2 more observations must not raise uncertainty, values held fixed
    many = sigma(TIGHT, count=16)
    if float(many["lambda_sigma_home"]) > base_home + 1e-12:
        failures.append("P2_sample_monotonicity")

    # P3 more dispersed observations must not lower uncertainty
    wide = sigma(WIDE, count=8)
    wide_home = float(wide["lambda_sigma_home"])
    if wide_home < base_home - 1e-12:
        failures.append("P3_dispersion_monotonicity")
    # P3b supplementary, and the same lesson the age invariant taught: a rule that
    # only forbids a decrease is satisfied by a formula that ignores the input
    # entirely. WIDE is genuinely more dispersed than TIGHT, so sigma must move.
    elif wide_home <= base_home + 1e-12:
        failures.append("P3b_dispersion_response_inert")

    # P4 a larger sigma must not lower EV_SE through the GH-3 propagation
    small, large = ev_se(base_home, base_home), ev_se(base_home * 3.0, base_home * 3.0)
    if small is None or large is None or large < small - 1e-12:
        failures.append("P4_propagation_monotonicity")
    return failures


# ------------------------------------------------ mutants injected into production
@contextmanager
def patched(name: str, replacement: Any):
    original = getattr(ReadModelService, name)
    setattr(ReadModelService, name, replacement)
    try:
        yield
    finally:
        setattr(ReadModelService, name, original)


def _fail_open(self: Any, rows: list[dict[str, Any]], *, field: str) -> dict[str, Any]:
    """Mutant: report READY on thin evidence instead of blocking."""
    values = [float(row[field]) for row in rows]
    if len(values) < 3:
        return {"status": "READY", "blocker": None, "n": len(values),
                "fixture_ids": [], "sample_variance": 0.04, "standard_error": 0.2}
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    if var <= 0:
        return {"status": "NOT_READY", "blocker": "XG_UNCERTAINTY_ZERO_VARIANCE",
                "n": len(values), "fixture_ids": [], "sample_variance": 0.0,
                "standard_error": None}
    return {"status": "READY", "blocker": None, "n": len(values), "fixture_ids": [],
            "sample_variance": var, "standard_error": math.sqrt(var) / math.sqrt(len(values))}


def _inverted_sample_scaling(
    self: Any, rows: list[dict[str, Any]], *, field: str
) -> dict[str, Any]:
    """Mutant: multiply by sqrt(n) instead of dividing, so more data looks worse."""
    values = [float(row[field]) for row in rows]
    if len(values) < 3:
        return {"status": "NOT_READY", "blocker": "XG_UNCERTAINTY_SAMPLE_INSUFFICIENT",
                "n": len(values), "fixture_ids": [], "sample_variance": None,
                "standard_error": None}
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    if var <= 0:
        return {"status": "NOT_READY", "blocker": "XG_UNCERTAINTY_ZERO_VARIANCE",
                "n": len(values), "fixture_ids": [], "sample_variance": 0.0,
                "standard_error": None}
    return {"status": "READY", "blocker": None, "n": len(values), "fixture_ids": [],
            "sample_variance": var, "standard_error": math.sqrt(var) * math.sqrt(len(values))}


def _dispersion_ignored(self: Any, rows: list[dict[str, Any]], *, field: str) -> dict[str, Any]:
    """Mutant: a fixed standard error, so spread stops mattering."""
    values = [float(row[field]) for row in rows]
    if len(values) < 3:
        return {"status": "NOT_READY", "blocker": "XG_UNCERTAINTY_SAMPLE_INSUFFICIENT",
                "n": len(values), "fixture_ids": [], "sample_variance": None,
                "standard_error": None}
    return {"status": "READY", "blocker": None, "n": len(values), "fixture_ids": [],
            "sample_variance": 0.04, "standard_error": 0.2}


PRODUCTION_MUTANTS = {
    "fail_open_below_evidence_threshold": ("_xg_standard_error", _fail_open),
    "inverted_sample_scaling": ("_xg_standard_error", _inverted_sample_scaling),
    "dispersion_ignored": ("_xg_standard_error", _dispersion_ignored),
}

NOT_EXPRESSIBLE = {
    "negative_age_coefficient": (
        "production carries no age coefficient: _empirical_xg_lambda_uncertainty "
        "derives sigma from the dispersion and count of the rows it holds and never "
        "reads observation age, so there is no age behaviour to invert"
    ),
    "inverted_coverage_sign": (
        "production carries no coverage term and consumes no expected-match "
        "denominator, so there is no coverage sign to flip"
    ),
    "age_reset_on_season_switch": (
        "production never reads a season field; team_xg_matches_for_teams orders by "
        "kickoff across seasons with limit_per_team=20, so there is no season reset "
        "to introduce"
    ),
}


# ------------------------------------------------------ research candidate formula
def candidate(
    se0: float, age: float, coverage: float | None, *, alpha: float, beta: float,
    reset_age: bool = False, constant_inflation: float = 0.0,
    coverage_sign: float = 1.0, fail_open: bool = False,
) -> float | None:
    """RESEARCH ONLY. Not shipped, not reachable from production, not a proposal."""
    if coverage is None:
        if not fail_open:
            return None
        coverage = 1.0
    total = se0**2 + alpha * (0.0 if reset_age else age) + coverage_sign * beta * (1.0 - coverage)
    return None if total < 0 else math.sqrt(total + constant_inflation)


def candidate_invariants(**knobs: Any) -> list[str]:
    base = sigma(TIGHT)
    se0 = float(base["lambda_sigma_home"])
    def at(age: float, cov: float | None) -> float | None:
        return candidate(se0, age, cov, **knobs)
    b, older, sparser, fresh = at(10.0, 1.0), at(60.0, 1.0), at(10.0, 0.5), at(0.0, 1.0)
    if None in (b, older, sparser, fresh):
        return ["candidate_unavailable_on_valid_inputs"]
    bad: list[str] = []
    if older < b:
        bad.append("age_monotonicity")
    if sparser < b:
        bad.append("coverage_monotonicity")
    if abs(fresh - se0) > 1e-12:
        bad.append("fresh_complete_baseline")
    if at(10.0, None) is not None:
        bad.append("no_evidence_fail_closed")
    seasonal = at(400.0, 1.0)
    if seasonal is None or seasonal < b:
        bad.append("seasonal_recovery")
    if float(knobs.get("alpha", 0.0)) > 0 and older <= b:
        bad.append("age_term_inert")
    return bad


def main() -> int:
    shipped = production_invariants()

    killed, survived = {}, []
    for name, (target, replacement) in PRODUCTION_MUTANTS.items():
        with patched(target, replacement):
            broken = production_invariants()
        if broken:
            killed[name] = broken
        else:
            survived.append(name)

    healthy = {"alpha": 1e-4, "beta": 1e-3}
    research_positive = candidate_invariants(**healthy)
    research_mutants = {
        "negative_age_coefficient": {"alpha": -1e-4},
        "inverted_coverage_sign": {"coverage_sign": -1.0},
        "constant_inflation_at_baseline": {"constant_inflation": 1e-3},
        "fail_open_without_denominator": {"fail_open": True},
        "age_reset_on_season_switch": {"reset_age": True},
    }
    research_killed = {
        n: candidate_invariants(**{**healthy, **o}) for n, o in research_mutants.items()
    }
    research_survived = [n for n, b in research_killed.items() if not b]

    fresh, stale = sigma(TIGHT, age_days=1.0), sigma(TIGHT, age_days=400.0)
    report = {
        "bound_to": [
            "w2.prematch.analysis_calculator.ReadModelService._empirical_xg_lambda_uncertainty",
            "w2.prematch.analysis_calculator.ReadModelService._xg_standard_error",
            "w2.strategy.simulate.ah_expected_value_uncertainty_from_lambdas",
        ],
        "production_behaviour": {
            "invariants_held": "PASS" if not shipped else shipped,
            "fresh_1d_sigma_home": fresh["lambda_sigma_home"],
            "stale_400d_sigma_home": stale["lambda_sigma_home"],
            "age_changes_sigma": fresh["lambda_sigma_home"] != stale["lambda_sigma_home"],
            "ev_se_fresh_1d": ev_se(float(fresh["lambda_sigma_home"]),
                                    float(fresh["lambda_sigma_away"])),
            "ev_se_stale_400d": ev_se(float(stale["lambda_sigma_home"]),
                                      float(stale["lambda_sigma_away"])),
            "two_observations_status": sigma(TIGHT, count=2)["lambda_uncertainty_status"],
        },
        "production_expressible_mutants": {
            "class": "PRODUCTION_EXPRESSIBLE",
            "injected_into": "ReadModelService._xg_standard_error, patched in place",
            "killed": killed,
            "survived": survived,
        },
        "not_expressible_in_production": {
            "class": "NOT_EXPRESSIBLE_IN_PRODUCTION",
            "scored": False,
            "note": (
                "these are preregistered mutants of a candidate formula that does not "
                "exist in production; they are NOT counted as passes, and their "
                "absence is itself the finding"
            ),
            "mutants": NOT_EXPRESSIBLE,
        },
        "research_candidate": {
            "class": "RESEARCH_CANDIDATE_ONLY",
            "note": (
                "exercised against research code; proves the suite can fail, "
                "not that production is right"
            ),
            "positive_invariants": "PASS" if not research_positive else research_positive,
            "killed": research_killed,
            "survived": research_survived,
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if (shipped or survived or research_positive or research_survived) else 0


if __name__ == "__main__":
    raise SystemExit(main())
