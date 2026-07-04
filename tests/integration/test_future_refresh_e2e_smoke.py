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
from w2.refresh.matchday_schedule import MatchdayRefreshPolicy, build_matchday_refresh_plan

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
        if endpoint == "statistics":
            return {
                "response": [
                    {
                        "team": {"id": 10},
                        "statistics": [{"type": "expected_goals", "value": "1.4"}],
                    },
                    {
                        "team": {"id": 20},
                        "statistics": [{"type": "expected_goals", "value": "0.7"}],
                    },
                ]
            }
        if endpoint == "lineups":
            return {
                "response": [
                    {"team": {"id": 10}, "startXI": [{} for _ in range(11)], "substitutes": []},
                    {"team": {"id": 20}, "startXI": [{} for _ in range(11)], "substitutes": [{}]},
                ]
            }
        if endpoint == "injuries":
            return {"response": []}
        raise AssertionError(endpoint)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_matchday_refresh_blocked_tick_has_zero_provider_calls_contract() -> None:
    fixtures = [
        {"fixture_id": f"fixture-{index}", "kickoff_utc": "2026-07-05T03:00:00Z"}
        for index in range(15)
    ]
    tick = build_matchday_refresh_plan(
        fixtures,
        as_of=datetime(2026, 7, 4, 0, 0, tzinfo=UTC),
        policy=MatchdayRefreshPolicy(),
    )[0]

    assert tick.status == "BLOCKED"
    assert tick.as_dict()["provider_calls"] == 0


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

    gate_seen: set[str] = set()

    def fake_task_key_gate(**kwargs: Any) -> Any:
        task_key = str(kwargs["task_key"])
        if task_key in gate_seen:
            return type(
                "Gate",
                (),
                {
                    "allowed": False,
                    "status": "DUPLICATE_TASK_KEY_SUPPRESSED",
                    "backend": "test",
                },
            )()
        gate_seen.add(task_key)
        return type(
            "Gate",
            (),
            {"allowed": True, "status": "ACQUIRED", "backend": "test"},
        )()

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_COMPETITION_ID", "world_cup_2026")
    monkeypatch.setenv("W2_PROVIDER_REFRESH_TICK_HARD_CAP", "100")
    monkeypatch.setattr(scheduler_main, "datetime", FixedDatetime)
    monkeypatch.setattr(
        scheduler_main,
        "due_checkpoint_refresh_batch",
        lambda now: {
            "status": "READY",
            "generated_plan_count": 8,
            "due_checkpoint_count": 1,
            "selected_checkpoint_count": 1,
            "projected_calls": 3,
            "all_due_projected_calls": 3,
            "tick_hard_cap": 100,
            "checkpoints": [
                {
                    "fixture_id": "1489404",
                    "checkpoint": "T24",
                    "kickoff_utc": "2026-06-24T17:00:00Z",
                    "due_at": "2026-06-23T17:00:00Z",
                    "endpoints": ["odds"],
                    "source": "scheduled",
                }
            ],
        },
    )
    monkeypatch.setattr(scheduler_main, "provider_task_key_gate", fake_task_key_gate)
    monkeypatch.setattr(worker_module, "run_future_refresh_task", fake_runtime_run_task)
    monkeypatch.setattr(worker_module.celery_app, "send_task", eager_send_task)
    monkeypatch.setattr(worker_module.celery_app.conf, "task_always_eager", True)

    first = scheduler_main.future_fixture_refresh_tick()
    second = scheduler_main.future_fixture_refresh_tick()

    assert first["status"] == "QUEUED"
    assert second["status"] == "DUPLICATE_TASK_KEY_SUPPRESSED"
    assert first["task_key"] == second["task_key"]
    assert first["candidate"] is False
    assert first["formal_recommendation"] is False
    assert second["candidate"] is False
    assert second["formal_recommendation"] is False
    assert [item["name"] for item in dispatched] == ["w2.future_fixture_refresh"]

    task_audits = sorted((runtime_root / "task_audit").glob("*.json"))
    assert len(task_audits) == 1
    first_audit = read_json(task_audits[0])
    assert first_audit["result"]["candidate"] is False
    assert first_audit["result"]["formal_recommendation"] is False

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
    assert len(fake_client.calls) == 3
    assert [endpoint for endpoint, _params in fake_client.calls] == [
        "status",
        "fixtures",
        "odds",
    ]
