from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import scripts.materialize_analysis_card_canary as canary_cli
import scripts.run_prematch_refresh as refresh_cli

from w2.api.repository import ReadModelService


def test_prematch_refresh_defaults_to_no_provider_call_plan() -> None:
    completed = subprocess.run(
        [
            "python3",
            "scripts/run_prematch_refresh.py",
            "--competition-id",
            "world_cup_2026",
            "--season",
            "2026",
            "--now-utc",
            "2026-06-27T00:08:25Z",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["status"] == "DRY_RUN"
    assert payload["would_execute"] is False
    assert payload["provider_calls"] is False
    assert payload["task_key"] == "future-refresh:world_cup_2026:2026:20260627T000000Z"
    assert payload["candidate"] is False
    assert payload["formal_recommendation"] is False
    assert payload["beats_market"] is False


def test_materialize_analysis_card_canary_executes_active_calculator_entry(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    class Repository:
        def fixture_payload(self, fixture_id: str) -> dict[str, Any]:
            return {
                "fixture": {"id": fixture_id, "date": "2026-07-18T06:00:00Z"},
                "league": {"id": "league"},
                "teams": {
                    "home": {"id": "home"},
                    "away": {"id": "away"},
                },
            }

        def future_market_observations_for_fixtures(
            self,
            fixture_ids: list[str],
        ) -> list[dict[str, Any]]:
            return [{"fixture_id": fixture_ids[0], "capture_id": "capture-1"}]

    calls = 0

    def calculate(
        _self: ReadModelService,
        fixture_id: str,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {
            "fixture_id": fixture_id,
            "competition_id": "league",
            "market_candidates": {},
        }

    monkeypatch.setattr(canary_cli, "ReadModelRepository", Repository)
    monkeypatch.setattr(ReadModelService, "public_analysis_card_bounded", calculate)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "materialize_analysis_card_canary.py",
            "--fixture-id",
            "fixture-1",
            "--evaluated-at",
            "2026-07-18T05:00:00Z",
        ],
    )

    assert canary_cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert calls == 1
    assert payload["status"] == "DRY_RUN"
    assert payload["artifacts"][0]["checkpoint_key"] == (
        "analysis-card:frozen:v1:fixture-1"
    )


def test_prematch_refresh_execute_db_injects_shadow_composition_adapter(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    captured: dict[str, Any] = {}

    def run_future_refresh_task(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            status="COMPLETED",
            task_id=kwargs["task_id"],
            key=kwargs["key"],
            result={"provider_calls": 0},
        )

    monkeypatch.setattr(
        "w2.ingestion.future_refresh.run_future_refresh_task",
        run_future_refresh_task,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_prematch_refresh.py",
            "--execute",
            "--persistence",
            "db",
            "--now-utc",
            "2026-07-18T05:00:00Z",
        ],
    )

    assert refresh_cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "COMPLETED"
    assert captured["persistence"] == "db"
    assert (
        captured["materialize_public_artifacts"]
        is refresh_cli.materialize_shadow_projection_events
    )


def test_prematch_refresh_execute_defaults_to_db_and_injects_shadow_adapter(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    captured: dict[str, Any] = {}

    def run_future_refresh_task(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            status="COMPLETED",
            task_id=kwargs["task_id"],
            key=kwargs["key"],
            result={"provider_calls": 0},
        )

    monkeypatch.delenv("W2_FUTURE_REFRESH_PERSISTENCE", raising=False)
    monkeypatch.setattr(
        "w2.ingestion.future_refresh.run_future_refresh_task",
        run_future_refresh_task,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_prematch_refresh.py",
            "--execute",
            "--now-utc",
            "2026-07-18T05:00:00Z",
        ],
    )

    assert refresh_cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "COMPLETED"
    assert captured["persistence"] == "db"
    assert (
        captured["materialize_public_artifacts"]
        is refresh_cli.materialize_shadow_projection_events
    )


def test_prematch_refresh_execute_uses_file_env_without_shadow_adapter(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    captured: dict[str, Any] = {}

    def run_future_refresh_task(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            status="COMPLETED",
            task_id=kwargs["task_id"],
            key=kwargs["key"],
            result={"provider_calls": 0},
        )

    monkeypatch.setenv("W2_FUTURE_REFRESH_PERSISTENCE", "file")
    monkeypatch.setattr(
        "w2.ingestion.future_refresh.run_future_refresh_task",
        run_future_refresh_task,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_prematch_refresh.py",
            "--execute",
            "--now-utc",
            "2026-07-18T05:00:00Z",
        ],
    )

    assert refresh_cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "COMPLETED"
    assert captured["persistence"] == "file"
    assert captured["materialize_public_artifacts"] is None
