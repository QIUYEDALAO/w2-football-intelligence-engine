from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "config/policies/gate_a_offline_contracts.v1.json"


def test_frozen_gate_a_denominator_and_contracts_are_complete() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    defaults = policy["contract_defaults"]
    assert policy["frozen_base_sha"] == "dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6"
    assert policy["final_gate_a_groups"] == 28
    assert len(policy["exact_blocker_mappings"]) == 35
    assert len(policy["test_contracts"]) == 30
    assert len({item["id"] for item in policy["test_contracts"]}) == 30
    assert set(defaults) == {
        "trigger",
        "expected_terminal_status",
        "provider_call_delta",
        "business_write_delta",
        "evidence_delta",
    }
    for contract in policy["test_contracts"]:
        assert contract["location"]
        test_file, test_name = contract["fault_injection_test"].split("::")
        text = (ROOT / test_file).read_text(encoding="utf-8")
        assert f"def {test_name}(" in text
    assert policy["independent_review_required"] is True
    assert policy["real_provider_authorized"] is False


def test_gate_a_entrypoint_is_foreground_only_and_not_compose_managed() -> None:
    compose = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "infra/compose").glob("*.yml")
    )
    assert "run_prematch_refresh.py" not in compose
    assert "--authorization-file" in (
        ROOT / "scripts/run_prematch_refresh.py"
    ).read_text(encoding="utf-8")
