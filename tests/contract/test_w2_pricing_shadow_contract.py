from __future__ import annotations

import json
from pathlib import Path

CONTRACT = Path("contracts/w2_pricing_shadow.v1.schema.json")


def load_contract() -> dict[str, object]:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_pricing_shadow_contract_freezes_required_fields() -> None:
    schema = load_contract()

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "factors",
        "model_version",
        "calibration_version",
        "fair_ah",
        "fair_ou",
        "market_ah",
        "market_ou",
        "edge_ah",
        "edge_ou",
        "coverage",
        "asof_market_snapshot_id",
        "devig_method",
        "settlement_outcome",
        "beats_market",
    ]


def test_pricing_shadow_contract_keeps_beats_market_false_only() -> None:
    properties = load_contract()["properties"]

    assert properties["beats_market"] == {"const": False}


def test_pricing_shadow_contract_is_shape_only_not_implementation() -> None:
    text = CONTRACT.read_text(encoding="utf-8")

    assert "evaluate_s2_gate" not in text
    assert "settlement_distribution" not in text
    assert "fair_decimal_odds" not in text
    assert "pricing formula" not in text.lower()
