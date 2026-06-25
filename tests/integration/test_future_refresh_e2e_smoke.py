from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apps.scheduler import main as scheduler_main
from apps.worker import celery_app as worker_module

from w2.config import Settings
from w2.ingestion import future_refresh as future_refresh_core
from w2.providers.api_football import LiveApiFootballResponse

NOW = datetime(2026, 6, 23, 10, 0, tzinfo=UTC)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        return NOW if tz is None else NOW.astimezone(tz)


class FakeLiveApiFootballPort:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        self.calls.append((endpoint, params))
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=200,
            elapsed_ms=5,
            payload=self.payload(endpoint, params),
            headers={"x-ratelimit-requests-remaining": "7000"},
            captured_at=NOW,
        )

    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint == "status":
            return {"response": {"requests": {"remaining": 7000}}}
        if endpoint == "fixtures":
            return {
                "response": [
                    {
                        "fixture": {
                            "id": 1489404,
                            "date": "2026-06-23T17:00:00+00:00",
                            "status": {"short": "NS"},
                            "venue": {"name": "Test Venue"},
                        },
                        "league": {"id": 1, "name": "World Cup", "round": "Group K"},
                        "teams": {
                            "home": {"id": 10, "name": "Team A"},
                            "away": {"id": 20, "name": "Team B"},
                        },
                    }
                ]
            }
        if endpoint == "odds":
            return {
                "response": [
                    {
                        "fixture": {"id": int(params["fixture"])},
                        "bookmakers": [
                            {
                                "id": 1,
                                "name": "Book A",
                                "bets": [
                                    {
                                        "id": 1,
                                        "name": "Match Winner",
                                        "values": [
                                            {"value": "Home", "odd": "1.80"},
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        raise AssertionError(endpoint)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_scheduler_to_celery_eager_future_refresh_smoke_is_fake_and_idempotent(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "future_refresh"
    fake_client = FakeLiveApiFootballPort()
    original_run_task = future_refresh_core.run_future_refresh_task
    dispatched: list[dict[str, Any]] = []

    def fake_runtime_run_task(**kwargs: Any) -> future_refresh_core.RefreshTaskAudit:
        patched_kwargs = dict(kwargs)
        patched_kwargs.pop("now", None)
        return original_run_task(
            **patched_kwargs,
            runtime_root=runtime_root,
            client=fake_client,
            now=NOW,
            settings=Settings(redis_url=None),
            redis_client=None,
            persistence="file",
        )

    def eager_send_task(name: str, *, kwargs: dict[str, Any], task_id: str) -> None:
        dispatched.append({"name": name, "kwargs": kwargs, "task_id": task_id})
        worker_module.celery_app.tasks[name].apply(kwargs=kwargs, task_id=task_id).get()

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_COMPETITION_ID", "world_cup_2026")
    monkeypatch.setattr(scheduler_main, "datetime", FixedDatetime)
    monkeypatch.setattr(worker_module, "run_future_refresh_task", fake_runtime_run_task)
    monkeypatch.setattr(worker_module.celery_app, "send_task", eager_send_task)
    monkeypatch.setattr(worker_module.celery_app.conf, "task_always_eager", True)

    first = scheduler_main.future_fixture_refresh_tick()
    second = scheduler_main.future_fixture_refresh_tick()

    assert first["status"] == "QUEUED"
    assert second["status"] == "QUEUED"
    assert first["task_key"] == second["task_key"]
    assert first["candidate"] is False
    assert first["formal_recommendation"] is False
    assert second["candidate"] is False
    assert second["formal_recommendation"] is False
    assert [item["name"] for item in dispatched] == [
        "w2.future_fixture_refresh",
        "w2.future_fixture_refresh",
    ]

    task_audits = sorted((runtime_root / "task_audit").glob("*.json"))
    assert len(task_audits) == 2
    first_audit = read_json(task_audits[0])
    second_audit = read_json(task_audits[1])
    assert first_audit["result"]["candidate"] is False
    assert first_audit["result"]["formal_recommendation"] is False
    assert second_audit["result"]["candidate"] is False
    assert second_audit["result"]["formal_recommendation"] is False

    ledger = runtime_root / "ledger/market_observations.jsonl"
    ledger_lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(ledger_lines) == 1

    assert (runtime_root / "read_model/fixtures.json").is_file()
    assert (runtime_root / "read_model/provider_mappings.json").is_file()
    assert (runtime_root / "read_model/market_snapshots.json").is_file()
    assert (runtime_root / "read_model/latest_market_observations.json").is_file()
    assert (runtime_root / "read_model/market_coverage.json").is_file()
    assert (runtime_root / "read_model/provider_status.json").is_file()
    assert read_json(runtime_root / "future_refresh_audit.json")["candidate"] is False
    assert len(fake_client.calls) == 6
