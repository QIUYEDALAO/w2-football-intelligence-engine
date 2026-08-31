#!/usr/bin/env python3
"""Read-only audit of frozen settled candidates and their persisted model inputs."""

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

csv.field_size_limit(sys.maxsize)


def _json(value: str | None) -> dict[str, Any]:
    return json.loads(value) if value else {}


def _settlement(market: str, selection: str, line: float, home: int, away: int) -> str:
    decimal_line = Decimal(str(line))
    if market == "ASIAN_HANDICAP":
        return settle_asian_handicap(home, away, selection, decimal_line).value
    return settle_total_goals(home + away, selection, decimal_line).value


def audit(path: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for raw in csv.DictReader(path.open(newline="", encoding="utf-8")):
        evaluation = _json(raw["evaluation_payload"])
        checkpoint = _json(raw.get("checkpoint_payload"))
        card = checkpoint.get("analysis_card", {})
        simulation = card.get("simulation", {})
        capture = _json(raw.get("model_capture_payload"))
        readiness = simulation.get("input_readiness", {})
        factors = card.get("feature_contributions", [])
        factor_status = {
            str(f.get("id")): {
                "status": f.get("status"),
                "collection_status": f.get("collection_status"),
                "score": f.get("score"),
                "source": f.get("source"),
                "inputs": f.get("inputs", {}),
            }
            for f in factors
            if isinstance(f, dict) and f.get("id")
        }
        market = str(raw["market"])
        selection = str(raw["selection"]).upper().replace("_AH", "").replace("_TOTALS", "")
        line = float(evaluation["exact_line"])
        home, away = int(raw["home_goals"]), int(raw["away_goals"])
        rows.append(
            {
                "evaluation_id": raw["evaluation_id"],
                "fixture_id": raw["fixture_id"],
                "market": market,
                "selection": selection,
                "line": line,
                "odds": float(evaluation["decimal_odds"]),
                "evaluated_at": raw["evaluated_at"],
                "capture_at": raw["capture_at"],
                "checkpoint_created_at": raw.get("checkpoint_created_at"),
                "calibration_status": simulation.get("calibration_status")
                or capture.get("calibration_status"),
                "calibration_identity": evaluation.get("calibration_identity"),
                "model_version": simulation.get("model_version"),
                "lambda_home": simulation.get("lambda_home"),
                "lambda_away": simulation.get("lambda_away"),
                "simulation_input_hash": simulation.get("calibration", {}).get(
                    "simulation_input_hash"
                ),
                "capture_simulation_input_hash": capture.get("source_artifact_hashes", {}).get(
                    "simulation_input_hash"
                ),
                "evaluation_capture_identity_match": (
                    evaluation.get("model_forecast_capture_identity_hash")
                    == capture.get("capture_identity_hash")
                ),
                "evaluation_model_input_manifest_match": (
                    evaluation.get("model_input_hash") == capture.get("model_input_manifest_hash")
                ),
                # The checkpoint is a mutable latest-fixture projection, not an
                # immutable child of this historical evaluation. Keep this only
                # as a time-difference diagnostic; it is not an identity gate.
                "latest_checkpoint_simulation_matches_capture": (
                    simulation.get("calibration", {}).get("simulation_input_hash")
                    == capture.get("source_artifact_hashes", {}).get("simulation_input_hash")
                ),
                "input_readiness": readiness,
                "factor_status": factor_status,
                "model_settlement_distribution": evaluation.get("model_settlement_distribution"),
                "current_ev": evaluation.get("current_ev"),
                "current_ev_minus_se": evaluation.get("current_ev_minus_se"),
                "current_delta": evaluation.get("current_delta"),
                "blockers": evaluation.get("blockers", []),
                "score": f"{home}-{away}",
                "settlement": _settlement(market, selection, line, home, away),
                "result_status": raw.get("result_status"),
                "result_confirmed_at": raw.get("confirmed_at"),
            }
        )
    factor_counts: dict[str, Counter[str]] = {}
    for row in rows:
        for factor, value in row["factor_status"].items():
            factor_counts.setdefault(factor, Counter())[str(value.get("status"))] += 1
    return {
        "input_rows": len(rows),
        "fixture_count": len({row["fixture_id"] for row in rows}),
        "by_market": dict(Counter(row["market"] for row in rows)),
        "by_settlement": dict(Counter(row["settlement"] for row in rows)),
        "by_calibration_status": dict(Counter(str(row["calibration_status"]) for row in rows)),
        "simulation_status": dict(
            Counter(
                "READY"
                if row["lambda_home"] is not None and row["lambda_away"] is not None
                else "UNAVAILABLE"
                for row in rows
            )
        ),
        "evaluation_capture_identity_match": dict(
            Counter(str(row["evaluation_capture_identity_match"]) for row in rows)
        ),
        "evaluation_model_input_manifest_match": dict(
            Counter(str(row["evaluation_model_input_manifest_match"]) for row in rows)
        ),
        "latest_checkpoint_simulation_matches_capture": dict(
            Counter(str(row["latest_checkpoint_simulation_matches_capture"]) for row in rows)
        ),
        "input_readiness": {
            key: dict(Counter(str(row["input_readiness"].get(key)) for row in rows))
            for key in (
                "xg_status",
                "ratings_used_in_lambda",
                "squad_value_used_in_lambda",
                "lineups",
                "h2h_ready",
                "history_ready",
                "proxy_elo_excluded",
            )
        },
        "factor_status": {factor: dict(counts) for factor, counts in sorted(factor_counts.items())},
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.input)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "rows"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
