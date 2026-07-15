from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, local
from typing import Any, cast

from w2.api.repository import ReadModelService


class _ThreadFixtureRepository:
    def __init__(self) -> None:
        self._local = local()

    def select_fixture(self, fixture_id: str) -> None:
        self._local.fixture_id = fixture_id

    def fixture_payloads(self) -> list[dict[str, Any]]:
        fixture_id = str(self._local.fixture_id)
        return [{"fixture": {"id": fixture_id}}]


def test_request_read_caches_are_isolated_between_concurrent_requests(tmp_path: Path) -> None:
    repository = _ThreadFixtureRepository()
    service = ReadModelService(
        repository=cast(Any, repository),
        r4_1_artifact_root=tmp_path,
    )
    first_loaded = Event()
    second_loaded = Event()

    def first_request() -> dict[str, Any] | None:
        repository.select_fixture("fixture-a")
        service._reset_read_caches()
        assert service._cached_fixture_payloads()[0]["fixture"]["id"] == "fixture-a"
        first_loaded.set()
        assert second_loaded.wait(timeout=2)
        return service._fixture_payload_by_id("fixture-a")

    def second_request() -> dict[str, Any] | None:
        assert first_loaded.wait(timeout=2)
        repository.select_fixture("fixture-b")
        service._reset_read_caches()
        assert service._cached_fixture_payloads()[0]["fixture"]["id"] == "fixture-b"
        second_loaded.set()
        return service._fixture_payload_by_id("fixture-b")

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(first_request)
        second = executor.submit(second_request)

    assert first.result() == {"fixture": {"id": "fixture-a"}}
    assert second.result() == {"fixture": {"id": "fixture-b"}}


def test_request_scope_does_not_reuse_previous_request_cache(tmp_path: Path) -> None:
    repository = _ThreadFixtureRepository()
    service = ReadModelService(
        repository=cast(Any, repository),
        r4_1_artifact_root=tmp_path,
    )

    repository.select_fixture("fixture-a")
    with service._read_request_scope():
        assert service._cached_fixture_payloads()[0]["fixture"]["id"] == "fixture-a"

    repository.select_fixture("fixture-b")
    with service._read_request_scope():
        assert service._cached_fixture_payloads()[0]["fixture"]["id"] == "fixture-b"
