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
    ) -> None:
        self.status_code = status_code
        self.remaining = remaining
        self.fixture_status = fixture_status
        self.actual_kickoff = actual_kickoff
        self.odds_payload_suffix = odds_payload_suffix
        self.burst_remaining = burst_remaining
        self.daily_header = daily_header
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
            fixture: dict[str, Any] = {
                "id": 1489404,
                "date": "2026-06-23T17:00:00+00:00",
                "status": {"short": self.fixture_status},
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
    assert len(list((tmp_path / "lifecycle/raw").glob("*.json"))) == 2


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
