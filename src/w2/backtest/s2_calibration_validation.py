from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import isclose, log
from typing import Any

from w2.backtest.s2_gate import S2GateEvidence, s2_walkforward_shadow_status
from w2.models.dixon_coles import DixonColesMatch, fit_dixon_coles

S2_CALIBRATION_VALIDATION_VERSION = "w2.s2.calibration_validation.v1"
MIN_DIXON_COLES_FIT_SAMPLE = 4


@dataclass(frozen=True, kw_only=True)
class S2CalibrationValidationInputs:
    payload: dict[str, Any]
    source: str = "dashboard_payload"


def build_s2_calibration_validation_report(
    inputs: S2CalibrationValidationInputs,
) -> dict[str, Any]:
    rows = _rows(inputs.payload)
    generated_at = _payload_time(inputs.payload)
    lambda_rows = [_lambda_row(row) for row in rows]
    clipped_rows = [row for row in lambda_rows if row["clipped"]]
    dc_matches = _dixon_coles_matches(rows)
    dc_report = _dixon_coles_report(dc_matches)
    covered_sample = len(dc_matches)
    gate = s2_walkforward_shadow_status(
        S2GateEvidence(
            covered_settled_sample=covered_sample,
            noise_separated_advantage=False,
            time_split_passed=False,
            holdout_replicated=False,
            forward_shadow_passed=False,
        )
    )
    blockers = _blockers(rows=rows, dc_matches=dc_matches)
    return {
        "report_version": S2_CALIBRATION_VALIDATION_VERSION,
        "report_type": "S2_DIXON_COLES_LAMBDA_CLIPPING_VALIDATION",
        "generated_at": generated_at,
        "source": inputs.source,
        "read_only": True,
        "provider_calls": 0,
        "db_writes": 0,
        "online_model_changed": False,
        "recommendation_logic_changed": False,
        "simulation_logic_changed": False,
        "formal_enabled": False,
        "candidate_enabled": False,
        "beats_market": False,
        "rows": len(rows),
        "covered_settled_sample": covered_sample,
        "lambda_clipping": {
            "status": "OBSERVED" if clipped_rows else "NOT_OBSERVED",
            "observed_rows": len(clipped_rows),
            "rows": clipped_rows,
        },
        "dixon_coles": dc_report,
        "s2_gate": gate,
        "blockers": blockers,
        "status": "BLOCKED" if blockers else "PASS_READ_ONLY_VALIDATION",
    }


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("all") or payload.get("rows") or []
    return [item for item in raw if isinstance(item, dict)]


def _payload_time(payload: dict[str, Any]) -> str | None:
    for key in ("generated_at", "as_of", "asof", "build_time"):
        value = payload.get(key)
        if value:
            return str(value)
    debug = payload.get("debug")
    if isinstance(debug, dict):
        for key in ("generated_at", "as_of", "asof"):
            value = debug.get(key)
            if value:
                return str(value)
    return None


def _lambda_row(row: dict[str, Any]) -> dict[str, Any]:
    shadow = _dict(row.get("pricing_shadow"))
    simulation = _dict(shadow.get("simulation"))
    calibration = _dict(simulation.get("calibration"))
    params = _dict(calibration.get("params"))
    lambda_home = _number(simulation.get("lambda_home") or shadow.get("lambda_home"))
    lambda_away = _number(simulation.get("lambda_away") or shadow.get("lambda_away"))
    minimum_lambda = _number(params.get("minimum_lambda"))
    maximum_lambda = _number(params.get("maximum_lambda"))
    clipped_sides: list[str] = []
    if (
        lambda_home is not None
        and minimum_lambda is not None
        and isclose(lambda_home, minimum_lambda, abs_tol=1e-6)
    ):
        clipped_sides.append("home_minimum_lambda")
    if (
        lambda_away is not None
        and minimum_lambda is not None
        and isclose(lambda_away, minimum_lambda, abs_tol=1e-6)
    ):
        clipped_sides.append("away_minimum_lambda")
    if (
        lambda_home is not None
        and maximum_lambda is not None
        and isclose(lambda_home, maximum_lambda, abs_tol=1e-6)
    ):
        clipped_sides.append("home_maximum_lambda")
    if (
        lambda_away is not None
        and maximum_lambda is not None
        and isclose(lambda_away, maximum_lambda, abs_tol=1e-6)
    ):
        clipped_sides.append("away_maximum_lambda")
    return {
        "fixture_id": str(row.get("fixture_id") or ""),
        "teams": _teams(row),
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "minimum_lambda": minimum_lambda,
        "maximum_lambda": maximum_lambda,
        "clipped": bool(clipped_sides),
        "clipped_sides": clipped_sides,
        "calibration_version": simulation.get("calibration_version")
        or shadow.get("simulation_calibration_version")
        or shadow.get("calibration_version"),
    }


def _dixon_coles_matches(rows: list[dict[str, Any]]) -> list[DixonColesMatch]:
    matches: list[DixonColesMatch] = []
    for row in rows:
        score = _result_score(row)
        kickoff = _parse_utc(row.get("kickoff_utc"))
        if score is None or kickoff is None:
            continue
        home_name = str(row.get("home_team_name") or "")
        away_name = str(row.get("away_team_name") or "")
        if not home_name or not away_name:
            continue
        market_probabilities = _market_probabilities(row)
        if market_probabilities is None:
            continue
        matches.append(
            DixonColesMatch(
                fixture_id=str(row.get("fixture_id") or ""),
                kickoff_utc=kickoff,
                home_team=home_name,
                away_team=away_name,
                home_goals=score[0],
                away_goals=score[1],
                market_probabilities=market_probabilities,
            )
        )
    return matches


def _dixon_coles_report(matches: list[DixonColesMatch]) -> dict[str, Any]:
    if len(matches) < MIN_DIXON_COLES_FIT_SAMPLE:
        return {
            "status": "INSUFFICIENT_SETTLED_SAMPLE",
            "fit_sample": len(matches),
            "n_min": MIN_DIXON_COLES_FIT_SAMPLE,
            "rho": None,
            "log_loss": None,
        }
    params = fit_dixon_coles(matches)
    log_loss = 0.0
    for match in matches:
        home_mu, away_mu = _expected_from_params(params, match)
        probability = _score_probability(
            match.home_goals,
            match.away_goals,
            home_mu,
            away_mu,
            params.rho,
        )
        log_loss += -log(max(probability, 1e-12))
    return {
        "status": "FIT_READY_FOR_OFFLINE_COMPARISON",
        "fit_sample": len(matches),
        "n_min": MIN_DIXON_COLES_FIT_SAMPLE,
        "rho": params.rho,
        "training_cutoff": params.training_cutoff.isoformat().replace("+00:00", "Z"),
        "log_loss": round(log_loss / len(matches), 6),
    }


def _expected_from_params(params: Any, match: DixonColesMatch) -> tuple[float, float]:
    from w2.models.dixon_coles import expected_goals_for

    return expected_goals_for(
        match.home_team,
        match.away_team,
        params.attack,
        params.defence,
        params.home_goal_baseline,
        params.away_goal_baseline,
    )


def _score_probability(
    home_goals: int,
    away_goals: int,
    home_mu: float,
    away_mu: float,
    rho: float,
) -> float:
    from w2.models.dixon_coles import score_probability

    return score_probability(home_goals, away_goals, home_mu, away_mu, rho)


def _blockers(*, rows: list[dict[str, Any]], dc_matches: list[DixonColesMatch]) -> list[str]:
    blockers: list[str] = []
    if not rows:
        blockers.append("MISSING_DASHBOARD_ROWS")
    if len(dc_matches) < MIN_DIXON_COLES_FIT_SAMPLE:
        blockers.append("INSUFFICIENT_DIXON_COLES_SETTLED_SAMPLE")
    if len(dc_matches) < 200:
        blockers.append("INSUFFICIENT_S2_WALK_FORWARD_SAMPLE")
    return blockers


def _result_score(row: dict[str, Any]) -> tuple[int, int] | None:
    result = row.get("result")
    if not isinstance(result, dict):
        return None
    home = (
        result.get("home_goals")
        if result.get("home_goals") is not None
        else result.get("home")
    )
    away = (
        result.get("away_goals")
        if result.get("away_goals") is not None
        else result.get("away")
    )
    if home is None or away is None:
        return None
    try:
        return int(home), int(away)
    except (TypeError, ValueError):
        return None


def _market_probabilities(row: dict[str, Any]) -> dict[str, float] | None:
    raw = row.get("market_probabilities")
    if not isinstance(raw, dict):
        raw = _dict(row.get("pricing_shadow")).get("market_probabilities")
    if not isinstance(raw, dict):
        return None
    probabilities: dict[str, float] = {}
    for key in ("HOME", "DRAW", "AWAY"):
        value = _number(raw.get(key) or raw.get(key.lower()))
        if value is None:
            return None
        probabilities[key] = value
    total = sum(probabilities.values())
    if total <= 0:
        return None
    return {key: value / total for key, value in probabilities.items()}


def _teams(row: dict[str, Any]) -> str:
    home = str(row.get("home_team_name") or "")
    away = str(row.get("away_team_name") or "")
    return f"{home} vs {away}".strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)
