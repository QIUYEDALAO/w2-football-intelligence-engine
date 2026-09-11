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

    assert "W2_MARKET_TIMELINE_REFRESH_ENABLED" not in normal
    assert "w2.market_timeline_refresh" not in normal
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


def test_admission_identity_evidence_and_oracle_authorities_are_closed() -> None:
    entrypoint = (ROOT / "scripts/run_prematch_refresh.py").read_text(encoding="utf-8")
    authorization = (ROOT / "src/w2/operations/gate_a.py").read_text(encoding="utf-8")
    validator = (ROOT / "src/w2/operations/gate_a_evidence.py").read_text(encoding="utf-8")
    producer = (ROOT / "src/w2/operations/gate_a_evidence_producer.py").read_text(encoding="utf-8")
    admission = (ROOT / "scripts/validate_gate_a_offline_evidence.py").read_text(
        encoding="utf-8"
    )
    trust = json.loads(
        (ROOT / "config/policies/gate_a_authorization_trust.v1.json").read_text(encoding="utf-8")
    )

    assert "--untracked-files=no" not in entrypoint
    assert '"--untracked-files=all"' in entrypoint
    assert "GATE_A_IGNORED_EXECUTABLE_CONTENT_PRESENT" in entrypoint
    assert "complete_checkout_manifest_sha256" in authorization
    assert "runtime_artifact_digest" in authorization
    assert "approval_public_key_sha256" in authorization
    assert "INDEPENDENT_SIGNER_CONFIRMED" in authorization
    assert "OWNER_APPROVED_UNSIGNED_ONE_SHOT" in authorization
    assert "GATE_A_OWNER_DECISION_ISSUE = 454" in authorization
    assert "GATE_A_OWNER_DECISION_COMMENT_ID = 5155919529" in authorization
    assert "expected_binding" not in validator
    assert "CALLER_ASSERTED_ARTIFACT_COUNT_REJECTED" in validator
    assert "subprocess.run" in validator
    assert '"-I"' in validator
    assert "produce_gate_a_evidence" in producer
    assert "GateARunReservationModel" in producer
    assert "FutureRefreshTaskAuditModel" in producer
    assert "RawPayloadModel" in producer
    assert "MatchdayEndpointCaptureModel" in producer
    assert "LineupConfirmedEventModel" in producer
    assert "DynamicPrematchEvaluationModel" in producer
    assert "FutureRefreshTaskAuditModel.gate_a_lease_epoch" in producer
    assert "row.inserted_at" in producer
    assert "produce_gate_a_evidence(" in admission
    assert "validate_gate_a_evidence(" in admission
    assert "CALLER_EVIDENCE_DB_RECOMPUTE_MISMATCH" in admission
    assert not (ROOT / "scripts/produce_gate_a_admission_evidence.py").exists()
    assert trust["private_keys_present"] is False
    assert all(
        key["authorization_enabled"] is False for key in trust["trusted_ed25519_keys"].values()
    )

    producer_sites = []
    for root in ("src/w2", "apps", "scripts"):
        for path in (ROOT / root).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            producer_sites.extend(
                (path.relative_to(ROOT).as_posix(), node.name)
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == "produce_gate_a_evidence"
            )
    assert producer_sites == [
        ("src/w2/operations/gate_a_evidence_producer.py", "produce_gate_a_evidence")
    ]

    for path in (
        ROOT / "oracle/canonical_serialization_oracle.py",
        ROOT / "scripts/invoke_independent_canonical_oracle.py",
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        assert not any(module == "w2" or module.startswith("w2.") for module in modules)
