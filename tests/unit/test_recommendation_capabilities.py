from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from w2.domain.recommendation_capabilities import (
    REQUIRED_CAPABILITIES,
    CapabilityManifestError,
    load_recommendation_capability_manifest,
)
from w2.strategy.formal_recommendation import formal_recommendations_enabled


def _payload() -> dict[str, Any]:
    manifest = load_recommendation_capability_manifest()
    return {
        "schema_version": manifest.schema_version,
        "capabilities": {
            name: capability.public_dict() for name, capability in manifest.capabilities.items()
        },
    }


def _write(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "recommendation_capabilities.v1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_default_manifest_is_complete_and_keeps_restricted_capabilities_closed() -> None:
    manifest = load_recommendation_capability_manifest()

    assert set(manifest.capabilities) == REQUIRED_CAPABILITIES
    assert manifest.capability("formal_ah").feature_enabled is False
    assert manifest.capability("formal_ou").publicly_available is False
    assert manifest.capability("lineup_numeric_adjustment_ah").feature_enabled is False
    assert manifest.capability("lineup_numeric_adjustment_ou").feature_enabled is False
    assert manifest.capability("production_recommendation").production_enabled is False


def test_manifest_fails_closed_for_missing_capability(tmp_path: Path) -> None:
    payload = _payload()
    payload["capabilities"].pop("formal_ou")

    with pytest.raises(CapabilityManifestError, match="entries mismatch"):
        load_recommendation_capability_manifest(_write(tmp_path, payload))


def test_manifest_fails_closed_for_public_without_feature(tmp_path: Path) -> None:
    payload = _payload()
    payload["capabilities"]["formal_ah"].update(
        {"feature_enabled": False, "publicly_available": True}
    )

    with pytest.raises(CapabilityManifestError, match="public while feature is disabled"):
        load_recommendation_capability_manifest(_write(tmp_path, payload))


def test_manifest_fails_closed_for_production_without_public(tmp_path: Path) -> None:
    payload = _payload()
    payload["capabilities"]["production_recommendation"].update(
        {"publicly_available": False, "production_enabled": True}
    )

    with pytest.raises(CapabilityManifestError, match="production enabled while not public"):
        load_recommendation_capability_manifest(_write(tmp_path, payload))


def test_legacy_environment_switch_is_admission_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("W2_FORMAL_RECOMMENDATION_ENABLED", "true")

    assert formal_recommendations_enabled() is False
