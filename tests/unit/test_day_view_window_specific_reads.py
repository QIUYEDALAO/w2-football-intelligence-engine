from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from w2.api.repository import ReadModelService
from w2.config import Environment
from w2.tracking.day_view_capture_index import _summary_from_capture


def _row(fixture_id: str) -> dict[str, Any]:
    return {
        "fixture_id": fixture_id,
        "kickoff_utc": "2030-07-16T10:00:00Z",
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
        requested_date=date(2030, 7, 16),
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

    def dashboard_fixtures_for_ids(
        self,
        fixture_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        return {}

    def next_checkpoint_plans_for_fixture_ids(
        self,
        fixture_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        return {}


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
            "captured_at": "2030-07-16T08:00:00Z",
            "kickoff_utc": "2030-07-16T10:00:00Z",
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
        target_date="2030-07-16",
        window="future",
        page_size=20,
    )

    assert repository.availability_calls == [["missing"]]
    cards = {card["fixture_id"]: card for card in view["cards"]}
    assert cards["captured"]["source"] != "bounded_fail_closed_projection"
    assert cards["missing"]["reason_code"] == "DECISION_SUMMARY_UNAVAILABLE"


def test_materialized_stale_card_is_displayed_without_live_rebuild(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    class Repository(_AvailabilityRepository):
        def dashboard_fixtures_for_ids(
            self,
            fixture_ids: list[str],
        ) -> dict[str, dict[str, Any]]:
            assert fixture_ids == ["stale"]
            return {
                "stale": {
                    "analysis_card": {
                        "fixture_id": "stale",
                        "decision_tier": "NOT_READY",
                        "data_status": "STALE",
                        "lifecycle_status": "DRAFT",
                        "lock_eligible": False,
                        "outcome_tracked": False,
                        "reason_code": "DATA_STALE_ODDS",
                        "current_odds": {
                            "ou": {
                                "line": "2.5",
                                "as_of": "2030-07-16T08:00:00Z",
                                "source": "api_football",
                                "source_hash": "source-hash",
                            }
                        },
                    }
                }
            }

        def next_checkpoint_plans_for_fixture_ids(
            self,
            fixture_ids: list[str],
        ) -> dict[str, dict[str, Any]]:
            return {
                "stale": {
                    "due_at": "2030-07-16T09:00:00Z",
                    "checkpoint": "T1_LINEUPS",
                }
            }

    repository = Repository()
    service = ReadModelService(repository=cast(Any, repository))
    monkeypatch.setattr(
        "w2.api.repository.get_settings",
        lambda: SimpleNamespace(resolved_runtime_root=tmp_path, environment=Environment.TEST),
    )
    monkeypatch.setenv("W2_GIT_SHA", "release-a")
    monkeypatch.setattr(service, "_dashboard_rows_for_window", lambda **_: [_row("stale")])
    monkeypatch.setattr(service, "_day_view_performance", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        "w2.api.repository.build_day_view_capture_index",
        lambda _: SimpleNamespace(
            summaries={},
            ledger_fingerprint="ledger-a",
            schema_version="w2.day_view_capture_summary.v1",
            source_status="PASS",
        ),
    )

    view = service.dashboard_day_view(
        target_date="2030-07-16",
        window="future",
        page_size=20,
    )

    card = view["cards"][0]
    assert card["data_status"] == "STALE"
    assert card["reason_code"] == "DATA_STALE_ODDS"
    assert card["current_odds"]["ou"]["line"] == "2.5"
    assert card["next_eval_at"] == "2030-07-16T09:00:00Z"
    assert view["freshness"]["next_refresh_tick"] == "2030-07-16T09:00:00Z"
    assert view["counts"]["stale"] == 1
    assert view["counts"]["blocked"] == 0


def test_materialized_fresh_card_ages_to_stale_without_model_rebuild() -> None:
    service = ReadModelService(repository=cast(Any, object()))
    card = {
        "decision_tier": "ANALYSIS_PICK",
        "data_status": "READY",
        "lock_eligible": True,
        "outcome_tracked": True,
        "pick": {"market": "TOTALS"},
        "current_odds": {"ou": {"as_of": "2030-07-16T08:00:00Z", "line": "2.5"}},
        "decision_contract": {
            "decision_tier": "ANALYSIS_PICK",
            "data_status": "READY",
            "lock_eligible": True,
            "pick": {"market": "TOTALS"},
        },
    }

    projected = service._project_materialized_card_freshness(
        card,
        as_of=datetime.fromisoformat("2030-07-16T08:31:00+00:00"),
    )

    assert projected["data_status"] == "STALE"
    assert projected["decision_tier"] == "NOT_READY"
    assert projected["lock_eligible"] is False
    assert projected["pick"] is None
    assert projected["decision_contract"]["data_status"] == "STALE"
    assert card["data_status"] == "READY"

    boundary = service._project_materialized_card_freshness(
        card,
        as_of=datetime.fromisoformat("2030-07-16T08:30:00+00:00"),
    )
    assert boundary["data_status"] == "READY"
