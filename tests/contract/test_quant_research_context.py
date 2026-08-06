from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

PROTOCOL = "docs/architecture/W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1.md"
BINDING = "docs/operations/W2_QUANT_FREEZE_A0_BINDING_20260805.md"
MASTER = "docs/operations/W2_QUANT_PROGRAM_MASTER_CHECKLIST.md"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_quant_freeze_a0_machine_state_is_bounded() -> None:
    state = yaml.safe_load(read("QUANT_PROJECT_STATE.yaml"))

    assert state["schema_version"] == "w2.quant_project_state.v1"
    assert state["program"] == "W2_SPORTTERY_QUANT_RESEARCH_PLATFORM"
    assert state["protocol_version"] == "v2.3.1"
    assert state["protocol_path"] == PROTOCOL
    assert state["binding_path"] == BINDING
    assert state["task_authority"] == MASTER
    assert state["active_next_action"] == "W2_QUANT_L1_OFFLINE_FOUNDATION"
    assert state["architecture"] == "SAME_REPOSITORY_INDEPENDENT_BOUNDED_CONTEXT"
    assert state["existing_v4_recommendation_chain"] == "PRESERVED_AND_UNMODIFIED"
    assert state["freeze_a0_offline_engineering"] == (
        "APPROVED_WITH_BINDING_ERRATA_A"
    )
    assert state["freeze_a1_live_collection"] == "DEFERRED_OWNER_API_AND_LICENSE"
    assert state["track1_forward_clock"] == "NOT_STARTED"
    assert state["live_capture_enabled"] is False
    assert state["quant_provider_calls"] == 0
    assert state["quant_deployment"] == "NOT_AUTHORIZED"

    for key in (
        "l2_strategy_engine",
        "l3_shadow_ledger",
        "l4_bankroll_risk",
        "phase_a",
        "phase_b",
        "portfolio",
        "two_leg_parlay",
        "real_money",
    ):
        assert state[key] == "NOT_AUTHORIZED"

    operational = state["operational_track"]
    assert operational["scheduler"] == "ON_CONTROLLED"
    assert {operational[key] for key in ("candidate", "formal", "lock", "production")} == {
        "OFF"
    }

    closure = state["context_closure"]
    assert closure == {
        "runtime_code_changed": False,
        "database_migration_created": False,
        "provider_calls": 0,
        "images_built": 0,
        "deployment_executed": False,
    }


def test_quant_protocol_and_binding_authorities_are_present() -> None:
    protocol = read(PROTOCOL)
    binding = read(BINDING)
    master = read(MASTER)

    expected_source_sha = (
        "SOURCE_SHA256 = "
        "b724bd3daf37d395966f78514ed1011e1ae95f6507ed959cd7d9d03f584142eb"
    )
    assert "PROTOCOL_VERSION = v2.3.1" in protocol
    assert expected_source_sha in protocol
    assert "HHAD_DECISION = OPTION_B" in protocol
    for part in range(1, 5):
        assert (
            ROOT
            / "docs/architecture/W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1"
            / f"part-{part:02d}.md"
        ).is_file()

    assert "FREEZE_A0_OFFLINE_ENGINEERING = APPROVED_WITH_BINDING_ERRATA_A" in binding
    assert "FREEZE_A1_LIVE_COLLECTION = DEFERRED_OWNER_API_AND_LICENSE" in binding
    assert "CURRENT_SCHEDULER = STANDALONE_SCHEDULER_PROCESS_DEPLOYED_AND_CONTROLLED" in binding
    assert "src/w2/domain/canonical_serialization.py" in binding
    assert "API_FOOTBALL_REQUEST_LIVE = CURRENT_WIRED_NETWORK_PATH" in binding
    assert "ONLY_3_COMPONENTS_WIRED" in binding and "withdrawn" in binding
    assert "Q14_CALLS_PER_DAY = NOT_EVALUATED" in binding
    assert "Q0_BLOCKS_FREEZE_A0 = false" in binding
    assert "quant_ingest_role" in binding

    assert "QUANT-L1-A0" in master
    assert "STATUS = AUTHORIZED_AFTER_QUANT_CTX_00_MERGE" in master
    assert "QUANT-L1-A1" in master
    assert "STATUS = BLOCKED_OWNER_API_AND_LICENSE" in master
    assert "QUANT-REAL-MONEY" in master
    assert master.count("STATUS = NOT_AUTHORIZED") >= 6


def test_next_action_prioritises_offline_quant_without_runtime_authority() -> None:
    next_action = read("NEXT_ACTION.md")

    assert "TOP_LEVEL_PROGRAM = W2_SPORTTERY_QUANT_RESEARCH_PLATFORM" in next_action
    assert "ACTIVE_NEXT_ACTION = W2_QUANT_L1_OFFLINE_FOUNDATION" in next_action
    assert "FREEZE_A0_OFFLINE_ENGINEERING = APPROVED_WITH_BINDING_ERRATA_A" in next_action
    assert "FREEZE_A1_LIVE_COLLECTION = DEFERRED_OWNER_API_AND_LICENSE" in next_action
    assert "TRACK1_FORWARD_CLOCK = NOT_STARTED" in next_action
    assert "LIVE_CAPTURE_ENABLED = false" in next_action
    assert "RUNTIME_CODE_CHANGED = false" in next_action
    assert "DATABASE_MIGRATION_CREATED = false" in next_action
    assert "PROVIDER_CALLS = 0" in next_action
    assert "IMAGES_BUILT = 0" in next_action
    assert "DEPLOYMENT_EXECUTED = false" in next_action

    for status in ("CANDIDATE = OFF", "FORMAL = OFF", "LOCK = OFF", "PRODUCTION = OFF"):
        assert status in next_action


def test_project_ledger_records_human_quant_reframe_decision() -> None:
    ledger = read("PROJECT_LEDGER.md")

    assert "2026-08-05 — Sporttery quant research reframe" in ledger
    assert "quant_research" in ledger
    assert "Freeze A0 offline engineering is approved" in ledger
    assert "Freeze A1 live dual-source collection remains" in ledger
    assert "W2_QUANT_L1_OFFLINE_FOUNDATION" in ledger
    assert "real-money execution are not authorized" in ledger
