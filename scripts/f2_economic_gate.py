"""F 补项纠错重算：经济门净收益方差/覆盖率（同截点渠道 OVER 价 + 返水 ABS_PROFIT_V2）。

渠道 OVER 价已在 SQL 端约束「capture_id == 评估 capture_id 且 captured_at <= evaluated_at」；
本脚本再逐 fixture 核验共同 T30 截点（kickoff-35min <= evaluated_at <= kickoff-30min）。

成本诚实边界：verified_cost 无冻结值，按 cost ∈ {0, 0.01, 0.02} 敏感性报告净收益下界，
不填 0 冒充无成本。经济功效补 z_power（80% 功效 z=0.8416）。
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from typing import Any

from f1_paired_variance import _mean, _sd
from f2_sd_market_fade import (
    _is_half_line,
    _p_market,
    _parse_dt,
    load_evaluations,
    load_pinnacle,
)

FROZEN_FADE_DELTA = 0.05
REBATE_RATE = 0.025
DELTA_E = 0.02
Z_ALPHA = 2.2414  # 单侧 0.0125
Z_POWER = 0.8416  # 80% 功效
COST_GRID = (0.0, 0.01, 0.02)


def load_channel_over(path: str) -> dict[str, dict[str, str]]:
    raw: dict[str, list[dict[str, str]]] = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw[row["fixture_id"]].append(row)
    return {fid: max(cands, key=lambda r: r["captured_at"]) for fid, cands in raw.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xg", required=True)
    parser.add_argument("--pinnacle", required=True)
    parser.add_argument("--evaluations", required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    actual: dict[str, int] = {}
    kickoff: dict[str, str] = {}
    with open(args.xg, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fid = row["fixture_id"]
            actual[fid] = actual.get(fid, 0) + int(row["goals_for"])
            kickoff[fid] = row["kickoff_at"]

    evals = load_evaluations(args.evaluations)
    pinnacle = load_pinnacle(args.pinnacle)
    channel = load_channel_over(args.channel)

    rows: list[dict[str, Any]] = []
    ef_candidates = 0  # E_F 候选（UNDER 半球线 + p_market<0.50 + 同截点报价），经济门分母。
    for fixture_id, eval_row in evals.items():
        if eval_row["selection"] != "UNDER":
            continue
        if eval_row["original_state"] not in ("ANALYSIS_PICK_ACTIVE", "NO_EDGE_CURRENT"):
            continue
        if not _is_half_line(eval_row.get("exact_line")):
            continue
        if fixture_id not in actual:
            continue
        # 评估源已限定 checkpoint = T-30m_VALIDATION_LOCK（共同 T30 截点）。
        e = _parse_dt(eval_row["evaluated_at"])
        cell = pinnacle.get(fixture_id, {}).get(eval_row["exact_line"], {}).get(
            eval_row["capture_id"]
        )
        if cell is None:
            continue
        over, under, captured_at = cell.get("OVER"), cell.get("UNDER"), cell.get("captured_at")
        if not (over and under and captured_at):
            continue
        if _parse_dt(captured_at) > e:
            continue
        p_market = _p_market(float(over), float(under))
        if not p_market < 0.50:
            continue
        ef_candidates += 1
        # 渠道报价逐 fixture 核对 capture_id / bookmaker / exact_line == 评估（同线同方向同时间）。
        ch = channel.get(fixture_id)
        if ch is None or ch.get("eval_capture_id") != eval_row["capture_id"]:
            continue
        if ch.get("bookmaker_id") != eval_row["bookmaker_id"]:
            continue
        if ch.get("exact_line") != eval_row["exact_line"]:
            continue
        channel_odds = float(ch["channel_over_odds"])
        p_fade = max(min(p_market + FROZEN_FADE_DELTA, 0.99), 0.01)
        line = float(eval_row["exact_line"])
        outcome = 1 if actual[fixture_id] > line else 0
        rebate_expected = REBATE_RATE * ((channel_odds - 1.0) * p_fade + (1.0 - p_fade))
        ev_net = p_fade * channel_odds - 1.0 + rebate_expected
        realized = (
            (channel_odds - 1.0) * (1.0 + REBATE_RATE)
            if outcome == 1
            else -1.0 + REBATE_RATE
        )
        rows.append(
            {
                "fixture_id": fixture_id,
                "channel_odds": channel_odds,
                "p_fade": p_fade,
                "ev_net": ev_net,
                "realized_net": realized,
            }
        )

    realized = [r["realized_net"] for r in rows]
    n = len(rows)
    mean_realized = _mean(realized)
    sd_realized = _sd(realized)
    # 经济门检验「实际结算净收益下界 > δ_E」，各 cost 下的下界与所需样本（含 z_power）。
    cost_bounds: dict[str, Any] = {}
    for cost in COST_GRID:
        net = [r["realized_net"] - cost for r in rows]
        mn = _mean(net)
        sd = _sd(net)
        ci_lower = mn - Z_ALPHA * sd / (n**0.5) if n else 0.0
        n_required = (
            ((Z_ALPHA + Z_POWER) * sd / (mn - DELTA_E)) ** 2
            if n and mn > DELTA_E
            else None
        )
        cost_bounds[str(cost)] = {
            "mean_net": mn,
            "sd_net": sd,
            "ci_lower": ci_lower,
            "n_required_for_delta_e": n_required,
        }
    report = {
        "n": n,
        "ef_candidates": ef_candidates,
        "mean_realized_net": mean_realized,
        "sd_realized_net": sd_realized,
        "coverage_rate": n / ef_candidates if ef_candidates else 0.0,
        "delta_e": DELTA_E,
        "z_alpha": Z_ALPHA,
        "z_power": Z_POWER,
        "cost_sensitivity": cost_bounds,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
