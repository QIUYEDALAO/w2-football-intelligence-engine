"""F-1：DA-XG-01 配对方差产出（rolling-origin 回放，开发诊断）。

在 E_R 研究集（双方 ≥3 场严格 PIT 的 fixture）上，用 da_xg_offline 的
challenger 与 baseline 同批同 PIT 重放，产出配对损失差的标准误、相关系数、
有效样本量（时间分块 block bootstrap）与按联赛分层。

只作开发诊断，不冒充确认性证据。损失核为「从双方完整比分分布（Dixon-Coles）
聚合的九类总进球 log loss」（研究主指标口径，见协议 research_metric）。

用法：
  python scripts/f1_paired_variance.py \
      --xg /tmp/w2_f1_data/team_xg_match.csv \
      --identity /tmp/w2_f1_data/fixture_identity.csv \
      --out /tmp/w2_f1_data/f1_paired_variance_report.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from w2.quant_research.da_xg_offline import (
    DaXgParameters,
    XgMatchRecord,
    predict,
    predict_baseline,
)
from w2.strategy.simulate import _exact_score_matrix

# 九类总进球分布桶 {0,1,2,3,4,5,6,7,8+}。
GOAL_BUCKETS = 9
MAX_EXPLICIT_BUCKET = 8
EPS = 1e-12
RHO = 0.0  # 冻结基线 dixon_coles_rho（线上实测 null/0.0）
MAX_GOALS = 12


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def load_matches(xg_path: str, identity_path: str) -> tuple[list[XgMatchRecord], list[str]]:
    """合并 team_xg_match（每 fixture 两行）为每场一行的 XgMatchRecord。

    返回 (matches, er_fixtures)，其中 er_fixtures 是「双方 ≥3 场严格 PIT」的
    fixture_id 列表（严格 PIT = 同队历史 kickoff < t.kickoff 且 captured_at < t.kickoff）。
    """
    # 1. 读 team_xg_match（每 fixture 两行：主队视角 + 客队视角）。
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with open(xg_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows[row["fixture_id"]].append(row)

    # 2. 读 fixture identity → provider_fixture_id 映射。
    identity: dict[str, dict[str, str]] = {}
    with open(identity_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            identity[row["provider_fixture_id"]] = row

    matches: list[XgMatchRecord] = []
    for fixture_id, pair in rows.items():
        if len(pair) != 2:
            # 单侧缺失的 fixture 无法构成完整一场，跳过（记录到诊断）。
            continue
        info = identity.get(fixture_id)
        if info is None:
            # 无 fixture identity → 排除（不猜主客/联赛/赛季，未知不当身份已核实）。
            continue
        home_team = info["home_provider_team_id"]
        away_team = info["away_provider_team_id"]
        competition = info["competition_id"]
        season = info["season"]
        home_row = next(r for r in pair if r["team_id"] == home_team)
        away_row = next(r for r in pair if r["team_id"] == away_team)

        kickoff = _parse_dt(home_row["kickoff_at"])
        # 双侧时间同时核验：一场比赛仅在两侧 xG 均已可见（取较晚 captured_at）后可用。
        home_captured = _parse_dt(home_row["captured_at"])
        away_captured = _parse_dt(away_row["captured_at"])
        captured = max(home_captured, away_captured)
        matches.append(
            XgMatchRecord(
                fixture_id=fixture_id,
                competition=competition,
                season=season,
                kickoff_utc=kickoff,
                captured_at=captured,
                home_team=home_team,
                away_team=away_team,
                home_xg=float(home_row["xg_for"]),
                away_xg=float(away_row["xg_for"]),
                home_goals=int(home_row["goals_for"]),
                away_goals=int(away_row["goals_for"]),
                neutral_site=False,
            )
        )

    # 4. 确定 E_R（双方 ≥3 场严格 PIT）。
    ordered = sorted(matches, key=lambda m: (m.kickoff_utc, m.fixture_id))
    own_pit: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for target in ordered:
        for hist in ordered:
            if hist.kickoff_utc >= target.kickoff_utc:
                break
            if hist.captured_at >= target.kickoff_utc:
                continue
            own_pit[target.fixture_id][hist.home_team] += 1
            own_pit[target.fixture_id][hist.away_team] += 1
    er_fixtures: list[str] = []
    for fixture_id, counts in own_pit.items():
        home = next((m for m in matches if m.fixture_id == fixture_id), None)
        if home is None:
            continue
        if counts.get(home.home_team, 0) >= 3 and counts.get(home.away_team, 0) >= 3:
            er_fixtures.append(fixture_id)

    return matches, er_fixtures


def _poisson_pmf(mu: float, k: int) -> float:
    return math.exp(-mu) * (mu**k) / math.factorial(k)


def total_goals_distribution(lambda_home: float, lambda_away: float) -> list[float]:
    """九类总进球分布 {0..7, 8+}，从双方完整比分分布（Dixon-Coles）聚合，概率下限 EPS 后归一。"""
    matrix = _exact_score_matrix(lambda_home, lambda_away, rho=RHO, max_goals=MAX_GOALS)
    buckets = [0.0] * (MAX_EXPLICIT_BUCKET + 1)
    for (home, away), probability in matrix.items():
        buckets[min(home + away, MAX_EXPLICIT_BUCKET)] += probability
    buckets = [max(p, EPS) for p in buckets]
    total = sum(buckets)
    return [p / total for p in buckets]


def total_goals_log_loss(lambda_home: float, lambda_away: float, actual_goals: int) -> float:
    dist = total_goals_distribution(lambda_home, lambda_away)
    bucket = min(actual_goals, MAX_EXPLICIT_BUCKET)
    return -math.log(max(dist[bucket], EPS))


def replay_er(matches: list[XgMatchRecord], er_fixtures: set[str]) -> list[dict[str, Any]]:
    """对 E_R 场跑 challenger + baseline（同批同 PIT），返回配对损失行。"""
    params = DaXgParameters()
    ordered = sorted(matches, key=lambda m: (m.kickoff_utc, m.fixture_id))
    rows: list[dict[str, Any]] = []
    for target in ordered:
        if target.fixture_id not in er_fixtures:
            continue
        cutoff = target.kickoff_utc - timedelta(minutes=30)
        history = [
            m
            for m in ordered
            if m.kickoff_utc < cutoff and m.captured_at < cutoff
        ]
        challenger = predict(
            fixture_id=target.fixture_id,
            home_team=target.home_team,
            away_team=target.away_team,
            kickoff_utc=target.kickoff_utc,
            matches=history,
            target_season=target.season,
            competition=target.competition,
            neutral_site=target.neutral_site,
            params=params,
        )
        baseline = predict_baseline(
            fixture_id=target.fixture_id,
            home_team=target.home_team,
            away_team=target.away_team,
            kickoff_utc=target.kickoff_utc,
            matches=history,
            target_season=target.season,
            competition=target.competition,
            neutral_site=target.neutral_site,
            params=params,
        )
        if challenger is None or baseline is None:
            continue
        actual_goals = target.home_goals + target.away_goals
        challenger_lambda = challenger.lambda_home + challenger.lambda_away
        baseline_lambda = baseline.lambda_home + baseline.lambda_away
        loss_c = total_goals_log_loss(
            challenger.lambda_home, challenger.lambda_away, actual_goals
        )
        loss_b = total_goals_log_loss(
            baseline.lambda_home, baseline.lambda_away, actual_goals
        )
        rows.append(
            {
                "fixture_id": target.fixture_id,
                "competition": target.competition,
                "season": target.season,
                "kickoff_utc": target.kickoff_utc.isoformat(),
                "actual_goals": actual_goals,
                "challenger_lambda": challenger_lambda,
                "baseline_lambda": baseline_lambda,
                "loss_challenger": loss_c,
                "loss_baseline": loss_b,
                "loss_diff": loss_c - loss_b,
            }
        )
    return rows


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _sd(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def _corr(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = _mean(xs), _mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


def _block_bootstrap_se(
    diffs: list[float],
    kickoffs: list[datetime],
    *,
    seed: int,
    boot: int = 10000,
) -> dict[str, float]:
    """按日历周分块，block bootstrap 估计配对损失差均值的标准误与有效样本量。

    统计对象 = 每场等权均值（主指标口径）。bootstrap 按预定义块重采样「完整比赛对」，
    并在每次样本中重算同一个每场等权统计量（不是先求周均值再对周均值等权采样）。
    """
    n = len(diffs)
    if n < 2:
        return {"se": _sd(diffs) / math.sqrt(n) if n else 0.0, "n_eff": float(n), "n_blocks": 0}
    # 按 UTC 周（ISO week）分块，块 = 完整比赛对列表（保持块内时间顺序与场次权重）。
    by_week: dict[str, list[float]] = {}
    for d, k in zip(diffs, kickoffs, strict=True):
        week = f"{k.isocalendar().year}-W{k.isocalendar().week:02d}"
        by_week.setdefault(week, []).append(d)
    blocks = list(by_week.values())
    n_blocks = len(blocks)
    rng = random.Random(seed)  # noqa: S311 — bootstrap 重采样，非加密用途
    # 重采样完整比赛对（以块为单位整块替换），重采样到累计场次数 >= n 后截断到 n，
    # 保持 bootstrap 样本场次数 == n，使统计对象 = 每场等权均值（而非周均值等权）。
    boot_means: list[float] = []
    for _ in range(boot):
        sampled: list[float] = []
        while len(sampled) < n:
            sampled.extend(rng.choice(blocks))
        boot_means.append(_mean(sampled[:n]))
    se_block = _sd(boot_means) if len(boot_means) >= 2 else (_sd(diffs) / math.sqrt(n))
    sd_diff = _sd(diffs)
    n_eff = (sd_diff**2 / se_block**2) if se_block > 0 else float(n)
    return {"se": se_block, "n_eff": n_eff, "n_blocks": n_blocks}


def paired_variance_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    diffs = [r["loss_diff"] for r in rows]
    loss_c = [r["loss_challenger"] for r in rows]
    loss_b = [r["loss_baseline"] for r in rows]
    kickoffs = [_parse_dt(r["kickoff_utc"]) for r in rows]
    n = len(diffs)
    mean_diff = _mean(diffs)
    sd_diff = _sd(diffs)
    naive_se = sd_diff / math.sqrt(n) if n else 0.0
    corr = _corr(loss_c, loss_b)
    block = _block_bootstrap_se(diffs, kickoffs, seed=20260927)
    return {
        "n": n,
        "mean_loss_diff": mean_diff,
        "sd_loss_diff": sd_diff,
        "se_naive": naive_se,
        "corr_loss_challenger_baseline": corr,
        "se_block_bootstrap": block["se"],
        "n_eff": block["n_eff"],
        "n_blocks": block["n_blocks"],
        "mean_loss_challenger": _mean(loss_c),
        "mean_loss_baseline": _mean(loss_b),
    }


def league_strata(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_league: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_league[row["competition"]].append(row)
    out: list[dict[str, Any]] = []
    for league, league_rows in sorted(by_league.items(), key=lambda kv: -len(kv[1])):
        summary = paired_variance_summary(league_rows)
        out.append({"competition": league, **summary})
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xg", required=True)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    matches, er_fixtures = load_matches(args.xg, args.identity)
    er_set = set(er_fixtures)
    rows = replay_er(matches, er_set)
    report = {
        "dataset": {
            "total_fixtures": len(matches),
            "er_fixtures": len(er_fixtures),
            "scored_pairs": len(rows),
        },
        "paired_variance": paired_variance_summary(rows),
        "by_league": league_strata(rows),
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report["dataset"], ensure_ascii=False))
    print(json.dumps(report["paired_variance"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
