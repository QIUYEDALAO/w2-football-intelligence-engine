from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_payload(path: str) -> dict[str, Any]:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _formal_market_row(card: dict[str, Any]) -> dict[str, Any]:
    recommendation = card.get("recommendation")
    shadow = card.get("pricing_shadow")
    current_odds = card.get("current_odds")
    recommendation = recommendation if isinstance(recommendation, dict) else {}
    shadow = shadow if isinstance(shadow, dict) else {}
    current_odds = current_odds if isinstance(current_odds, dict) else {}
    return {
        "fixture_id": card.get("fixture_id"),
        "home_team_name": card.get("home_team_name"),
        "away_team_name": card.get("away_team_name"),
        "formal_recommendation": card.get("formal_recommendation"),
        "candidate": card.get("candidate"),
        "recommendation": {
            "tier": recommendation.get("tier"),
            "market": recommendation.get("market"),
            "selection": recommendation.get("selection"),
            "selection_label_cn": recommendation.get("selection_label_cn"),
            "line": recommendation.get("line"),
            "odds": recommendation.get("odds"),
            "expected_value": recommendation.get("expected_value"),
            "risk_adjusted_ev": recommendation.get("risk_adjusted_ev"),
            "reverse_factor_value": recommendation.get("reverse_factor_value"),
        },
        "current_ah": current_odds.get("ah"),
        "pricing_shadow": {
            "market_ah": shadow.get("market_ah"),
            "fair_ah": shadow.get("fair_ah"),
            "canonical_ah_market": shadow.get("canonical_ah_market"),
            "canonical_ah_market_validation_status": shadow.get(
                "canonical_ah_market_validation_status",
            ),
            "canonical_ah_market_blocker": shadow.get("canonical_ah_market_blocker"),
            "formal_blockers": shadow.get("formal_blockers"),
            "beats_market": shadow.get("beats_market"),
        },
        "scoreline_picks": card.get("scoreline_picks", [])[:3],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize W2 formal AH market price/EV integrity from a dashboard payload.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Dashboard JSON payload path, or '-' for stdin.",
    )
    args = parser.parse_args()
    payload = _load_payload(args.input)
    cards = payload.get("all") if isinstance(payload, dict) else None
    if not isinstance(cards, list):
        raise SystemExit("input must be a /v1/dashboard payload with an all[] list")
    rows = [_formal_market_row(card) for card in cards if isinstance(card, dict)]
    print(json.dumps({"rows": rows}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
