from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"STAGE10C_CHECK_FAILED: {message}")


def load_report(name: str) -> dict[str, object]:
    path = ROOT / "reports" / name
    require(path.exists(), f"missing report {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    fixture_audit = load_report("W2_STAGE10C_DAILY_FIXTURE_AUDIT.json")
    integrity = load_report("W2_STAGE10C_SNAPSHOT_INTEGRITY.json")
    cards = load_report("W2_STAGE10C_ALL_MARKET_CARDS.json")
    result = ROOT / "reports/W2_STAGE10C_RESULT.md"
    require(result.exists(), "missing result report")
    items = cards.get("items")
    require(isinstance(items, list), "cards items must be a list")
    for item in items:
        require(isinstance(item, dict), "card item must be object")
        card = item.get("card")
        ranking = item.get("market_ranking")
        temporal = item.get("temporal")
        require(isinstance(card, dict), "card missing")
        require(isinstance(ranking, list), "ranking missing")
        require(isinstance(temporal, dict), "temporal missing")
        require(card.get("formal_recommendation") is False, "formal recommendation enabled")
        require(card.get("candidate") is False, "candidate enabled")
        require(card.get("published_grade") in {"A", "B", "C", "D", "X"}, "bad grade")
        require(card.get("published_grade") not in {"A", "B"}, "Gate4 cap violated")
        markets = {row.get("market") for row in ranking if isinstance(row, dict)}
        require(markets <= {"ONE_X_TWO", "ASIAN_HANDICAP", "TOTALS", "BTTS"}, "bad market")
        require("source_captured_at" in temporal, "source time missing")
        require("valuation_generated_at" in temporal, "valuation time missing")
    require(isinstance(fixture_audit.get("items"), list), "fixture audit items missing")
    require(isinstance(integrity.get("items"), list), "integrity items missing")
    print(json.dumps({"stage": "10C", "status": "PASS"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
