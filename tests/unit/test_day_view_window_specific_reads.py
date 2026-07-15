from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from w2.api.repository import ReadModelService
from w2.config import Environment
from w2.tracking.day_view_capture_index import _summary_from_capture


def _row(fixture_id: str) -> dict[str, Any]:
    return {
        "fixture_id": fixture_id,
        "kickoff_utc": "2026-07-16T10:00:00Z",
        "competition_id": "chinese_super_league",
        "competition_name": "中超",
        "home_team_name": "Home",
        "away_team_name": "Away",
        "status": "NS",
    }


def test_future_does_not_read_today_next36_or_results(monkeypatch: Any) -> None:
    service = ReadModelService(repository=cast(Any, object()))
    future = [_row("future")]
    monkeypatch.setattr(service, "_future_fixture_rows_with_errors", lambda: (future, 0))
    monkeypatch.setattr(
        service,
        "matchday",
        lambda **_: (_ for _ in ()).throw(AssertionError("future read today")),
    )
    monkeypatch.setattr(
        service,
        "matchday_next_36_hours",
        lambda **_: (_ for _ in ()).throw(AssertionError("future read next36")),
    )
    monkeypatch.setattr(
        service,
        "_all_matchday_rows",
        lambda: (_ for _ in ()).throw(AssertionError("future read results")),
    )

    assert service._dashboard_rows_for_window(
        requested_date=date(2026, 7, 16),
        window="future",
    ) == future


class _AvailabilityRepository:
    def __init__(self) -> None:
        self.availability_calls: list[list[str]] = []

    def day_view_source_watermarks(self) -> dict[str, Any]:
        return {
            "schema_version": "w2.day_view_source_watermarks.v1",
            "source_status": "PASS",
            "fixture_source_hash": "source-a",
        }

    def market_availability_for_fixture_ids(
        self,
        fixture_ids: list[str],
    ) -> dict[str, bool]:
        self.availability_calls.append(fixture_ids)
        return {fixture_id: True for fixture_id in fixture_ids}

    def market_observation_history_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> list[dict[str, Any]]:
        raise AssertionError(f"L1 queried observation history for {fixture_ids}")


def test_capture_backed_card_skips_market_read_and_missing_capture_uses_availability(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    repository = _AvailabilityRepository()
    service = ReadModelService(repository=cast(Any, repository))
    rows = [_row("captured"), _row("missing")]
    summary = _summary_from_capture(
        {
            "fixture_id": "captured",
            "captured_at": "2026-07-16T08:00:00Z",
            "kickoff_utc": "2026-07-16T10:00:00Z",
            "capture_hash": "capture-a",
            "decision_tier": "WATCH",
            "data_status": "BLOCKED",
            "status": "NS",
        }
    )
    assert summary is not None
    monkeypatch.setattr(
        "w2.api.repository.get_settings",
        lambda: SimpleNamespace(
            resolved_runtime_root=tmp_path,
            environment=Environment.TEST,
        ),
    )
    monkeypatch.setenv("W2_GIT_SHA", "release-a")
    monkeypatch.setenv("W2_RELEASE_ID", "release-a")
    monkeypatch.setattr(service, "_dashboard_rows_for_window", lambda **_: rows)
    monkeypatch.setattr(service, "_day_view_performance", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        "w2.api.repository.build_day_view_capture_index",
        lambda _: SimpleNamespace(
            summaries={"captured": summary},
            ledger_fingerprint="ledger-a",
            schema_version="w2.day_view_capture_summary.v1",
            source_status="PASS",
        ),
    )

    view = service.dashboard_day_view(
        target_date="2026-07-16",
        window="future",
        page_size=20,
    )

    assert repository.availability_calls == [["missing"]]
    cards = {card["fixture_id"]: card for card in view["cards"]}
    assert cards["captured"]["source"] != "bounded_fail_closed_projection"
    assert cards["missing"]["reason_code"] == "DECISION_SUMMARY_UNAVAILABLE"
