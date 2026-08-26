"""v2 estimator: within-season variogram with a free intercept.

E[(y_j - y_i)^2] = 2*tau^2 + sigma^2 * (t_j - t_i)

Slope is the drift variance rate (xG^2/day); intercept/2 is single-match
observation noise. Frozen protocol: docs/review_packages/EV_SE_DRIFT_V2/
PROTOCOL_FROZEN_20260826.md (commit 3fca0384).
"""

from __future__ import annotations

import random

SEED = 20260826
REPS = 10_000
CI = 0.95
MIN_TEAMS = 10
MIN_PAIRS = 1_000
MIN_DELTA_SPAN = 100.0
BINS = 5
MIN_PAIRS_PER_BIN = 50
MIN_TEAMS_PER_BIN = 5
CURVATURE_TOL = 0.20


def variogram_pairs(
    series_by_key: dict[tuple[str, str, str], list[tuple[float, float]]],
) -> dict[str, list[tuple[str, float, float]]]:
    """(league, team, season) -> series  ==>  league -> [(team, delta, d), ...]"""
    out: dict[str, list[tuple[str, float, float]]] = {}
    for (league, team, _season), s in series_by_key.items():
        s = sorted(s)
        rows = out.setdefault(league, [])
        for i in range(len(s)):
            ti, yi = s[i]
            for j in range(i + 1, len(s)):
                tj, yj = s[j]
                rows.append((team, tj - ti, (yj - yi) ** 2))
    return out


def _weights(rows: list[tuple[str, float, float]]) -> dict[str, float]:
    counts: dict[str, int] = {}
    for team, _, _ in rows:
        counts[team] = counts.get(team, 0) + 1
    return {t: 1.0 / n for t, n in counts.items()}


def team_stats(rows: list[tuple[str, float, float]]) -> dict[str, tuple[float, ...]]:
    """Per team: (Sw, SwD, SwDD, Swd, SwDd) for weighted LS with intercept."""
    w = _weights(rows)
    acc: dict[str, list[float]] = {}
    for team, delta, d in rows:
        wi = w[team]
        a = acc.setdefault(team, [0.0] * 5)
        a[0] += wi
        a[1] += wi * delta
        a[2] += wi * delta * delta
        a[3] += wi * d
        a[4] += wi * delta * d
    return {t: tuple(v) for t, v in acc.items()}


def solve(
    stats: dict[str, tuple[float, ...]], teams: list[str]
) -> tuple[float | None, float | None]:
    s = [0.0] * 5
    for t in teams:
        v = stats[t]
        for i in range(5):
            s[i] += v[i]
    sw, swd, swdd, swy, swdy = s
    det = sw * swdd - swd * swd
    if abs(det) < 1e-18:
        return None, None
    intercept = (swy * swdd - swdy * swd) / det
    slope = (sw * swdy - swd * swy) / det
    return intercept, slope


def bootstrap(
    stats: dict[str, tuple[float, ...]], *, reps: int = REPS, seed: int = SEED
) -> tuple[float | None, float | None]:
    teams = sorted(stats)
    if not teams:
        return None, None
    rng = random.Random(seed)  # noqa: S311 - statistical bootstrap, not crypto
    n = len(teams)
    draws: list[float] = []
    for _ in range(reps):
        sample = [teams[rng.randrange(n)] for _ in range(n)]
        _, slope = solve(stats, sample)
        if slope is not None:
            draws.append(slope)
    if not draws:
        return None, None
    draws.sort()
    lo = draws[int((1 - CI) / 2 * len(draws))]
    hi = draws[min(int((1 + CI) / 2 * len(draws)), len(draws) - 1)]
    return lo, hi
