from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "config/policies/gate_a_offline_contracts.v1.json"


def test_frozen_gate_a_denominator_and_contracts_are_complete() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    required_fields = set(policy["required_contract_fields"])
    assert policy["frozen_base_sha"] == "dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6"
    assert policy["final_gate_a_groups"] == 28
    assert len(policy["exact_blocker_mappings"]) == 35
    assert len(policy["test_contracts"]) == 30
    assert len({item["id"] for item in policy["test_contracts"]}) == 30
    assert required_fields == {
        "trigger",
        "expected_terminal_status",
        "expected_provider_delta",
        "expected_business_delta",
        "expected_evidence_delta",
        "exact_test_node",
        "exact_executed_result",
    }
    for contract in policy["test_contracts"]:
        assert contract["location"]
        assert required_fields <= set(contract)
        assert contract["trigger"] != "INJECT_FAILURE_AT_FROZEN_CODE_LOCATION"
        assert contract["expected_terminal_status"]
        assert contract["expected_provider_delta"]
        assert contract["expected_business_delta"]
        assert contract["expected_evidence_delta"]
        assert contract["exact_executed_result"] == "PASS"
        test_file, test_name = contract["exact_test_node"].split("::")
        text = (ROOT / test_file).read_text(encoding="utf-8")
        assert f"def {test_name}(" in text
    assert policy["independent_review_required"] is True
    assert policy["real_provider_authorized"] is False


def test_gate_a_entrypoint_is_foreground_only_and_not_compose_managed() -> None:
    compose = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "infra/compose").glob("*.yml")
    )
    assert "run_prematch_refresh.py" not in compose
    assert "--authorization-file" in (ROOT / "scripts/run_prematch_refresh.py").read_text(
        encoding="utf-8"
    )


def test_gate_a_canary_compose_isolates_persistent_scheduler() -> None:
    normal = (ROOT / "infra/compose/compose.staging.yml").read_text(encoding="utf-8")
    override = (ROOT / "infra/compose/gate-a-canary.override.yml").read_text(encoding="utf-8")

    assert 'W2_MARKET_TIMELINE_REFRESH_ENABLED: "true"' in normal
    assert "restart: unless-stopped" in normal
    assert 'profiles: ["persistent-scheduler"]' in override
    assert 'restart: "no"' in override


def test_every_explicit_live_constructor_uses_central_fail_closed_client() -> None:
    sites: list[str] = []
    for production_root in ("src/w2", "apps", "scripts"):
        for path in (ROOT / production_root).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                allow_live = next(
                    (keyword.value for keyword in node.keywords if keyword.arg == "allow_live"),
                    None,
                )
                if not isinstance(allow_live, ast.Constant) or allow_live.value is not True:
                    continue
                if not isinstance(node.func, ast.Name) or node.func.id != "ApiFootballClient":
                    continue
                sites.append(path.relative_to(ROOT).as_posix())
    assert sites
    client_source = (ROOT / "src/w2/providers/api_football.py").read_text(encoding="utf-8")
    assert "if provider_calls_disabled():" in client_source
    assert "self._require_endpoint_allowed(endpoint)" in client_source
