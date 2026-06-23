from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from w2.ingestion.retry import CircuitBreaker, RetryPolicy, call_with_retry
from w2.providers.api_football import ApiFootballClient, LiveApiFootballResponse


class FutureRefreshError(RuntimeError):
    pass


class LiveApiFootballPort(Protocol):
    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        pass


@dataclass(frozen=True)
class FutureRefreshConfig:
    runtime_root: Path = Path("runtime/future_refresh")
    league_id: str = "1"
    season: str = "2026"
    horizon_days: int = 4
    max_fixture_candidates: int = 20
    max_odds_requests: int = 10
    quota_reserve: int = 1500
    market_freshness_seconds: int = 3600
    request_budget: int = 40


@dataclass(frozen=True)
class FutureRefreshResult:
    generated_at_utc: datetime
    fixture_count: int
    mapping_count: int
    market_snapshot_count: int
    request_count: int
    remaining_quota: int | None
    selected_market_fixture_ids: list[str]
    blockers: list[str] = field(default_factory=list)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def write_raw_once(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        write_json_atomic(path, payload)


def parse_provider_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def provider_remaining_quota(response: LiveApiFootballResponse) -> int | None:
    for key in (
        "x-ratelimit-requests-remaining",
        "X-RateLimit-Requests-Remaining",
        "x-ratelimit-remaining",
    ):
        value = response.headers.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except ValueError:
            continue
    try:
        return int(response.payload["response"]["requests"]["remaining"])
    except (KeyError, TypeError, ValueError):
        return None


def response_count(payload: dict[str, Any]) -> int:
    response = payload.get("response")
    return len(response) if isinstance(response, list) else 0


def bookmaker_count(payload: dict[str, Any]) -> int:
    total = 0
    response = payload.get("response")
    if not isinstance(response, list):
        return total
    for entry in response:
        bookmakers = entry.get("bookmakers", []) if isinstance(entry, dict) else []
        if isinstance(bookmakers, list):
            total += len(bookmakers)
    return total


def fixture_id_from_payload(item: dict[str, Any]) -> str:
    return str(item.get("fixture", {}).get("id") or "")


def kickoff_from_payload(item: dict[str, Any]) -> datetime | None:
    return parse_provider_datetime(item.get("fixture", {}).get("date"))


class FutureFixtureRefreshService:
    def __init__(
        self,
        *,
        client: LiveApiFootballPort | None = None,
        config: FutureRefreshConfig | None = None,
        now: datetime | None = None,
        sleep: Any | None = None,
    ) -> None:
        self.client = client or ApiFootballClient(allow_live=True)
        self.config = config or FutureRefreshConfig()
        self.now = now or utc_now()
        self.sleep = sleep or time.sleep
        self._request_count = 0
        self._latest_remaining: int | None = None
        self._audit: list[dict[str, Any]] = []
        self._breaker = CircuitBreaker(failure_threshold=3)
        self._retry = RetryPolicy(max_attempts=3, base_delay_seconds=0.2, multiplier=2.0)

    def run(self) -> FutureRefreshResult:
        blockers: list[str] = []
        try:
            self._request("status", {})
            fixtures_response = self._request(
                "fixtures",
                {
                    "league": self.config.league_id,
                    "season": self.config.season,
                    "from": self.now.date().isoformat(),
                    "to": (self.now + timedelta(days=self.config.horizon_days)).date().isoformat(),
                },
            )
            future_fixtures = self._future_fixtures(fixtures_response.payload)
            odds_responses = self._fetch_market_snapshots(future_fixtures)
            result = self._persist(fixtures_response, future_fixtures, odds_responses, blockers)
        except FutureRefreshError as exc:
            blockers.append(str(exc))
            result = FutureRefreshResult(
                generated_at_utc=self.now,
                fixture_count=0,
                mapping_count=0,
                market_snapshot_count=0,
                request_count=self._request_count,
                remaining_quota=self._latest_remaining,
                selected_market_fixture_ids=[],
                blockers=blockers,
            )
            self._write_failure(result)
        return result

    def _request(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        if self._request_count >= self.config.request_budget:
            raise FutureRefreshError("REQUEST_BUDGET_EXHAUSTED")

        def op() -> LiveApiFootballResponse:
            return self.client.request_live(endpoint, params)

        response = call_with_retry(op, self._retry, self._breaker, sleep=self.sleep)
        self._request_count += 1
        remaining = provider_remaining_quota(response)
        self._latest_remaining = remaining
        payload_hash = sha256_payload(response.payload)
        self._audit.append(
            {
                "endpoint": endpoint,
                "params": params,
                "status_code": response.status_code,
                "elapsed_ms": response.elapsed_ms,
                "captured_at_utc": iso(response.captured_at),
                "remaining_quota": remaining,
                "response_count": response_count(response.payload),
                "payload_sha256": payload_hash,
            }
        )
        if response.status_code in {401, 403, 429}:
            raise FutureRefreshError(f"PROVIDER_HTTP_{response.status_code}")
        if remaining is None:
            raise FutureRefreshError("PROVIDER_REMAINING_QUOTA_UNKNOWN")
        if remaining < self.config.quota_reserve:
            raise FutureRefreshError("QUOTA_BELOW_RESERVE")
        return response

    def _future_fixtures(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        response = payload.get("response")
        if not isinstance(response, list):
            return []
        rows: list[dict[str, Any]] = []
        for item in response:
            if not isinstance(item, dict):
                continue
            status = item.get("fixture", {}).get("status", {}).get("short")
            kickoff = kickoff_from_payload(item)
            if status != "NS" or kickoff is None or kickoff <= self.now:
                continue
            rows.append(item)
        rows.sort(key=lambda item: kickoff_from_payload(item) or datetime.max.replace(tzinfo=UTC))
        return rows[: self.config.max_fixture_candidates]

    def _fetch_market_snapshots(
        self,
        fixtures: list[dict[str, Any]],
    ) -> list[tuple[str, LiveApiFootballResponse]]:
        odds: list[tuple[str, LiveApiFootballResponse]] = []
        for item in fixtures[: self.config.max_odds_requests]:
            fixture_id = fixture_id_from_payload(item)
            if not fixture_id:
                continue
            response = self._request("odds", {"fixture": fixture_id})
            if bookmaker_count(response.payload) > 0:
                odds.append((fixture_id, response))
        return odds

    def _persist(
        self,
        fixtures_response: LiveApiFootballResponse,
        fixtures: list[dict[str, Any]],
        odds_responses: list[tuple[str, LiveApiFootballResponse]],
        blockers: list[str],
    ) -> FutureRefreshResult:
        raw_dir = self.config.runtime_root / "raw"
        read_model = self.config.runtime_root / "read_model"
        write_raw_once(
            raw_dir / f"fixtures_{sha256_payload(fixtures_response.payload)}.json",
            {"payload": fixtures_response.payload, "audit": self._audit[1]},
        )
        for fixture_id, response in odds_responses:
            write_raw_once(
                raw_dir / f"odds_{fixture_id}_{sha256_payload(response.payload)}.json",
                {"payload": response.payload, "audit": self._audit[-1]},
            )
        mappings = [self._mapping_from_fixture(item) for item in fixtures]
        markets = [
            self._market_snapshot_from_odds(fixture_id, response)
            for fixture_id, response in odds_responses
        ]
        write_json_atomic(read_model / "fixtures.json", {"items": fixtures})
        write_json_atomic(read_model / "provider_mappings.json", {"items": mappings})
        write_json_atomic(read_model / "market_snapshots.json", markets)
        provider_status = {
            "provider": "api_football",
            "status": "READY",
            "remaining_quota": self._latest_remaining,
            "credential_status": "PRESENT",
            "last_request_status": self._audit[-1]["status_code"] if self._audit else None,
            "last_successful_request_at": (
                self._audit[-1]["captured_at_utc"] if self._audit else None
            ),
        }
        write_json_atomic(read_model / "provider_status.json", provider_status)
        result = FutureRefreshResult(
            generated_at_utc=self.now,
            fixture_count=len(fixtures),
            mapping_count=len(mappings),
            market_snapshot_count=len(markets),
            request_count=self._request_count,
            remaining_quota=self._latest_remaining,
            selected_market_fixture_ids=[fixture_id for fixture_id, _ in odds_responses],
            blockers=blockers,
        )
        self._write_audit(result)
        return result

    def _mapping_from_fixture(self, item: dict[str, Any]) -> dict[str, Any]:
        teams = item.get("teams", {})
        fixture_id = fixture_id_from_payload(item)
        return {
            "fixture_id": fixture_id,
            "provider": "api_football",
            "provider_fixture_id": fixture_id,
            "home_provider_team_id": str((teams.get("home") or {}).get("id") or ""),
            "away_provider_team_id": str((teams.get("away") or {}).get("id") or ""),
            "source": "future_fixture_refresh",
            "confidence": 1.0,
            "reliable": True,
            "conflict": False,
            "evidence_sha256": sha256_payload(item),
        }

    def _market_snapshot_from_odds(
        self,
        fixture_id: str,
        response: LiveApiFootballResponse,
    ) -> dict[str, Any]:
        captured_at = iso(response.captured_at)
        quality = "READY" if bookmaker_count(response.payload) > 0 else "MARKET_NOT_COMPARABLE"
        return {
            "fixture_id": fixture_id,
            "captured_at": captured_at,
            "captured_at_utc": captured_at,
            "snapshot_semantics": "CAPTURED_AT",
            "bookmaker_count": bookmaker_count(response.payload),
            "quality": quality,
            "source": "future_fixture_refresh",
            "provenance": {
                "provider": "api_football",
                "endpoint": "odds",
                "payload_sha256": sha256_payload(response.payload),
            },
            "freshness_limit_seconds": self.config.market_freshness_seconds,
            "candidate": False,
            "formal_recommendation": False,
        }

    def _write_audit(self, result: FutureRefreshResult) -> None:
        write_json_atomic(
            self.config.runtime_root / "future_refresh_audit.json",
            {
                "generated_at_utc": iso(result.generated_at_utc),
                "request_count": result.request_count,
                "remaining_quota": result.remaining_quota,
                "fixture_count": result.fixture_count,
                "mapping_count": result.mapping_count,
                "market_snapshot_count": result.market_snapshot_count,
                "selected_market_fixture_ids": result.selected_market_fixture_ids,
                "blockers": result.blockers,
                "requests": self._audit,
                "candidate": False,
                "formal_recommendation": False,
            },
        )

    def _write_failure(self, result: FutureRefreshResult) -> None:
        self._write_audit(result)


def run_future_fixture_refresh(
    *,
    runtime_root: Path | None = None,
    client: LiveApiFootballPort | None = None,
    now: datetime | None = None,
) -> FutureRefreshResult:
    config = FutureRefreshConfig(runtime_root=runtime_root or FutureRefreshConfig().runtime_root)
    return FutureFixtureRefreshService(client=client, config=config, now=now).run()
