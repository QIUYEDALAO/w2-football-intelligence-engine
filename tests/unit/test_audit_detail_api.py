from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import sleep
from types import SimpleNamespace
from typing import Any, cast

from apps.api.main import app
from fastapi.testclient import TestClient

from w2.api import routers
from w2.api.repository import ReadModelService
from w2.config import Environment
from w2.dashboard.day_view import build_dashboard_day_view
from w2.tracking.frozen_capture_identity import audit_capture_id


class _EmptyRepository:
    def matchday_cards(self) -> list[dict[str, Any]]:
        return []

    def dashboard_fixture(self, fixture_id: str) -> None:
        return None

    def fixture_payloads(self) -> list[dict[str, Any]]:
        return []


def _client(monkeypatch, runtime_root: Path) -> TestClient:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "w2.api.repository.get_settings",
        lambda: SimpleNamespace(
            resolved_runtime_root=runtime_root,
            environment=Environment.TEST,
        ),
    )
    monkeypatch.setattr(
        routers,
        "service",
        ReadModelService(repository=cast(Any, _EmptyRepository())),
    )
    return TestClient(app)


def test_known_oom_fixture_returns_bounded_projection(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fixture_root = Path(__file__).parents[1] / "fixtures" / "frozen_audit"
    response = _client(monkeypatch, fixture_root).get(
        "/v1/fixtures/1576804/audit-detail",
        params={
            "capture_hash": "0ceebd3db9a826d72cdafef626d64f54f7fdd837cca528a29188b3c1e93457bc"
        },
    )

    assert response.status_code == 200
    assert len(response.content) <= 512 * 1024
    payload = response.json()
    assert payload["audit"]["fixture_id"] == "1576804"
    assert payload["audit"]["historical_compatibility"] is True
    assert payload["performance"]["frozen_audit_response_bytes"] <= 512 * 1024


def test_audit_detail_uses_exact_capture_hash_and_identity_mismatch_is_409(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    ledger = tmp_path / "forward_outcome_ledger"
    ledger.mkdir()
    (ledger / "ledger.jsonl").write_text(
        json.dumps(
            {
                "fixture_id": "fixture-1",
                "capture_hash": "capture-a",
                "fair_market_estimate_ids": ["fme-a"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    client = _client(monkeypatch, tmp_path)

    capture_mismatch = client.get(
        "/v1/fixtures/fixture-1/audit-detail", params={"capture_hash": "capture-b"}
    )
    estimate_mismatch = client.get(
        "/v1/fixtures/fixture-1/audit-detail",
        params={"capture_hash": "capture-a", "estimate_id": "fme-b"},
    )

    assert capture_mismatch.status_code == 409
    assert capture_mismatch.json()["code"] == "CAPTURE_IDENTITY_MISMATCH"
    assert estimate_mismatch.status_code == 409
    assert estimate_mismatch.json()["code"] == "ESTIMATE_IDENTITY_MISMATCH"


def test_missing_capture_is_404_and_corrupt_ledger_is_503(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _client(monkeypatch, tmp_path)
    missing = client.get(
        "/v1/fixtures/missing/audit-detail", params={"capture_hash": "missing"}
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "LEDGER_NOT_FOUND"

    ledger = tmp_path / "forward_outcome_ledger"
    ledger.mkdir()
    (ledger / "ledger.jsonl").write_text('{"broken":', encoding="utf-8")
    corrupt = client.get(
        "/v1/fixtures/missing/audit-detail", params={"capture_hash": "missing"}
    )
    assert corrupt.status_code == 503
    assert corrupt.json()["code"] == "LEDGER_CORRUPTION"


def test_audit_detail_does_not_call_live_rebuild_functions(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fixture_root = Path(__file__).parents[1] / "fixtures" / "frozen_audit"
    service = ReadModelService(repository=cast(Any, _EmptyRepository()))
    monkeypatch.setattr(
        "w2.api.repository.get_settings",
        lambda: SimpleNamespace(
            resolved_runtime_root=fixture_root,
            environment=Environment.TEST,
        ),
    )
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

    response = TestClient(app).get(
        "/v1/fixtures/1576804/audit-detail",
        params={
            "capture_hash": "0ceebd3db9a826d72cdafef626d64f54f7fdd837cca528a29188b3c1e93457bc"
        },
    )

    assert response.status_code == 200


def test_l1_requires_exact_audit_identity_triple() -> None:
    capture = {
        "fixture_id": "fixture-1",
        "captured_at": "2099-07-01T09:00:00Z",
        "kickoff_utc": "2099-07-01T10:00:00Z",
        "capture_hash": "capture-exact",
        "decision_tier": "WATCH",
        "data_status": "READY",
        "pick": {"estimate_id": "fme-exact"},
    }
    capture["audit_capture_id"] = audit_capture_id(capture)
    capture["audit_identity_status"] = "PASS"
    view = build_dashboard_day_view(
        {
            "date": "2099-07-01",
            "selected_football_day": "2099-07-01",
            "generated_at": "2099-07-01T00:00:00Z",
            "timezone": "UTC",
            "window": "today",
            "all": [capture],
        },
        environment="staging",
    )
    card = view["cards"][0]

    assert card["audit_capture_id"] == capture["audit_capture_id"]
    assert card["audit_capture_hash"] == "capture-exact"
    assert card["audit_estimate_id"] == "fme-exact"
    assert card["audit_available"] is True
    assert f"capture_id={capture['audit_capture_id']}" in card["audit_detail_url"]
    assert "capture_hash=capture-exact" in card["audit_detail_url"]
    assert "estimate_id=fme-exact" in card["audit_detail_url"]


def test_l1_hash_only_identity_is_not_audit_available() -> None:
    view = build_dashboard_day_view(
        {
            "date": "2099-07-01",
            "selected_football_day": "2099-07-01",
            "generated_at": "2099-07-01T00:00:00Z",
            "timezone": "UTC",
            "window": "today",
            "all": [
                {
                    "fixture_id": "fixture-1",
                    "kickoff_utc": "2099-07-01T10:00:00Z",
                    "capture_hash": "capture-only",
                    "decision_tier": "WATCH",
                    "data_status": "READY",
                }
            ],
        },
        environment="staging",
    )

    card = view["cards"][0]
    assert card["audit_available"] is False
    assert card["audit_detail_url"] is None


def test_same_key_concurrency_builds_projection_once(
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    fixture_root = Path(__file__).parents[1] / "fixtures" / "frozen_audit"
    service = ReadModelService(repository=cast(Any, _EmptyRepository()))
    monkeypatch.setattr(
        "w2.api.repository.get_settings",
        lambda: SimpleNamespace(
            resolved_runtime_root=fixture_root,
            environment=Environment.TEST,
        ),
    )
    from w2.api import repository as repository_module

    original = repository_module.build_frozen_fixture_audit
    calls = 0
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def build(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        with lock:
            calls += 1
        sleep(0.05)
        return original(*args, **kwargs)

    monkeypatch.setattr(repository_module, "build_frozen_fixture_audit", build)

    def request(_: int) -> dict[str, Any]:
        barrier.wait()
        return service.audit_detail(
            "1576804",
            capture_hash=(
                "0ceebd3db9a826d72cdafef626d64f54f7fdd837cca528a29188b3c1e93457bc"
            ),
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(request, range(8)))

    assert calls == 1
    assert max(
        row["performance"]["frozen_audit_singleflight_waiter"] for row in results
    ) == 7
    assert all(row["audit"] == results[0]["audit"] for row in results)
