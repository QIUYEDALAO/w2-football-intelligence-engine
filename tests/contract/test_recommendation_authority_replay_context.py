from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

import jsonschema
import yaml
from tests.secret_scan import SENSITIVE

ROOT = Path(__file__).resolve().parents[2]
RECEIPT_PATH = (
    "docs/operations/"
    "W2_RECOMMENDATION_AUTHORITY_REAL_FIXTURE_REPLAY_RECEIPT_20260804.md"
)
MANIFEST_PATH = (
    "docs/operations/W2_REAL_FIXTURE_REPLAY_SANITIZED_MANIFEST_20260804.json"
)
SCHEMA_PATH = "contracts/replay/w2_real_fixture_sanitized_manifest.v1.schema.json"
HANDOFF_PATHS = (
    "AI_PROJECT_CONTEXT.md",
    "NEXT_ACTION.md",
    "AGENTS.md",
    ".github/copilot-instructions.md",
)
REQUIRED_FACTS = (
    "PUBLIC_RECOMMENDATION_AUTHORITY = SINGLE",
    "REAL_FIXTURE_OFFLINE_REPLAY = PASS",
    "LINEUP_NUMERIC_VALUE_MODEL = NOT_IMPLEMENTED",
    "LINEUP_NUMERIC_ADJUSTMENT = OFF",
    "CANDIDATE = OFF",
    "FORMAL = OFF",
    "LOCK = OFF",
    "PRODUCTION = OFF",
)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_recommendation_authority_closure_is_synchronized() -> None:
    for path in HANDOFF_PATHS:
        text = _read(path)
        for fact in REQUIRED_FACTS:
            assert fact in text, (path, fact)
        assert RECEIPT_PATH in text
        assert MANIFEST_PATH in text

    state = yaml.safe_load(_read("PROJECT_STATE.yaml"))
    assert state["PUBLIC_RECOMMENDATION_AUTHORITY"] == "SINGLE"
    assert state["REAL_FIXTURE_OFFLINE_REPLAY"] == "PASS"
    assert state["LINEUP_NUMERIC_VALUE_MODEL"] == "NOT_IMPLEMENTED"
    assert state["LINEUP_NUMERIC_ADJUSTMENT"] == "OFF"
    for gate in ("CANDIDATE", "FORMAL", "LOCK", "PRODUCTION"):
        assert state[gate] == "OFF"

    closure = state["recommendation_authority_replay_closure"]
    assert closure == {
        "status": "PASS",
        "receipt": RECEIPT_PATH,
        "sanitized_manifest": MANIFEST_PATH,
        "public_recommendation_authority": "SINGLE",
        "public_direction_writer_count": 1,
        "public_decision_authority_count": 1,
        "legacy_object_can_create_public_pick": False,
        "decision_schema_version": "w2.recommendation_decision.v4",
        "real_fixture_offline_replay": "PASS",
        "network_calls_during_replay": 0,
        "real_provider_calls_executed": 0,
        "manual_evaluation_inserts": 0,
        "manual_pair_inserts": 0,
        "manual_checkpoint_inserts": 0,
        "db_recompute_byte_identical": True,
        "replay_idempotent": True,
        "lineup_validator_authority_count": 1,
        "lineup_numeric_value_model": "NOT_IMPLEMENTED",
        "lineup_numeric_adjustment": "OFF",
        "candidate": "OFF",
        "formal": "OFF",
        "lock": "OFF",
        "production": "OFF",
    }


def test_sanitized_manifest_is_schema_valid_and_bound_to_receipt() -> None:
    manifest_bytes = (ROOT / MANIFEST_PATH).read_bytes()
    manifest = json.loads(manifest_bytes)
    schema = json.loads((ROOT / SCHEMA_PATH).read_bytes())
    jsonschema.validators.validator_for(schema).check_schema(schema)
    jsonschema.validate(manifest, schema)

    assert manifest["contains_raw_payloads"] is False
    receipts = manifest["file_receipts"]
    logical_paths = [item["logical_path"] for item in receipts]
    assert len(logical_paths) == len(set(logical_paths)) == 6
    assert all(
        not PurePosixPath(path).is_absolute()
        and ".." not in PurePosixPath(path).parts
        for path in logical_paths
    )
    assert all(re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) for item in receipts)
    assert all(item["size_bytes"] > 0 for item in receipts)

    receipt = _read(RECEIPT_PATH)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    assert f"SANITIZED_MANIFEST_SHA256 = {manifest_sha}" in receipt
    assert f"SOURCE_GIT_SHA = {manifest['source_git_sha']}" in receipt
    assert f"BUNDLE_ID = {manifest['bundle_id']}" in receipt
    assert f"FIXTURE_ID_SHA256 = {manifest['fixture_id_sha256']}" in receipt
    for fact in REQUIRED_FACTS:
        assert fact in receipt


def test_committed_replay_artifacts_are_desensitized() -> None:
    combined = f"{_read(RECEIPT_PATH)}\n{_read(MANIFEST_PATH)}"
    assert SENSITIVE.search(combined) is None
    assert re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", combined) is None
    for forbidden in (
        "1494232",
        "/private/",
        "/Users/",
    ):
        assert forbidden not in combined
