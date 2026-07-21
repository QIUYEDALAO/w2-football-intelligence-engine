from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from w2.api.repository import ReadModelService  # noqa: E402


def _pick(payload: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: payload.get(key) for key in keys if key in payload}


def _market_summary(market: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "market",
        "decision",
        "status",
        "selection",
        "line",
        "model_probability",
        "market_probability",
        "probability_delta",
        "expected_value",
        "uncertainty",
        "model_version",
        "calibration_version",
        "quote_identity",
        "blockers",
    ]
    return _pick(market, keys)


def summarize_card(card: dict[str, Any] | None, fixture_id: str) -> dict[str, Any]:
    if card is None:
        return {"fixture_id": fixture_id, "status": "NO_CARD"}
    summary = _pick(
        card,
        [
            "fixture_id",
            "decision",
            "decision_tier",
            "data_status",
            "primary_market",
            "model_version",
            "calibration_version",
        ],
    )
    for key in (
        "data_readiness",
        "available_inputs",
        "recommendation",
        "simulation",
        "analysis_summary",
        "market_evidence",
    ):
        if key in card:
            summary[key] = card[key]
    markets = card.get("markets")
    if isinstance(markets, list):
        summary["markets"] = [
            _market_summary(item) for item in markets if isinstance(item, dict)
        ]
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe W2 analysis chain read model.")
    parser.add_argument("fixture_ids", nargs="+")
    args = parser.parse_args()

    service = ReadModelService()
    payload = {
        "provider_calls": 0,
        "candidate": False,
        "formal_recommendation": False,
        "fixtures": [
            summarize_card(service.analysis_card(fixture_id), fixture_id)
            for fixture_id in args.fixture_ids
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
