#!/usr/bin/env python3
"""Score the frozen V1 slope candidate with strict-PIT outcome evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from statistics import mean
from typing import Any

from scripts.fit_v1_raw_delta_scale import (
    _lambda_difference,
    _poisson_nll,
    _regression,
    fit,
    load_rows,
)

CURRENT_SCALE = 1.0
CANDIDATE_SCALE = 1.102038
LEGACY_UNREPRODUCED_SCALE = 1.848
WARMUP = 1500
FOLDS = 10
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20260901


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _paired_bootstrap(values: list[float]) -> dict[str, float | int]:
    rng = random.Random(BOOTSTRAP_SEED)  # noqa: S311 - deterministic statistical bootstrap
    size = len(values)
    estimates = [
        sum(values[rng.randrange(size)] for _ in range(size)) / size
        for _ in range(BOOTSTRAP_RESAMPLES)
    ]
    return {
        "resamples": BOOTSTRAP_RESAMPLES,
        "seed": BOOTSTRAP_SEED,
        "mean": round(mean(values), 9),
        "lower_95": round(_percentile(estimates, 0.025), 9),
        "upper_95": round(_percentile(estimates, 0.975), 9),
    }


def _final_total(row: dict[str, Any], scale: float) -> float:
    total = min(max(row["base_home"] + row["base_away"], 1.35), 4.4)
    delta = scale * (row["base_home"] - row["base_away"]) + 0.30
    home = min(max((total + delta) / 2.0, 0.15), 4.25)
    away = min(max((total - delta) / 2.0, 0.15), 4.25)
    return home + away


def _rolling_origin(rows: list[dict[str, Any]]) -> dict[str, Any]:
    remaining = len(rows) - WARMUP
    base, extra = divmod(remaining, FOLDS)
    start = WARMUP
    current_x: list[float] = []
    candidate_x: list[float] = []
    outcomes: list[float] = []
    nll_differences: list[float] = []
    folds: list[dict[str, Any]] = []
    total_changed = 0
    for index in range(FOLDS):
        size = base + (1 if index < extra else 0)
        stop = start + size
        candidate_scale = fit(rows[:start])
        fold = rows[start:stop]
        current_nll = [_poisson_nll(row, CURRENT_SCALE) for row in fold]
        candidate_nll = [_poisson_nll(row, candidate_scale) for row in fold]
        differences = [
            candidate - current
            for current, candidate in zip(current_nll, candidate_nll, strict=True)
        ]
        current_x.extend(_lambda_difference(row, CURRENT_SCALE) for row in fold)
        candidate_x.extend(_lambda_difference(row, candidate_scale) for row in fold)
        outcomes.extend(row["goals_home"] - row["goals_away"] for row in fold)
        nll_differences.extend(differences)
        total_changed += sum(
            abs(_final_total(row, CURRENT_SCALE) - _final_total(row, candidate_scale)) > 1e-12
            for row in fold
        )
        folds.append(
            {
                "fold": index + 1,
                "train_count": start,
                "validation_count": size,
                "validation_kickoff_start": fold[0]["kickoff_at"],
                "validation_kickoff_end": fold[-1]["kickoff_at"],
                "fitted_scale": candidate_scale,
                "current_mean_nll": round(mean(current_nll), 9),
                "candidate_mean_nll": round(mean(candidate_nll), 9),
                "candidate_minus_current_mean_nll": round(mean(differences), 9),
                "candidate_improves": mean(differences) < 0,
            }
        )
        start = stop
    return {
        "fixture_count": len(outcomes),
        "current_net_margin_regression": _regression(current_x, outcomes),
        "candidate_net_margin_regression": _regression(candidate_x, outcomes),
        "paired_nll_difference": _paired_bootstrap(nll_differences),
        "folds_improved": sum(row["candidate_improves"] for row in folds),
        "individual_clamp_total_changed_count": total_changed,
        "folds": folds,
    }


def _market_diagnostic(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fixtures = payload["fixtures"]
    raw: list[float] = []
    current: list[float] = []
    candidate: list[float] = []
    market: list[float] = []
    signed_home: dict[str, list[float]] = {name: [] for name in ("X", "Y", "Z")}
    favorite_conditioned: dict[str, list[float]] = {name: [] for name in ("X", "Y", "Z")}
    for fixture in fixtures:
        tracks = fixture["tracks"]
        line = float(tracks["Y"]["ASIAN_HANDICAP"]["market_line"])
        y_delta = float(tracks["Y"]["lambda_home"]) - float(tracks["Y"]["lambda_away"])
        z_delta = float(tracks["Z"]["lambda_home"]) - float(tracks["Z"]["lambda_away"])
        raw.append(y_delta - 0.30)
        current.append(y_delta)
        candidate.append(z_delta)
        market.append(-line)
        for name in ("X", "Y", "Z"):
            gap = float(tracks[name]["ASIAN_HANDICAP"]["fair_minus_market_line"])
            signed_home[name].append(gap)
            if line != 0:
                favorite_conditioned[name].append(gap if line < 0 else -gap)
    return {
        "fixture_count": len(fixtures),
        "nonzero_market_line_count": sum(value != 0 for value in market),
        "means": {
            "raw_delta": round(mean(raw), 6),
            "current_model_delta": round(mean(current), 6),
            "candidate_model_delta": round(mean(candidate), 6),
            "market_implied_delta": round(mean(market), 6),
        },
        "market_delta_on_raw_delta": _regression(raw, market),
        "market_delta_on_current_model_delta": _regression(current, market),
        "market_delta_on_candidate_model_delta": _regression(candidate, market),
        "signed_home_fair_minus_market_mean": {
            name: round(mean(values), 6) for name, values in signed_home.items()
        },
        "favorite_conditioned_fair_minus_market_mean": {
            name: round(mean(values), 6) for name, values in favorite_conditioned.items()
        },
        "interpretation": (
            "Signed home-perspective means describe aggregate alignment. Favorite-conditioned "
            "means select orientation using the market itself and are diagnostic only, not gates."
        ),
    }


def build(
    home_away_path: Path,
    xg_path: Path,
    market_path: Path,
    protocol_path: Path,
) -> dict[str, Any]:
    rows = load_rows(home_away_path, xg_path)
    rolling = _rolling_origin(rows)
    full_outcomes = [row["goals_home"] - row["goals_away"] for row in rows]
    full = {
        str(scale): {
            "scale": scale,
            "mean_nll": round(mean(_poisson_nll(row, scale) for row in rows), 9),
            "net_margin_regression": _regression(
                [_lambda_difference(row, scale) for row in rows], full_outcomes
            ),
        }
        for scale in (CURRENT_SCALE, CANDIDATE_SCALE, LEGACY_UNREPRODUCED_SCALE)
    }
    current_regression = rolling["current_net_margin_regression"]
    candidate_regression = rolling["candidate_net_margin_regression"]
    checks = {
        "paired_oof_nll_mean_lower": rolling["paired_nll_difference"]["mean"] < 0,
        "paired_oof_nll_upper_95_le_zero": rolling["paired_nll_difference"]["upper_95"] <= 0,
        "candidate_slope_closer_to_one": abs(candidate_regression["slope"] - 1)
        < abs(current_regression["slope"] - 1),
        "candidate_abs_intercept_le_0_10": abs(candidate_regression["intercept"]) <= 0.10,
        "at_least_7_of_10_folds_improve": rolling["folds_improved"] >= 7,
        "oof_fixture_count_7159": rolling["fixture_count"] == 7159,
    }
    return {
        "schema": "w2.v1.strict_pit_outcome_correction.v1",
        "sources": {
            "protocol_sha256": _sha256(protocol_path),
            "home_away_sha256": _sha256(home_away_path),
            "xg_sha256": _sha256(xg_path),
            "market_audit_sha256": _sha256(market_path),
        },
        "strict_pit_full_development": full,
        "rolling_origin_oof": rolling,
        "market_diagnostic_only": _market_diagnostic(market_path),
        "binding_local_implementation_checks": checks,
        "all_checks_pass": all(checks.values()),
        "legacy_1_848_claim": {
            "status": "NOT_REPRODUCIBLE_FROM_COMMITTED_EVIDENCE",
            "provenance": (
                "user-supplied reviewer text; no producing script or immutable row artifact"
            ),
            "strict_pit_effect_if_used_as_scale": full[str(LEGACY_UNREPRODUCED_SCALE)],
        },
        "safety": {
            "provider_calls": 0,
            "production_reads": 0,
            "production_writes": 0,
            "ledger_writes": 0,
            "result_records_loaded_from_market_artifact": 0,
            "v2_factors": 0,
        },
    }


def write_report(payload: dict[str, Any], path: Path) -> None:
    oof = payload["rolling_origin_oof"]
    market = payload["market_diagnostic_only"]
    lines = [
        "# V1 严格 PIT 赛果纠偏复核",
        "",
        f"状态：`{'PASS_LOCAL_IMPLEMENTATION' if payload['all_checks_pass'] else 'FAIL_STOP'}`。",
        "",
        "本报告只支持本地候选实现，不构成生产认证、ledger 授权或部署许可。",
        "",
        "## OOF 主结果",
        "",
        f"- OOF fixtures: `{oof['fixture_count']}`",
        f"- 现役净胜球 slope/intercept: `{oof['current_net_margin_regression']}`",
        f"- 候选净胜球 slope/intercept: `{oof['candidate_net_margin_regression']}`",
        f"- paired NLL candidate-current: `{oof['paired_nll_difference']}`",
        f"- 改善 folds: `{oof['folds_improved']}/10`",
        "- individual clamp 改变总进球的 OOF fixtures: "
        f"`{oof['individual_clamp_total_changed_count']}`",
        "",
        "## 冻结检查",
        "",
        "```json",
        json.dumps(payload["binding_local_implementation_checks"], indent=2, sort_keys=True),
        "```",
        "",
        "## 市场条件选择偏差",
        "",
        f"- delta 均值: `{market['means']}`",
        f"- market delta ~ raw delta: `{market['market_delta_on_raw_delta']}`",
        f"- market delta ~ candidate delta: `{market['market_delta_on_candidate_model_delta']}`",
        f"- signed HOME fair-minus-market: `{market['signed_home_fair_minus_market_mean']}`",
        f"- favorite-conditioned: `{market['favorite_conditioned_fair_minus_market_mean']}`",
        "",
        "favorite-conditioned 数字使用市场自身决定选边，只作诊断；"
        "不得作为迫使模型复制盘口的上线门。",
        "",
        "## 1.848 更正",
        "",
        "`1.848 [1.758, 1.939]` 没有可执行脚本或不可变逐行 artifact，无法从仓库证据复现。",
        "严格 PIT 现役 scale=1.0 的开发集 slope 以本 artifact 为准；"
        "不得继续引用 1.848 为已证事实。",
        "",
        "121 注已结算候选仅用于解释冻结概率、赔率、EV 选择与输赢，不进入这里的拟合或验收。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home-away", type=Path, required=True)
    parser.add_argument("--xg", type=Path, required=True)
    parser.add_argument("--market-audit", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    args = parser.parse_args()
    payload = build(args.home_away, args.xg, args.market_audit, args.protocol)
    args.output_json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_report(payload, args.output_report)
    print(json.dumps({"all_checks_pass": payload["all_checks_pass"]}, indent=2))


if __name__ == "__main__":
    main()
