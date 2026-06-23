from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from w2.monitoring.stage7i_lifecycle import (
    FileLock,
    LifecycleConfig,
    Stage7ILifecycleCollector,
    build_final_evidence,
    read_jsonl,
    resolve_actual_kickoff,
    resolve_closing,
)
from w2.providers.api_football import LiveApiFootballResponse

NOW = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 6, 23, 17, 0, tzinfo=UTC)


class FakeLifecycleClient:
    def __init__(
        self,
        *,
        status_code: int = 200,
        remaining: int = 7000,
        fixture_status: str = "NS",
        actual_kickoff: str | None = None,
        odds_payload_suffix: str = "a",
        burst_remaining: int | None = None,
        daily_header: str = "x-ratelimit-requests-remaining",
        statuses: list[str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.remaining = remaining
        self.fixture_status = fixture_status
        self.actual_kickoff = actual_kickoff
        self.odds_payload_suffix = odds_payload_suffix
        self.burst_remaining = burst_remaining
        self.daily_header = daily_header
        self.statuses = statuses or []
        self.calls: list[str] = []

    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        self.calls.append(endpoint)
        payload = self.payload(endpoint)
        headers = {self.daily_header: str(self.remaining)}
        if self.burst_remaining is not None:
            headers["x-ratelimit-remaining"] = str(self.burst_remaining)
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=self.status_code,
            elapsed_ms=4,
            payload=payload,
            headers=headers,
            captured_at=NOW + timedelta(seconds=len(self.calls)),
        )

    def payload(self, endpoint: str) -> dict[str, Any]:
        if endpoint == "fixtures":
            status = self.statuses.pop(0) if self.statuses else self.fixture_status
            fixture: dict[str, Any] = {
                "id": 1489404,
                "date": "2026-06-23T17:00:00+00:00",
                "status": {"short": status},
                "periods": {},
            }
            if self.actual_kickoff:
                fixture["periods"]["first"] = self.actual_kickoff
            return {"response": [{"fixture": fixture, "goals": {"home": None, "away": None}}]}
        return {
            "response": [
                {
                    "fixture": {"id": 1489404},
                    "update": f"2026-06-23T11:59:0{self.odds_payload_suffix}+00:00",
                    "bookmakers": [
                        {
                            "id": 1,
                            "name": "Book A",
                            "bets": [
                                {
                                    "id": 1,
                                    "name": "Match Winner",
                                    "values": [{"value": "Home", "odd": "1.8"}],
                                }
                            ],
                        }
                    ],
                }
            ]
        }


def config(tmp_path: Path) -> LifecycleConfig:
    return LifecycleConfig(
        runtime_dir=tmp_path,
        fixture_id="1489404",
        scheduled_kickoff_utc=KICKOFF,
    )


def test_lifecycle_collector_appends_once_for_same_payload(tmp_path: Path) -> None:
    client = FakeLifecycleClient()
    collector = Stage7ILifecycleCollector(config=config(tmp_path), client=client, now=NOW)

    first = collector.probe_once()
    second = Stage7ILifecycleCollector(
        config=config(tmp_path),
        client=client,
        now=NOW,
    ).probe_once()

    assert first.fixture_events == 1
    assert first.market_events == 1
    assert second.fixture_events == 0
    assert second.market_events == 0
    assert len(read_jsonl(tmp_path / "lifecycle/fixture_status.jsonl")) == 1
    assert len(read_jsonl(tmp_path / "lifecycle/market_observations.jsonl")) == 1
    assert len(read_jsonl(tmp_path / "lifecycle/request_audit.jsonl")) == 4
    assert len(list((tmp_path / "lifecycle/raw").glob("*.json"))) == 2


def test_request_audit_counts_replayed_payload_attempts(tmp_path: Path) -> None:
    client = FakeLifecycleClient()

    Stage7ILifecycleCollector(
        config=config(tmp_path),
        client=client,
        now=NOW,
    ).probe_once()
    Stage7ILifecycleCollector(
        config=config(tmp_path),
        client=client,
        now=NOW,
    ).probe_once()

    request_rows = read_jsonl(tmp_path / "lifecycle/request_audit.jsonl")
    raw_files = list((tmp_path / "lifecycle/raw").glob("*.json"))
    assert len(request_rows) == 4
    assert len(raw_files) == 2
    assert len({row["event_id"] for row in request_rows}) == 4


def test_lifecycle_collector_appends_new_market_payload(tmp_path: Path) -> None:
    Stage7ILifecycleCollector(
        config=config(tmp_path),
        client=FakeLifecycleClient(odds_payload_suffix="1"),
        now=NOW,
    ).probe_once()
    Stage7ILifecycleCollector(
        config=config(tmp_path),
        client=FakeLifecycleClient(odds_payload_suffix="2"),
        now=NOW,
    ).probe_once()

    assert len(read_jsonl(tmp_path / "lifecycle/market_observations.jsonl")) == 2


def test_lifecycle_lock_is_independent_from_observer_global_lock(tmp_path: Path) -> None:
    observer_lock = FileLock(tmp_path / "observer-global.lock")
    lifecycle_lock = FileLock(tmp_path / "lifecycle-1489404.lock")

    assert observer_lock.acquire()
    assert lifecycle_lock.acquire()
    lifecycle_lock.release()
    observer_lock.release()


def test_provider_401_stops_without_retry(tmp_path: Path) -> None:
    client = FakeLifecycleClient(status_code=401)
    collector = Stage7ILifecycleCollector(config=config(tmp_path), client=client, now=NOW)

    try:
        collector.probe_once()
    except RuntimeError as exc:
        assert "PROVIDER_HTTP_401" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("401 unexpectedly passed")
    assert client.calls == ["fixtures"]


def test_lifecycle_daily_quota_uses_daily_not_burst(tmp_path: Path) -> None:
    client = FakeLifecycleClient(remaining=6774, burst_remaining=299)
    result = Stage7ILifecycleCollector(
        config=config(tmp_path),
        client=client,
        now=NOW,
    ).probe_once()

    assert result.remaining_quota == 6774
    assert result.blockers == []
    audit = read_jsonl(tmp_path / "lifecycle/request_audit.jsonl")[0]
    assert audit["daily_remaining"] == 6774
    assert audit["burst_remaining"] == 299


def test_lifecycle_low_daily_quota_blocks_even_with_burst(tmp_path: Path) -> None:
    client = FakeLifecycleClient(remaining=1499, burst_remaining=299)
    collector = Stage7ILifecycleCollector(config=config(tmp_path), client=client, now=NOW)

    try:
        collector.probe_once()
    except RuntimeError as exc:
        assert "QUOTA_BELOW_RESERVE" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("low daily quota unexpectedly passed")


def test_lifecycle_burst_only_is_daily_unknown(tmp_path: Path) -> None:
    client = FakeLifecycleClient(
        remaining=299,
        daily_header="x-ratelimit-remaining",
    )
    collector = Stage7ILifecycleCollector(config=config(tmp_path), client=client, now=NOW)

    try:
        collector.probe_once()
    except RuntimeError as exc:
        assert "DAILY_QUOTA_UNKNOWN" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("burst-only quota unexpectedly passed")


def test_lifecycle_live_state_does_not_request_odds_or_exit(tmp_path: Path) -> None:
    client = FakeLifecycleClient(fixture_status="1H")
    result = Stage7ILifecycleCollector(
        config=config(tmp_path),
        client=client,
        now=NOW,
    ).probe_once()
    result_event = read_jsonl(tmp_path / "lifecycle/result_status.jsonl")[0]
    fixture_event = read_jsonl(tmp_path / "lifecycle/fixture_status.jsonl")[0]

    assert client.calls == ["fixtures"]
    assert result.state == "LIVE"
    assert result.completed is False
    assert result_event["evidence_category"] == "RETROSPECTIVE"
    assert fixture_event["evidence_category"] == "RETROSPECTIVE"


def test_lifecycle_final_state_records_result_and_completes(tmp_path: Path) -> None:
    client = FakeLifecycleClient(fixture_status="FT")
    result = Stage7ILifecycleCollector(
        config=config(tmp_path),
        client=client,
        now=NOW,
    ).probe_once()
    result_event = read_jsonl(tmp_path / "lifecycle/result_status.jsonl")[0]

    assert client.calls == ["fixtures"]
    assert result.state == "FINAL"
    assert result.completed is True
    assert result_event["confirmed"] is True
    assert result_event["evidence_category"] == "RETROSPECTIVE"


def test_run_loop_final_state_writes_exit_and_releases_lock(tmp_path: Path) -> None:
    cfg = config(tmp_path / "runs/run-1")
    collector = Stage7ILifecycleCollector(
        config=cfg,
        client=FakeLifecycleClient(fixture_status="FT"),
        now=NOW,
    )

    collector.run_loop()

    lifecycle = cfg.runtime_dir / "lifecycle"
    exit_payload = json.loads((lifecycle / "collector_exit.json").read_text())
    lock = FileLock(tmp_path / "lifecycle-1489404.lock")
    assert exit_payload["exit_reason"] == "COMPLETED"
    assert exit_payload["candidate"] is False
    assert lock.acquire()
    lock.release()


def test_run_loop_shutdown_request_writes_audit_without_requests(tmp_path: Path) -> None:
    cfg = config(tmp_path / "runs/run-1")
    collector = Stage7ILifecycleCollector(
        config=cfg,
        client=FakeLifecycleClient(),
        now=NOW,
    )
    collector.stop_requested = True
    collector.stop_signal = "SIGTERM"

    collector.run_loop()

    lifecycle = cfg.runtime_dir / "lifecycle"
    shutdown = read_jsonl(lifecycle / "shutdown_audit.jsonl")[0]
    exit_payload = json.loads((lifecycle / "collector_exit.json").read_text())
    lock = FileLock(tmp_path / "lifecycle-1489404.lock")
    assert shutdown["stopped_new_provider_requests"] is True
    assert shutdown["evidence_deleted"] is False
    assert exit_payload["exit_reason"] == "SHUTDOWN_REQUESTED"
    assert exit_payload["received_signal"] == "SIGTERM"
    assert collector.request_count == 0
    assert lock.acquire()
    lock.release()


def test_run_loop_shutdown_request_appends_collector_exit_event(tmp_path: Path) -> None:
    cfg = config(tmp_path / "runs/run-1")
    collector = Stage7ILifecycleCollector(
        config=cfg,
        client=FakeLifecycleClient(),
        now=NOW,
    )
    collector.stop_requested = True
    collector.stop_signal = "SIGTERM"

    collector.run_loop()

    exits = read_jsonl(cfg.runtime_dir / "lifecycle/collector_exits.jsonl")
    assert len(exits) == 1
    assert exits[0]["exit_reason"] == "SHUTDOWN_REQUESTED"
    assert exits[0]["budget_preflight"]["configured_request_budget"] == "AUTO"
    assert exits[0]["budget_preflight"]["request_budget_sufficient"] is True
    assert exits[0]["candidate"] is False
    assert exits[0]["formal_recommendation"] is False


def test_lifecycle_restart_never_deletes_existing_evidence(tmp_path: Path) -> None:
    lifecycle = tmp_path / "lifecycle"
    lifecycle.mkdir()
    existing = json.dumps({"event_id": "existing", "fixture_id": "1489404"}) + "\n"
    (lifecycle / "fixture_status.jsonl").write_text(existing, encoding="utf-8")

    Stage7ILifecycleCollector(
        config=config(tmp_path),
        client=FakeLifecycleClient(),
        now=NOW,
    ).probe_once()

    rows = read_jsonl(lifecycle / "fixture_status.jsonl")
    assert rows[0]["event_id"] == "existing"
    assert len(rows) == 2


def test_delayed_kickoff_prematch_after_scheduled_time_allows_odds(
    tmp_path: Path,
) -> None:
    delayed_now = KICKOFF + timedelta(minutes=10)
    client = FakeLifecycleClient(fixture_status="NS")
    result = Stage7ILifecycleCollector(
        config=config(tmp_path),
        client=client,
        now=delayed_now,
    ).probe_once()

    assert client.calls == ["fixtures", "odds"]
    assert result.market_events == 1
    assert read_jsonl(tmp_path / "lifecycle/market_observations.jsonl")[0][
        "evidence_category"
    ] == "FORWARD"


def test_request_budget_counts_existing_audit_on_restart(tmp_path: Path) -> None:
    lifecycle = tmp_path / "lifecycle"
    lifecycle.mkdir()
    (lifecycle / "request_audit.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "event_id": f"request-{index}",
                    "fixture_id": "1489404",
                    "endpoint": "fixtures",
                    "status_code": 200,
                }
            )
            for index in range(2)
        )
        + "\n",
        encoding="utf-8",
    )
    cfg = LifecycleConfig(
        runtime_dir=tmp_path,
        fixture_id="1489404",
        scheduled_kickoff_utc=KICKOFF,
        request_budget=2,
    )
    collector = Stage7ILifecycleCollector(
        config=cfg,
        client=FakeLifecycleClient(),
        now=NOW,
    )

    try:
        collector.probe_once()
    except RuntimeError as exc:
        assert "REQUEST_BUDGET_EXHAUSTED" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("exhausted restart budget unexpectedly passed")


def test_auto_request_budget_covers_projected_runtime_need(tmp_path: Path) -> None:
    lifecycle = tmp_path / "lifecycle"
    lifecycle.mkdir()
    (lifecycle / "request_audit.jsonl").write_text(
        json.dumps({"event_id": "request-1"}) + "\n",
        encoding="utf-8",
    )
    collector = Stage7ILifecycleCollector(
        config=config(tmp_path),
        client=FakeLifecycleClient(),
        now=NOW,
    )

    preflight = collector.budget_preflight(now=NOW)

    assert preflight["configured_request_budget"] == "AUTO"
    assert preflight["consumed_attempts"] == 1
    assert preflight["remaining_budget"] >= preflight["projected_required"]
    assert collector.effective_request_budget() == (
        preflight["consumed_attempts"] + preflight["projected_required"]
    )


def test_auto_request_budget_is_fixed_for_collector_instance(tmp_path: Path) -> None:
    collector = Stage7ILifecycleCollector(
        config=config(tmp_path),
        client=FakeLifecycleClient(),
        now=NOW,
    )
    initial_budget = collector.effective_request_budget()

    Stage7ILifecycleCollector(
        config=config(tmp_path),
        client=FakeLifecycleClient(),
        now=NOW,
    ).probe_once()

    assert collector.effective_request_budget() == initial_budget


def test_explicit_request_budget_can_still_block_restart(tmp_path: Path) -> None:
    lifecycle = tmp_path / "lifecycle"
    lifecycle.mkdir()
    (lifecycle / "request_audit.jsonl").write_text(
        json.dumps({"event_id": "request-1"}) + "\n",
        encoding="utf-8",
    )
    cfg = LifecycleConfig(
        runtime_dir=tmp_path,
        fixture_id="1489404",
        scheduled_kickoff_utc=KICKOFF,
        request_budget=1,
    )
    collector = Stage7ILifecycleCollector(
        config=cfg,
        client=FakeLifecycleClient(),
        now=NOW,
    )

    try:
        collector.probe_once()
    except RuntimeError as exc:
        assert "REQUEST_BUDGET_EXHAUSTED" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("explicit exhausted budget unexpectedly passed")


def test_projected_budget_reports_consumed_attempts(tmp_path: Path) -> None:
    lifecycle = tmp_path / "lifecycle"
    lifecycle.mkdir()
    (lifecycle / "request_audit.jsonl").write_text(
        json.dumps({"event_id": "request-1"}) + "\n",
        encoding="utf-8",
    )
    collector = Stage7ILifecycleCollector(
        config=config(tmp_path),
        client=FakeLifecycleClient(),
        now=NOW,
    )
    projection = collector.projected_budget(now=NOW)

    assert projection["consumed_attempts"] == 1
    assert projection["projected_required"] > 80
    assert projection["remaining_budget"] >= projection["projected_required"]


def test_actual_kickoff_requires_internal_provider_field() -> None:
    scheduled_only = [
        {
            "event_id": "fixture-1",
            "fixture_id": "1489404",
            "provider_fixture_date": "2026-06-23T17:00:00Z",
            "actual_kickoff_utc": None,
        }
    ]
    confirmed = [
        {
            "event_id": "fixture-2",
            "fixture_id": "1489404",
            "actual_kickoff_utc": "2026-06-23T17:01:00Z",
            "actual_kickoff_source": "fixture.periods.first",
        }
    ]

    assert resolve_actual_kickoff(scheduled_only)["status"] == (
        "ACTUAL_KICKOFF_SOURCE_UNAVAILABLE"
    )
    assert resolve_actual_kickoff(confirmed)["status"] == "CONFIRMED_INTERNAL"


def test_closing_requires_pre_actual_non_live_market() -> None:
    market_events = [
        {
            "event_id": "before",
            "captured_at_utc": "2026-06-23T16:59:00Z",
            "bookmaker_count": 3,
            "live": False,
            "suspended": False,
            "raw_payload_sha256": "abc",
        },
        {
            "event_id": "after",
            "captured_at_utc": "2026-06-23T17:01:00Z",
            "bookmaker_count": 3,
            "live": False,
            "suspended": False,
            "raw_payload_sha256": "def",
        },
    ]

    closing = resolve_closing(market_events, actual_kickoff_utc=KICKOFF)

    assert closing["status"] == "RESOLVED_INTERNAL"
    assert closing["selected_observation_id"] == "before"


def test_incomplete_final_evidence_does_not_pass(tmp_path: Path) -> None:
    (tmp_path / "lifecycle").mkdir()
    (tmp_path / "start.json").write_text(
        json.dumps(
            {
                "observer_started_at_utc": "2026-06-23T09:59:44Z",
                "fixture_id": "1489404",
            }
        ),
        encoding="utf-8",
    )

    evidence = build_final_evidence(tmp_path, expected_fixture_id="1489404")

    assert evidence["status"] == "IN_PROGRESS"
    assert "OBSERVER_SUMMARY_NOT_COMPLETE" in evidence["blockers"]
    assert evidence["candidate"] is False
    assert evidence["formal_recommendation"] is False
