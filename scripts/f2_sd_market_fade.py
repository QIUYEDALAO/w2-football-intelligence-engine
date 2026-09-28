"""F 补项纠错重算：sd_M / sd_F 半球线二元配对回放（修正版）。

纠错点：
1. 半球线概率事件：OVER L = 总进球 > L = 总进球 >= ceil(L)。修正 threshold 为
   ceil(line)（旧代码 ceil(line-0.5) 把 OVER2.5 错算成 >=2，即 OVER1.5）。
2. 正式比较用「完整比分分布投影」_exact_score_matrix（Dixon-Coles tau 修正 + max_goals
   归一，rho=冻结基线 0.0）；独立泊松简化核 _p_over_from_poisson 只标开发诊断。
3. 报价匹配约束到同一预测截点：capture_id == 评估 capture_id 且 captured_at <=
   evaluated_at，双侧 OVER/UNDER 同 capture_id；不取「最新 capture」。

主线 = 评估 exact_line（半球线）。只读生产导数据 + 本地回放，开发诊断。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from typing import Any

from f1_paired_variance import _block_bootstrap_se, _mean, _sd, load_matches

from w2.strategy.simulate import _exact_score_matrix

FROZEN_FADE_DELTA = 0.05
RHO = 0.0  # 冻结基线 dixon_coles_rho（线上实测 null/0.0）
MAX_GOALS = 12
EPS = 1e-12
T30_CHECKPOINT = "T-30m_VALIDATION_LOCK"  # 共同 T30 截点（在函数内固定，不依赖上游行序）


def _poisson_pmf(mu: float, k: int) -> float:
    return math.exp(-mu) * (mu**k) / math.factorial(k)


def _p_over_poisson(lambda_total: float, line: float) -> float:
    """开发诊断简化核：独立 Poisson 总进球。OVER L = 总进球 > L = 总进球 >= ceil(L)。"""
    threshold = int(math.ceil(line))
    cdf = sum(_poisson_pmf(lambda_total, k) for k in range(threshold))
    return max(min(1.0 - cdf, 1 - EPS), EPS)


def p_over_full(lambda_home: float, lambda_away: float, line: float) -> float:
    """正式比较：完整比分分布投影（Dixon-Coles tau + max_goals 归一，rho=冻结基线）。

    OVER L 的概率 = sum_{h+a > L} P(h,a)。
    """
    matrix = _exact_score_matrix(lambda_home, lambda_away, rho=RHO, max_goals=MAX_GOALS)
    p_over = sum(p for (home, away), p in matrix.items() if home + away > line)
    return max(min(p_over, 1 - EPS), EPS)


def _binary_log_loss(probability: float, outcome: int) -> float:
    p = max(min(probability, 1 - EPS), EPS)
    return -(outcome * math.log(p) + (1 - outcome) * math.log(1 - p))


def _p_market(o_over: float, o_under: float) -> float:
    inv_over = 1.0 / o_over
    inv_under = 1.0 / o_under
    return inv_over / (inv_over + inv_under)


def _is_half_line(line: str | None) -> bool:
    if not line:
        return False
    try:
        value = float(line)
    except (TypeError, ValueError):
        return False
    doubled = value * 2
    return abs(doubled - round(doubled)) < 1e-9 and int(round(doubled)) % 2 == 1


def load_evaluations(path: str) -> dict[str, dict[str, str]]:
    """只取 T30 checkpoint 评估；同 fixture 多行取 evaluated_at 最新（确定性，不依赖 CSV 行序）。"""
    evals: dict[str, dict[str, str]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("checkpoint") != T30_CHECKPOINT:
                continue
            fid = row["fixture_id"]
            current = evals.get(fid)
            if current is None or row["evaluated_at"] > current["evaluated_at"]:
                evals[fid] = row
    return evals


def load_pinnacle(path: str) -> dict[str, dict[str, dict[str, dict[str, str]]]]:
    """fixture_id -> line -> capture_id -> {over, under, captured_at}。"""
    raw: dict[str, dict[str, dict[str, dict[str, str]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(dict))
    )
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cell = raw[row["provider_fixture_id"]][row["line"]][row["capture_id"]]
            cell[row["canonical_selection"]] = row["decimal_odds"]
            cell["captured_at"] = row["captured_at"]
    return raw


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    diffs = [r["loss_diff"] for r in rows]
    loss_model = [r["loss_model"] for r in rows]
    loss_market = [r["loss_market"] for r in rows]
    kickoffs = [_parse_dt(r["kickoff_utc"]) for r in rows]
    n = len(diffs)
    if n == 0:
        return {"n": 0}
    # 统计对象一致：se / n_eff / n_blocks 均来自同一次配对差 block bootstrap。
    block = _block_bootstrap_se(diffs, kickoffs, seed=20260927)
    return {
        "n": n,
        "mean_loss_diff": _mean(diffs),
        "sd_loss_diff": _sd(diffs),
        "corr_loss_model_market": _corr(loss_model, loss_market),
        "se_block_bootstrap": block["se"],
        "n_eff": block["n_eff"],
        "n_blocks": block["n_blocks"],
        "mean_loss_model": _mean(loss_model),
        "mean_loss_market": _mean(loss_market),
    }


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


def _parse_dt(value: str) -> Any:
    from datetime import UTC, datetime

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _selfcheck() -> None:
    """独立算例：0.5/1.5/2.5/3.5 线数值正例 + 完整投影 == 一维泊松（rho=0）。"""
    assert abs(_p_over_poisson(2.5, 0.5) - 0.917915) < 1e-4
    assert abs(_p_over_poisson(2.5, 1.5) - 0.712703) < 1e-4
    assert abs(_p_over_poisson(2.5, 2.5) - 0.456187) < 1e-4
    assert abs(_p_over_poisson(2.5, 3.5) - 0.242424) < 1e-4
    # 完整比分分布投影（rho=0）与一维泊松（λh+λa）一致（泊松可加性）。
    for lh, la in ((1.2, 1.3), (2.0, 0.5)):
        full = p_over_full(lh, la, 2.5)
        simple = _p_over_poisson(lh + la, 2.5)
        assert abs(full - simple) < 1e-6, (full, simple)
    print("selfcheck: half-line probability cases passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xg", required=True)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--pinnacle", required=True)
    parser.add_argument("--evaluations", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    _selfcheck()

    matches, er_fixtures = load_matches(args.xg, args.identity)
    er_set = set(er_fixtures)
    actual = {m.fixture_id: m.home_goals + m.away_goals for m in matches}
    kickoff = {m.fixture_id: m.kickoff_utc.isoformat() for m in matches}
    competition = {m.fixture_id: m.competition for m in matches}

    evals = load_evaluations(args.evaluations)
    pinnacle = load_pinnacle(args.pinnacle)

    # challenger λ 回放（只对 E_R 场）。
    ordered = sorted(matches, key=lambda m: (m.kickoff_utc, m.fixture_id))
    lambdas: dict[str, tuple[float, float]] = {}
    from w2.quant_research.da_xg_offline import DaXgParameters, predict

    params = DaXgParameters()
    for target in ordered:
        if target.fixture_id not in er_set:
            continue
        from datetime import timedelta

        cutoff = target.kickoff_utc - timedelta(minutes=30)
        history = [
            m
            for m in ordered
            if m.kickoff_utc < cutoff and m.captured_at < cutoff
        ]
        pred = predict(
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
        if pred is not None:
            lambdas[target.fixture_id] = (pred.lambda_home, pred.lambda_away)

    def _match_quote(fixture_id: str, line: str, capture_id: str, evaluated_at: str):
        # 评估源已限定 checkpoint = T-30m_VALIDATION_LOCK（共同 T30 截点）；
        # 此处只核验报价 captured_at <= evaluated_at 且双侧同 capture_id。
        e = _parse_dt(evaluated_at)
        cell = pinnacle.get(fixture_id, {}).get(line, {}).get(capture_id)
        if cell is None:
            return None
        over, under, captured_at = cell.get("OVER"), cell.get("UNDER"), cell.get("captured_at")
        if not (over and under and captured_at):
            return None
        if _parse_dt(captured_at) > e:
            return None
        return float(over), float(under)

    # ---- sd_M：E_M = E_R ∩ 半球线评估 ∩ Pinnacle 同截点报价 ----
    em_rows: list[dict[str, Any]] = []
    for fixture_id, eval_row in evals.items():
        if not _is_half_line(eval_row.get("exact_line")):
            continue
        if fixture_id not in lambdas:
            continue
        quote = _match_quote(
            fixture_id, eval_row["exact_line"], eval_row["capture_id"], eval_row["evaluated_at"]
        )
        if quote is None:
            continue
        o_over, o_under = quote
        line = float(eval_row["exact_line"])
        lh, la = lambdas[fixture_id]
        p_model = p_over_full(lh, la, line)
        p_market = _p_market(o_over, o_under)
        outcome = 1 if actual[fixture_id] > line else 0
        loss_model = _binary_log_loss(p_model, outcome)
        loss_market = _binary_log_loss(p_market, outcome)
        em_rows.append(
            {
                "fixture_id": fixture_id,
                "competition": competition[fixture_id],
                "kickoff_utc": kickoff[fixture_id],
                "line": eval_row["exact_line"],
                "loss_model": loss_model,
                "loss_market": loss_market,
                "loss_diff": loss_model - loss_market,
            }
        )

    # ---- sd_F：E_F = UNDER eligible ∩ 半球线 ∩ 同截点报价 ∩ p_market<0.50 ----
    ef_rows: list[dict[str, Any]] = []
    for fixture_id, eval_row in evals.items():
        if eval_row["selection"] != "UNDER":
            continue
        if eval_row["original_state"] not in ("ANALYSIS_PICK_ACTIVE", "NO_EDGE_CURRENT"):
            continue
        if not _is_half_line(eval_row.get("exact_line")):
            continue
        if fixture_id not in actual:
            continue
        quote = _match_quote(
            fixture_id, eval_row["exact_line"], eval_row["capture_id"], eval_row["evaluated_at"]
        )
        if quote is None:
            continue
        o_over, o_under = quote
        p_market = _p_market(o_over, o_under)
        if not p_market < 0.50:
            continue
        line = float(eval_row["exact_line"])
        p_fade = max(min(p_market + FROZEN_FADE_DELTA, 0.99), 0.01)
        outcome = 1 if actual[fixture_id] > line else 0
        loss_candidate = _binary_log_loss(p_fade, outcome)
        loss_market = _binary_log_loss(p_market, outcome)
        ef_rows.append(
            {
                "fixture_id": fixture_id,
                "competition": competition[fixture_id],
                "kickoff_utc": kickoff[fixture_id],
                "line": eval_row["exact_line"],
                "loss_model": loss_candidate,
                "loss_market": loss_market,
                "loss_diff": loss_candidate - loss_market,
            }
        )

    report = {
        "sd_M": {
            "_note": (
                "E_M challenger vs Pinnacle 去水，完整比分分布投影，"
                "主线=评估 exact_line，同截点"
            ),
            **_summarize(em_rows),
        },
        "sd_F": {
            "_note": "E_F DA-FADE-02 候选 vs Pinnacle 去水，主线=评估 exact_line，同截点",
            **_summarize(ef_rows),
        },
        "dataset": {
            "er_fixtures": len(er_fixtures),
            "replay_lambdas": len(lambdas),
            "em_fixtures": len(em_rows),
            "ef_fixtures": len(ef_rows),
            "totals_evaluations": len(evals),
        },
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report["dataset"], ensure_ascii=False))
    print(json.dumps(report["sd_M"], ensure_ascii=False, indent=2))
    print(json.dumps(report["sd_F"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
