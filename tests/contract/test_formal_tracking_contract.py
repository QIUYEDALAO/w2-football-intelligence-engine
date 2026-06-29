from __future__ import annotations

import json
from pathlib import Path

CONTRACT = Path("contracts/w2_formal_tracking_report.v1.schema.json")


def load_contract() -> dict[str, object]:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_formal_tracking_report_contract_marks_posthoc_only() -> None:
    schema = load_contract()

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    properties = schema["properties"]
    assert properties["schema_version"] == {"const": "w2_formal_tracking_report.v1"}
    assert properties["not_a_formal_gate"] == {"const": True}
    assert properties["posthoc_only"] == {"const": True}
    assert properties["min_bucket_samples_for_rate"] == {"const": 30}


def test_formal_tracking_report_requires_null_rates_for_observing_payload_shape() -> None:
    schema = load_contract()

    assert "win_rate" in schema["required"]
    assert "roi" in schema["required"]
    properties = schema["properties"]
    assert properties["win_rate"]["type"] == ["number", "null"]
    assert properties["roi"]["type"] == ["number", "null"]


def test_formal_tracking_report_does_not_define_formal_gate_fields() -> None:
    text = CONTRACT.read_text(encoding="utf-8").lower()

    assert "beats_market" not in text
    assert "formal_enabled" not in text
    assert "candidate_enabled" not in text
    assert "unlock" not in text

