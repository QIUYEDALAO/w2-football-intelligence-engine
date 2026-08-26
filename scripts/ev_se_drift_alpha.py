"""EV-SE drift-rate estimation under the frozen acceptance protocol (2026-08-26).

Estimates alpha_abs (xG^2/day) from historical team xG series only.
Never reads settled bet outcomes, profit, loss, or hit rate.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime

# ---------------------------------------------------------------- frozen protocol
SEED = 20260826
BOOTSTRAP_REPS = 10_000
CI_LEVEL = 0.95
MAIN_WINDOW = 5
SENSITIVITY_WINDOWS = (4, 6, 8)
HOLDOUT_CUTOFF = "2026-01-01"

MIN_TEAMS = 10
MIN_PAIRS = 100
MIN_BINS = 4
H_BINS = 5
MIN_PAIRS_PER_BIN = 20
MIN_TEAMS_PER_BIN = 5
CURVATURE_TOLERANCE = 0.20

DAY = 86400.0


def parse_ts(text: str) -> float:
    """Kickoff timestamp -> epoch days."""
    text = text.strip().replace(" ", "T")
    if text.endswith("+00"):
        text = text[:-3] + "+00:00"
    return datetime.fromisoformat(text).timestamp() / DAY


@dataclass(frozen=True)
class Window:
    team: str
    league: str
    season: str
    times: tuple[float, ...]
    values: tuple[float, ...]

    @property
    def mean(self) -> float:
        return sum(self.values) / len(self.values)

    @property
    def sample_variance(self) -> float:
        k = len(self.values)
        if k < 2:
            return 0.0
        m = self.mean
        return sum((v - m) ** 2 for v in self.values) / (k - 1)


def brownian_exposure(w1: Window, w2: Window) -> float:
    """H(W1,W2): Var(mean2 - mean1) / sigma^2 for Brownian latent strength.

    Cov(theta(a), theta(b)) = sigma^2 * min(a, b), so for equal within-window
    weights 1/k the exposure is the full double sum, not the centre gap.
    """
    a, b = w1.times, w2.times
    ka, kb = len(a), len(b)
    saa = sum(min(x, y) for x in a for y in a) / (ka * ka)
    sbb = sum(min(x, y) for x in b for y in b) / (kb * kb)
    sab = sum(min(x, y) for x in a for y in b) / (ka * kb)
    return sbb + saa - 2.0 * sab


def naive_exposure(w1: Window, w2: Window) -> float:
    """Sensitivity-only comparator: gap between window mean times."""
    return sum(w2.times) / len(w2.times) - sum(w1.times) / len(w1.times)


# ---------------------------------------------------------------- window building
def build_windows(
    series: list[tuple[float, float]],
    *,
    team: str,
    league: str,
    season: str,
    size: int,
) -> list[Window]:
    """Non-overlapping consecutive windows inside one provider season."""
    series = sorted(series)
    out: list[Window] = []
    for start in range(0, len(series) - size + 1, size):
        chunk = series[start : start + size]
        out.append(
            Window(
                team=team,
                league=league,
                season=season,
                times=tuple(t for t, _ in chunk),
                values=tuple(v for _, v in chunk),
            )
        )
    return out


@dataclass
class Pair:
    team: str
    league: str
    h: float
    naive: float
    y: float
    same_season: bool


def make_pairs(windows: list[Window], *, same_season_only: bool) -> list[Pair]:
    pairs: list[Pair] = []
    for i, w1 in enumerate(windows):
        for w2 in windows[i + 1 :]:
            if w1.times[-1] >= w2.times[0]:
                continue  # overlap guard
            same = w1.season == w2.season
            if same_season_only and not same:
                continue
            k1, k2 = len(w1.values), len(w2.values)
            sampling = w1.sample_variance / k1 + w2.sample_variance / k2
            pairs.append(
                Pair(
                    team=w1.team,
                    league=w1.league,
                    h=brownian_exposure(w1, w2),
                    naive=naive_exposure(w1, w2),
                    y=(w2.mean - w1.mean) ** 2 - sampling,
                    same_season=same,
                )
            )
    return pairs


# ---------------------------------------------------------------- estimation
def _cluster_weights(pairs: list[Pair]) -> dict[str, float]:
    counts: dict[str, int] = {}
    for p in pairs:
        counts[p.team] = counts.get(p.team, 0) + 1
    return {team: 1.0 / n for team, n in counts.items()}


def _team_stats(pairs: list[Pair], exposure: str) -> dict[str, tuple[float, float]]:
    """Per team: (sum w*H*y, sum w*H*H) so bootstrap is O(teams)."""
    w = _cluster_weights(pairs)
    acc: dict[str, list[float]] = {}
    for p in pairs:
        h = p.h if exposure == "brownian" else p.naive
        s = acc.setdefault(p.team, [0.0, 0.0])
        s[0] += w[p.team] * h * p.y
        s[1] += w[p.team] * h * h
    return {t: (v[0], v[1]) for t, v in acc.items()}


def slope_through_origin(stats: dict[str, tuple[float, float]], teams: list[str]) -> float | None:
    num = den = 0.0
    for t in teams:
        a, b = stats[t]
        num += a
        den += b
    if den <= 0:
        return None
    return num / den


def bootstrap_ci(
    stats: dict[str, tuple[float, float]],
    *,
    reps: int = BOOTSTRAP_REPS,
    seed: int = SEED,
) -> tuple[float | None, float | None, list[float]]:
    teams = sorted(stats)
    if not teams:
        return None, None, []
    rng = random.Random(seed)  # noqa: S311 - statistical bootstrap, not crypto
    draws: list[float] = []
    n = len(teams)
    for _ in range(reps):
        sample = [teams[rng.randrange(n)] for _ in range(n)]
        s = slope_through_origin(stats, sample)
        if s is not None:
            draws.append(s)
    if not draws:
        return None, None, []
    draws.sort()
    lo = draws[int((1 - CI_LEVEL) / 2 * len(draws))]
    hi = draws[min(int((1 + CI_LEVEL) / 2 * len(draws)), len(draws) - 1)]
    return lo, hi, draws


# ------------------------------------------------------- linearity gate (H^2 term)
def _quad_team_stats(pairs: list[Pair]) -> dict[str, tuple[float, ...]]:
    """Per team sufficient statistics for y = a*H + b*H^2 through the origin."""
    w = _cluster_weights(pairs)
    acc: dict[str, list[float]] = {}
    for p in pairs:
        h, wi = p.h, w[p.team]
        s = acc.setdefault(p.team, [0.0] * 5)
        s[0] += wi * h * h            # sum w H^2
        s[1] += wi * h ** 3           # sum w H^3
        s[2] += wi * h ** 4           # sum w H^4
        s[3] += wi * h * p.y          # sum w H y
        s[4] += wi * h * h * p.y      # sum w H^2 y
    return {t: tuple(v) for t, v in acc.items()}


def solve_quadratic(stats: dict[str, tuple[float, ...]], teams: list[str]):
    s = [0.0] * 5
    for t in teams:
        v = stats[t]
        for i in range(5):
            s[i] += v[i]
    a11, a12, a22, b1, b2 = s[0], s[1], s[2], s[3], s[4]
    det = a11 * a22 - a12 * a12
    if abs(det) < 1e-18:
        return None, None
    return (b1 * a22 - b2 * a12) / det, (a11 * b2 - a12 * b1) / det


def weighted_quantile_bins(pairs: list[Pair], bins: int = H_BINS) -> list[list[Pair]]:
    ordered = sorted(pairs, key=lambda p: p.h)
    w = _cluster_weights(pairs)
    total = sum(w[p.team] for p in ordered)
    if total <= 0:
        return []
    edges = [total * (i + 1) / bins for i in range(bins)]
    out: list[list[Pair]] = [[] for _ in range(bins)]
    run, idx = 0.0, 0
    for p in ordered:
        run += w[p.team]
        while idx < bins - 1 and run > edges[idx]:
            idx += 1
        out[idx].append(p)
    return out


def linearity_gate(pairs: list[Pair], *, reps: int = BOOTSTRAP_REPS, seed: int = SEED) -> dict:
    """Frozen gate: H^2 CI excludes 0 AND max binned curvature deviation > 20%."""
    lin_stats = _team_stats(pairs, "brownian")
    teams = sorted(lin_stats)
    a_lin = slope_through_origin(lin_stats, teams)

    quad = _quad_team_stats(pairs)
    a_q, b_q = solve_quadratic(quad, teams)

    rng = random.Random(seed)  # noqa: S311 - statistical bootstrap, not crypto
    n = len(teams)
    draws = []
    for _ in range(reps):
        sample = [teams[rng.randrange(n)] for _ in range(n)]
        _, b = solve_quadratic(quad, sample)
        if b is not None:
            draws.append(b)
    draws.sort()
    b_lo = draws[int((1 - CI_LEVEL) / 2 * len(draws))] if draws else None
    b_hi = draws[min(int((1 + CI_LEVEL) / 2 * len(draws)), len(draws) - 1)] if draws else None

    bins = weighted_quantile_bins(pairs)
    valid = [
        b
        for b in bins
        if len(b) >= MIN_PAIRS_PER_BIN and len({p.team for p in b}) >= MIN_TEAMS_PER_BIN
    ]
    max_dev, bin_report = 0.0, []
    for b in valid:
        h_mid = sum(p.h for p in b) / len(b)
        lin = a_lin * h_mid if a_lin else 0.0
        qua = (a_q * h_mid + b_q * h_mid * h_mid) if a_q is not None else 0.0
        dev = abs(qua - lin) / abs(lin) if lin else 0.0
        max_dev = max(max_dev, dev)
        bin_report.append(
            {"h_mid": h_mid, "pairs": len(b), "linear": lin,
             "quadratic": qua, "rel_dev": dev}
        )

    excludes_zero = b_lo is not None and b_hi is not None and not (b_lo <= 0.0 <= b_hi)
    nonlinear = excludes_zero and max_dev > CURVATURE_TOLERANCE
    return {
        "alpha_linear": a_lin,
        "quad_a": a_q,
        "quad_b": b_q,
        "quad_b_ci": [b_lo, b_hi],
        "h2_ci_excludes_zero": excludes_zero,
        "valid_bins": len(valid),
        "max_relative_curvature_deviation": max_dev,
        "bins": bin_report,
        "status": (
            "NONLINEAR_DRIFT"
            if nonlinear
            else ("INSUFFICIENT_SUPPORT" if len(valid) < MIN_BINS else "LINEAR_OK")
        ),
    }
