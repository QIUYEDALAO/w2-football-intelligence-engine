from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from w2.api.repository import ReadModelService
from w2.config import Environment


class _WatermarkRepository:
    def __init__(self) -> None:
        self.revision = "source-a"

    def day_view_source_watermarks(self) -> dict[str, Any]:
        return {
            "schema_version": "w2.day_view_source_watermarks.v1",
            "source_status": "PASS",
            "fixture_source_hash": self.revision,
            "observation_count": 1,
            "result_event_count": 1,
        }


def _rows(count: int = 40) -> list[dict[str, Any]]:
    return [
        {
            "fixture_id": f"fixture-{index:03d}",
            "kickoff_utc": f"2026-07-{16 + index // 24:02d}T{index % 24:02d}:00:00Z",
            "competition_id": "chinese_super_league",
            "competition_name": "中超",
            "home_team_name": "Home",
            "away_team_name": "Away",
            "status": "NS",
        }
        for index in range(count)
    ]


def _prepare(
    service: ReadModelService,
    tmp_path: Path,
    monkeypatch: Any,
) -> dict[str, int]:
    calls = {"fixtures": 0, "captures": 0, "performance": 0}

    def fixture_rows(**_: Any) -> list[dict[str, Any]]:
        calls["fixtures"] += 1
        return _rows()

    def capture_index(_: Path) -> Any:
        calls["captures"] += 1
        return SimpleNamespace(
            summaries={},
            ledger_fingerprint="ledger-a",
            schema_version="w2.day_view_capture_summary.v1",
            source_status="PASS",
        )

    def performance(*_: Any, **__: Any) -> dict[str, Any]:
        calls["performance"] += 1
        return {}

    monkeypatch.setattr(
        "w2.api.repository.get_settings",
        lambda: SimpleNamespace(
            resolved_runtime_root=tmp_path,
            environment=Environment.TEST,
        ),
    )
    monkeypatch.setenv("W2_GIT_SHA", "release-a")
    monkeypatch.setenv("W2_RELEASE_ID", "release-a")
    monkeypatch.setenv("W2_ENVIRONMENT", "test")
    monkeypatch.setattr(service, "_dashboard_rows_for_window", fixture_rows)
    monkeypatch.setattr(service, "_prime_observations_for_rows", lambda _: None)
    monkeypatch.setattr(service, "_observations_for_fixture", lambda _: [])
    monkeypatch.setattr(service, "_day_view_performance", performance)
    monkeypatch.setattr("w2.api.repository.build_day_view_capture_index", capture_index)
    monkeypatch.setattr(
        service,
        "version",
        lambda: {"api_git_sha": "release-a", "release_id": "release-a"},
    )
    return calls


def test_page_one_and_page_two_share_one_window_snapshot(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    service = ReadModelService(repository=cast(Any, _WatermarkRepository()))
    calls = _prepare(service, tmp_path, monkeypatch)

    first = service.dashboard_day_view(
        target_date="2026-07-16",
        window="future",
        page_size=20,
    )
    second = service.dashboard_day_view(
        target_date="2026-07-16",
        window="future",
        page_size=20,
        cursor=str(first["pagination"]["next_cursor"]),
    )

    assert first["pagination"]["snapshot_id"] == second["pagination"]["snapshot_id"]
    assert calls == {"fixtures": 1, "captures": 1, "performance": 1}
    assert {card["fixture_id"] for card in first["cards"]}.isdisjoint(
        {card["fixture_id"] for card in second["cards"]}
    )


def test_source_watermark_change_invalidates_snapshot(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    repository = _WatermarkRepository()
    service = ReadModelService(repository=cast(Any, repository))
    _prepare(service, tmp_path, monkeypatch)

    first = service.dashboard_day_view(target_date="2026-07-16", window="future")
    repository.revision = "source-b"
    second = service.dashboard_day_view(target_date="2026-07-16", window="future")

    assert first["pagination"]["snapshot_id"] != second["pagination"]["snapshot_id"]


def test_release_identity_does_not_call_release_counts(monkeypatch: Any) -> None:
    class _Repository:
        def release_counts(self) -> dict[str, int]:
            raise AssertionError("release_counts is not part of the DayView hot path")

    monkeypatch.setenv("W2_GIT_SHA", "release-a")
    monkeypatch.setenv("W2_RELEASE_ID", "release-a")
    monkeypatch.setenv("W2_ENVIRONMENT", "test")
    service = ReadModelService(repository=cast(Any, _Repository()))

    assert service.release_identity() == {
        "api_git_sha": "release-a",
        "release_id": "release-a",
        "environment": "test",
    }
