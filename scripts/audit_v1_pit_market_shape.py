#!/usr/bin/env python3
"""Compare strict-PIT X/Y/Z V1 tracks against frozen pre-match quotes."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from statistics import mean, median
from typing import Any

from scripts.audit_v1_market_shape import (
    _distribution_detail,
    _score_matrix,
    fair_line_at_even_odds,
)

from w2.markets.devig import DevigMethod, devig

EXPECTED_FROZEN_MARKET_SHA256 = (
    "47ede4e8c1e40fbf4217d2adcd713141f0cb410de0f62430ffefdb68b25b2698"
)
EXPECTED_TRACKS = {"X", "Y", "Z"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summary(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "mean": round(mean(values), 6) if values else None,
        "median": round(median(values), 6) if values else None,
        "min": round(min(values), 6) if values else None,
        "max": round(max(values), 6) if values else None,
    }


def _frozen_quote(track: dict[str, Any], market: str) -> dict[str, Any]:
    detail = track[market]
    sides = ("HOME", "AWAY") if market == "ASIAN_HANDICAP" else ("OVER", "UNDER")
    quote_pair = detail["quote_pair"]
    return {
        "market_line": detail["market_line"],
        "captured_at": detail["captured_at"],
        "selected_bookmakers": detail["selected_bookmakers"],
        "quote_pair": {side: quote_pair[side] for side in sides},
    }


def _assert_frozen_market_is_model_independent(fixture: dict[str, Any]) -> None:
    for market in ("ASIAN_HANDICAP", "TOTALS"):
        if _frozen_quote(fixture["tracks"]["X"], market) != _frozen_quote(
            fixture["tracks"]["Y"], market
        ):
            raise AssertionError(f"{fixture['fixture_id']} {market} X/Y quote mismatch")


def _market_detail(
    matrix: dict[tuple[int, int], Decimal], market: str, frozen: dict[str, Any]
) -> dict[str, Any]:
    sides = ("HOME", "AWAY") if market == "ASIAN_HANDICAP" else ("OVER", "UNDER")
    market_line = Decimal(str(frozen["market_line"]))
    lines = (
        {"HOME": market_line, "AWAY": -market_line}
        if market == "ASIAN_HANDICAP"
        else {side: market_line for side in sides}
    )
    prices = {
        side: Decimal(str(frozen["quote_pair"][side]["decimal_odds"])) for side in sides
    }
    probabilities = devig(prices, DevigMethod.PROPORTIONAL).probabilities
    if abs(sum(probabilities.values()) - 1) > 1e-9:
        raise AssertionError("proportional devig probabilities do not sum to one")
    return {
        **frozen,
        "devig_method": DevigMethod.PROPORTIONAL.value,
        "sides": [
            _distribution_detail(
                matrix,
                market=market,
                side=side,
                line=lines[side],
                price=prices[side],
                market_probability=probabilities[side],
            )
            for side in sides
        ],
    }


def _track_detail(track: dict[str, Any], frozen_fixture: dict[str, Any]) -> dict[str, Any]:
    matrix = _score_matrix(track)
    home = Decimal(str(track["lambda_home"]))
    away = Decimal(str(track["lambda_away"]))
    output: dict[str, Any] = {
        "lambda_home": float(home),
        "lambda_away": float(away),
        "lambda_total": float(home + away),
    }
    for market, anchor in (
        ("ASIAN_HANDICAP", -(home - away)),
        ("TOTALS", home + away),
    ):
        frozen = _frozen_quote(frozen_fixture["tracks"]["Y"], market)
        detail = _market_detail(matrix, market, frozen)
        fair_line, residual = fair_line_at_even_odds(
            matrix, market=market, anchor=anchor
        )
        detail.update(
            {
                "model_fair_line_at_2_00": float(fair_line),
                "fair_line_residual_ev": round(float(residual), 6),
                "fair_minus_market_line": round(
                    float(fair_line - Decimal(str(frozen["market_line"]))), 6
                ),
            }
        )
        output[market] = detail
    return output


def _side(detail: dict[str, Any], side: str) -> dict[str, Any]:
    return next(row for row in detail["sides"] if row["side"] == side)


def _cohort(fixtures: list[dict[str, Any]], ids: set[str]) -> dict[str, Any]:
    rows = [row for row in fixtures if row["fixture_id"] in ids]
    output: dict[str, Any] = {"fixture_count": len(rows), "tracks": {}}
    for track_name in sorted(EXPECTED_TRACKS):
        tracks = [row["tracks"][track_name] for row in rows]
        favorite_shortfalls: list[float] = []
        favorite_edges: list[float] = []
        underdog_edges: list[float] = []
        home_favorite_shortfalls: list[float] = []
        away_favorite_shortfalls: list[float] = []
        totals_differences: list[float] = []
        for track in tracks:
            ah = track["ASIAN_HANDICAP"]
            line = float(ah["market_line"])
            if line == 0:
                continue
            home_favorite = line < 0
            shortfall = ah["fair_minus_market_line"] * (1 if home_favorite else -1)
            favorite = "HOME" if home_favorite else "AWAY"
            underdog = "AWAY" if home_favorite else "HOME"
            favorite_shortfalls.append(shortfall)
            favorite_edges.append(_side(ah, favorite)["cashflow_price_edge"])
            underdog_edges.append(_side(ah, underdog)["cashflow_price_edge"])
            (home_favorite_shortfalls if home_favorite else away_favorite_shortfalls).append(
                shortfall
            )
            totals_differences.append(track["TOTALS"]["fair_minus_market_line"])
        output["tracks"][track_name] = {
            "AH": {
                "favorite_strength_shortfall": _summary(favorite_shortfalls),
                "favorite_cashflow_price_edge": _summary(favorite_edges),
                "underdog_cashflow_price_edge": _summary(underdog_edges),
                "underdog_edge_gt_0_05_count": sum(edge > 0.05 for edge in underdog_edges),
                "underdog_edge_gt_0_05_fraction": round(
                    sum(edge > 0.05 for edge in underdog_edges) / len(underdog_edges), 6
                )
                if underdog_edges
                else None,
                "home_favorite_shortfall": _summary(home_favorite_shortfalls),
                "away_favorite_shortfall": _summary(away_favorite_shortfalls),
            },
            "TOTALS": {"fair_minus_market": _summary(totals_differences)},
        }
    return output


def _gates(all_cohort: dict[str, Any]) -> dict[str, Any]:
    y = all_cohort["tracks"]["Y"]
    z = all_cohort["tracks"]["Z"]
    z_ah = z["AH"]
    y_ah = y["AH"]
    values = {
        "a_underdog_edge_mean": z_ah["underdog_cashflow_price_edge"]["mean"],
        "b_underdog_edge_gt_0_05_fraction": z_ah["underdog_edge_gt_0_05_fraction"],
        "c_abs_favorite_shortfall_mean": abs(
            z_ah["favorite_strength_shortfall"]["mean"]
        ),
        "d_favorite_shortfall_mean": z_ah["favorite_strength_shortfall"]["mean"],
        "d_favorite_edge_mean": z_ah["favorite_cashflow_price_edge"]["mean"],
        "e_home_favorite_abs_worsening": abs(
            z_ah["home_favorite_shortfall"]["mean"]
        )
        - abs(y_ah["home_favorite_shortfall"]["mean"]),
        "e_away_favorite_abs_worsening": abs(
            z_ah["away_favorite_shortfall"]["mean"]
        )
        - abs(y_ah["away_favorite_shortfall"]["mean"]),
        "f_totals_mean_change": abs(
            z["TOTALS"]["fair_minus_market"]["mean"]
            - y["TOTALS"]["fair_minus_market"]["mean"]
        ),
    }
    checks = {
        "a_underdog_edge_mean_le_0_05": values["a_underdog_edge_mean"] <= 0.05,
        "b_underdog_fraction_le_0_35": values[
            "b_underdog_edge_gt_0_05_fraction"
        ]
        <= 0.35,
        "c_abs_favorite_shortfall_mean_le_0_25": values[
            "c_abs_favorite_shortfall_mean"
        ]
        <= 0.25,
        "d_no_shortfall_overshoot_le_minus_0_25": values[
            "d_favorite_shortfall_mean"
        ]
        > -0.25,
        "d_favorite_edge_mean_le_0_05": values["d_favorite_edge_mean"] <= 0.05,
        "e_home_favorite_worsening_le_0_10": values[
            "e_home_favorite_abs_worsening"
        ]
        <= 0.10,
        "e_away_favorite_worsening_le_0_10": values[
            "e_away_favorite_abs_worsening"
        ]
        <= 0.10,
        "f_totals_mean_change_le_0_02": values["f_totals_mean_change"] <= 0.02,
    }
    return {"values": values, "checks": checks, "all_pass": all(checks.values())}


def build(a2_path: Path, frozen_market_path: Path) -> dict[str, Any]:
    if _sha256(frozen_market_path) != EXPECTED_FROZEN_MARKET_SHA256:
        raise AssertionError("frozen market audit SHA-256 changed")
    a2 = json.loads(a2_path.read_text(encoding="utf-8"))
    frozen_market = json.loads(frozen_market_path.read_text(encoding="utf-8"))
    frozen_by_id = {str(row["fixture_id"]): row for row in frozen_market["fixtures"]}
    tracks: dict[str, dict[str, dict[str, Any]]] = {}
    for row in a2["tracks"]:
        tracks.setdefault(str(row["fixture_id"]), {})[str(row["track"])] = row
    if len(tracks) != 259 or any(set(rows) != EXPECTED_TRACKS for rows in tracks.values()):
        raise AssertionError("strict-PIT track count is not 259 fixtures x X/Y/Z")

    fixtures = []
    for fixture_id in sorted(tracks, key=int):
        frozen_fixture = frozen_by_id[fixture_id]
        _assert_frozen_market_is_model_independent(frozen_fixture)
        fixture_tracks = {
            name: _track_detail(track, frozen_fixture) for name, track in tracks[fixture_id].items()
        }
        x = tracks[fixture_id]["X"]
        y = tracks[fixture_id]["Y"]
        x_delta = float(x["lambda_home"]) - float(x["lambda_away"])
        y_delta = float(y["lambda_home"]) - float(y["lambda_away"])
        x_total = float(x["lambda_home"]) + float(x["lambda_away"])
        y_total = float(y["lambda_home"]) + float(y["lambda_away"])
        clamp_affected = abs((y_delta - x_delta) - 0.18) > 1e-9 or abs(
            y_total - x_total
        ) > 1e-9
        fixtures.append(
            {
                "fixture_id": fixture_id,
                "input_path": tracks[fixture_id]["Y"]["input_path"],
                "clamp_affected": clamp_affected,
                "tracks": fixture_tracks,
            }
        )

    all_ids = {row["fixture_id"] for row in fixtures}
    snapshot_ids = {row["fixture_id"] for row in fixtures if row["input_path"] == "snapshot"}
    rebuild_ids = all_ids - snapshot_ids
    clamp_ids = {row["fixture_id"] for row in fixtures if row["clamp_affected"]}
    if (len(snapshot_ids), len(rebuild_ids)) != (178, 81):
        raise AssertionError("strict-PIT split is not 178/81")
    cohorts = {
        "all_259": _cohort(fixtures, all_ids),
        "snapshot_178": _cohort(fixtures, snapshot_ids),
        "rebuild_81": _cohort(fixtures, rebuild_ids),
        f"clamp_affected_{len(clamp_ids)}": _cohort(fixtures, clamp_ids),
        f"excluding_clamp_{len(all_ids - clamp_ids)}": _cohort(
            fixtures, all_ids - clamp_ids
        ),
    }
    nonzero = [
        side["probability_gap"]
        for row in fixtures
        for track in row["tracks"].values()
        for market in ("ASIAN_HANDICAP", "TOTALS")
        for side in track[market]["sides"]
    ]
    if not nonzero or not any(value != 0 for value in nonzero):
        raise AssertionError("model/market comparison output is empty or all zero")
    return {
        "schema": "w2.v1_recalibration.strict_pit_market_shape.v1",
        "mode": "FROZEN_PREMATCH_QUOTES_STRICT_PIT_MODELS_NO_RESULTS",
        "sources": {
            "a2_pit_sha256": _sha256(a2_path),
            "frozen_market_audit_sha256": _sha256(frozen_market_path),
            "frozen_quote_fields_only": True,
            "discarded_from_old_audit": "all model lambdas, probabilities, edges and fair lines",
        },
        "method": {
            "devig": "PROPORTIONAL",
            "fair_line": "quarter line minimizing absolute five-state EV at decimal odds 2.00",
            "result_fields_loaded": False,
            "uncertainty_sigma": 0.0,
        },
        "assertions": {
            "fixture_count": len(fixtures),
            "snapshot_count": len(snapshot_ids),
            "rebuild_count": len(rebuild_ids),
            "track_count": sum(len(rows) for rows in tracks.values()),
            "clamp_affected_count": len(clamp_ids),
            "all_model_market_gaps_nonempty": bool(nonzero),
            "at_least_one_model_market_gap_nonzero": any(value != 0 for value in nonzero),
        },
        "cohorts": cohorts,
        "development_shipping_gates": _gates(cohorts["all_259"]),
        "fixtures": fixtures,
        "safety": {
            "provider_calls": 0,
            "production_reads": 0,
            "production_writes": 0,
            "result_records_loaded": 0,
            "ledger_writes": 0,
        },
    }


def write_report(payload: dict[str, Any], path: Path) -> None:
    def fmt(value: float | None) -> str:
        return f"{value:.6f}" if value is not None else "-"

    lines = [
        "# V1 严格 PIT 斜率候选市场复核",
        "",
        "> 结论边界：259 场均为开发数据；本报告不能证明生产有效性或 EV 已完全修复。",
        "",
        f"- A2 strict-PIT SHA-256: `{payload['sources']['a2_pit_sha256']}`",
        f"- frozen market audit SHA-256: `{payload['sources']['frozen_market_audit_sha256']}`",
        "- 只复用旧审计冻结的盘口、赔率、机构和 captured_at；旧模型输出全部丢弃。",
        "- 去水实际实现：`PROPORTIONAL`。",
        "- X=`0.12/1.0`，Y=`0.30/1.0`，Z=`0.30/1.102038`。",
        "",
        "## 强制计数",
        "",
        "```json",
        json.dumps(payload["assertions"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## 分组结果",
        "",
        "| cohort | track | AH强队缺口mean | 弱队edge mean | 弱队edge>5% | "
        "强队edge mean | TOTALS差mean |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for cohort_name, cohort in payload["cohorts"].items():
        for track_name, track in cohort["tracks"].items():
            ah = track["AH"]
            lines.append(
                f"| {cohort_name} ({cohort['fixture_count']}) | {track_name} | "
                f"{fmt(ah['favorite_strength_shortfall']['mean'])} | "
                f"{fmt(ah['underdog_cashflow_price_edge']['mean'])} | "
                f"{ah['underdog_edge_gt_0_05_count']}/"
                f"{ah['underdog_cashflow_price_edge']['count']} "
                f"({fmt(ah['underdog_edge_gt_0_05_fraction'])}) | "
                f"{fmt(ah['favorite_cashflow_price_edge']['mean'])} | "
                f"{fmt(track['TOTALS']['fair_minus_market']['mean'])} |"
            )
    gates = payload["development_shipping_gates"]
    lines.extend(
        [
            "",
            "## 六项开发上线门",
            "",
            "```json",
            json.dumps(gates, ensure_ascii=False, indent=2),
            "```",
            "",
            (
                "结论：`PASS`，可进入最小代码实现。"
                if gates["all_pass"]
                else "结论：`FAIL`，不得实现、授权或部署该候选。"
            ),
            "",
            "## 独立复核",
            "",
            "```bash",
            "check_dir=$(mktemp -d /private/tmp/v1-pit-market-shape.XXXXXX)",
            "PYTHONPATH=src:. .venv/bin/python scripts/audit_v1_pit_market_shape.py \\",
            "  --a2-pit docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/"
            "A2_PIT_SIMULATION_TRACKS_REDO.json \\",
            "  --frozen-market-audit docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/"
            "MARKET_SHAPE_AUDIT.json \\",
            '  --output-json "$check_dir/audit.json" --output-report "$check_dir/audit.md"',
            "cmp docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/"
            "PIT_MARKET_SHAPE_XYZ.json \"$check_dir/audit.json\"",
            "cmp docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/"
            "PIT_MARKET_SHAPE_XYZ.md \"$check_dir/audit.md\"",
            "```",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a2-pit", type=Path, required=True)
    parser.add_argument("--frozen-market-audit", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    args = parser.parse_args()
    payload = build(args.a2_pit, args.frozen_market_audit)
    args.output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_report(payload, args.output_report)
    print(json.dumps(payload["development_shipping_gates"], sort_keys=True))


if __name__ == "__main__":
    main()
