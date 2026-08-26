"""Exact Gaussian likelihood for the local level model -- the v3 primary estimator.

Protocol: docs/review_packages/EV_SE_DRIFT_V3/PROTOCOL_FROZEN_V3_20260826.md
(commit 603a9753).

    theta_k = theta_{k-1} + N(0, sigma^2 * dt_k)      latent team strength
    y_k     = theta_k     + N(0, tau^2)               observed match xG

The variogram of v2 is a method-of-moments estimator for the same model. This one
is the maximum-likelihood estimator, so it is the efficient estimator under the
model and the honest place to ask whether the data can identify `sigma^2` at all.

`sigma^2 = 0` sits on the boundary of the parameter space, so the likelihood-ratio
statistic is not chi-square under the null. It is the 50:50 mixture of a point mass
at zero and chi^2_1, which is what `lrt_pvalue` applies. Using chi^2_1 here would
roughly double the false-positive rate.
"""

from __future__ import annotations

import math

# One-sided boundary LRT at 5%: 0.5*P(chi2_1 > c) = 0.05  =>  c = 2.7055
LRT_CRITICAL_95 = 2.705543454095404


def loglik(series: list[tuple[float, float]], sigma2: float, tau2: float) -> float:
    """Exact log-likelihood of one team-season series, diffuse in the level.

    The diffuse start is used in closed form: after the first observation a
    diffuse level leaves theta_1 ~ N(y_1, tau^2), so the likelihood accumulates
    from k=2 and the team's own level never needs a prior.
    """
    if len(series) < 3 or tau2 <= 0.0:
        return 0.0 if len(series) < 3 else float("-inf")
    a = series[0][1]
    p = tau2
    total = 0.0
    prev_t = series[0][0]
    for t, y in series[1:]:
        p += sigma2 * (t - prev_t)          # predict
        f = p + tau2                        # innovation variance
        if f <= 0.0:
            return float("-inf")
        v = y - a
        total -= 0.5 * (math.log(2.0 * math.pi * f) + v * v / f)
        gain = p / f                        # update
        a += gain * v
        p -= gain * p
        prev_t = t
    return total


def cell_loglik(
    series_list: list[list[tuple[float, float]]], sigma2: float, tau2: float
) -> float:
    """Team-season series are independent, so the cell likelihood is their sum."""
    total = 0.0
    for s in series_list:
        total += loglik(s, sigma2, tau2)
        if total == float("-inf"):
            return total
    return total


# ------------------------------------------------------------------ optimisation
def _nelder_mead(
    fn, start: list[float], step: float = 0.5, tol: float = 1e-10, max_iter: int = 2000
) -> tuple[list[float], float]:
    """Deterministic Nelder-Mead. No third-party dependency, so fits reproduce bit for bit."""
    n = len(start)
    simplex = [list(start)]
    for i in range(n):
        point = list(start)
        point[i] += step
        simplex.append(point)
    values = [fn(p) for p in simplex]
    for _ in range(max_iter):
        order = sorted(range(n + 1), key=lambda i: values[i])
        simplex = [simplex[i] for i in order]
        values = [values[i] for i in order]
        if abs(values[-1] - values[0]) <= tol * (abs(values[0]) + abs(values[-1]) + tol):
            break
        centroid = [sum(simplex[i][d] for i in range(n)) / n for d in range(n)]
        worst = simplex[-1]
        refl = [centroid[d] + (centroid[d] - worst[d]) for d in range(n)]
        f_refl = fn(refl)
        if f_refl < values[0]:
            exp_pt = [centroid[d] + 2.0 * (centroid[d] - worst[d]) for d in range(n)]
            f_exp = fn(exp_pt)
            simplex[-1], values[-1] = (
                (exp_pt, f_exp) if f_exp < f_refl else (refl, f_refl)
            )
        elif f_refl < values[-2]:
            simplex[-1], values[-1] = refl, f_refl
        else:
            con = [centroid[d] + 0.5 * (worst[d] - centroid[d]) for d in range(n)]
            f_con = fn(con)
            if f_con < values[-1]:
                simplex[-1], values[-1] = con, f_con
            else:
                for i in range(1, n + 1):
                    simplex[i] = [
                        simplex[0][d] + 0.5 * (simplex[i][d] - simplex[0][d])
                        for d in range(n)
                    ]
                    values[i] = fn(simplex[i])
    best = min(range(n + 1), key=lambda i: values[i])
    return simplex[best], values[best]


def _golden(fn, lo: float, hi: float, tol: float = 1e-9, max_iter: int = 300) -> float:
    """Golden-section minimisation on a scalar, for the restricted and profile fits."""
    inv = (math.sqrt(5.0) - 1.0) / 2.0
    c, d = hi - inv * (hi - lo), lo + inv * (hi - lo)
    fc, fd = fn(c), fn(d)
    for _ in range(max_iter):
        if hi - lo < tol:
            break
        if fc < fd:
            hi, d, fd = d, c, fc
            c = hi - inv * (hi - lo)
            fc = fn(c)
        else:
            lo, c, fc = c, d, fd
            d = lo + inv * (hi - lo)
            fd = fn(d)
    return (lo + hi) / 2.0


def _pooled_variance(series_list: list[list[tuple[float, float]]]) -> float:
    values = [y for s in series_list for _, y in s]
    if len(values) < 2:
        return 1.0
    mean = sum(values) / len(values)
    return max(sum((v - mean) ** 2 for v in values) / (len(values) - 1), 1e-9)


def fit_restricted(series_list: list[list[tuple[float, float]]]) -> tuple[float, float]:
    """Best log-likelihood with sigma^2 pinned to zero. Returns (tau2, loglik)."""
    v0 = _pooled_variance(series_list)
    best = _golden(
        lambda lt: -cell_loglik(series_list, 0.0, math.exp(lt)),
        math.log(v0) - 6.0,
        math.log(v0) + 3.0,
    )
    tau2 = math.exp(best)
    return tau2, cell_loglik(series_list, 0.0, tau2)


def fit_full(series_list: list[list[tuple[float, float]]]) -> tuple[float, float, float]:
    """Unrestricted MLE. Returns (sigma2, tau2, loglik)."""
    v0 = _pooled_variance(series_list)
    start = [math.log(v0), math.log(1e-4)]

    def objective(p: list[float]) -> float:
        lt, ls = p
        if lt > 20.0 or ls > 20.0 or lt < -40.0 or ls < -40.0:
            return 1e18
        return -cell_loglik(series_list, math.exp(ls), math.exp(lt))

    point, value = _nelder_mead(objective, start)
    sigma2, tau2 = math.exp(point[1]), math.exp(point[0])
    # The boundary is a legitimate optimum; take it when it wins.
    tau0, ll0 = fit_restricted(series_list)
    if ll0 >= -value:
        return 0.0, tau0, ll0
    return sigma2, tau2, -value


def lrt_pvalue(ll_full: float, ll_restricted: float) -> float:
    """One-sided p-value under the 50:50 point-mass / chi^2_1 mixture."""
    stat = 2.0 * (ll_full - ll_restricted)
    if stat <= 0.0:
        return 1.0
    return 0.5 * math.erfc(math.sqrt(stat / 2.0))


def profile_interval(
    series_list: list[list[tuple[float, float]]], sigma2_hat: float, ll_max: float
) -> tuple[float, float | None]:
    """95% profile-likelihood interval for sigma^2, boundary-calibrated.

    The region is {sigma^2 : 2*(ll_max - ll_profile) <= 2.7055}, the same critical
    value the one-sided boundary LRT uses. Interval and test therefore agree by
    construction: the interval excludes zero exactly when the test rejects.
    """
    v0 = _pooled_variance(series_list)

    def profile(sigma2: float) -> float:
        best = _golden(
            lambda lt: -cell_loglik(series_list, sigma2, math.exp(lt)),
            math.log(v0) - 6.0,
            math.log(v0) + 3.0,
        )
        return cell_loglik(series_list, sigma2, math.exp(best))

    target = ll_max - LRT_CRITICAL_95 / 2.0

    lo = 0.0
    if profile(0.0) < target:                      # zero is excluded: bisect for the bound
        a, b = 0.0, max(sigma2_hat, 1e-12)
        for _ in range(60):
            mid = (a + b) / 2.0
            if profile(mid) < target:
                a = mid
            else:
                b = mid
        lo = (a + b) / 2.0

    hi_scale = max(sigma2_hat, 1e-9)
    b = hi_scale if hi_scale > 0 else 1e-6
    for _ in range(60):
        b *= 2.0
        if profile(b) < target:
            break
    else:
        return lo, None
    a = max(sigma2_hat, 0.0)
    for _ in range(60):
        mid = (a + b) / 2.0
        if profile(mid) < target:
            b = mid
        else:
            a = mid
    return lo, (a + b) / 2.0
