from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"STAGE6B_CHECK_FAILED: {message}")


def main() -> int:
    required = [
        "src/w2/markets/value_engine.py",
        "config/policies/research_grade.v1.json",
        "tests/unit/test_stage6b_market_value_engine.py",
        "reports/W2_STAGE6B_PRICING_AUDIT.json",
        "reports/W2_STAGE6B_CORRECTED_ARG_AUT.json",
        "reports/W2_STAGE6B_TODAY_ALL_MATCHES.json",
        "reports/W2_STAGE6B_RESULT.md",
        "docs/adr/ADR-0020-ah-ou-market-value-engine.md",
        "docs/markets/W2_AH_OU_SETTLEMENT_V1.md",
        "docs/markets/W2_CROSS_MARKET_VALUE_V1.md",
    ]
    for relative in required:
        if not (ROOT / relative).exists():
            fail(f"missing {relative}")
    engine = (ROOT / "src/w2/markets/value_engine.py").read_text(encoding="utf-8")
    for token in [
        "hong_kong_to_decimal",
        "settlement_distribution_ah",
        "settlement_distribution_totals",
        "fair_hk_odds",
        "MarketValueEngine",
        "BookmakerPair",
    ]:
        if token not in engine:
            fail(f"value engine missing {token}")
    grade = json.loads((ROOT / "config/policies/research_grade.v1.json").read_text())
    if grade["gate4_pending_published_grade_cap"] != "C":
        fail("Gate4 pending grade cap must be C")
    audit = json.loads((ROOT / "reports/W2_STAGE6B_PRICING_AUDIT.json").read_text())
    if audit.get("formal_recommendation") is not False or audit.get("candidate") is not False:
        fail("Stage6B must not enable formal recommendations or candidates")
    corrected = json.loads((ROOT / "reports/W2_STAGE6B_CORRECTED_ARG_AUT.json").read_text())
    if corrected.get("formal_recommendation") is not False:
        fail("corrected ARG/AUT output must keep formal_recommendation=false")
    if corrected.get("candidate") is not False:
        fail("corrected ARG/AUT output must keep candidate=false")
    print(json.dumps({"status": "PASS", "stage": "6B"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
