#!/usr/bin/env python3
"""Audit settled candidate picks and their same-line opposite directions.

The script consumes frozen CSV exports only.  It never connects to production,
calls a provider, or changes model/authority state.  Reverse EV-SE is reported
as unavailable when the frozen capture did not persist lambda uncertainty.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.domain.enums import SettlementOutcome
from w2.domain.five_state_pricing import SettlementDistribution
from w2.domain.five_state_pricing import cashflow_price_edge, expected_value, fair_decimal_odds
from w2.markets.devig import DevigMethod, devig
from w2.markets.settlement_probability import effective_settlement_probability
from w2.strategy.calibration import LambdaCalibrationParams, calibrate_lambdas


OUTCOMES = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")


def _d(value: Any) -> Decimal:
    return Decimal(str(value))


def _norm(value: str) -> str:
    return value.upper().replace("_AH", "").replace("_TOTALS", "")


def _distribution(raw: dict[str, Any]) -> SettlementDistribution:
    return SettlementDistribution(
        full_win_probability=_d(raw["WIN"]),
        half_win_probability=_d(raw["HALF_WIN"]),
        push_probability=_d(raw["PUSH"]),
        half_loss_probability=_d(raw["HALF_LOSS"]),
        full_loss_probability=_d(raw["LOSS"]),
    )


def _metrics(distribution: dict[str, Any], odds: Decimal, market_prob: float) -> dict[str, Any]:
    model = _distribution(distribution)
    fair = fair_decimal_odds(model)
    ev = expected_value(odds, model)
    edge = cashflow_price_edge(odds, fair)
    effective = effective_settlement_probability(distribution)
    delta = None if effective is None else float(effective) - market_prob
    return {
        "odds": float(odds),
        "fair_decimal_odds": float(fair),
        "expected_value": float(ev),
        "cashflow_price_edge": float(edge),
        "effective_probability": effective,
        "market_probability": market_prob,
        "delta": delta,
        "economic_gates": {
            "ev_positive": ev > 0,
            "cashflow_edge_ge_005": edge >= Decimal("0.05"),
            "ev_minus_se_positive": None,
        },
    }


def _settlement(market: str, selection: str, line: Decimal, home: int, away: int) -> str:
    if market == "ASIAN_HANDICAP":
        return settle_asian_handicap(home, away, selection, line).value
    return settle_total_goals(home + away, selection, line).value


def _find_ladder(capture: dict[str, Any], market: str, selection: str, line: Decimal) -> tuple[dict[str, Any], Decimal]:
    if market == "ASIAN_HANDICAP":
        canonical_home_line = line if selection == "HOME" else -line
        rows = capture["ah_settlement_distributions"]["ladder"]
        row = next(r for r in rows if abs(float(r["home_line"]) - float(canonical_home_line)) < 1e-8)
        return row, canonical_home_line
    rows = capture["ou_settlement_distributions"]["ladder"]
    row = next(r for r in rows if abs(float(r["line"]) - float(line)) < 1e-8)
    return row, line


def _quote_pair(
    market_rows: list[dict[str, str]],
    *,
    market: str,
    selection: str,
    line: Decimal,
    bookmaker: str,
    target_odds: Decimal,
) -> tuple[Decimal, Decimal, float, str, Decimal]:
    # The evaluation line is side-oriented; observations store the provider's
    # canonical line.  Anchor the pair on the exact selected quote (bookmaker,
    # side, odds), then use that row's line for the opposite quote.
    opposite = {"HOME": "AWAY", "AWAY": "HOME", "OVER": "UNDER", "UNDER": "OVER"}[selection]
    targets = [row for row in market_rows if row["bookmaker_id"] == bookmaker and row["canonical_selection"] == selection and abs(float(row["decimal_odds"]) - float(target_odds)) < 1e-8]
    if not targets:
        raise KeyError("TARGET_QUOTE_MISSING")
    target_row = targets[0]
    canonical_line = _d(target_row["line"])
    relevant = [row for row in market_rows if row["bookmaker_id"] == bookmaker and row["canonical_selection"] in {selection, opposite} and abs(float(row["line"]) - float(canonical_line)) < 1e-8]
    by_side: dict[str, dict[str, str]] = {}
    for row in relevant:
        by_side.setdefault(row["canonical_selection"], row)
    if selection not in by_side or opposite not in by_side:
        raise KeyError("OPPOSITE_QUOTE_MISSING")
    target = _d(by_side[selection]["decimal_odds"])
    reverse = _d(by_side[opposite]["decimal_odds"])
    probabilities = devig({selection: target, opposite: reverse}, DevigMethod.PROPORTIONAL).probabilities
    return target, reverse, probabilities[selection], by_side[opposite]["bookmaker_name"], canonical_line


def analyze(evaluations_path: Path, market_path: Path) -> dict[str, Any]:
    evaluations = list(csv.DictReader(evaluations_path.open(newline="")))
    market_rows = list(csv.DictReader(market_path.open(newline="")))
    by_group: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in market_rows:
        by_group[(row["fixture_id"], row["market"], row["capture_id"])].append(row)

    rows: list[dict[str, Any]] = []
    missing = Counter()
    for raw in evaluations:
        evaluation = json.loads(raw["evaluation_payload"])
        capture = json.loads(raw["model_capture_payload"])
        market = raw["market"]
        selection = _norm(raw["selection"])
        line = _d(evaluation["exact_line"])
        opposite = {"HOME": "AWAY", "AWAY": "HOME", "OVER": "UNDER", "UNDER": "OVER"}[selection]
        try:
            target_odds, reverse_odds, target_market_prob, reverse_bookmaker_name, canonical_line = _quote_pair(
                by_group[(raw["fixture_id"], market, raw["capture_id"])],
                market=market,
                selection=selection,
                line=line,
                bookmaker=str(evaluation["bookmaker_id"]),
                target_odds=_d(evaluation["decimal_odds"]),
            )
            # Evaluation payload persists the uncertainty-mixed target five-state
            # distribution.  The exact opposite side is its WIN/LOSS and
            # HALF_WIN/HALF_LOSS complement (PUSH unchanged), avoiding the
            # lower-precision deterministic ladder in the capture.
            target_dist = dict(evaluation["model_settlement_distribution"])
            reverse_dist = {
                "WIN": target_dist["LOSS"],
                "HALF_WIN": target_dist["HALF_LOSS"],
                "PUSH": target_dist["PUSH"],
                "HALF_LOSS": target_dist["HALF_WIN"],
                "LOSS": target_dist["WIN"],
            }
        except (KeyError, StopIteration) as exc:
            missing[str(exc)] += 1
            continue
        quote_rows = by_group[(raw["fixture_id"], market, raw["capture_id"])]
        opposite_row = next(r for r in quote_rows if r["bookmaker_name"] == reverse_bookmaker_name and r["canonical_selection"] == opposite and abs(float(r["line"]) - float(canonical_line)) < 1e-8)
        opposite_market_prob = devig({selection: target_odds, opposite: reverse_odds}, DevigMethod.PROPORTIONAL).probabilities[opposite]
        target_metrics = _metrics(target_dist, target_odds, target_market_prob)
        reverse_metrics = _metrics(reverse_dist, reverse_odds, opposite_market_prob)
        all_opposite = [
            row for row in by_group[(raw["fixture_id"], market, raw["capture_id"])]
            if row["canonical_selection"] == opposite
            and abs(float(row["line"]) - float(canonical_line)) < 1e-8
        ]
        best_reverse = None
        if all_opposite:
            scored = []
            for quote in all_opposite:
                metrics = _metrics(
                    reverse_dist,
                    _d(quote["decimal_odds"]),
                    devig({selection: target_odds, opposite: _d(quote["decimal_odds"])}, DevigMethod.PROPORTIONAL).probabilities[opposite],
                )
                scored.append((metrics["expected_value"], metrics["cashflow_price_edge"], quote["bookmaker_id"], quote["bookmaker_name"], metrics))
            _, _, best_id, best_name, best_reverse = max(scored, key=lambda item: item[0])
            best_reverse["bookmaker_id"] = best_id
            best_reverse["bookmaker_name"] = best_name
        recorded_ev = evaluation.get("current_ev")
        recorded_minus_se = evaluation.get("current_ev_minus_se")
        if recorded_ev is not None and recorded_minus_se is not None:
            target_metrics["recorded_ev_minus_se"] = float(recorded_minus_se)
            target_metrics["recorded_ev_se"] = float(recorded_ev) - float(recorded_minus_se)
            target_metrics["economic_gates"]["ev_minus_se_positive"] = float(recorded_minus_se) > 0

        home, away = raw["home_goals"], raw["away_goals"]
        home_goals, away_goals = int(home), int(away)
        target_line = line
        reverse_line = -line if market == "ASIAN_HANDICAP" else line
        target_settlement = _settlement(market, selection, target_line, home_goals, away_goals)
        reverse_settlement = _settlement(market, opposite, reverse_line, home_goals, away_goals)
        xg = capture.get("four_field_xg_identity", {}).get("four_fields", {})
        rows.append({
            "fixture_id": raw["fixture_id"], "market": market, "selection": selection, "opposite_selection": opposite,
            "line": float(line), "opposite_line": float(reverse_line), "bookmaker_id": str(evaluation["bookmaker_id"]),
            "bookmaker_name": reverse_bookmaker_name, "capture_id": raw["capture_id"], "evaluated_at": raw["evaluated_at"],
            "calibration_status": capture.get("calibration_status"), "calibration_version": capture.get("calibration_version"),
            "calibration_identity": evaluation.get("calibration_identity") or capture.get("calibration_identity"),
            "lambda_inputs": xg, "target": target_metrics, "reverse": reverse_metrics,
            "reverse_best_available": best_reverse,
            "target_settlement": target_settlement, "reverse_settlement": reverse_settlement,
            "score": f"{home_goals}-{away_goals}", "reverse_ev_se_status": "NOT_PERSISTED_IN_CAPTURE",
        })

    summary = _summarize(rows)
    return {"input_rows": len(evaluations), "analyzed_rows": len(rows), "missing": dict(missing), "rows": rows, "summary": summary}


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"by_market": {}, "by_target_settlement": Counter(), "reverse_hard_gate_pass": 0, "reverse_hard_gate_fail": 0, "best_available_reverse_ev_positive": 0}
    for market in ("ASIAN_HANDICAP", "TOTALS"):
        scoped = [r for r in rows if r["market"] == market]
        result["by_market"][market] = {
            "count": len(scoped),
            "target_settlements": dict(Counter(r["target_settlement"] for r in scoped)),
            "reverse_settlements": dict(Counter(r["reverse_settlement"] for r in scoped)),
            "target_ev_mean": round(sum(r["target"]["expected_value"] for r in scoped) / len(scoped), 6) if scoped else None,
            "reverse_ev_mean": round(sum(r["reverse"]["expected_value"] for r in scoped) / len(scoped), 6) if scoped else None,
            "target_edge_mean": round(sum(r["target"]["cashflow_price_edge"] for r in scoped) / len(scoped), 6) if scoped else None,
            "reverse_edge_mean": round(sum(r["reverse"]["cashflow_price_edge"] for r in scoped) / len(scoped), 6) if scoped else None,
        }
    for row in rows:
        result["by_target_settlement"][row["target_settlement"]] += 1
        gates = row["reverse"]["economic_gates"]
        if gates["ev_positive"] and gates["cashflow_edge_ge_005"]:
            result["reverse_hard_gate_pass"] += 1
        else:
            result["reverse_hard_gate_fail"] += 1
        if row.get("reverse_best_available") and row["reverse_best_available"]["expected_value"] > 0:
            result["best_available_reverse_ev_positive"] += 1
    result["by_target_settlement"] = dict(result["by_target_settlement"])
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluations", type=Path, required=True)
    parser.add_argument("--market", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.evaluations, args.market)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"input_rows": result["input_rows"], "analyzed_rows": result["analyzed_rows"], "missing": result["missing"], "summary": result["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
