from __future__ import annotations

import fcntl
import hashlib
import json
import os
import signal
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from w2.providers.api_football import ApiFootballClient, LiveApiFootballResponse
from w2.providers.quota import parse_api_football_quota

PREMATCH_STATUS = {"NS", "TBD", "PST"}
LIVE_STATUS = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "IN_PROGRESS"}
FINAL_STATUS = {"FT", "AET", "PEN"}
BLOCKED_STATUS = {"CANC", "ABD", "AWD", "WO"}


class Stage7ILifecycleError(RuntimeError):
    pass


class LiveClientPort(Protocol):
    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        ...


@dataclass(frozen=True)
class LifecycleConfig:
    runtime_dir: Path
    fixture_id: str
    scheduled_kickoff_utc: datetime
    quota_reserve: int = 1500
    request_budget: int = 80
    interval_seconds: int = 300
    source_revision: str = "LOCAL_UNDEPLOYED"


@dataclass(frozen=True)
class LifecycleProbeResult:
    status: str
    fixture_status: str | None
    fixture_events: int
    market_events: int
    result_events: int
    request_count: int
    remaining_quota: int | None
    blockers: list[str]
    state: str = "UNKNOWN"
    completed: bool = False


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_utc(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_once(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def append_jsonl_once(path: Path, event: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        existing = {str(row.get("event_id")) for row in read_jsonl(path)}
        if str(event["event_id"]) in existing:
            return False
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return True


def write_raw_once(raw_dir: Path, endpoint: str, payload: dict[str, Any]) -> tuple[str, Path]:
    raw_hash = sha256_payload(payload)
    path = raw_dir / f"{endpoint}_{raw_hash}.json"
    write_json_once(path, payload)
    return raw_hash, path


def fixture_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response")
    return response if isinstance(response, list) else []


def fixture_status(payload: dict[str, Any]) -> str | None:
    for item in fixture_items(payload):
        status = item.get("fixture", {}).get("status", {}).get("short")
        if status:
            return str(status)
    return None


def provider_actual_kickoff(payload: dict[str, Any]) -> tuple[datetime | None, str | None]:
    for item in fixture_items(payload):
        fixture = item.get("fixture", {})
        for field in ("actual_kickoff_utc", "actual_kickoff", "kickoff_actual_utc"):
            parsed = parse_utc(fixture.get(field))
            if parsed:
                return parsed, f"fixture.{field}"
        periods = fixture.get("periods")
        if isinstance(periods, dict):
            parsed = parse_utc(periods.get("first"))
            if parsed:
                return parsed, "fixture.periods.first"
    return None, None


def bookmaker_count(payload: dict[str, Any]) -> int:
    total = 0
    for item in fixture_items(payload):
        bookmakers = item.get("bookmakers")
        if isinstance(bookmakers, list):
            total += len(bookmakers)
    return total


def has_live_or_suspended_market(payload: dict[str, Any]) -> bool:
    for item in fixture_items(payload):
        for bookmaker in item.get("bookmakers", []) if isinstance(item, dict) else []:
            for bet in bookmaker.get("bets", []) if isinstance(bookmaker, dict) else []:
                for value in bet.get("values", []) if isinstance(bet, dict) else []:
                    if not isinstance(value, dict):
                        continue
                    if value.get("suspended") in {True, "true", "1"}:
                        return True
                    if value.get("live") in {True, "true", "1"}:
                        return True
    return False


def stable_event_id(*parts: Any) -> str:
    return hashlib.sha256(canonical_json(parts)).hexdigest()


class FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.close()
            self.handle = None
            return False
        return True

    def release(self) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None


class Stage7ILifecycleCollector:
    def __init__(
        self,
        *,
        config: LifecycleConfig,
        client: LiveClientPort | None = None,
        now: datetime | None = None,
        sleep: Any | None = None,
    ) -> None:
        self.config = config
        self.client = client or ApiFootballClient(allow_live=True)
        self.now = now or utc_now()
        self.sleep = sleep or time.sleep
        self.lifecycle_dir = config.runtime_dir / "lifecycle"
        self.raw_dir = self.lifecycle_dir / "raw"
        self.request_count = self.consumed_attempts()
        self.remaining_quota: int | None = None
        self.blockers: list[str] = []
        self.stop_requested = False
        self.stop_signal: str | None = None
        self.instance_id = stable_event_id(
            "collector-instance",
            config.fixture_id,
            os.getpid(),
            iso(utc_now()),
        )

    def consumed_attempts(self) -> int:
        return len(read_jsonl(self.lifecycle_dir / "request_audit.jsonl"))

    def projected_budget(self, *, now: datetime | None = None) -> dict[str, int]:
        current = now or utc_now()
        kickoff = self.config.scheduled_kickoff_utc
        seconds_to_kickoff = max(0, int((kickoff - current).total_seconds()))
        remaining_prematch_cycles = (seconds_to_kickoff // self.config.interval_seconds) + 1
        live_cycles = (4 * 60 * 60) // self.config.interval_seconds
        projected = remaining_prematch_cycles * 2 + live_cycles + 4
        consumed = self.consumed_attempts()
        return {
            "projected_required": projected,
            "consumed_attempts": consumed,
            "remaining_budget": max(0, self.config.request_budget - consumed),
        }

    def start_metadata(self) -> None:
        write_json_once(
            self.lifecycle_dir / "collector_start.json",
            {
                "fixture_id": self.config.fixture_id,
                "scheduled_kickoff_utc": iso(self.config.scheduled_kickoff_utc),
                "started_at_utc": iso(self.now),
                "request_budget": self.config.request_budget,
                "budget_projection": self.projected_budget(now=self.now),
                "quota_reserve": self.config.quota_reserve,
                "candidate": False,
                "formal_recommendation": False,
            },
        )

    def _record_instance_metadata(self, *, lock_path: Path) -> None:
        append_jsonl_once(
            self.lifecycle_dir / "collector_instances.jsonl",
            {
                "event_id": self.instance_id,
                "fixture_id": self.config.fixture_id,
                "pid": os.getpid(),
                "started_at_utc": iso(utc_now()),
                "tooling_sha": os.environ.get("W2_STAGE7I_TOOLING_SHA", "UNKNOWN"),
                "lock_path": str(lock_path),
                "state": "RUNNING",
                "candidate": False,
                "formal_recommendation": False,
            },
        )

    def probe_once(self) -> LifecycleProbeResult:
        self.start_metadata()
        fixture_response = self._request("fixtures", {"id": self.config.fixture_id})
        fixture_status_value = fixture_status(fixture_response.payload)
        fixture_events = self._record_fixture_status(fixture_response)
        state = self._state_from_status(fixture_status_value)
        market_events = 0
        result_events = 0
        if state == "PREMATCH":
            odds_response = self._request("odds", {"fixture": self.config.fixture_id})
            market_events = self._record_market(odds_response, state=state)
        if state in {"LIVE", "FINAL", "BLOCKED"}:
            result_events = self._record_result_status(fixture_response)
        return LifecycleProbeResult(
            status="BLOCKED" if self.blockers else "OK",
            fixture_status=fixture_status_value,
            fixture_events=fixture_events,
            market_events=market_events,
            result_events=result_events,
            request_count=self.request_count,
            remaining_quota=self.remaining_quota,
            blockers=list(self.blockers),
            state=state,
            completed=state in {"FINAL", "BLOCKED"},
        )

    def run_loop(self) -> None:
        lock_path = (
            self.config.runtime_dir.parent.parent / f"lifecycle-{self.config.fixture_id}.lock"
        )
        lock = FileLock(lock_path)
        if not lock.acquire():
            raise Stage7ILifecycleError("LIFECYCLE_COLLECTOR_ALREADY_RUNNING")
        previous_handlers: dict[int, Any] = {}
        try:
            previous_handlers = self._install_signal_handlers()
            self.start_metadata()
            self._record_instance_metadata(lock_path=lock_path)
            (self.lifecycle_dir / "collector.pid").write_text(str(os.getpid()) + "\n")
            exit_reason = "UNKNOWN"
            while True:
                if self.stop_requested:
                    exit_reason = "SHUTDOWN_REQUESTED"
                    self._record_shutdown_request()
                    break
                result = self.probe_once()
                if result.blockers:
                    exit_reason = "BLOCKED"
                    break
                if result.completed:
                    exit_reason = "COMPLETED"
                    self._write_summary(result)
                    break
                if self._sleep_or_stop(self.config.interval_seconds):
                    exit_reason = "SHUTDOWN_REQUESTED"
                    self._record_shutdown_request()
                    break
            self._write_collector_exit(exit_reason)
        finally:
            self._restore_signal_handlers(previous_handlers)
            lock.release()

    def _install_signal_handlers(self) -> dict[int, Any]:
        previous: dict[int, Any] = {}
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, self._handle_signal)
        return previous

    def _restore_signal_handlers(self, previous: dict[int, Any]) -> None:
        for signum, handler in previous.items():
            signal.signal(signum, handler)

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        self.stop_requested = True
        self.stop_signal = signal.Signals(signum).name

    def _sleep_or_stop(self, seconds: int) -> bool:
        deadline = time.monotonic() + seconds
        while not self.stop_requested:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            self.sleep(min(1.0, remaining))
        return True

    def _record_shutdown_request(self) -> None:
        append_jsonl_once(
            self.lifecycle_dir / "shutdown_audit.jsonl",
            {
                "event_id": stable_event_id(
                    "shutdown",
                    self.config.fixture_id,
                    self.instance_id,
                    self.stop_signal,
                ),
                "fixture_id": self.config.fixture_id,
                "pid": os.getpid(),
                "collector_instance_id": self.instance_id,
                "received_signal": self.stop_signal,
                "shutdown_at_utc": iso(utc_now()),
                "stopped_new_provider_requests": True,
                "evidence_deleted": False,
                "candidate": False,
                "formal_recommendation": False,
            },
        )

    def _write_collector_exit(self, reason: str) -> None:
        write_json_once(
            self.lifecycle_dir / "collector_exit.json",
            {
                "fixture_id": self.config.fixture_id,
                "pid": os.getpid(),
                "collector_instance_id": self.instance_id,
                "exited_at_utc": iso(utc_now()),
                "exit_reason": reason,
                "received_signal": self.stop_signal,
                "request_count": self.consumed_attempts(),
                "evidence_deleted": False,
                "candidate": False,
                "formal_recommendation": False,
            },
        )

    def _state_from_status(self, status: str | None) -> str:
        if status in PREMATCH_STATUS:
            return "PREMATCH"
        if status in LIVE_STATUS:
            return "LIVE"
        if status in FINAL_STATUS:
            return "FINAL"
        if status in BLOCKED_STATUS:
            return "BLOCKED"
        return "UNKNOWN"

    def _write_summary(self, result: LifecycleProbeResult) -> None:
        write_json_once(
            self.lifecycle_dir / "collector_summary.json",
            {
                "fixture_id": self.config.fixture_id,
                "completed_at_utc": iso(utc_now()),
                "state": result.state,
                "fixture_status": result.fixture_status,
                "request_count": result.request_count,
                "remaining_quota": result.remaining_quota,
                "blockers": result.blockers,
                "candidate": False,
                "formal_recommendation": False,
            },
        )
        if result.state == "FINAL":
            (self.lifecycle_dir / "COLLECTOR_COMPLETED").write_text(iso(utc_now()) + "\n")

    def _request(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        if self.stop_requested:
            raise Stage7ILifecycleError("COLLECTOR_SHUTDOWN_REQUESTED")
        self.request_count = self.consumed_attempts()
        if self.request_count >= self.config.request_budget:
            raise Stage7ILifecycleError("REQUEST_BUDGET_EXHAUSTED")
        self.request_count += 1
        response = self.client.request_live(endpoint, params)
        quota = parse_api_football_quota(
            headers=response.headers,
            payload=response.payload,
            observed_at=response.captured_at,
        )
        self.remaining_quota = quota.daily_remaining
        raw_hash, raw_path = write_raw_once(self.raw_dir, endpoint, response.payload)
        append_jsonl_once(
            self.lifecycle_dir / "request_audit.jsonl",
            {
                "event_id": stable_event_id("request", endpoint, params, raw_hash),
                "endpoint": endpoint,
                "params": dict(params),
                "fixture_id": self.config.fixture_id,
                "status_code": response.status_code,
                "elapsed_ms": response.elapsed_ms,
                "captured_at_utc": iso(response.captured_at),
                "remaining_quota": self.remaining_quota,
                "daily_remaining": quota.daily_remaining,
                "burst_remaining": quota.burst_remaining,
                "quota_observed_at": iso(quota.observed_at),
                "daily_source": quota.daily_source,
                "burst_source": quota.burst_source,
                "raw_payload_sha256": raw_hash,
                "raw_path": str(raw_path),
                "candidate": False,
                "formal_recommendation": False,
            },
        )
        if response.status_code in {401, 403}:
            raise Stage7ILifecycleError(f"PROVIDER_HTTP_{response.status_code}")
        if response.status_code == 429:
            self.blockers.append("PROVIDER_HTTP_429")
            raise Stage7ILifecycleError("PROVIDER_HTTP_429")
        if response.status_code >= 400:
            self.blockers.append(f"PROVIDER_HTTP_{response.status_code}")
            raise Stage7ILifecycleError(f"PROVIDER_HTTP_{response.status_code}")
        if self.remaining_quota is None:
            self.blockers.append("DAILY_QUOTA_UNKNOWN")
            raise Stage7ILifecycleError("DAILY_QUOTA_UNKNOWN")
        if self.remaining_quota < self.config.quota_reserve:
            self.blockers.append("QUOTA_BELOW_RESERVE")
            raise Stage7ILifecycleError("QUOTA_BELOW_RESERVE")
        return response

    def _record_fixture_status(self, response: LiveApiFootballResponse) -> int:
        payload_hash = sha256_payload(response.payload)
        actual, actual_source = provider_actual_kickoff(response.payload)
        status = fixture_status(response.payload)
        state = self._state_from_status(status)
        category = "FORWARD" if state == "PREMATCH" else "RETROSPECTIVE"
        event = {
            "event_id": stable_event_id("fixture_status", self.config.fixture_id, payload_hash),
            "fixture_id": self.config.fixture_id,
            "event_time_utc": iso(response.captured_at),
            "captured_at_utc": iso(response.captured_at),
            "provider_status": status,
            "provider_fixture_date": self._provider_fixture_date(response.payload),
            "actual_kickoff_utc": iso(actual) if actual else None,
            "actual_kickoff_source": actual_source,
            "raw_payload_sha256": payload_hash,
            "state": state,
            "evidence_category": category,
            "candidate": False,
            "formal_recommendation": False,
        }
        return int(append_jsonl_once(self.lifecycle_dir / "fixture_status.jsonl", event))

    def _record_market(self, response: LiveApiFootballResponse, *, state: str) -> int:
        payload_hash = sha256_payload(response.payload)
        count = bookmaker_count(response.payload)
        live_or_suspended = has_live_or_suspended_market(response.payload)
        if state != "PREMATCH" or live_or_suspended:
            return 0
        event = {
            "event_id": stable_event_id("market", self.config.fixture_id, payload_hash),
            "fixture_id": self.config.fixture_id,
            "event_time_utc": iso(response.captured_at),
            "captured_at_utc": iso(response.captured_at),
            "provider_updated_at_utc": self._provider_market_updated_at(response.payload),
            "bookmaker_count": count,
            "state": state,
            "live": live_or_suspended,
            "suspended": live_or_suspended,
            "raw_payload_sha256": payload_hash,
            "evidence_category": "FORWARD",
            "candidate": False,
            "formal_recommendation": False,
        }
        return int(append_jsonl_once(self.lifecycle_dir / "market_observations.jsonl", event))

    def _record_result_status(self, response: LiveApiFootballResponse) -> int:
        payload_hash = sha256_payload(response.payload)
        status = fixture_status(response.payload)
        state = self._state_from_status(status)
        event = {
            "event_id": stable_event_id("result_status", self.config.fixture_id, payload_hash),
            "fixture_id": self.config.fixture_id,
            "event_time_utc": iso(response.captured_at),
            "captured_at_utc": iso(response.captured_at),
            "provider_status": status,
            "confirmed": status in FINAL_STATUS,
            "raw_payload_sha256": payload_hash,
            "state": state,
            "evidence_category": "RETROSPECTIVE",
            "candidate": False,
            "formal_recommendation": False,
        }
        return int(append_jsonl_once(self.lifecycle_dir / "result_status.jsonl", event))

    def _provider_fixture_date(self, payload: dict[str, Any]) -> str | None:
        for item in fixture_items(payload):
            value = item.get("fixture", {}).get("date")
            return str(value) if value else None
        return None

    def _provider_market_updated_at(self, payload: dict[str, Any]) -> str | None:
        timestamps: list[datetime] = []
        for item in fixture_items(payload):
            for field in ("update", "updated_at", "last_update"):
                parsed = parse_utc(item.get(field))
                if parsed:
                    timestamps.append(parsed)
            for bookmaker in item.get("bookmakers", []) if isinstance(item, dict) else []:
                parsed = parse_utc(bookmaker.get("update") if isinstance(bookmaker, dict) else None)
                if parsed:
                    timestamps.append(parsed)
        return iso(max(timestamps)) if timestamps else None


def resolve_actual_kickoff(fixture_events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in fixture_events:
        actual = parse_utc(event.get("actual_kickoff_utc"))
        if actual and event.get("actual_kickoff_source"):
            return {
                "status": "CONFIRMED_INTERNAL",
                "actual_kickoff_utc": iso(actual),
                "source": event["actual_kickoff_source"],
                "evidence_event_id": event["event_id"],
            }
    return {
        "status": "ACTUAL_KICKOFF_SOURCE_UNAVAILABLE",
        "actual_kickoff_utc": None,
        "source": None,
        "evidence_event_id": None,
    }


def resolve_closing(
    market_events: list[dict[str, Any]],
    *,
    actual_kickoff_utc: datetime | None,
) -> dict[str, Any]:
    if actual_kickoff_utc is None:
        return {"status": "PENDING_ACTUAL_KICKOFF", "selected_observation_id": None}
    eligible = []
    for event in market_events:
        captured = parse_utc(event.get("captured_at_utc"))
        if captured is None or captured >= actual_kickoff_utc:
            continue
        if event.get("live") is True or event.get("suspended") is True:
            continue
        if int(event.get("bookmaker_count") or 0) <= 0:
            continue
        if not event.get("raw_payload_sha256"):
            continue
        eligible.append((captured, event))
    if not eligible:
        return {"status": "NO_ELIGIBLE_CLOSING_OBSERVATION", "selected_observation_id": None}
    _, selected = max(eligible, key=lambda item: item[0])
    return {
        "status": "RESOLVED_INTERNAL",
        "selected_observation_id": selected["event_id"],
        "captured_at_utc": selected["captured_at_utc"],
        "provider_updated_at_utc": selected.get("provider_updated_at_utc"),
        "bookmaker_count": selected.get("bookmaker_count"),
        "raw_payload_sha256": selected.get("raw_payload_sha256"),
        "resolution_reason": "LAST_PRE_ACTUAL_KICKOFF_NON_LIVE_NON_SUSPENDED_MARKET",
    }


def build_final_evidence(runtime_dir: Path, *, expected_fixture_id: str) -> dict[str, Any]:
    start = load_json(runtime_dir / "start.json", {})
    summary = load_json(runtime_dir / "summary.json", {})
    lifecycle = runtime_dir / "lifecycle"
    fixture_events = read_jsonl(lifecycle / "fixture_status.jsonl")
    market_events = read_jsonl(lifecycle / "market_observations.jsonl")
    result_events = read_jsonl(lifecycle / "result_status.jsonl")
    actual = resolve_actual_kickoff(fixture_events)
    actual_dt = parse_utc(actual.get("actual_kickoff_utc"))
    closing = resolve_closing(market_events, actual_kickoff_utc=actual_dt)
    started = parse_utc(start.get("observer_started_at_utc") or start.get("started_at_utc"))
    completed = parse_utc(summary.get("completed_at_utc"))
    status = "IN_PROGRESS"
    blockers: list[str] = []
    if completed is not None and started is not None:
        if completed - started >= timedelta(hours=24):
            status = "COMPLETED"
        else:
            blockers.append("OBSERVATION_DURATION_LT_24H")
    else:
        blockers.append("OBSERVER_SUMMARY_NOT_COMPLETE")
    if actual["status"] != "CONFIRMED_INTERNAL":
        blockers.append("ACTUAL_KICKOFF_SOURCE_UNAVAILABLE")
    if closing["status"] != "RESOLVED_INTERNAL":
        blockers.append(str(closing["status"]))
    if status == "COMPLETED" and blockers:
        status = "BLOCKED"
    evidence_events = fixture_events + market_events + result_events
    evidence_events.sort(key=lambda item: str(item.get("event_time_utc", "")))
    observer_started = start.get("observer_started_at_utc") or start.get("started_at_utc")
    return {
        "status": status,
        "fixture_id": expected_fixture_id,
        "observer_started_at_utc": observer_started,
        "completed_at_utc": summary.get("completed_at_utc"),
        "stable_revision": summary.get("stable_revision", False),
        "actual_kickoff_status": actual["status"],
        "actual_kickoff_utc": actual.get("actual_kickoff_utc"),
        "actual_kickoff_source": actual.get("source"),
        "closing_status": closing["status"],
        "closing_observation_utc": closing.get("captured_at_utc"),
        "closing_evidence": closing,
        "forward_retrospective_separated": all(
            event.get("evidence_category") in {"FORWARD", "RETROSPECTIVE"}
            for event in evidence_events
        ),
        "settlement_evaluation_legal": not any(
            event.get("evidence_category") == "FORWARD"
            and str(event.get("event_id", "")).startswith("settlement")
            for event in evidence_events
        ),
        "final_shadow_db_audit": summary.get("final_shadow_db_audit", "PENDING"),
        "evidence_events": evidence_events,
        "blockers": blockers,
        "candidate": False,
        "formal_recommendation": False,
    }
