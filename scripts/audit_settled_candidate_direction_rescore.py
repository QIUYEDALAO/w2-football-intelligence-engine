#!/usr/bin/env python3
"""Replay settled candidates and compare model direction with the result.

The input is the frozen, read-only CSV export produced by
``settled_candidate_rescore_export.sql``.  It contains no provider or database
calls.  Direction is derived from the immutable model capture bound to each
evaluation, never from the later mutable shadow checkpoint.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.markets.settlement_probability import effective_settlement_probability
csv.field_size_limit(sys.maxsize)

SIDES = {"HOME": "AWAY", "AWAY": "HOME", "OVER": "UNDER", "UNDER": "OVER"}
OUTCOMES = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")


def _json(value: str | None) -> dict[str, Any]:
    return json.loads(value) if value else {}


def _effective(distribution: dict[str, Any]) -> float:
    value = effective_settlement_probability(distribution)
    if value is None:
        raise ValueError("invalid five-state distribution")
    return float(value)


def _direction_from_capture(
    market: str, selection: str, line: Decimal, capture: dict[str, Any]
) -> dict[str, Any]:
    sides = ("HOME", "AWAY") if market == "ASIAN_HANDICAP" else ("OVER", "UNDER")
    if market == "ASIAN_HANDICAP":
        canonical_line = -line if selection == "AWAY" else line
        ladder = capture.get("ah_settlement_distributions", {}).get("ladder", [])
        item = next(
            (row for row in ladder if Decimal(str(row.get("home_line"))) == canonical_line),
            None,
        )
        keys = {"HOME": "home_settlement_distribution", "AWAY": "away_settlement_distribution"}
    else:
        ladder = capture.get("ou_settlement_distributions", {}).get("ladder", [])
        item = next((row for row in ladder if Decimal(str(row.get("line"))) == line), None)
        keys = {"OVER": "over_settlement_distribution", "UNDER": "under_settlement_distribution"}
    if item is None:
        raise ValueError(f"capture ladder has no {market} line {line}")
    distributions = {side: item[keys[side]] for side in sides}
    probabilities = {side: round(_effective(dist), 6) for side, dist in distributions.items()}
    ordered = sorted(sides, key=lambda side: (-probabilities[side], side))
    return {
        "predicted": ordered[0],
        "probabilities": probabilities,
        "settlement_distributions": distributions,
        "margin": round(probabilities[ordered[0]] - probabilities[ordered[1]], 6),
    }


def _actual(market: str, selection: str, line: Decimal, home: int, away: int) -> dict[str, Any]:
    target = (
        settle_asian_handicap(home, away, selection, line)
        if market == "ASIAN_HANDICAP"
        else settle_total_goals(home + away, selection, line)
    ).value
    opposite = SIDES[selection]
    opposite_line = -line if market == "ASIAN_HANDICAP" else line
    reverse = (
        settle_asian_handicap(home, away, opposite, opposite_line)
        if market == "ASIAN_HANDICAP"
        else settle_total_goals(home + away, opposite, opposite_line)
    ).value
    if target in {"WIN", "HALF_WIN"}:
        direction = selection
    elif reverse in {"WIN", "HALF_WIN"}:
        direction = opposite
    else:
        direction = "PUSH"
    return {
        "direction": direction,
        "target_settlement": target,
        "opposite_settlement": reverse,
        "score": f"{home}-{away}",
    }


def _replay_row(raw: dict[str, str]) -> dict[str, Any]:
    evaluation = _json(raw["evaluation_payload"])
    capture = _json(raw.get("model_capture_payload"))
    if not capture:
        raise ValueError(f"{raw.get('fixture_id')}: missing immutable model capture")
    market = str(raw["market"])
    selection = str(raw["selection"]).upper().replace("_AH", "").replace("_TOTALS", "")
    line = Decimal(str(evaluation["exact_line"]))
    home, away = int(raw["home_goals"]), int(raw["away_goals"])
    predicted = _direction_from_capture(market, selection, line, capture)
    actual = _actual(market, selection, line, home, away)
    four_fields = capture.get("four_field_xg_identity", {}).get("four_fields", {})
    return {
        "evaluation_id": raw["evaluation_id"],
        "fixture_id": raw["fixture_id"],
        "market": market,
        "selection": selection,
        "line": float(line),
        "evaluated_at": raw["evaluated_at"],
        "calibration_identity": evaluation.get("calibration_identity")
        or capture.get("calibration_identity"),
        "model_version": capture.get("model_version"),
        "calibration_version": capture.get("calibration_version"),
        "calibration_status": capture.get("calibration_status"),
        "input": {
            "four_field_xg": four_fields,
            "four_field_xg_identity_hash": capture.get("four_field_xg_identity", {}).get(
                "identity_hash"
            ),
        },
        "immutable_capture_replay": {
            "predicted": predicted,
            "original_selection": selection,
            "original_selection_matches_model": predicted["predicted"] == selection,
        },
        "actual": actual,
        "settlement_outcome": actual["target_settlement"],
        "direction_correct": predicted["predicted"] == actual["direction"],
        "original_bet_direction_correct": selection == actual["direction"],
        "settlement": raw.get("result_status"),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_market: dict[str, Any] = {}
    for market in ("ASIAN_HANDICAP", "TOTALS"):
        scoped = [row for row in rows if row["market"] == market]
        by_market[market] = {
            "count": len(scoped),
            "model_predicted_direction": dict(
                Counter(row["immutable_capture_replay"]["predicted"]["predicted"] for row in scoped)
            ),
            "actual_direction": dict(Counter(row["actual"]["direction"] for row in scoped)),
            "model_direction_correct": sum(row["direction_correct"] for row in scoped),
            "original_selection_matches_model": sum(
                row["immutable_capture_replay"]["original_selection_matches_model"] for row in scoped
            ),
            "original_bet_direction_correct": sum(
                row["original_bet_direction_correct"] for row in scoped
            ),
        }
    return {
        "by_market": by_market,
        "by_result_status": dict(Counter(row["settlement"] for row in rows)),
        "by_settlement_outcome": {
            outcome: {
                "count": sum(row["settlement_outcome"] == outcome for row in rows),
                "model_direction_correct": sum(
                    row["settlement_outcome"] == outcome and row["direction_correct"]
                    for row in rows
                ),
                "original_bet_direction_correct": sum(
                    row["settlement_outcome"] == outcome and row["original_bet_direction_correct"]
                    for row in rows
                ),
            }
            for outcome in OUTCOMES
        },
        "model_direction_correct": sum(row["direction_correct"] for row in rows),
        "original_selection_matches_model": sum(
            row["immutable_capture_replay"]["original_selection_matches_model"] for row in rows
        ),
        "original_bet_direction_correct": sum(
            row["original_bet_direction_correct"] for row in rows
        ),
    }


def audit(path: Path) -> dict[str, Any]:
    rows = [_replay_row(raw) for raw in csv.DictReader(path.open(newline="", encoding="utf-8"))]
    if not rows:
        raise ValueError("input export is empty")
    result = {
        "schema_version": "w2.settled_candidate_direction_rescore.v2",
        "input_rows": len(rows),
        "fixture_count": len({row["fixture_id"] for row in rows}),
        "rows": rows,
        "summary": _summary(rows),
        "limitations": [
            (
                "This is a diagnostic replay of an already observed cohort; no parameter "
                "or threshold selection is authorized."
            ),
            (
                "Direction is compared separately from admission and P&L; a correct "
                "direction can still lose because of the AH line or totals line."
            ),
            (
                "The prior no-home-advantage counterfactual was withdrawn because it used "
                "a later shadow checkpoint rather than the evaluation-bound immutable capture."
            ),
        ],
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.input)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
