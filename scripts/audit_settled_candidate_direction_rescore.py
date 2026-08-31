#!/usr/bin/env python3
"""Replay settled candidates and compare model direction with the result.

The input is the frozen, read-only CSV export produced by
``settled_candidate_rescore_export.sql``.  It contains no provider or database
calls. Direction and EV are reproduced from each evaluation's own frozen
five-state distribution, never from an earlier model capture or later mutable
shadow checkpoint.
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

from w2.domain.five_state_pricing import SettlementDistribution, expected_value
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


def _reverse_distribution(distribution: dict[str, Any]) -> dict[str, Any]:
    return {
        "WIN": distribution["LOSS"],
        "HALF_WIN": distribution["HALF_LOSS"],
        "PUSH": distribution["PUSH"],
        "HALF_LOSS": distribution["HALF_WIN"],
        "LOSS": distribution["WIN"],
    }


def _pricing_distribution(distribution: dict[str, Any]) -> SettlementDistribution:
    return SettlementDistribution(
        full_win_probability=Decimal(str(distribution["WIN"])),
        half_win_probability=Decimal(str(distribution["HALF_WIN"])),
        push_probability=Decimal(str(distribution["PUSH"])),
        half_loss_probability=Decimal(str(distribution["HALF_LOSS"])),
        full_loss_probability=Decimal(str(distribution["LOSS"])),
    )


def _direction_from_evaluation(
    selection: str,
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    opposite = SIDES[selection]
    target_distribution = evaluation.get("model_settlement_distribution")
    if not isinstance(target_distribution, dict) or set(target_distribution) != set(OUTCOMES):
        raise ValueError("evaluation has no complete five-state model distribution")
    distributions = {
        selection: target_distribution,
        opposite: _reverse_distribution(target_distribution),
    }
    sides = (selection, opposite)
    probabilities = {side: round(_effective(dist), 6) for side, dist in distributions.items()}
    ordered = sorted(sides, key=lambda side: (-probabilities[side], side))
    recomputed_ev = expected_value(
        Decimal(str(evaluation["decimal_odds"])),
        _pricing_distribution(target_distribution),
    )
    stored_ev = Decimal(str(evaluation["current_ev"]))
    return {
        "higher_probability_side": ordered[0],
        "probabilities": probabilities,
        "settlement_distributions": distributions,
        "margin": round(probabilities[ordered[0]] - probabilities[ordered[1]], 6),
        "recommended_side": selection,
        "decimal_odds": float(evaluation["decimal_odds"]),
        "stored_ev": float(stored_ev),
        "recomputed_ev": round(float(recomputed_ev), 6),
        "ev_matches": abs(recomputed_ev - stored_ev) <= Decimal("0.000001"),
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
    predicted = _direction_from_evaluation(selection, evaluation)
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
        "frozen_evaluation_replay": {
            "predicted": predicted,
            "original_selection": selection,
            "original_selection_matches_model": (
                predicted["higher_probability_side"] == selection
            ),
        },
        "actual": actual,
        "settlement_outcome": actual["target_settlement"],
        "direction_correct": predicted["higher_probability_side"] == actual["direction"],
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
                Counter(
                    row["frozen_evaluation_replay"]["predicted"]["higher_probability_side"]
                    for row in scoped
                )
            ),
            "actual_direction": dict(Counter(row["actual"]["direction"] for row in scoped)),
            "model_direction_correct": sum(row["direction_correct"] for row in scoped),
            "original_selection_matches_model": sum(
                row["frozen_evaluation_replay"]["original_selection_matches_model"]
                for row in scoped
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
            row["frozen_evaluation_replay"]["original_selection_matches_model"] for row in rows
        ),
        "original_bet_direction_correct": sum(
            row["original_bet_direction_correct"] for row in rows
        ),
        "stored_ev_recomputed_exactly": sum(
            row["frozen_evaluation_replay"]["predicted"]["ev_matches"] for row in rows
        ),
    }


def audit(path: Path) -> dict[str, Any]:
    rows = [_replay_row(raw) for raw in csv.DictReader(path.open(newline="", encoding="utf-8"))]
    if not rows:
        raise ValueError("input export is empty")
    if not all(row["frozen_evaluation_replay"]["predicted"]["ev_matches"] for row in rows):
        raise ValueError("stored evaluation EV does not reproduce from its five-state distribution")
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
                "The earlier model capture and later shadow checkpoint are not substitutes for "
                "the five-state distribution frozen in the evaluated recommendation itself."
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
