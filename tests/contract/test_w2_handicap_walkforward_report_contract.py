from __future__ import annotations

import json
from pathlib import Path

CONTRACT = Path("contracts/w2_handicap_walkforward_report.v1.schema.json")


def load_contract() -> dict[str, object]:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_walkforward_report_contract_required_shape() -> None:
    schema = load_contract()

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"] == {
        "const": "w2.handicap_walkforward_report.v1"
    }
    assert schema["required"] == [
        "schema_version",
        "generated_at",
        "data_source",
        "authoritative",
        "authoritative_reason",
        "dataset_version",
        "sample",
        "market_policy",
        "settlement_policy",
        "splits",
        "metrics",
        "s2_gate",
        "calibration",
        "rows",
    ]


def test_walkforward_report_contract_locks_market_and_settlement_policy() -> None:
    properties = load_contract()["properties"]

    assert properties["market_policy"]["properties"] == {
        "as_of_required": {"const": True},
        "locked_market_snapshot_required": {"const": True},
        "devig_required": {"const": True},
        "no_post_kickoff_odds": {"const": True},
    }
    assert properties["settlement_policy"]["properties"] == {
        "asian_handicap": {"const": True},
        "push_excluded_from_win_rate": {"const": True},
        "void_excluded_from_sample": {"const": True},
        "half_win_loss_supported": {"const": True},
    }


def test_walkforward_report_contract_keeps_formal_gate_disabled() -> None:
    s2 = load_contract()["properties"]["s2_gate"]["properties"]

    assert s2["n_min"] == {"const": 200}
    assert s2["beats_market"] == {"const": False}
    assert s2["formal_enabled"] == {"const": False}
    assert s2["candidate_enabled"] == {"const": False}
