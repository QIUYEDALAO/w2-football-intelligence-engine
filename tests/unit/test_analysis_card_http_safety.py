from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any, cast

from apps.api.main import app
from fastapi.testclient import TestClient

from w2.api import repository as repository_module
from w2.api import routers
from w2.api.repository import ReadModelService


class _Repository:
    def matchday_cards(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture": {"fixture_id": "fixture-1"},
                "capture_hash": "capture-1",
                "analysis_card": {
                    "fixture_id": "fixture-1",
                    "decision": "SKIP",
                    "scoreline_readiness": None,
                },
            }
        ]

    def dashboard_fixture(self, fixture_id: str) -> None:
        return None

    def fixture_payloads(self) -> list[dict[str, Any]]:
        return []


def test_historical_analysis_card_does_not_rebuild_model(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    service = ReadModelService(repository=cast(Any, _Repository()))
    monkeypatch.setattr(
        service,
        "build_analysis_card_offline",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("offline builder called")),
    )
    monkeypatch.setattr(
        service,
        "_db_analysis_card_from_fixture",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("db builder called")),
    )
    monkeypatch.setattr(routers, "service", service)

    response = TestClient(app).get("/v1/fixtures/fixture-1/analysis-card")

    assert response.status_code == 200
    assert response.json()["card"]["fixture_id"] == "fixture-1"
    assert len(response.content) < 512 * 1024


def test_missing_frozen_analysis_returns_small_fail_closed_card(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class EmptyRepository:
        def matchday_cards(self) -> list[dict[str, Any]]:
            return []

        def dashboard_fixture(self, fixture_id: str) -> None:
            return None

        def fixture_payloads(self) -> list[dict[str, Any]]:
            return [{"fixture": {"id": "fixture-1"}}]

    monkeypatch.setattr(
        routers,
        "service",
        ReadModelService(repository=cast(Any, EmptyRepository())),
    )
    response = TestClient(app).get("/v1/fixtures/fixture-1/analysis-card")

    assert response.status_code == 200
    assert response.json()["card"]["reason_code"] == "FROZEN_ANALYSIS_CAPTURE_UNAVAILABLE"
    assert len(response.content) < 32 * 1024


def test_http_frontdoors_have_no_forbidden_rebuild_calls() -> None:
    router_source = inspect.getsource(routers)
    service_source = inspect.getsource(repository_module.ReadModelService.frozen_analysis_card)
    service_source += inspect.getsource(repository_module.ReadModelService.audit_detail)
    source = router_source + service_source
    tree = ast.parse(source)
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute | ast.Name)
    }

    assert called.isdisjoint(
        {
            "build_analysis_card_offline",
            "_db_analysis_card_from_fixture",
            "run_simulation",
            "build_feature_set",
        }
    )


def test_full_dashboard_card_does_not_call_provider_analysis_builder() -> None:
    source = Path(repository_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_dashboard_card_from_matchday"
    )
    called = {
        node.func.attr
        for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "build_analysis_card_offline" not in called
    assert "_analysis_card_from_provider_payload" not in called
