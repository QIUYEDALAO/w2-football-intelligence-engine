"""Beta derivation for EV-SE: how much age a coverage gap actually buys.

Frozen protocol section 6 (commit 3fca0384). `E` is the expected point-in-time
fixture set, `O` those of its fixtures carrying two-sided numeric xG,
`u = 1 - |O|/|E|` the coverage deficit and `D = mean_age(O) - mean_age(E)` the
age the deficit costs. Fitting `D ~ kappa*u` through the origin converts a
coverage gap into age, and `beta_abs = alpha_abs * kappa` then converts it into
the same variance currency the age term already uses.

The conversion is only allowed when four premises hold jointly:

  1. the cell's `alpha` CI excludes zero;
  2. the lower CI bounds of both `kappa` and mean `D` are above zero;
  3. the approximation NRMSE is at most 50%;
  4. at least 10 teams and at least 50 states carry `u > 0`.

Otherwise the cell is `MISSINGNESS_PREMISE_FAILED` and no beta is emitted.
Argentina is reported on its own and is presumed neither to pass nor to fail.
"""

from __future__ import annotations

import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _load import CORPUS, CSV, LEAGUE
from ev_se_drift_alpha import HOLDOUT_CUTOFF, parse_ts
from ev_se_variogram import CI, REPS, SEED

DENOMINATOR = 20          # the latest-20 expected-match denominator
MIN_OBSERVED = 3          # invariant 4: fewer than three observations fails closed
MIN_TEAMS = 10
MIN_STATES_WITH_GAP = 50
MAX_NRMSE = 0.50


def observed_fixtures() -> set[tuple[str, str]]:
    """(fixture_id, team_id) carrying two-sided numeric xG in the final extract.

    STATIC existence. This is what a reader of the finished table sees, not what was
    visible at any earlier moment. Use `observed_capture_times` for the
    point-in-time question.
    """
    return set(observed_capture_times())


def observed_capture_times() -> dict[tuple[str, str], float]:
    """(fixture_id, team_id) -> capture time in epoch days.

    `captured_at` is the column `ReadModelService._xg_uncertainty_rows` compares
    against `as_of`, so it is the visibility clock production itself honours.
    Ordinary ingestion is first-write-wins behind an immutability guard, so the value
    is the first write for the rows it covers; the one controlled path that can
    rewrite it, `XgRetentionService.repair_derived_lineage`, needs write_db plus a
    backup and rejects any non-timestamp drift.
    """
    out: dict[tuple[str, str], float] = {}
    for line in open(CSV):
        p = line.rstrip("\n").split(",")
        if len(p) != 7 or p[0] in ("BEGIN", "ROLLBACK"):
            continue
        try:
            float(p[4])
            float(p[5])
        except ValueError:
            continue
        out[(p[0], p[1])] = parse_ts(p[3])
    return out


def xg_era_start() -> float:
    """Earliest kickoff the xG extract reaches, in epoch days."""
    lo = None
    for line in open(CSV):
        p = line.rstrip("\n").split(",")
        if len(p) != 7 or p[0] in ("BEGIN", "ROLLBACK"):
            continue
        if lo is None or p[2] < lo:
            lo = p[2]
    return parse_ts(lo)


def states(
    *, era_restricted: bool = False, pit: bool = False
) -> dict[str, list[tuple[str, float, float]]]:
    """league -> [(team, u, D), ...] over every full-denominator evaluation state.

    With `era_restricted`, only states whose whole expected window sits inside the
    xG extract's own coverage era are kept. Fixtures older than the feed can never
    carry xG, so including them measures where the feed starts rather than whether
    fixture-level missingness ages a team's observations. The frozen protocol
    defines `E` as the expected PIT fixture set with no era qualifier, so the
    unrestricted form stays primary and this one is reported beside it.
    """
    capture = observed_capture_times()
    era0 = xg_era_start() if era_restricted else None
    timelines: dict[tuple[str, str], list[tuple[float, bool]]] = {}
    for row in json.load(open(CORPUS))["history_rows"]:
        league = LEAGUE.get(row["provider_league_id"])
        if league is None:
            continue
        kickoff = row["kickoff_utc"]
        if kickoff >= HOLDOUT_CUTOFF:
            continue          # the holdout is reserved for path C
        key = (league, row["team_id"])
        seen_at = capture.get((row["provider_fixture_id"], row["team_id"]))
        timelines.setdefault(key, []).append((parse_ts(kickoff), seen_at))

    out: dict[str, list[tuple[str, float, float]]] = {}
    for (league, team), series in timelines.items():
        series.sort()
        for i in range(DENOMINATOR, len(series)):
            as_of = series[i][0]
            expected = series[i - DENOMINATOR : i]
            if era0 is not None and expected[0][0] < era0:
                continue
            if pit:
                # visible at the evaluation epoch, the filter production applies
                got = [t for t, seen in expected if seen is not None and seen <= as_of]
            else:
                got = [t for t, seen in expected if seen is not None]
            if len(got) < MIN_OBSERVED:
                continue      # fail closed rather than contribute a state
            coverage = len(got) / DENOMINATOR
            mean_age_e = sum(as_of - t for t, _ in expected) / DENOMINATOR
            mean_age_o = sum(as_of - t for t in got) / len(got)
            out.setdefault(league, []).append((team, 1.0 - coverage, mean_age_o - mean_age_e))
    return out


def _weights(rows: list[tuple[str, float, float]]) -> dict[str, float]:
    counts: dict[str, int] = {}
    for team, _, _ in rows:
        counts[team] = counts.get(team, 0) + 1
    return {t: 1.0 / n for t, n in counts.items()}


def team_stats(rows: list[tuple[str, float, float]]) -> dict[str, tuple[float, ...]]:
    """Per team: (sum w*u*D, sum w*u*u, sum w*D, sum w)."""
    w = _weights(rows)
    acc: dict[str, list[float]] = {}
    for team, u, d in rows:
        wi = w[team]
        a = acc.setdefault(team, [0.0] * 4)
        a[0] += wi * u * d
        a[1] += wi * u * u
        a[2] += wi * d
        a[3] += wi
    return {t: tuple(v) for t, v in acc.items()}


def solve(stats: dict[str, tuple[float, ...]], teams: list[str]) -> tuple[float | None, float]:
    """Through-origin kappa and the equal-team-weight mean of D."""
    num = den = sum_d = sum_w = 0.0
    for t in teams:
        v = stats[t]
        num += v[0]
        den += v[1]
        sum_d += v[2]
        sum_w += v[3]
    kappa = num / den if den > 0 else None
    mean_d = sum_d / sum_w if sum_w > 0 else 0.0
    return kappa, mean_d


def bootstrap(stats: dict[str, tuple[float, ...]]) -> dict[str, list[float | None]]:
    teams = sorted(stats)
    rng = random.Random(SEED)  # noqa: S311 - statistical bootstrap, not crypto
    n = len(teams)
    kappas: list[float] = []
    means: list[float] = []
    for _ in range(REPS):
        sample = [teams[rng.randrange(n)] for _ in range(n)]
        k, m = solve(stats, sample)
        if k is not None:
            kappas.append(k)
        means.append(m)

    def interval(draws: list[float]) -> list[float | None]:
        if not draws:
            return [None, None]
        draws.sort()
        lo = draws[int((1 - CI) / 2 * len(draws))]
        hi = draws[min(int((1 + CI) / 2 * len(draws)), len(draws) - 1)]
        return [lo, hi]

    return {"kappa_ci": interval(kappas), "mean_d_ci": interval(means)}


def nrmse(rows: list[tuple[str, float, float]], kappa: float) -> float | None:
    """Residual RMS of D - kappa*u over the RMS of D, at equal team weight."""
    w = _weights(rows)
    resid = signal = total = 0.0
    for team, u, d in rows:
        wi = w[team]
        resid += wi * (d - kappa * u) ** 2
        signal += wi * d * d
        total += wi
    if total <= 0 or signal <= 0:
        return None
    return (resid / signal) ** 0.5


def kappa_by_league(
    *, era_restricted: bool = False, pit: bool = False
) -> dict[str, dict[str, object]]:
    """Per league kappa. With `pit`, the observed set honours captured_at <= as_of.

    When the point-in-time observed set is empty or too thin at every epoch the
    league is `MISSINGNESS_NOT_IDENTIFIABLE`. That is a different verdict from
    `MISSINGNESS_PREMISE_FAILED`, which asserts a measured direction and may not be
    reported when no admissible measurement exists. v3 reported the second where the
    first was true.
    """
    report: dict[str, dict[str, object]] = {}
    produced = states(era_restricted=era_restricted, pit=pit)
    if pit and not produced:
        return {
            "_verdict": {
                "status": "MISSINGNESS_NOT_IDENTIFIABLE",
                "reason": (
                    "no evaluation epoch has at least three xG observations visible "
                    "at that epoch, so u and D cannot be formed at all"
                ),
            }
        }
    for league, rows in sorted(produced.items()):
        gapped = [r for r in rows if r[1] > 0.0]
        teams_with_gap = {r[0] for r in gapped}
        stats = team_stats(rows)
        kappa, mean_d = solve(stats, sorted(stats))
        cis = bootstrap(stats)
        err = nrmse(rows, kappa) if kappa is not None else None
        support = (
            len(teams_with_gap) >= MIN_TEAMS and len(gapped) >= MIN_STATES_WITH_GAP
        )
        kappa_lo = cis["kappa_ci"][0]
        d_lo = cis["mean_d_ci"][0]
        premises = {
            "kappa_ci_above_zero": bool(kappa_lo is not None and kappa_lo > 0),
            "mean_d_ci_above_zero": bool(d_lo is not None and d_lo > 0),
            "nrmse_within_tolerance": bool(err is not None and err <= MAX_NRMSE),
            "support_sufficient": bool(support),
        }
        report[league] = {
            "status": (
                "MISSINGNESS_NOT_IDENTIFIABLE"
                if not support
                else "MISSINGNESS_PREMISE_FAILED"
                if not all(premises.values())
                else "PREMISES_MET_PENDING_ALPHA"
            ),
            "states": len(rows),
            "states_with_gap": len(gapped),
            "teams": len(stats),
            "teams_with_gap": len(teams_with_gap),
            "mean_coverage_deficit": (
                sum(r[1] for r in rows) / len(rows) if rows else None
            ),
            "kappa_days_per_unit_deficit": kappa,
            "kappa_ci": cis["kappa_ci"],
            "mean_d_days": mean_d,
            "mean_d_ci": cis["mean_d_ci"],
            "nrmse": err,
            "nrmse_tolerance": MAX_NRMSE,
            "premises": premises,
            "premises_met_without_alpha": all(premises.values()),
        }
    return report
