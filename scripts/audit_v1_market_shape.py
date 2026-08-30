#!/usr/bin/env python3
"""Audit frozen V1 model/market shape without loading match results."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from statistics import mean, median
from typing import Any

from w2.domain.five_state_pricing import cashflow_price_edge, expected_value, fair_decimal_odds
from w2.markets.asian_handicap_mainline import (
    CANONICAL_AH_MAINLINE_POLICY,
    select_canonical_ah_mainline,
)
from w2.markets.devig import DevigMethod, devig
from w2.markets.settlement_probability import effective_settlement_probability
from w2.markets.totals_mainline import (
    CANONICAL_TOTALS_MAINLINE_POLICY,
    select_canonical_totals_mainline,
)
from w2.markets.value_engine import settlement_distribution_ah, settlement_distribution_totals

EXPECTED_FIXTURES = 283
EXPECTED_SNAPSHOT = 178
EXPECTED_REBUILD = 105
EXPECTED_BOOKMAKERS = 14
EXPECTED_MARKET_ROWS = 118_015
EXPECTED_MARKET_SHA256 = "30a40da45636c3bd6548e0627e45d5903f9b7622184ba3715cc556fb802f3144"
EXPECTED_HOME_ADVANTAGE = {"X": Decimal("0.12"), "Y": Decimal("0.30")}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a1", type=Path, required=True)
    parser.add_argument("--a2", type=Path, required=True)
    parser.add_argument("--market-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_time(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _boolean(value: object) -> bool:
    return str(value).strip().lower() in {"1", "t", "true", "yes"}


def _score_matrix(track: dict[str, Any]) -> dict[tuple[int, int], Decimal]:
    # These are frozen pre-match model outcomes, never observed match scores.
    return {
        (int(row["home_goals"]), int(row["away_goals"])): Decimal(str(row["probability"]))
        for row in track["score_matrix_summary"]["distribution"]
    }


def _quarter_grid(start: Decimal, end: Decimal) -> list[Decimal]:
    count = int((end - start) * 4)
    return [start + Decimal(index) / 4 for index in range(count + 1)]


def fair_line_at_even_odds(
    score_matrix: dict[tuple[int, int], Decimal],
    *,
    market: str,
    anchor: Decimal,
) -> tuple[Decimal, Decimal]:
    """Return the quarter line whose five-state EV at 2.00 is nearest zero."""
    if market == "ASIAN_HANDICAP":
        lines = _quarter_grid(Decimal("-6"), Decimal("6"))
        distribution: Callable[..., Any] = settlement_distribution_ah
        selection = "HOME"
    elif market == "TOTALS":
        lines = _quarter_grid(Decimal("0"), Decimal("12"))
        distribution = settlement_distribution_totals
        selection = "OVER"
    else:
        raise ValueError(f"unsupported market: {market}")
    candidates = [
        (
            abs(
                ev := expected_value(
                    Decimal("2"), distribution(score_matrix, selection=selection, line=line)
                )
            ),
            abs(line - anchor),
            line,
            ev,
        )
        for line in lines
    ]
    _, _, line, ev = min(candidates)
    return line, ev


def clamp_fixture_ids(tracks: list[dict[str, Any]]) -> set[str]:
    by_fixture: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in tracks:
        by_fixture[str(row["fixture_id"])][str(row["track"])] = row
    clamped = set()
    for fixture_id, pair in by_fixture.items():
        x, y = pair["X"], pair["Y"]
        x_difference = Decimal(str(x["lambda_home"])) - Decimal(str(x["lambda_away"]))
        y_difference = Decimal(str(y["lambda_home"])) - Decimal(str(y["lambda_away"]))
        x_total = Decimal(str(x["lambda_home"])) + Decimal(str(x["lambda_away"]))
        y_total = Decimal(str(y["lambda_home"])) + Decimal(str(y["lambda_away"]))
        if y_difference - x_difference != Decimal("0.18") or y_total != x_total:
            clamped.add(fixture_id)
    return clamped


def _distribution_detail(
    matrix: dict[tuple[int, int], Decimal],
    *,
    market: str,
    side: str,
    line: Decimal,
    price: Decimal,
    market_probability: float,
) -> dict[str, Any]:
    distribution = (
        settlement_distribution_ah(matrix, selection=side, line=line)
        if market == "ASIAN_HANDICAP"
        else settlement_distribution_totals(matrix, selection=side, line=line)
    )
    values = distribution.as_dict()
    five_state = {
        "WIN": float(values["full_win_probability"]),
        "HALF_WIN": float(values["half_win_probability"]),
        "PUSH": float(values["push_probability"]),
        "HALF_LOSS": float(values["half_loss_probability"]),
        "LOSS": float(values["full_loss_probability"]),
    }
    model_probability = effective_settlement_probability(five_state)
    if model_probability is None:
        raise AssertionError("model settlement distribution is incomplete")
    fair_odds = fair_decimal_odds(distribution)
    return {
        "side": side,
        "line": float(line),
        "price": float(price),
        "market_probability": round(market_probability, 6),
        "model_probability": round(model_probability, 6),
        "probability_gap": round(model_probability - market_probability, 6),
        "model_fair_odds": float(fair_odds),
        "expected_value": round(float(expected_value(price, distribution)), 6),
        "cashflow_price_edge": round(float(cashflow_price_edge(price, fair_odds)), 6),
        "settlement_distribution": five_state,
    }


def _quote_pair(selected: Any, sides: tuple[str, str]) -> dict[str, Any]:
    rows = selected.authoritative_quote_rows or {}
    result = {}
    for side in sides:
        row = rows[side.lower()]
        result[side] = {
            "observation_id": row["observation_id"],
            "bookmaker_id": row["bookmaker_id"],
            "bookmaker_name": row["bookmaker_name"],
            "line": row["line"],
            "decimal_odds": float(row["decimal_odds"]),
            "captured_at": row["captured_at"],
            "raw_payload_sha256": row["raw_payload_sha256"],
        }
    return result


def _market_detail(
    matrix: dict[tuple[int, int], Decimal],
    *,
    market: str,
    selected: Any,
) -> dict[str, Any]:
    if selected.status != "READY" or selected.line is None:
        raise AssertionError(f"{market} mainline is not READY: {selected.status}")
    if market == "ASIAN_HANDICAP":
        sides = ("HOME", "AWAY")
        lines = {"HOME": selected.line, "AWAY": -selected.line}
        prices = {"HOME": selected.home_price, "AWAY": selected.away_price}
        policy = CANONICAL_AH_MAINLINE_POLICY
    else:
        sides = ("OVER", "UNDER")
        lines = {side: selected.line for side in sides}
        prices = {"OVER": selected.over_price, "UNDER": selected.under_price}
        policy = CANONICAL_TOTALS_MAINLINE_POLICY
    decimals = {side: Decimal(str(prices[side])) for side in sides}
    probabilities = devig(decimals, DevigMethod.PROPORTIONAL).probabilities
    if abs(sum(probabilities.values()) - 1) > 1e-9:
        raise AssertionError("proportional devig probabilities do not sum to one")
    return {
        "status": selected.status,
        "selection_policy": policy,
        "devig_method": DevigMethod.PROPORTIONAL.value,
        "market_line": float(selected.line),
        "captured_at": selected.captured_at.isoformat().replace("+00:00", "Z"),
        "selected_bookmakers": selected.selected_bookmakers,
        "quote_pair": _quote_pair(selected, sides),
        "sides": [
            _distribution_detail(
                matrix,
                market=market,
                side=side,
                line=Decimal(str(lines[side])),
                price=decimals[side],
                market_probability=probabilities[side],
            )
            for side in sides
        ],
    }


def _number_summary(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "mean": round(mean(values), 6) if values else None,
        "median": round(median(values), 6) if values else None,
        "min": round(min(values), 6) if values else None,
        "max": round(max(values), 6) if values else None,
    }


def _side_summary(rows: list[dict[str, Any]], side: str) -> dict[str, Any]:
    values = [item for row in rows for item in row["sides"] if item["side"] == side]
    gaps = [item["probability_gap"] for item in values]
    return {
        "probability_gap": _number_summary(gaps),
        "positive_gap_count": sum(value > 0 for value in gaps),
        "gap_gt_5pp_count": sum(value > 0.05 for value in gaps),
        "gap_gt_10pp_count": sum(value > 0.10 for value in gaps),
        "gap_gt_20pp_count": sum(value > 0.20 for value in gaps),
        "mean_cashflow_price_edge": round(mean(item["cashflow_price_edge"] for item in values), 6),
        "positive_ev_count": sum(item["expected_value"] > 0 for item in values),
    }


def _ah_role_summary(rows: list[dict[str, Any]], role: str) -> dict[str, Any]:
    values = [
        side
        for row in rows
        for side in row["sides"]
        if row["market_line"] != 0
        and side["side"]
        == (
            ("HOME" if row["market_line"] < 0 else "AWAY")
            if role == "FAVORITE"
            else ("AWAY" if row["market_line"] < 0 else "HOME")
        )
    ]
    gaps = [item["probability_gap"] for item in values]
    edges = [item["cashflow_price_edge"] for item in values]
    return {
        "fixture_count": len(values),
        "probability_gap": _number_summary(gaps),
        "gap_gt_5pp_count": sum(value > 0.05 for value in gaps),
        "gap_gt_10pp_count": sum(value > 0.10 for value in gaps),
        "gap_gt_20pp_count": sum(value > 0.20 for value in gaps),
        "cashflow_price_edge": _number_summary(edges),
        "price_edge_gt_5pct_count": sum(value > 0.05 for value in edges),
        "price_edge_gt_10pct_count": sum(value > 0.10 for value in edges),
        "price_edge_gt_20pct_count": sum(value > 0.20 for value in edges),
        "positive_ev_count": sum(item["expected_value"] > 0 for item in values),
    }


def _ah_orientation_summary(rows: list[dict[str, Any]], orientation: str) -> dict[str, Any]:
    home_favorite = orientation == "HOME_FAVORITE"
    scoped = [
        row for row in rows if (row["market_line"] < 0) == home_favorite and row["market_line"] != 0
    ]
    favorite = "HOME" if home_favorite else "AWAY"
    underdog = "AWAY" if home_favorite else "HOME"
    return {
        "fixture_count": len(scoped),
        "favorite_strength_shortfall": _number_summary(
            [
                row["fair_minus_market_line"] if home_favorite else -row["fair_minus_market_line"]
                for row in scoped
            ]
        ),
        "FAVORITE": _side_summary(scoped, favorite),
        "UNDERDOG": _side_summary(scoped, underdog),
    }


def _cohort_summary(fixtures: list[dict[str, Any]], fixture_ids: set[str]) -> dict[str, Any]:
    scoped = [row for row in fixtures if row["fixture_id"] in fixture_ids]
    result: dict[str, Any] = {"fixture_count": len(scoped), "tracks": {}}
    for track_name in ("X", "Y"):
        track_rows = [row["tracks"][track_name] for row in scoped]
        ah = [row["ASIAN_HANDICAP"] for row in track_rows]
        totals = [row["TOTALS"] for row in track_rows]
        result["tracks"][track_name] = {
            "home_advantage_goals": float(EXPECTED_HOME_ADVANTAGE[track_name]),
            "ASIAN_HANDICAP": {
                "fair_minus_market_home_line": _number_summary(
                    [row["fair_minus_market_line"] for row in ah]
                ),
                "favorite_strength_shortfall": _number_summary(
                    [
                        row["fair_minus_market_line"]
                        if row["market_line"] < 0
                        else -row["fair_minus_market_line"]
                        for row in ah
                        if row["market_line"] != 0
                    ]
                ),
                "HOME": _side_summary(ah, "HOME"),
                "AWAY": _side_summary(ah, "AWAY"),
                "FAVORITE": _ah_role_summary(ah, "FAVORITE"),
                "UNDERDOG": _ah_role_summary(ah, "UNDERDOG"),
                "HOME_FAVORITE": _ah_orientation_summary(ah, "HOME_FAVORITE"),
                "AWAY_FAVORITE": _ah_orientation_summary(ah, "AWAY_FAVORITE"),
            },
            "TOTALS": {
                "fair_minus_market_total": _number_summary(
                    [row["fair_minus_market_line"] for row in totals]
                ),
                "OVER": _side_summary(totals, "OVER"),
                "UNDER": _side_summary(totals, "UNDER"),
            },
        }
    return result


def _band_summaries(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    ah_bands = {
        "0_to_0.25": lambda line: line <= 0.25,
        "0.5_to_0.75": lambda line: Decimal("0.5") <= line <= Decimal("0.75"),
        "1.0_to_1.25": lambda line: Decimal("1") <= line <= Decimal("1.25"),
        "gte_1.5": lambda line: line >= Decimal("1.5"),
    }
    totals_bands = {
        "lte_2.25": lambda line: line <= Decimal("2.25"),
        "2.5_to_2.75": lambda line: Decimal("2.5") <= line <= Decimal("2.75"),
        "3.0_to_3.25": lambda line: Decimal("3") <= line <= Decimal("3.25"),
        "gte_3.5": lambda line: line >= Decimal("3.5"),
    }
    output: dict[str, Any] = {"ASIAN_HANDICAP": {}, "TOTALS": {}}
    for name, predicate in ah_bands.items():
        ids = {
            row["fixture_id"]
            for row in fixtures
            if predicate(abs(Decimal(str(row["tracks"]["Y"]["ASIAN_HANDICAP"]["market_line"]))))
        }
        output["ASIAN_HANDICAP"][name] = _cohort_summary(fixtures, ids)
    for name, predicate in totals_bands.items():
        ids = {
            row["fixture_id"]
            for row in fixtures
            if predicate(Decimal(str(row["tracks"]["Y"]["TOTALS"]["market_line"])))
        }
        output["TOTALS"][name] = _cohort_summary(fixtures, ids)
    return output


def build_audit(a1_path: Path, a2_path: Path, market_path: Path) -> dict[str, Any]:
    a1 = json.loads(a1_path.read_text())
    a2 = json.loads(a2_path.read_text())
    market_sha = _sha256(market_path)
    if market_sha != EXPECTED_MARKET_SHA256 or a1["source_sha256"]["market.csv"] != market_sha:
        raise AssertionError("market.csv SHA-256 does not match frozen A1 evidence")
    if a1["observed"] != a1["assertions"]:
        raise AssertionError("A1 observed counts differ from assertions")

    fixture_meta = {str(row["provider_fixture_id"]): row for row in a1["fixtures"]}
    tracks: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in a2["tracks"]:
        tracks[str(row["fixture_id"])][str(row["track"])] = row
    clamped = clamp_fixture_ids(a2["tracks"])
    observations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    bookmakers = set()
    with market_path.open(newline="") as source:
        reader = csv.DictReader(source)
        for row in reader:
            row["live"] = _boolean(row["live"])
            row["suspended"] = _boolean(row["suspended"])
            fixture_id = str(row["provider_fixture_id"])
            observations[fixture_id].append(row)
            bookmakers.add(str(row["bookmaker_id"]))

    if len(fixture_meta) != EXPECTED_FIXTURES or len(observations) != EXPECTED_FIXTURES:
        raise AssertionError("fixture count is not 283")
    if sum(len(rows) for rows in observations.values()) != EXPECTED_MARKET_ROWS:
        raise AssertionError("market row count is not 118015")
    if len(bookmakers) != EXPECTED_BOOKMAKERS:
        raise AssertionError("bookmaker count is not 14")
    if len(clamped) != 12:
        raise AssertionError(f"expected 12 clamped fixtures, found {len(clamped)}")

    fixture_rows = []
    for fixture_id in sorted(fixture_meta, key=int):
        meta = fixture_meta[fixture_id]
        rows = observations[fixture_id]
        target = max(_parse_time(row["captured_at"]) for row in rows)
        kickoff = _parse_time(meta["kickoff_at"])
        internal_fixture_id = str(rows[0]["fixture_id"])
        ah = select_canonical_ah_mainline(
            rows, fixture_id=internal_fixture_id, target=target, kickoff=kickoff
        )
        totals = select_canonical_totals_mainline(
            rows, fixture_id=internal_fixture_id, target=target, kickoff=kickoff
        )
        track_output = {}
        for track_name in ("X", "Y"):
            track = tracks[fixture_id][track_name]
            if Decimal(str(track["home_advantage_goals"])) != EXPECTED_HOME_ADVANTAGE[track_name]:
                raise AssertionError(f"unexpected home advantage for track {track_name}")
            matrix = _score_matrix(track)
            ah_detail = _market_detail(matrix, market="ASIAN_HANDICAP", selected=ah)
            totals_detail = _market_detail(matrix, market="TOTALS", selected=totals)
            lambda_home = Decimal(str(track["lambda_home"]))
            lambda_away = Decimal(str(track["lambda_away"]))
            fair_ah, fair_ah_ev = fair_line_at_even_odds(
                matrix, market="ASIAN_HANDICAP", anchor=-(lambda_home - lambda_away)
            )
            fair_total, fair_total_ev = fair_line_at_even_odds(
                matrix, market="TOTALS", anchor=lambda_home + lambda_away
            )
            ah_detail.update(
                {
                    "model_fair_home_line_at_2_00": float(fair_ah),
                    "fair_line_residual_ev": round(float(fair_ah_ev), 6),
                    "fair_minus_market_line": round(float(fair_ah - ah.line), 6),
                }
            )
            totals_detail.update(
                {
                    "model_fair_total_at_2_00": float(fair_total),
                    "fair_line_residual_ev": round(float(fair_total_ev), 6),
                    "fair_minus_market_line": round(float(fair_total - totals.line), 6),
                }
            )
            track_output[track_name] = {
                "lambda_home": float(lambda_home),
                "lambda_away": float(lambda_away),
                "ASIAN_HANDICAP": ah_detail,
                "TOTALS": totals_detail,
            }
        if (
            track_output["X"]["ASIAN_HANDICAP"]["market_line"]
            != track_output["Y"]["ASIAN_HANDICAP"]["market_line"]
        ):
            raise AssertionError("X/Y did not use the same AH market line")
        fixture_rows.append(
            {
                "fixture_id": fixture_id,
                "input_path": meta["input_path"],
                "clamp_affected": fixture_id in clamped,
                "bookmaker_depth": meta["bookmaker_depth"],
                "tracks": track_output,
            }
        )

    snapshot_ids = {row["fixture_id"] for row in fixture_rows if row["input_path"] == "snapshot"}
    rebuild_ids = {row["fixture_id"] for row in fixture_rows if row["input_path"] == "rebuild"}
    all_ids = set(fixture_meta)
    if len(snapshot_ids) != EXPECTED_SNAPSHOT or len(rebuild_ids) != EXPECTED_REBUILD:
        raise AssertionError("snapshot/rebuild split is not 178/105")
    ah_gaps = [
        side["probability_gap"]
        for row in fixture_rows
        for track in row["tracks"].values()
        for side in track["ASIAN_HANDICAP"]["sides"]
    ]
    totals_gaps = [
        side["probability_gap"]
        for row in fixture_rows
        for track in row["tracks"].values()
        for side in track["TOTALS"]["sides"]
    ]
    ah_line_gaps = [
        track["ASIAN_HANDICAP"]["fair_minus_market_line"]
        for row in fixture_rows
        for track in row["tracks"].values()
    ]
    totals_line_gaps = [
        track["TOTALS"]["fair_minus_market_line"]
        for row in fixture_rows
        for track in row["tracks"].values()
    ]
    if not ah_gaps or not totals_gaps:
        raise AssertionError("AH/TOTALS comparison output is empty")
    if not any(value != 0 for value in ah_gaps + totals_gaps):
        raise AssertionError("model/market probability gaps are all zero")
    if not any(value != 0 for value in ah_line_gaps):
        raise AssertionError("AH fair/market line gaps are all zero")
    if not any(value != 0 for value in totals_line_gaps):
        raise AssertionError("TOTALS fair/market line gaps are all zero")

    cohorts = {
        "all_283": _cohort_summary(fixture_rows, all_ids),
        "snapshot_178": _cohort_summary(fixture_rows, snapshot_ids),
        "rebuild_105": _cohort_summary(fixture_rows, rebuild_ids),
        "clamp_affected_12": _cohort_summary(fixture_rows, clamped),
        "excluding_clamp_271": _cohort_summary(fixture_rows, all_ids - clamped),
    }
    all_x = cohorts["all_283"]["tracks"]["X"]
    all_y = cohorts["all_283"]["tracks"]["Y"]
    payload = {
        "schema_version": "w2.v1_market_shape_audit.v1",
        "mode": "FROZEN_PREMATCH_ONLY_NO_RESULTS_NO_PROVIDER_NO_DB_WRITE",
        "sources": {
            "a1_sha256": _sha256(a1_path),
            "a2_sha256": _sha256(a2_path),
            "market_csv_sha256": market_sha,
            "T_EXTRACT": a1["T_EXTRACT"],
        },
        "method": {
            "AH_market_selector": CANONICAL_AH_MAINLINE_POLICY,
            "TOTALS_market_selector": CANONICAL_TOTALS_MAINLINE_POLICY,
            "devig": "PROPORTIONAL",
            "model_fair_line": (
                "quarter line minimizing absolute five-state EV at decimal odds 2.00"
            ),
            "probability_scalar": "WIN + 0.5*HALF_WIN + 0.5*PUSH",
            "result_fields_loaded": False,
        },
        "assertions": {
            "fixture_count": len(fixture_rows),
            "snapshot_count": len(snapshot_ids),
            "rebuild_count": len(rebuild_ids),
            "market_rows": sum(len(rows) for rows in observations.values()),
            "bookmakers": len(bookmakers),
            "track_X_count": sum("X" in row for row in tracks.values()),
            "track_Y_count": sum("Y" in row for row in tracks.values()),
            "clamp_affected_count": len(clamped),
            "AH_ready_count": len(fixture_rows),
            "TOTALS_ready_count": len(fixture_rows),
        },
        "findings": {
            "AH_favorite_strength_shortfall_mean_X": all_x["ASIAN_HANDICAP"][
                "favorite_strength_shortfall"
            ]["mean"],
            "AH_favorite_strength_shortfall_mean_Y": all_y["ASIAN_HANDICAP"][
                "favorite_strength_shortfall"
            ]["mean"],
            "AH_underdog_cashflow_price_edge_mean_X": all_x["ASIAN_HANDICAP"]["UNDERDOG"][
                "cashflow_price_edge"
            ]["mean"],
            "AH_underdog_cashflow_price_edge_mean_Y": all_y["ASIAN_HANDICAP"]["UNDERDOG"][
                "cashflow_price_edge"
            ]["mean"],
            "AH_underdog_price_edge_gt_5pct_X": all_x["ASIAN_HANDICAP"]["UNDERDOG"][
                "price_edge_gt_5pct_count"
            ],
            "AH_underdog_price_edge_gt_5pct_Y": all_y["ASIAN_HANDICAP"]["UNDERDOG"][
                "price_edge_gt_5pct_count"
            ],
            "AH_home_favorite_shortfall_mean_X": all_x["ASIAN_HANDICAP"]["HOME_FAVORITE"][
                "favorite_strength_shortfall"
            ]["mean"],
            "AH_home_favorite_shortfall_mean_Y": all_y["ASIAN_HANDICAP"]["HOME_FAVORITE"][
                "favorite_strength_shortfall"
            ]["mean"],
            "AH_away_favorite_shortfall_mean_X": all_x["ASIAN_HANDICAP"]["AWAY_FAVORITE"][
                "favorite_strength_shortfall"
            ]["mean"],
            "AH_away_favorite_shortfall_mean_Y": all_y["ASIAN_HANDICAP"]["AWAY_FAVORITE"][
                "favorite_strength_shortfall"
            ]["mean"],
            "TOTALS_fair_minus_market_mean_X": all_x["TOTALS"]["fair_minus_market_total"]["mean"],
            "TOTALS_fair_minus_market_mean_Y": all_y["TOTALS"]["fair_minus_market_total"]["mean"],
        },
        "cohorts": cohorts,
        "market_line_bands": _band_summaries(fixture_rows),
        "fixtures": fixture_rows,
        "safety": {
            "provider_calls": 0,
            "production_reads": 0,
            "production_writes": 0,
            "result_records_loaded": 0,
            "parameters_changed": 0,
        },
    }
    return payload


def _fmt(summary: dict[str, Any]) -> str:
    return (
        f"{summary['mean']:.4f} / {summary['median']:.4f}" if summary["mean"] is not None else "-"
    )


def write_report(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# V1 赛前 AH / TOTALS 市场形状审计",
        "",
        (
            "> 结论边界：本报告只比较冻结的赛前模型分布与赛前市场，"
            "不读取赛果，不能证明生产有效性或 EV 已完全修复。"
        ),
        "",
        f"- A1 SHA-256: `{payload['sources']['a1_sha256']}`",
        f"- A2 SHA-256: `{payload['sources']['a2_sha256']}`",
        f"- market.csv SHA-256: `{payload['sources']['market_csv_sha256']}`",
        f"- T_EXTRACT: `{payload['sources']['T_EXTRACT']}`",
        "- 实际去水实现：`proportional`；不采用 provenance 中可能出现的 `POWER` 标签。",
        (
            "- 公平盘口：以完整赛前模型分布计算五态现金流，在十进制赔率 "
            "2.00 下选择绝对 EV 最接近 0 的 0.25 盘口。"
        ),
        "",
        "## 强制计数",
        "",
        "```json",
        json.dumps(payload["assertions"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## 主要对比",
        "",
        (
            "| Cohort | Track | AH强队幅度缺口 mean/median | FAVORITE gap mean/median | "
            "UNDERDOG gap mean/median | HOME gap mean/median | AWAY gap mean/median | "
            "Total公平-市场 mean/median | OVER gap mean/median | UNDER gap mean/median |"
        ),
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cohort_name, cohort in payload["cohorts"].items():
        for track_name, track in cohort["tracks"].items():
            ah = track["ASIAN_HANDICAP"]
            totals = track["TOTALS"]
            lines.append(
                f"| {cohort_name} ({cohort['fixture_count']}) | {track_name} | "
                f"{_fmt(ah['favorite_strength_shortfall'])} | "
                f"{_fmt(ah['FAVORITE']['probability_gap'])} | "
                f"{_fmt(ah['UNDERDOG']['probability_gap'])} | "
                f"{_fmt(ah['HOME']['probability_gap'])} | "
                f"{_fmt(ah['AWAY']['probability_gap'])} | "
                f"{_fmt(totals['fair_minus_market_total'])} | "
                f"{_fmt(totals['OVER']['probability_gap'])} | "
                f"{_fmt(totals['UNDER']['probability_gap'])} |"
            )
    lines.extend(
        [
            "",
            "## 冻结证据内结论",
            "",
            (
                "- AH：市场强队相对模型的平均盘口幅度缺口从 "
                f"`{payload['findings']['AH_favorite_strength_shortfall_mean_X']:.3f}` 球变为 "
                f"`{payload['findings']['AH_favorite_strength_shortfall_mean_Y']:.3f}` 球；"
                "0.30 只缩小其中一小部分，未消除全局实力幅度压缩。"
            ),
            (
                "- AH 弱队侧：平均 cashflow price edge 从 "
                f"`{payload['findings']['AH_underdog_cashflow_price_edge_mean_X']:.3f}` 降至 "
                f"`{payload['findings']['AH_underdog_cashflow_price_edge_mean_Y']:.3f}`；"
                "客侧/主侧会随主场项移动，但弱队方向的系统性市场偏离仍明显。"
            ),
            (
                "- 方向分解：主队为强队时幅度缺口从 "
                f"`{payload['findings']['AH_home_favorite_shortfall_mean_X']:.3f}` 降至 "
                f"`{payload['findings']['AH_home_favorite_shortfall_mean_Y']:.3f}`；"
                "客队为强队时反而从 "
                f"`{payload['findings']['AH_away_favorite_shortfall_mean_X']:.3f}` 升至 "
                f"`{payload['findings']['AH_away_favorite_shortfall_mean_Y']:.3f}`。"
                "这符合主场常数只移动截距、不能修复强弱幅度斜率的结构。"
            ),
            (
                "- TOTALS：公平总进球线相对市场的均值从 "
                f"`{payload['findings']['TOTALS_fair_minus_market_mean_X']:.3f}` 变为 "
                f"`{payload['findings']['TOTALS_fair_minus_market_mean_Y']:.3f}`；"
                "符合主场项理论上不改变总 λ 的预期，TOTALS 是否可靠不能由 0.12→0.30 得到证明。"
            ),
            "",
            "## 独立复核命令",
            "",
            "```bash",
            "check_dir=$(mktemp -d /private/tmp/v1-market-shape-review.XXXXXX)",
            "PYTHONPATH=src:. python3 scripts/audit_v1_market_shape.py \\",
            "  --a1 docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/A1_PIT_EVIDENCE_REDO.json \\",
            (
                "  --a2 docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/"
                "A2_SIMULATION_OUTPUTS.json \\"
            ),
            "  --market-csv /private/tmp/v1-a1-recheck.jHaT4e/market.csv \\",
            '  --output-json "$check_dir/audit.json" --output-report "$check_dir/audit.md"',
            (
                "cmp docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/"
                'MARKET_SHAPE_AUDIT.json "$check_dir/audit.json"'
            ),
            (
                "cmp docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/"
                'MARKET_SHAPE_AUDIT.md "$check_dir/audit.md"'
            ),
            "```",
            "",
            "## 解释限制",
            "",
            "- 市场一致性可以定位系统性假 edge 的形状，但市场不是赛果真值，不能替代前向概率校准。",
            "- 283 场参与过 0.30 的参数选择；任何结果都不得用于回头调参或调阈值。",
            (
                "- 98 注 / -10.865 单位与 26 场 / 62 pick 目前仍是待独立复算的"
                "页面观察值，本报告不将其作为根因前提。"
            ),
            (
                "- `APPROVED_VALIDATED` 的既有证据只覆盖 1X2 三侧相对偏差，"
                "不自动覆盖 AH、TOTALS、EV 或 EV-SE。"
            ),
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = _arguments()
    payload = build_audit(args.a1, args.a2, args.market_csv)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    write_report(payload, args.output_report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
