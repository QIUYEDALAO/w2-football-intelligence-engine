"""Protocol gates for EV-SE drift v2: linearity and the season-boundary jump.

Frozen protocol section 4 (commit 3fca0384) asks for two things the primary
within-season slope does not answer on its own:

  * a linearity gate -- add `delta^2` and call the cell `NONLINEAR_DRIFT` when
    its 95% CI excludes zero *and* the worst binned relative deviation from the
    linear fit exceeds 20%;
  * a season boundary -- cross-season pairs estimated separately with an added
    jump term, provider season being the boundary authority.

Both reuse the weighting and bootstrap of the primary estimator: every team
carries total weight one, and the CI is a cluster bootstrap over teams with
10,000 reps at seed 20260826.
"""

from __future__ import annotations

import random

from ev_se_variogram import (
    BINS,
    CI,
    CURVATURE_TOL,
    MIN_PAIRS_PER_BIN,
    MIN_TEAMS_PER_BIN,
    REPS,
    SEED,
)

MIN_VALID_BINS = 4


# --------------------------------------------------------------- weighted least squares
def team_weights(rows: list[tuple[str, ...]]) -> dict[str, float]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row[0]] = counts.get(row[0], 0) + 1
    return {team: 1.0 / n for team, n in counts.items()}


def wls_stats(rows: list, basis) -> dict[str, tuple[list[list[float]], list[float]]]:
    """Per team: (X'WX, X'Wy) so each bootstrap replication is O(teams)."""
    w = team_weights(rows)
    acc: dict[str, tuple[list[list[float]], list[float]]] = {}
    for row in rows:
        team, y = row[0], row[-1]
        x = basis(row)
        k = len(x)
        wi = w[team]
        xtx, xty = acc.setdefault(team, ([[0.0] * k for _ in range(k)], [0.0] * k))
        for a in range(k):
            xty[a] += wi * x[a] * y
            for b in range(k):
                xtx[a][b] += wi * x[a] * x[b]
    return acc


def _solve_linear_system(mat: list[list[float]], rhs: list[float]) -> list[float] | None:
    """Gaussian elimination with partial pivoting; None when singular."""
    k = len(rhs)
    aug = [row[:] + [rhs[i]] for i, row in enumerate(mat)]
    for col in range(k):
        pivot = max(range(col, k), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-18:
            return None
        aug[col], aug[pivot] = aug[pivot], aug[col]
        for r in range(k):
            if r == col:
                continue
            factor = aug[r][col] / aug[col][col]
            for c in range(col, k + 1):
                aug[r][c] -= factor * aug[col][c]
    return [aug[i][k] / aug[i][i] for i in range(k)]


def wls_solve(stats: dict, teams: list[str]) -> list[float] | None:
    first = next(iter(stats.values()))
    k = len(first[1])
    mat = [[0.0] * k for _ in range(k)]
    rhs = [0.0] * k
    for t in teams:
        xtx, xty = stats[t]
        for a in range(k):
            rhs[a] += xty[a]
            for b in range(k):
                mat[a][b] += xtx[a][b]
    return _solve_linear_system(mat, rhs)


def wls_bootstrap(
    stats: dict, index: int, *, reps: int = REPS, seed: int = SEED
) -> tuple[float | None, float | None]:
    teams = sorted(stats)
    if not teams:
        return None, None
    rng = random.Random(seed)  # noqa: S311 - statistical bootstrap, not crypto
    n = len(teams)
    draws: list[float] = []
    for _ in range(reps):
        beta = wls_solve(stats, [teams[rng.randrange(n)] for _ in range(n)])
        if beta is not None:
            draws.append(beta[index])
    if not draws:
        return None, None
    draws.sort()
    lo = draws[int((1 - CI) / 2 * len(draws))]
    hi = draws[min(int((1 + CI) / 2 * len(draws)), len(draws) - 1)]
    return lo, hi


# --------------------------------------------------------------------- linearity gate
def weighted_quantile_bins(
    rows: list[tuple[str, float, float]], bins: int = BINS
) -> list[list[tuple[str, float, float]]]:
    """Split pairs into `bins` equal-weight groups ordered by delta."""
    ordered = sorted(rows, key=lambda r: r[1])
    w = team_weights(rows)
    total = sum(w[r[0]] for r in ordered)
    if total <= 0:
        return []
    edges = [total * (i + 1) / bins for i in range(bins)]
    out: list[list[tuple[str, float, float]]] = [[] for _ in range(bins)]
    run, idx = 0.0, 0
    for r in ordered:
        run += w[r[0]]
        while idx < bins - 1 and run > edges[idx]:
            idx += 1
        out[idx].append(r)
    return out


def linearity_gate(rows: list[tuple[str, float, float]]) -> dict:
    """Frozen gate: delta^2 CI excludes zero AND max binned rel. deviation > 20%.

    Two relative-deviation conventions are reported because the protocol sentence
    ("max binned relative deviation from the linear fit") does not fix a
    denominator, and with a free intercept the choice matters:

      * `observed`  -- binned mean of d against the fitted line. This is the
        literal reading (the data deviates, the line is the reference) and it is
        the one the gate uses.
      * `quadratic` -- the v1 convention, quadratic prediction against linear
        prediction at the bin midpoint, kept so the two generations stay
        comparable.

    Both are emitted for every cell so the gate never depends on an unstated
    choice. The drift component alone is also reported, since the intercept
    2*tau^2 dominates the linear prediction and shrinks any relative deviation.
    """
    lin_stats = wls_stats(rows, lambda r: (1.0, r[1]))
    teams = sorted(lin_stats)
    lin = wls_solve(lin_stats, teams)

    quad_stats = wls_stats(rows, lambda r: (1.0, r[1], r[1] * r[1]))
    quad = wls_solve(quad_stats, teams)
    q_lo, q_hi = wls_bootstrap(quad_stats, 2)

    w = team_weights(rows)
    max_dev_obs = max_dev_quad = max_dev_drift = 0.0
    bin_report: list[dict] = []
    valid = 0
    for group in weighted_quantile_bins(rows):
        n_pairs = len(group)
        n_teams = len({r[0] for r in group})
        ok = n_pairs >= MIN_PAIRS_PER_BIN and n_teams >= MIN_TEAMS_PER_BIN
        if not ok:
            bin_report.append({"pairs": n_pairs, "teams": n_teams, "valid": False})
            continue
        valid += 1
        wsum = sum(w[r[0]] for r in group)
        delta_mid = sum(w[r[0]] * r[1] for r in group) / wsum
        observed = sum(w[r[0]] * r[2] for r in group) / wsum
        pred_lin = lin[0] + lin[1] * delta_mid if lin else 0.0
        pred_quad = (
            quad[0] + quad[1] * delta_mid + quad[2] * delta_mid * delta_mid if quad else 0.0
        )
        drift_lin = lin[1] * delta_mid if lin else 0.0
        dev_obs = abs(observed - pred_lin) / abs(pred_lin) if pred_lin else 0.0
        dev_quad = abs(pred_quad - pred_lin) / abs(pred_lin) if pred_lin else 0.0
        dev_drift = abs(observed - pred_lin) / abs(drift_lin) if drift_lin else 0.0
        max_dev_obs = max(max_dev_obs, dev_obs)
        max_dev_quad = max(max_dev_quad, dev_quad)
        max_dev_drift = max(max_dev_drift, dev_drift)
        bin_report.append(
            {
                "pairs": n_pairs,
                "teams": n_teams,
                "valid": True,
                "delta_mid_days": delta_mid,
                "observed_mean_d": observed,
                "linear_pred": pred_lin,
                "quadratic_pred": pred_quad,
                "rel_dev_observed": dev_obs,
                "rel_dev_quadratic": dev_quad,
                "rel_dev_vs_drift_component": dev_drift,
            }
        )

    excludes_zero = q_lo is not None and q_hi is not None and not (q_lo <= 0.0 <= q_hi)
    nonlinear = excludes_zero and max_dev_obs > CURVATURE_TOL
    return {
        "linear_intercept": lin[0] if lin else None,
        "linear_slope": lin[1] if lin else None,
        "quad_delta2": quad[2] if quad else None,
        "quad_delta2_ci": [q_lo, q_hi],
        "delta2_ci_excludes_zero": excludes_zero,
        "valid_bins": valid,
        "max_rel_dev_observed": max_dev_obs,
        "max_rel_dev_quadratic": max_dev_quad,
        "max_rel_dev_vs_drift_component": max_dev_drift,
        "curvature_tolerance": CURVATURE_TOL,
        "bins": bin_report,
        "gate": "NONLINEAR_DRIFT" if nonlinear else "LINEAR_OK",
        "bins_sufficient": valid >= MIN_VALID_BINS,
    }


# ------------------------------------------------------------------- season boundary
def boundary_model(rows: list[tuple[str, float, float, float]]) -> dict:
    """d = 2*tau^2 + sigma^2*delta + jump*crosses_boundary, on all pairs.

    Rows are (team, delta, crossed, d). The jump term carries the one-off variance
    a team's strength picks up over a season break; the slope stays a per-day rate.
    Provider season is the boundary authority, so `crossed` is set by the season
    label rather than by any gap in the calendar.
    """
    crossing = sum(1 for r in rows if r[2] > 0.0)
    if crossing == 0 or crossing == len(rows):
        return {
            "status": "BOUNDARY_NOT_IDENTIFIED",
            "reason": "no_contrast_between_within_and_cross_season_pairs",
            "pairs": len(rows),
            "cross_season_pairs": crossing,
        }
    stats = wls_stats(rows, lambda r: (1.0, r[1], r[2]))
    teams = sorted(stats)
    beta = wls_solve(stats, teams)
    if beta is None:
        return {
            "status": "BOUNDARY_NOT_IDENTIFIED",
            "reason": "singular_design",
            "pairs": len(rows),
            "cross_season_pairs": crossing,
        }
    jump_lo, jump_hi = wls_bootstrap(stats, 2)
    slope_lo, slope_hi = wls_bootstrap(stats, 1)
    return {
        "status": "IDENTIFIED",
        "pairs": len(rows),
        "cross_season_pairs": crossing,
        "teams": len(teams),
        "tau2": beta[0] / 2,
        "alpha_abs_pooled": beta[1],
        "alpha_abs_pooled_ci": [slope_lo, slope_hi],
        "season_jump_variance": beta[2],
        "season_jump_variance_ci": [jump_lo, jump_hi],
    }
