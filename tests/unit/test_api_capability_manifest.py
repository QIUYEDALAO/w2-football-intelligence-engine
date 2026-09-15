from __future__ import annotations

from apps.api.main import app
from fastapi.testclient import TestClient


def test_version_exposes_manifest_as_the_public_capability_authority() -> None:
    response = TestClient(app).get("/v1/version")

    assert response.status_code == 200
    manifest = response.json()["capability_manifest"]
    assert manifest["schema_version"] == "w2.recommendation_capabilities.v1"
    assert manifest["capabilities"]["formal_ah"]["feature_enabled"] is False
    assert manifest["capabilities"]["formal_ou"]["publicly_available"] is False
    assert manifest["capabilities"]["lineup_numeric_adjustment_ah"]["feature_enabled"] is False
