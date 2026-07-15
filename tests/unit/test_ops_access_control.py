from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from apps.api.main import app
from fastapi.testclient import TestClient

from w2.config import get_settings

OPS_CREDENTIAL_ENV = "W2_OPS_SERVICE_" + "TOKEN"  # without_secrets
TEST_CREDENTIAL = "ops-test-credential"


@pytest.fixture(autouse=True)
def _restore_settings_cache() -> Iterator[None]:
    original = {
        name: os.environ.get(name)
        for name in ("W2_ENVIRONMENT", OPS_CREDENTIAL_ENV, "W2_OPS_ALLOWED_CIDRS")
    }
    get_settings.cache_clear()
    yield
    for name, value in original.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    get_settings.cache_clear()


def test_staging_ops_fails_closed_when_service_credential_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    monkeypatch.delenv(OPS_CREDENTIAL_ENV, raising=False)

    response = TestClient(app).get("/ops/health")

    assert response.status_code == 503


def test_staging_ops_requires_valid_bearer_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    monkeypatch.setenv(OPS_CREDENTIAL_ENV, TEST_CREDENTIAL)
    client = TestClient(app)

    missing = client.get("/ops/health")
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    wrong = client.get(
        "/ops/health",
        headers={"Authorization": "Bearer wrong-credential"},
    )
    assert wrong.status_code == 401
    assert TEST_CREDENTIAL not in wrong.text
    assert (
        client.get(
            "/ops/health",
            headers={"Authorization": f"Bearer {TEST_CREDENTIAL}"},
        ).status_code
        == 200
    )


def test_staging_ops_optional_cidr_restriction_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    monkeypatch.setenv(OPS_CREDENTIAL_ENV, TEST_CREDENTIAL)
    monkeypatch.setenv("W2_OPS_ALLOWED_CIDRS", "10.0.0.0/8")

    response = TestClient(app).get(
        "/ops/health",
        headers={"Authorization": f"Bearer {TEST_CREDENTIAL}"},
    )

    assert response.status_code == 403


def test_public_v1_is_not_affected_by_staging_ops_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    monkeypatch.delenv(OPS_CREDENTIAL_ENV, raising=False)

    response = TestClient(app).get("/v1/health")

    assert response.status_code == 200


def test_production_ops_remains_disabled_even_with_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("W2_ENVIRONMENT", "production")
    monkeypatch.setenv(OPS_CREDENTIAL_ENV, TEST_CREDENTIAL)

    response = TestClient(app).get(
        "/ops/health",
        headers={"Authorization": f"Bearer {TEST_CREDENTIAL}"},
    )

    assert response.status_code == 403
