from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError

from w2.competitions.registry import CompetitionRegistry, CompetitionRegistryError
from w2.config import Settings, get_settings
from w2.ingestion.future_refresh_repository import (
    FutureRefreshDbRepository,
    FutureRefreshPersistenceError,
)
from w2.markets.asian_handicap_scope import canonical_market_from_label
from w2.providers.api_football import ApiFootballClient, LiveApiFootballResponse
from w2.providers.control import (
    env_int,
    provider_endpoint_allowlist,
    provider_http_max_attempts,
    provider_refresh_tick_hard_cap,
)
from w2.providers.quota import (
    parse_api_football_quota,
    provider_daily_hard_cap_decision,
    quota_guard_decision,
)


class FutureRefreshError(RuntimeError):
    pass


class RefreshLockError(RuntimeError):
    pass


class LiveApiFootballPort(Protocol):
    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        pass


@dataclass(frozen=True)
class CompetitionRefreshPolicy:
    competition_id: str
    provider_league_id: str
    season: str
    horizon_days: int
    scheduler_interval_seconds: int
    quota_reserve: int
    request_budget: int
    feature_enrichment_enabled: bool
    feature_enrichment_endpoints: tuple[str, ...]
    feature_enrichment_request_budget: int
    max_fixture_candidates: int
    max_odds_requests: int
    market_freshness_seconds: int
    enabled: bool
    daily_hard_cap: int
    daily_reserve: int
    daily_usage_scope: str
    checkpoint_mode: str
    trickle_backfill_daily_budget: int


@dataclass(frozen=True)
class FutureRefreshConfig:
    runtime_root: Path = Path("runtime/future_refresh")
    competition_id: str = "world_cup_2026"
    league_id: str = "1"
    season: str = "2026"
    horizon_days: int = 4
    max_fixture_candidates: int = 20
    max_odds_requests: int = 20
    quota_reserve: int = 1500
    market_freshness_seconds: int = 3600
    request_budget: int = 40
    feature_enrichment_enabled: bool = False
    feature_enrichment_endpoints: tuple[str, ...] = ("statistics", "lineups", "injuries")
    feature_enrichment_request_budget: int = 0
    scheduler_interval_seconds: int = 900
    source_revision: str = "LOCAL_UNDEPLOYED"
    enabled: bool = True
    persistence: str = "db"
    daily_hard_cap: int = 7500
    daily_reserve: int = 1500
    daily_usage_scope: str = "w2_ledger"
    checkpoint_mode: str = "matchday_intake_v2_compatibility"
    trickle_backfill_daily_budget: int = 0
    actual_provider_calls_today: int | None = None
    provider_refresh_batch_size: int = 3
    checkpoint_fixture_ids: tuple[str, ...] = ()
    refresh_checkpoints: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class FutureRefreshResult:
    generated_at_utc: datetime
    fixture_count: int
    mapping_count: int
    market_snapshot_count: int
    feature_enrichment_payload_count: int
    ledger_appended_count: int
    request_count: int
    remaining_quota: int | None
    selected_market_fixture_ids: list[str]
    blockers: list[str] = field(default_factory=list)
    status: str = "COMPLETED"
    raw_payload_written_count: int = 0
    error_code: str | None = None
    materialized_fixture_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RefreshTaskAudit:
    task_id: str
    key: str
    owner: str
    queued_at: str
    started_at: str
    finished_at: str
    status: str
    result: dict[str, Any]


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_raw_once(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        write_json_atomic(path, payload)


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
    return parse_utc(item.get("fixture", {}).get("date"))


def sanitize_params(params: dict[str, str]) -> dict[str, str]:
    blocked = {"key", "api_key", "token", "password", "authorization"}
    return {key: ("REDACTED" if key.lower() in blocked else value) for key, value in params.items()}


def load_refresh_policy(
    *,
    competition_id: str,
    policy_path: Path = Path("config/policies/future_fixture_refresh.v1.json"),
) -> CompetitionRefreshPolicy:
    try:
        CompetitionRegistry().require_enabled(competition_id)
    except CompetitionRegistryError as exc:
        raise FutureRefreshError(str(exc)) from exc
    payload = load_json(policy_path, {})
    competitions = payload.get("competitions")
    if not isinstance(competitions, list):
        raise FutureRefreshError("FUTURE_REFRESH_POLICY_INVALID")
    for item in competitions:
        if not isinstance(item, dict) or item.get("competition_id") != competition_id:
            continue
        required = {
            "provider_league_id": str,
            "season": str,
            "horizon_days": int,
            "scheduler_interval_seconds": int,
            "quota_reserve": int,
            "request_budget": int,
            "max_fixture_candidates": int,
            "max_odds_requests": int,
            "market_freshness_seconds": int,
            "enabled": bool,
        }
        for field_name, field_type in required.items():
            if not isinstance(item.get(field_name), field_type):
                raise FutureRefreshError(f"FUTURE_REFRESH_POLICY_FIELD_INVALID:{field_name}")
        enrichment_endpoints = item.get("feature_enrichment_endpoints", [])
        if not isinstance(enrichment_endpoints, list) or not all(
            isinstance(endpoint, str) for endpoint in enrichment_endpoints
        ):
            raise FutureRefreshError(
                "FUTURE_REFRESH_POLICY_FIELD_INVALID:feature_enrichment_endpoints"
            )
        quota_reserve = int(item["quota_reserve"])
        return CompetitionRefreshPolicy(
            competition_id=competition_id,
            provider_league_id=item["provider_league_id"],
            season=item["season"],
            horizon_days=item["horizon_days"],
            scheduler_interval_seconds=item["scheduler_interval_seconds"],
            quota_reserve=quota_reserve,
            request_budget=item["request_budget"],
            feature_enrichment_enabled=bool(item.get("feature_enrichment_enabled") is True),
            feature_enrichment_endpoints=tuple(enrichment_endpoints),
            feature_enrichment_request_budget=int(item.get("feature_enrichment_request_budget", 0)),
            max_fixture_candidates=item["max_fixture_candidates"],
            max_odds_requests=item["max_odds_requests"],
            market_freshness_seconds=item["market_freshness_seconds"],
            enabled=item["enabled"],
            daily_hard_cap=int(item.get("daily_hard_cap", 7500)),
            daily_reserve=int(item.get("daily_reserve", quota_reserve)),
            daily_usage_scope=str(item.get("daily_usage_scope", "provider_quota")),
            checkpoint_mode=str(item.get("checkpoint_mode", "matchday_intake_v2_compatibility")),
            trickle_backfill_daily_budget=int(item.get("trickle_backfill_daily_budget", 0)),
        )
    raise FutureRefreshError("FUTURE_REFRESH_COMPETITION_NOT_REGISTERED")


def config_from_policy(
    *,
    competition_id: str = "world_cup_2026",
    runtime_root: Path | None = None,
    policy_path: Path = Path("config/policies/future_fixture_refresh.v1.json"),
) -> FutureRefreshConfig:
    policy = load_refresh_policy(competition_id=competition_id, policy_path=policy_path)
    return FutureRefreshConfig(
        runtime_root=runtime_root or FutureRefreshConfig().runtime_root,
        competition_id=policy.competition_id,
        league_id=policy.provider_league_id,
        season=policy.season,
        horizon_days=policy.horizon_days,
        max_fixture_candidates=policy.max_fixture_candidates,
        max_odds_requests=policy.max_odds_requests,
        quota_reserve=policy.quota_reserve,
        market_freshness_seconds=policy.market_freshness_seconds,
        request_budget=policy.request_budget,
        feature_enrichment_enabled=policy.feature_enrichment_enabled,
        feature_enrichment_endpoints=policy.feature_enrichment_endpoints,
        feature_enrichment_request_budget=policy.feature_enrichment_request_budget,
        scheduler_interval_seconds=policy.scheduler_interval_seconds,
        enabled=policy.enabled,
        persistence=os.environ.get("W2_FUTURE_REFRESH_PERSISTENCE", "db").lower(),
        daily_hard_cap=policy.daily_hard_cap,
        daily_reserve=policy.daily_reserve,
        daily_usage_scope=policy.daily_usage_scope,
        checkpoint_mode=policy.checkpoint_mode,
        trickle_backfill_daily_budget=policy.trickle_backfill_daily_budget,
    )


class RefreshSingletonLock:
    def __init__(
        self,
        *,
        key: str,
        owner: str,
        ttl_seconds: int = 900,
        settings: Settings | None = None,
        runtime_root: Path = Path("runtime/future_refresh"),
        redis_client: Any | None = None,
    ) -> None:
        self.key = key
        self.owner = owner
        self.ttl_seconds = ttl_seconds
        self.settings = settings or get_settings()
        self.runtime_root = runtime_root
        self.redis_client = redis_client
        self._backend = "file"

    def acquire(self, *, now: datetime | None = None) -> bool:
        redis_client = self._redis()
        if redis_client is not None:
            self._backend = "redis"
            try:
                return bool(redis_client.set(self.key, self.owner, nx=True, ex=self.ttl_seconds))
            except RedisError:
                return False
        current = now or utc_now()
        lock_path = self._file_lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            raw = handle.read().strip()
            if raw:
                try:
                    payload = json.loads(raw)
                    expires_at = parse_utc(payload.get("expires_at_utc"))
                    if expires_at and expires_at > current:
                        return False
                except json.JSONDecodeError:
                    return False
            handle.seek(0)
            handle.truncate()
            handle.write(
                json.dumps(
                    {
                        "key": self.key,
                        "owner": self.owner,
                        "expires_at_utc": iso(current + timedelta(seconds=self.ttl_seconds)),
                    },
                    sort_keys=True,
                )
            )
            handle.flush()
            os.fsync(handle.fileno())
            return True

    def release(self) -> bool:
        redis_client = self._redis()
        if redis_client is not None:
            self._backend = "redis"
            script = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            end
            return 0
            """
            try:
                return bool(redis_client.eval(script, 1, self.key, self.owner))
            except RedisError:
                return False
        lock_path = self._file_lock_path()
        if not lock_path.exists():
            return False
        with lock_path.open("r+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                payload = json.loads(handle.read() or "{}")
            except json.JSONDecodeError:
                return False
            if payload.get("owner") != self.owner:
                return False
            handle.seek(0)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
            return True

    @property
    def backend(self) -> str:
        return self._backend

    def _redis(self) -> Any | None:
        if self.redis_client is not None:
            return self.redis_client
        if self.settings.redis_url is None:
            return None
        self.redis_client = Redis.from_url(
            self.settings.redis_url.get_secret_value(),
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        return self.redis_client

    def _file_lock_path(self) -> Path:
        digest = hashlib.sha256(self.key.encode("utf-8")).hexdigest()[:24]
        return self.runtime_root / "locks" / f"{digest}.lock"


class MarketObservationLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")

    def append_observations(self, observations: list[dict[str, Any]]) -> int:
        if not observations:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            existing = self._existing_ids_unlocked()
            new_rows = [row for row in observations if row["observation_id"] not in existing]
            if not new_rows:
                return 0
            with self.path.open("a", encoding="utf-8") as handle:
                for row in new_rows:
                    handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return len(new_rows)

    def read_observations(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def _existing_ids_unlocked(self) -> set[str]:
        return {str(row.get("observation_id")) for row in self.read_observations()}


def canonical_market(raw_label: str) -> str:
    return canonical_market_from_label(raw_label)


def parse_line(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    split = _split_line_value(value)
    if split is not None:
        return f"{split:g}"
    parts = value.replace("+", " +").replace("-", " -").split()
    for part in reversed(parts):
        try:
            float(part)
        except ValueError:
            continue
        return part
    return None


def _split_line_value(value: str) -> float | None:
    # API-Football can emit Asian split lines like "Over 2/2.5" or "Home -0/0.5".
    # Treat these as quarter lines instead of silently binding the price to the
    # second half of the split.
    match = re.search(
        r"(?P<left>[+-]?\d+(?:\.\d+)?)\s*(?:/|(?:\s+-\s+))\s*(?P<right>[+-]?\d+(?:\.\d+)?)\s*$",
        value.strip(),
    )
    if match is None:
        return None
    left_raw = match.group("left")
    right_raw = match.group("right")
    try:
        left = float(left_raw)
        right = float(right_raw)
    except ValueError:
        return None
    if right_raw[0] not in "+-" and left_raw.startswith("-"):
        right = -abs(right)
    elif right_raw[0] not in "+-" and left_raw.startswith("+"):
        right = abs(right)
    return (left + right) / 2


def parse_decimal(value: Any) -> str | None:
    if value is None:
        return None
    try:
        parsed = float(str(value))
    except ValueError:
        return None
    if parsed <= 1:
        return None
    return f"{parsed:.6g}"


def observations_from_odds_payload(
    *,
    fixture_id: str,
    payload: dict[str, Any],
    response: LiveApiFootballResponse,
    source_revision: str,
    raw_payload_sha256: str | None = None,
) -> list[dict[str, Any]]:
    raw_hash = raw_payload_sha256 or sha256_payload(payload)
    captured_at = iso(response.captured_at)
    rows: list[dict[str, Any]] = []
    provider_updated = captured_at
    for entry in payload.get("response", []):
        if not isinstance(entry, dict):
            continue
        provider_updated = (
            entry.get("update")
            or entry.get("fixture", {}).get("timestamp")
            or entry.get("fixture", {}).get("date")
            or captured_at
        )
        for bookmaker in entry.get("bookmakers", []) or []:
            bookmaker_id = str(bookmaker.get("id") or "")
            bookmaker_name = str(bookmaker.get("name") or "")
            for bet in bookmaker.get("bets", []) or []:
                bet_id = str(bet.get("id") or "")
                raw_market = str(bet.get("name") or bet_id)
                market = canonical_market(raw_market)
                for value in bet.get("values", []) or []:
                    selection = str(value.get("value") or "")
                    decimal_odds = parse_decimal(value.get("odd"))
                    if not selection or decimal_odds is None:
                        continue
                    line = parse_line(selection)
                    identity = {
                        "provider": "api_football",
                        "fixture_id": fixture_id,
                        "bookmaker_id": bookmaker_id,
                        "bet_id": bet_id,
                        "selection": selection,
                        "line": line,
                        "decimal_odds": decimal_odds,
                        "raw_payload_sha256": raw_hash,
                        # A quote observed again in a later provider response is a
                        # new authoritative capture even when its business value
                        # and payload hash are unchanged. Keeping the response
                        # timestamp in the identity preserves append-only history
                        # while replaying the same response remains idempotent.
                        "captured_at": captured_at,
                    }
                    observation_id = sha256_payload(identity)
                    rows.append(
                        {
                            "observation_id": observation_id,
                            "fixture_id": fixture_id,
                            "provider": "api_football",
                            "bookmaker_id": bookmaker_id,
                            "bookmaker_name": bookmaker_name,
                            "provider_bet_id": bet_id,
                            "raw_market_label": raw_market,
                            "canonical_market": market,
                            "selection": selection,
                            "line": line,
                            "decimal_odds": decimal_odds,
                            "suspended": False,
                            "live": False,
                            "provider_last_update": str(provider_updated),
                            "captured_at": captured_at,
                            "ingested_at": iso(utc_now()),
                            "raw_payload_sha256": raw_hash,
                            "source_revision": source_revision,
                            "candidate": False,
                            "formal_recommendation": False,
                        }
                    )
    return rows


def project_ledger_to_read_model(
    *,
    ledger: MarketObservationLedger,
    read_model_dir: Path,
) -> list[dict[str, Any]]:
    observations = ledger.read_observations()
    latest: dict[tuple[str, str, str, str, str | None], dict[str, Any]] = {}
    for row in observations:
        key = (
            str(row.get("fixture_id")),
            str(row.get("canonical_market")),
            str(row.get("bookmaker_id")),
            str(row.get("selection")),
            row.get("line"),
        )
        current = latest.get(key)
        if current is None or str(row.get("captured_at")) > str(current.get("captured_at")):
            latest[key] = row
    latest_rows = sorted(
        latest.values(),
        key=lambda row: (
            str(row.get("fixture_id")),
            str(row.get("captured_at")),
            str(row.get("canonical_market")),
            str(row.get("bookmaker_id")),
            str(row.get("selection")),
        ),
    )
    coverage: dict[str, dict[str, Any]] = {}
    for row in latest_rows:
        fixture_id = str(row.get("fixture_id"))
        item = coverage.setdefault(
            fixture_id,
            {"fixture_id": fixture_id, "markets": {}, "bookmaker_count": 0},
        )
        item["markets"][str(row.get("canonical_market"))] = True
        item["bookmaker_count"] = len(
            {
                str(candidate.get("bookmaker_id"))
                for candidate in latest_rows
                if str(candidate.get("fixture_id")) == fixture_id
            }
        )
    write_json_atomic(read_model_dir / "latest_market_observations.json", latest_rows)
    write_json_atomic(read_model_dir / "market_coverage.json", {"items": list(coverage.values())})
    return latest_rows


class FutureFixtureRefreshService:
    def __init__(
        self,
        *,
        client: LiveApiFootballPort | None = None,
        config: FutureRefreshConfig | None = None,
        now: datetime | None = None,
        sleep: Any | None = None,
        materialize_public_artifacts: Callable[[list[str]], list[str]] | None = None,
    ) -> None:
        self.config = config or config_from_policy()
        self.client = client or ApiFootballClient(
            allow_live=True,
            allowed_live_endpoints=self._allowed_live_endpoints(self.config),
        )
        self.now = now or utc_now()
        self.sleep = sleep or time.sleep
        self.materialize_public_artifacts = materialize_public_artifacts
        self._attempt_count = 0
        self._latest_remaining: int | None = None
        self._audit: list[dict[str, Any]] = []
        self._odds_request_fixture_ids: list[str] = []
        self._raw_payload_written: set[str] = set()
        self._raw_payload_written_count = 0
        self._feature_enrichment_batch_count = 0
        self._matchday_capture_by_payload: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    def _db_repository(self) -> FutureRefreshDbRepository:
        return FutureRefreshDbRepository()

    def _allowed_live_endpoints(self, config: FutureRefreshConfig) -> frozenset[str]:
        base = {"status", "fixtures", "odds"}
        enrichment = (
            set(config.feature_enrichment_endpoints) if config.feature_enrichment_enabled else set()
        )
        configured = base | (enrichment & {"statistics", "lineups", "injuries"})
        return frozenset(configured & set(provider_endpoint_allowlist()))

    def run(self) -> FutureRefreshResult:
        blockers: list[str] = []
        if not self.config.enabled:
            result = FutureRefreshResult(
                generated_at_utc=self.now,
                fixture_count=0,
                mapping_count=0,
                market_snapshot_count=0,
                feature_enrichment_payload_count=0,
                ledger_appended_count=0,
                request_count=0,
                remaining_quota=None,
                selected_market_fixture_ids=[],
                blockers=["FUTURE_REFRESH_POLICY_DISABLED"],
                status="BLOCKED",
            )
            self._write_audit(result)
            return result
        self._validate_checkpoint_claims()
        tick_cap = self._provider_tick_hard_cap_preflight()
        if not tick_cap["allowed"]:
            blocker = str(tick_cap["blocker"])
            self._audit.append(
                {
                    "endpoint": "provider_refresh_tick_hard_cap_preflight",
                    "params": {},
                    "attempt": 0,
                    "status_code": None,
                    "elapsed_ms": 0,
                    "captured_at_utc": iso(utc_now()),
                    "remaining_quota": self._latest_remaining,
                    "payload_sha256": None,
                    "error_code": blocker,
                    "projected_calls": tick_cap["projected_calls"],
                    "tick_hard_cap": tick_cap["tick_hard_cap"],
                }
            )
            result = FutureRefreshResult(
                generated_at_utc=self.now,
                fixture_count=0,
                mapping_count=0,
                market_snapshot_count=0,
                feature_enrichment_payload_count=0,
                ledger_appended_count=0,
                request_count=0,
                remaining_quota=None,
                selected_market_fixture_ids=[],
                blockers=[blocker],
                status="BLOCKED",
                raw_payload_written_count=self._raw_payload_written_count,
            )
            self._write_audit(result)
            return result
        preflight = self._provider_hard_cap_preflight()
        if not preflight["allowed"]:
            blocker = str(preflight["blocker"])
            self._audit.append(
                {
                    "endpoint": "provider_daily_hard_cap_preflight",
                    "params": {},
                    "attempt": 0,
                    "status_code": None,
                    "elapsed_ms": 0,
                    "captured_at_utc": iso(utc_now()),
                    "remaining_quota": self._latest_remaining,
                    "payload_sha256": None,
                    "error_code": blocker,
                    "quota_guard_mode": preflight["mode"],
                    "actual_calls_today": preflight["actual_calls_today"],
                    "planned_calls": preflight["planned_calls"],
                    "daily_cap": preflight["daily_cap"],
                    "reserve_bucket": preflight["reserve_bucket"],
                }
            )
            result = FutureRefreshResult(
                generated_at_utc=self.now,
                fixture_count=0,
                mapping_count=0,
                market_snapshot_count=0,
                feature_enrichment_payload_count=0,
                ledger_appended_count=0,
                request_count=0,
                remaining_quota=None,
                selected_market_fixture_ids=[],
                blockers=[blocker],
                status="BLOCKED",
                raw_payload_written_count=self._raw_payload_written_count,
            )
            self._write_audit(result)
            return result
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
            enrichment_responses = self._fetch_feature_enrichment(future_fixtures)
            result = self._persist(
                fixtures_response,
                future_fixtures,
                odds_responses,
                enrichment_responses,
                blockers,
            )
        except FutureRefreshError as exc:
            blockers.append(str(exc))
            result = FutureRefreshResult(
                generated_at_utc=self.now,
                fixture_count=0,
                mapping_count=0,
                market_snapshot_count=0,
                feature_enrichment_payload_count=0,
                ledger_appended_count=0,
                request_count=self._attempt_count,
                remaining_quota=self._latest_remaining,
                selected_market_fixture_ids=[],
                blockers=blockers,
                status="BLOCKED",
                raw_payload_written_count=self._raw_payload_written_count,
                error_code=str(exc),
            )
            self._write_audit(result)
        except Exception as exc:
            blockers.append(exc.__class__.__name__)
            result = FutureRefreshResult(
                generated_at_utc=self.now,
                fixture_count=0,
                mapping_count=0,
                market_snapshot_count=0,
                feature_enrichment_payload_count=0,
                ledger_appended_count=0,
                request_count=self._attempt_count,
                remaining_quota=self._latest_remaining,
                selected_market_fixture_ids=[],
                blockers=blockers,
                status="PARTIAL_FAILED",
                raw_payload_written_count=self._raw_payload_written_count,
                error_code=exc.__class__.__name__,
            )
            self._write_audit(result)
        return result

    def _validate_checkpoint_claims(self) -> None:
        if self.config.persistence != "db" or not self.config.refresh_checkpoints:
            return
        from w2.matchday.repository import MatchdayRuntimeRepository

        repository = MatchdayRuntimeRepository()
        for checkpoint in self.config.refresh_checkpoints:
            plan_id = str(checkpoint.get("id") or checkpoint.get("plan_id") or "")
            claim_token = str(checkpoint.get("claim_token") or "")
            fixture_id = str(checkpoint.get("fixture_id") or "")
            if not plan_id or not claim_token:
                raise FutureRefreshError("CHECKPOINT_CLAIM_REQUIRED")
            repository.validate_checkpoint_claim(
                plan_id=plan_id,
                claim_token=claim_token,
                now=self.now,
                fixture_id=fixture_id or None,
                competition_id=self.config.competition_id,
                season=self.config.season,
            )

    def _request(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        if not self._endpoint_authorized(endpoint):
            raise FutureRefreshError(f"ENDPOINT_NOT_AUTHORIZED:{endpoint}")
        last_error: Exception | None = None
        max_attempts = provider_http_max_attempts()
        for attempt in range(1, max_attempts + 1):
            if self._attempt_count >= self.config.request_budget:
                raise FutureRefreshError("REQUEST_BUDGET_EXHAUSTED")
            self._attempt_count += 1
            captured_at = utc_now()
            started = time.monotonic()
            try:
                response = self.client.request_live(endpoint, params)
            except Exception as exc:
                last_error = exc
                self._audit.append(
                    {
                        "endpoint": endpoint,
                        "params": sanitize_params(params),
                        "attempt": attempt,
                        "status_code": None,
                        "elapsed_ms": int((time.monotonic() - started) * 1000),
                        "captured_at_utc": iso(captured_at),
                        "remaining_quota": self._latest_remaining,
                        "payload_sha256": None,
                        "error_code": exc.__class__.__name__,
                    }
                )
                if attempt < max_attempts:
                    self.sleep(0.2 * (2 ** (attempt - 1)))
                    continue
                raise FutureRefreshError(exc.__class__.__name__) from exc
            quota = parse_api_football_quota(
                headers=response.headers,
                payload=response.payload,
                observed_at=response.captured_at,
            )
            remaining = quota.daily_remaining
            self._latest_remaining = remaining
            status = response.status_code
            raw_payload = self._raw_payload_record(
                endpoint=endpoint,
                params=params,
                payload=response.payload,
            )
            payload_sha = sha256_payload(raw_payload)
            response_size = response_count(response.payload)
            raw_payload_persisted, raw_payload_error = self._save_raw_payload_first(
                endpoint=endpoint,
                params=params,
                response=response,
                payload_hash=payload_sha,
                payload=raw_payload,
            )
            if not raw_payload_persisted:
                raise FutureRefreshError(f"RAW_PAYLOAD_WRITE_FAILED:{raw_payload_error}")
            endpoint_capture_id, endpoint_capture_error = self._persist_matchday_endpoint_capture(
                endpoint=endpoint,
                params=params,
                attempt=attempt,
                response=response,
                payload=raw_payload,
            )
            if (
                self.config.persistence == "db"
                and (endpoint_capture_error is not None or endpoint_capture_id is None)
            ):
                raise FutureRefreshError(
                    f"ENDPOINT_CAPTURE_WRITE_FAILED:{endpoint_capture_error}"
                )
            self._audit.append(
                {
                    "endpoint": endpoint,
                    "params": sanitize_params(params),
                    "attempt": attempt,
                    "status_code": status,
                    "elapsed_ms": response.elapsed_ms,
                    "captured_at_utc": iso(response.captured_at),
                    "remaining_quota": remaining,
                    "daily_remaining": quota.daily_remaining,
                    "daily_limit": quota.daily_limit,
                    "burst_remaining": quota.burst_remaining,
                    "quota_observed_at": iso(quota.observed_at),
                    "daily_source": quota.daily_source,
                    "daily_limit_source": quota.daily_limit_source,
                    "burst_source": quota.burst_source,
                    "response_count": response_size,
                    "payload_sha256": payload_sha,
                    "raw_payload_persisted": raw_payload_persisted,
                    "raw_payload_error": raw_payload_error,
                    "matchday_endpoint_capture_id": endpoint_capture_id,
                    "matchday_endpoint_capture_error": endpoint_capture_error,
                    "diagnostic_code": self._diagnostic_code_for_response(
                        endpoint=endpoint,
                        response_count=response_size,
                    ),
                    "error_code": None if status < 400 else f"PROVIDER_HTTP_{status}",
                }
            )
            if status in {401, 403}:
                raise FutureRefreshError(f"PROVIDER_HTTP_{status}")
            if remaining is None:
                raise FutureRefreshError("DAILY_QUOTA_UNKNOWN")
            min_remaining = env_int("W2_PROVIDER_PREFLIGHT_MIN_REMAINING", default=50)
            if remaining < min_remaining:
                raise FutureRefreshError("PROVIDER_HEADER_REMAINING_BELOW_MINIMUM")
            guard = quota_guard_decision(
                remaining_quota=remaining,
                reserve_bucket=self.config.quota_reserve,
                task_type=endpoint,
            )
            if not guard["allowed"]:
                raise FutureRefreshError(str(guard["blocker"]))
            if status == 429 and attempt < max_attempts:
                self.sleep(0.2 * (2 ** (attempt - 1)))
                continue
            if status >= 400:
                raise FutureRefreshError(f"PROVIDER_HTTP_{status}")
            return response
        raise FutureRefreshError(last_error.__class__.__name__ if last_error else "REQUEST_FAILED")

    def _persist_matchday_endpoint_capture(
        self,
        *,
        endpoint: str,
        params: dict[str, str],
        attempt: int,
        response: LiveApiFootballResponse,
        payload: dict[str, Any],
    ) -> tuple[str | None, str | None]:
        if self.config.persistence != "db":
            return None, "NON_DB_PERSISTENCE"
        try:
            from w2.matchday.intake_v2 import endpoint_capture_contract
            from w2.matchday.repository import MatchdayRuntimeRepository

            fixture_id = str(params.get("fixture") or "") or None
            matching_plans = self._matching_checkpoint_plans(
                endpoint=endpoint,
                fixture_id=fixture_id,
                captured_at=response.captured_at,
            )
            checkpoint_names = sorted(
                {
                    str(item.get("checkpoint") or "")
                    for item in matching_plans
                    if item.get("checkpoint")
                }
            )
            checkpoint_plan_ids = [
                str(item.get("id") or item.get("plan_id") or "")
                for item in matching_plans
                if str(item.get("id") or item.get("plan_id") or "")
            ]
            quota = parse_api_football_quota(
                headers=response.headers,
                payload=response.payload,
                observed_at=response.captured_at,
            )
            capture = endpoint_capture_contract(
                endpoint=endpoint,
                params=params,
                requested_at=response.requested_at or response.captured_at,
                provider_captured_at=response.captured_at,
                status_code=response.status_code,
                elapsed_ms=response.elapsed_ms,
                payload=payload,
                fixture_id=f"api_football:{fixture_id}" if fixture_id else None,
                competition_id=self.config.competition_id,
                checkpoint=",".join(checkpoint_names) or None,
                checkpoint_plan_ids=checkpoint_plan_ids,
                attempt=attempt,
                quota_values={
                    "daily_remaining": quota.daily_remaining,
                    "daily_limit": quota.daily_limit,
                    "burst_remaining": quota.burst_remaining,
                    "observed_at": iso(quota.observed_at),
                    "daily_source": quota.daily_source,
                    "daily_limit_source": quota.daily_limit_source,
                    "burst_source": quota.burst_source,
                },
            )
            repository = MatchdayRuntimeRepository()
            repository.insert_endpoint_capture(capture)
            if checkpoint_plan_ids:
                repository.link_endpoint_capture_plans(
                    capture_id=str(capture["capture_id"]),
                    plan_ids=checkpoint_plan_ids,
                    endpoint=endpoint,
                    linked_at=response.captured_at,
                )
            lookup_key = self._capture_lookup_key(
                endpoint=endpoint,
                params=params,
                raw_payload_sha256=str(capture["raw_payload_sha256"]),
                captured_at=response.captured_at,
            )
            self._matchday_capture_by_payload[lookup_key] = capture
            return str(capture["capture_id"]), None
        except Exception as exc:
            raise FutureRefreshError(f"ENDPOINT_CAPTURE_WRITE_FAILED:{exc}") from exc

    def _matching_checkpoint_plans(
        self,
        *,
        endpoint: str,
        fixture_id: str | None,
        captured_at: datetime,
    ) -> list[dict[str, Any]]:
        if not fixture_id:
            return []
        captured = captured_at.astimezone(UTC)
        matches: list[dict[str, Any]] = []
        for item in self.config.refresh_checkpoints:
            raw = str(item.get("fixture_id") or "")
            if raw not in {fixture_id, f"api_football:{fixture_id}"}:
                continue
            if endpoint not in set(item.get("endpoints") or []):
                continue
            window_start = parse_utc(item.get("window_start"))
            window_end = parse_utc(item.get("window_end"))
            if window_start is not None and captured < window_start:
                continue
            if window_end is not None and captured > window_end:
                continue
            matches.append(dict(item))
        return matches

    def _capture_lookup_key(
        self,
        *,
        endpoint: str,
        params: dict[str, str],
        raw_payload_sha256: str,
        captured_at: datetime,
    ) -> tuple[str, str, str, str]:
        return (
            endpoint,
            sha256_payload(sanitize_params(params)),
            raw_payload_sha256,
            iso(captured_at),
        )

    def _save_raw_payload_first(
        self,
        *,
        endpoint: str,
        params: dict[str, str],
        response: LiveApiFootballResponse,
        payload_hash: str,
        payload: dict[str, Any],
    ) -> tuple[bool, str | None]:
        if payload_hash in self._raw_payload_written:
            return True, None
        try:
            if self.config.persistence == "db":
                repository = self._db_repository()
                repository.save_raw_payload(
                    sha256=payload_hash,
                    endpoint=endpoint,
                    captured_at=response.captured_at,
                    payload=payload,
                )
                if endpoint == "lineups":
                    fixture_id = str(params.get("fixture") or "")
                    if not fixture_id:
                        return False, "LINEUP_FIXTURE_ID_MISSING"
                    repository.save_lineup_snapshots(
                        fixture_id=fixture_id,
                        captured_at=response.captured_at,
                        raw_sha256=payload_hash,
                        payload=payload,
                    )
            elif self.config.persistence == "file":
                file_fixture_id = params.get("fixture")
                suffix = f"_{file_fixture_id}" if file_fixture_id else ""
                write_raw_once(
                    self.config.runtime_root / "raw" / f"{endpoint}{suffix}_{payload_hash}.json",
                    {
                        "payload": payload,
                        "audit": {
                            "endpoint": endpoint,
                            "params": sanitize_params(params),
                            "captured_at_utc": iso(response.captured_at),
                            "payload_sha256": payload_hash,
                        },
                    },
                )
            else:
                return False, f"FUTURE_REFRESH_PERSISTENCE_INVALID:{self.config.persistence}"
        except Exception as exc:
            return False, exc.__class__.__name__
        self._raw_payload_written.add(payload_hash)
        self._raw_payload_written_count += 1
        return True, None

    def _raw_payload_record(
        self,
        *,
        endpoint: str,
        params: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        record = dict(payload)
        record["parameters"] = sanitize_params(params)
        record["endpoint"] = endpoint
        return record

    def _request_payload_hash(
        self,
        *,
        endpoint: str,
        params: dict[str, str],
        payload: dict[str, Any],
    ) -> str:
        return sha256_payload(
            self._raw_payload_record(endpoint=endpoint, params=params, payload=payload)
        )

    def _diagnostic_code_for_response(
        self,
        *,
        endpoint: str,
        response_count: int,
    ) -> str | None:
        if endpoint != "lineups":
            return None
        if response_count == 0:
            return "PROVIDER_LINEUPS_EMPTY"
        return None if self.config.persistence == "db" else "LINEUPS_MATERIALIZATION_MISSING"

    def _provider_hard_cap_preflight(self) -> dict[str, Any]:
        daily_cap = env_int("W2_PROVIDER_DAILY_HARD_CAP", default=self.config.daily_hard_cap)
        reserve = env_int("W2_PROVIDER_DAILY_RESERVE", default=self.config.daily_reserve)
        planned_calls = self._planned_provider_calls()
        actual_calls_today = self._actual_provider_calls_today()
        return provider_daily_hard_cap_decision(
            actual_calls_today=actual_calls_today,
            planned_calls=planned_calls,
            daily_cap=daily_cap,
            reserve_bucket=reserve,
        )

    def _provider_tick_hard_cap_preflight(self) -> dict[str, Any]:
        projected_calls = self._projected_provider_calls()
        tick_hard_cap = provider_refresh_tick_hard_cap()
        return {
            "allowed": projected_calls <= tick_hard_cap,
            "blocker": None
            if projected_calls <= tick_hard_cap
            else "PROVIDER_REFRESH_BUDGET_TOO_HIGH",
            "projected_calls": projected_calls,
            "tick_hard_cap": tick_hard_cap,
        }

    def _projected_provider_calls(self) -> int:
        core_calls = sum(
            1 for endpoint in ("status", "fixtures") if self._endpoint_authorized(endpoint)
        )
        fixture_estimate = self._fixture_candidate_estimate()
        odds_calls = min(
            max(self.config.max_odds_requests, 0),
            max(self.config.max_fixture_candidates, 0),
            fixture_estimate,
        )
        if not self._endpoint_authorized("odds"):
            odds_calls = 0
        enrichment_calls = self._projected_feature_enrichment_calls(fixture_estimate)
        return core_calls + odds_calls + enrichment_calls

    def _fixture_candidate_estimate(self) -> int:
        if self.config.checkpoint_fixture_ids:
            return len(set(self.config.checkpoint_fixture_ids))
        if self.config.persistence == "db":
            try:
                fixture_payloads = self._db_repository().fixture_payloads()
            except FutureRefreshPersistenceError:
                return max(self.config.max_fixture_candidates, 0)
            count = 0
            for item in fixture_payloads:
                fixture = item.get("fixture", {}) if isinstance(item, dict) else {}
                status = fixture.get("status", {}) if isinstance(fixture, dict) else {}
                if not isinstance(status, dict) or status.get("short") != "NS":
                    continue
                kickoff = parse_utc(fixture.get("date")) if isinstance(fixture, dict) else None
                if kickoff is None or kickoff <= self.now:
                    continue
                count += 1
            return min(count, max(self.config.max_fixture_candidates, 0))
        return max(self.config.max_fixture_candidates, 0)

    def _projected_feature_enrichment_calls(self, fixture_estimate: int) -> int:
        if not self.config.feature_enrichment_enabled:
            return 0
        endpoints = [
            endpoint
            for endpoint in self.config.feature_enrichment_endpoints
            if endpoint in {"statistics", "lineups", "injuries"}
            and self._endpoint_authorized(endpoint)
        ]
        if not endpoints:
            return 0
        return min(
            max(self.config.feature_enrichment_request_budget, 0),
            max(fixture_estimate, 0) * len(endpoints),
        )

    def _planned_provider_calls(self) -> int:
        return self._projected_provider_calls()

    def _endpoint_authorized(self, endpoint: str) -> bool:
        return endpoint in provider_endpoint_allowlist()

    def _append_unauthorized_endpoint_skip(self, endpoint: str, fixture_id: str | None) -> None:
        self._audit.append(
            {
                "endpoint": endpoint,
                "params": {"fixture": fixture_id} if fixture_id else {},
                "attempt": 0,
                "status_code": None,
                "elapsed_ms": 0,
                "captured_at_utc": iso(utc_now()),
                "remaining_quota": self._latest_remaining,
                "payload_sha256": None,
                "error_code": f"ENDPOINT_NOT_AUTHORIZED:{endpoint}",
            }
        )

    def _actual_provider_calls_today(self) -> int:
        if self.config.actual_provider_calls_today is not None:
            return max(self.config.actual_provider_calls_today, 0)
        if self.config.persistence != "db":
            return 0
        day_start = self.now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            return self._db_repository().request_count_since(
                day_start,
                include_quota_usage=self.config.daily_usage_scope != "w2_ledger",
            )
        except FutureRefreshPersistenceError as exc:
            raise FutureRefreshError("PROVIDER_USAGE_AUDIT_UNAVAILABLE") from exc

    def _future_fixtures(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        response = payload.get("response")
        if not isinstance(response, list):
            return []
        allowed_fixture_ids = set(self.config.checkpoint_fixture_ids)
        rows: list[dict[str, Any]] = []
        for item in response:
            if not isinstance(item, dict):
                continue
            fixture_id = fixture_id_from_payload(item)
            if allowed_fixture_ids and fixture_id not in allowed_fixture_ids:
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
            self._odds_request_fixture_ids.append(fixture_id)
            response = self._request("odds", {"fixture": fixture_id})
            if bookmaker_count(response.payload) > 0:
                odds.append((fixture_id, response))
        return odds

    def _fetch_feature_enrichment(
        self,
        fixtures: list[dict[str, Any]],
    ) -> list[tuple[str, str, int]]:
        if not self.config.feature_enrichment_enabled:
            return []
        allowed = {"statistics", "lineups", "injuries"}
        endpoints = [
            endpoint for endpoint in self.config.feature_enrichment_endpoints if endpoint in allowed
        ]
        if not endpoints:
            return []
        budget = max(self.config.feature_enrichment_request_budget, 0)
        if budget == 0:
            return []
        responses: list[tuple[str, str, int]] = []
        batch_size = max(
            env_int(
                "W2_PROVIDER_REFRESH_BATCH_SIZE",
                default=self.config.provider_refresh_batch_size,
            ),
            1,
        )
        pending: list[tuple[str, str, int]] = []
        for item in fixtures:
            fixture_id = fixture_id_from_payload(item)
            if not fixture_id:
                continue
            for endpoint in endpoints:
                if not self._endpoint_authorized(endpoint):
                    self._append_unauthorized_endpoint_skip(endpoint, fixture_id)
                    continue
                if len(responses) + len(pending) >= budget:
                    if pending:
                        self._feature_enrichment_batch_count += 1
                        responses.extend(pending)
                    return responses
                if self._latest_remaining is not None:
                    guard = quota_guard_decision(
                        remaining_quota=self._latest_remaining,
                        reserve_bucket=self.config.quota_reserve,
                        task_type=endpoint,
                    )
                    if not guard["allowed"]:
                        self._audit.append(
                            {
                                "endpoint": endpoint,
                                "params": {"fixture": fixture_id},
                                "attempt": 0,
                                "status_code": None,
                                "elapsed_ms": 0,
                                "captured_at_utc": iso(utc_now()),
                                "remaining_quota": self._latest_remaining,
                                "payload_sha256": None,
                                "error_code": guard["blocker"],
                                "quota_guard_mode": guard["mode"],
                            }
                        )
                        continue
                response = self._request(endpoint, {"fixture": fixture_id})
                pending.append((fixture_id, endpoint, response_count(response.payload)))
                if len(pending) >= batch_size:
                    self._feature_enrichment_batch_count += 1
                    responses.extend(pending)
                    pending = []
        if pending:
            self._feature_enrichment_batch_count += 1
            responses.extend(pending)
        return responses

    def _persist(
        self,
        fixtures_response: LiveApiFootballResponse,
        fixtures: list[dict[str, Any]],
        odds_responses: list[tuple[str, LiveApiFootballResponse]],
        enrichment_responses: list[tuple[str, str, int]],
        blockers: list[str],
    ) -> FutureRefreshResult:
        if self.config.persistence == "db":
            return self._persist_db(
                fixtures_response,
                fixtures,
                odds_responses,
                enrichment_responses,
                blockers,
            )
        if self.config.persistence != "file":
            raise FutureRefreshError(
                f"FUTURE_REFRESH_PERSISTENCE_INVALID:{self.config.persistence}"
            )
        read_model = self.config.runtime_root / "read_model"
        ledger = MarketObservationLedger(
            self.config.runtime_root / "ledger" / "market_observations.jsonl"
        )
        observations: list[dict[str, Any]] = []
        for fixture_id, response in odds_responses:
            observations.extend(
                observations_from_odds_payload(
                    fixture_id=fixture_id,
                    payload=response.payload,
                    response=response,
                    source_revision=self.config.source_revision,
                    raw_payload_sha256=self._request_payload_hash(
                        endpoint="odds",
                        params={"fixture": fixture_id},
                        payload=response.payload,
                    ),
                )
            )
        appended = ledger.append_observations(observations)
        latest_rows = project_ledger_to_read_model(ledger=ledger, read_model_dir=read_model)
        mappings = [self._mapping_from_fixture(item) for item in fixtures]
        markets = [
            self._market_snapshot_from_observations(fixture_id, latest_rows)
            for fixture_id, _ in odds_responses
        ]
        write_json_atomic(read_model / "fixtures.json", {"items": fixtures})
        write_json_atomic(read_model / "provider_mappings.json", {"items": mappings})
        write_json_atomic(read_model / "market_snapshots.json", markets)
        write_json_atomic(read_model / "provider_status.json", self._provider_status())
        result = FutureRefreshResult(
            generated_at_utc=self.now,
            fixture_count=len(fixtures),
            mapping_count=len(mappings),
            market_snapshot_count=len(markets),
            feature_enrichment_payload_count=len(enrichment_responses),
            ledger_appended_count=appended,
            request_count=self._attempt_count,
            remaining_quota=self._latest_remaining,
            selected_market_fixture_ids=[fixture_id for fixture_id, _ in odds_responses],
            blockers=blockers,
            raw_payload_written_count=self._raw_payload_written_count,
            materialized_fixture_ids=(
                self._materialize_refreshed_public_artifacts(
                    appended=appended,
                    fixture_ids=[fixture_id for fixture_id, _response in odds_responses],
                )
                if self.materialize_public_artifacts is not None
                else []
            ),
        )
        self._write_audit(result)
        return result

    def _materialize_refreshed_public_artifacts(
        self,
        *,
        appended: int,
        fixture_ids: list[str],
    ) -> list[str]:
        if not self.config.refresh_checkpoints or appended <= 0:
            return []
        materializer = self.materialize_public_artifacts or materialize_refreshed_public_artifacts
        return materializer(fixture_ids)

    def _persist_db(
        self,
        fixtures_response: LiveApiFootballResponse,
        fixtures: list[dict[str, Any]],
        odds_responses: list[tuple[str, LiveApiFootballResponse]],
        enrichment_responses: list[tuple[str, str, int]],
        blockers: list[str],
    ) -> FutureRefreshResult:
        try:
            observations: list[dict[str, Any]] = []
            for fixture_id, response in odds_responses:
                from w2.matchday.intake_v2 import normalize_matchday_odds_payload
                from w2.matchday.repository import MatchdayRuntimeRepository

                raw_record = self._raw_payload_record(
                    endpoint="odds",
                    params={"fixture": fixture_id},
                    payload=response.payload,
                )
                raw_sha = sha256_payload(raw_record)
                capture = self._matchday_capture_by_payload.get(
                    self._capture_lookup_key(
                        endpoint="odds",
                        params={"fixture": fixture_id},
                        raw_payload_sha256=raw_sha,
                        captured_at=response.captured_at,
                    )
                )
                if capture is None:
                    raise FutureRefreshError("ENDPOINT_CAPTURE_REQUIRED_BEFORE_NORMALIZATION")
                rows, rejections = normalize_matchday_odds_payload(
                    response.payload,
                    captured_at=response.captured_at,
                    ingested_at=utc_now(),
                    raw_payload_sha256=raw_sha,
                    source_revision=self.config.source_revision,
                    capture_id=str(capture["capture_id"]),
                    competition_id=self.config.competition_id,
                )
                if any(
                    item.get("reason") == "OBSERVATION_IDENTITY_CONFLICT"
                    for item in rejections
                ):
                    raise FutureRefreshError("OBSERVATION_NORMALIZATION_CONFLICT")
                observations.extend(rows)
            appended = MatchdayRuntimeRepository().insert_market_observations(observations)
            latest_rows = [
                {
                    **row,
                    "fixture_id": str(row.get("provider_fixture_id") or row.get("fixture_id")),
                    "selection": row.get("canonical_selection"),
                }
                for row in observations
            ]
        except FutureRefreshPersistenceError as exc:
            raise FutureRefreshError(f"PERSISTENCE_WRITE_FAILED:{exc}") from exc
        mappings = [self._mapping_from_fixture(item) for item in fixtures]
        markets = [
            self._market_snapshot_from_observations(fixture_id, latest_rows)
            for fixture_id, _ in odds_responses
        ]
        result = FutureRefreshResult(
            generated_at_utc=self.now,
            fixture_count=len(fixtures),
            mapping_count=len(mappings),
            market_snapshot_count=len(markets),
            feature_enrichment_payload_count=len(enrichment_responses),
            ledger_appended_count=appended,
            request_count=self._attempt_count,
            remaining_quota=self._latest_remaining,
            selected_market_fixture_ids=[fixture_id for fixture_id, _ in odds_responses],
            blockers=blockers,
            raw_payload_written_count=self._raw_payload_written_count,
            materialized_fixture_ids=self._materialize_refreshed_public_artifacts(
                appended=appended,
                fixture_ids=[fixture_id for fixture_id, _response in odds_responses],
            ),
        )
        self._write_audit(result)
        return result

    def _audit_for_payload(self, payload_hash: str) -> dict[str, Any] | None:
        for item in self._audit:
            if item.get("payload_sha256") == payload_hash:
                return item
        return None

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

    def _market_snapshot_from_observations(
        self,
        fixture_id: str,
        observations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        fixture_rows = [row for row in observations if str(row.get("fixture_id")) == fixture_id]
        captured_at = max([str(row.get("captured_at")) for row in fixture_rows] or [iso(self.now)])
        bookmakers = {
            str(row.get("bookmaker_id")) for row in fixture_rows if row.get("bookmaker_id")
        }
        markets = {str(row.get("canonical_market")) for row in fixture_rows}
        return {
            "fixture_id": fixture_id,
            "captured_at": captured_at,
            "captured_at_utc": captured_at,
            "snapshot_semantics": "CAPTURED_AT",
            "bookmaker_count": len(bookmakers),
            "quality": "READY" if fixture_rows else "MARKET_NOT_COMPARABLE",
            "source": "future_fixture_refresh_ledger",
            "market_coverage": {market: True for market in sorted(markets)},
            "freshness_limit_seconds": self.config.market_freshness_seconds,
            "candidate": False,
            "formal_recommendation": False,
        }

    def _provider_status(self) -> dict[str, Any]:
        last_success = next(
            (item for item in reversed(self._audit) if item.get("status_code") == 200),
            {},
        )
        return {
            "provider": "api_football",
            "status": "READY" if not self._blocking_audit_errors() else "DEGRADED",
            "remaining_quota": self._latest_remaining,
            "credential_status": "PRESENT",
            "last_request_status": self._audit[-1]["status_code"] if self._audit else None,
            "last_successful_refresh_at": last_success.get("captured_at_utc"),
            "blockers": self._blocking_audit_errors(),
        }

    def _blocking_audit_errors(self) -> list[str]:
        return [str(item["error_code"]) for item in self._audit if item.get("error_code")]

    def _write_audit(self, result: FutureRefreshResult) -> None:
        payload = {
            "generated_at_utc": iso(result.generated_at_utc),
            "competition_id": self.config.competition_id,
            "request_count": result.request_count,
            "remaining_quota": result.remaining_quota,
            "fixture_count": result.fixture_count,
            "mapping_count": result.mapping_count,
            "market_snapshot_count": result.market_snapshot_count,
            "odds_request_fixture_ids": list(self._odds_request_fixture_ids),
            "odds_request_attempt_count": len(self._odds_request_fixture_ids),
            "odds_request_limit": self.config.max_odds_requests,
            "odds_request_coverage_ratio": (
                round(len(self._odds_request_fixture_ids) / result.fixture_count, 4)
                if result.fixture_count
                else None
            ),
            "feature_enrichment_payload_count": result.feature_enrichment_payload_count,
            "feature_enrichment_batch_count": self._feature_enrichment_batch_count,
            "ledger_appended_count": result.ledger_appended_count,
            "materialized_fixture_ids": result.materialized_fixture_ids,
            "raw_payload_written_count": result.raw_payload_written_count,
            "selected_market_fixture_ids": result.selected_market_fixture_ids,
            "blockers": result.blockers,
            "status": result.status,
            "error_code": result.error_code,
            "requests": self._audit,
            "candidate": False,
            "formal_recommendation": False,
        }
        if self.config.persistence == "db":
            try:
                repository = self._db_repository()
                repository.write_run_audit(payload)
                self._write_checkpoint_audits(repository, result)
                return
            except FutureRefreshPersistenceError as exc:
                raise FutureRefreshError(f"PERSISTENCE_WRITE_FAILED:{exc}") from exc
        write_json_atomic(self.config.runtime_root / "future_refresh_audit.json", payload)

    def _write_checkpoint_audits(
        self,
        repository: FutureRefreshDbRepository,
        result: FutureRefreshResult,
    ) -> None:
        if not self.config.refresh_checkpoints:
            return
        calls_by_fixture: dict[str, int] = {}
        for item in self._audit:
            params = item.get("params") if isinstance(item, dict) else None
            fixture_id = (
                str(params.get("fixture"))
                if isinstance(params, dict) and params.get("fixture")
                else ""
            )
            if fixture_id:
                calls_by_fixture[fixture_id] = calls_by_fixture.get(fixture_id, 0) + int(
                    item.get("attempt") or 0
                )
        for checkpoint in self.config.refresh_checkpoints:
            fixture_id = str(checkpoint.get("fixture_id") or "")
            name = str(checkpoint.get("checkpoint") or "")
            if not fixture_id or not name:
                continue
            status = "COMPLETED" if not result.blockers else result.status
            repository.write_checkpoint_audit(
                fixture_id=fixture_id,
                checkpoint=name,
                as_of=result.generated_at_utc,
                calls_used=max(calls_by_fixture.get(fixture_id, 0), 0),
                status=status,
                details={
                    "contract": "w2.checkpoint_refresh.v1",
                    "request_count": result.request_count,
                    "selected_market_fixture_ids": result.selected_market_fixture_ids,
                    "blockers": result.blockers,
                    "endpoints": list(checkpoint.get("endpoints") or []),
                    "source": checkpoint.get("source"),
                },
            )
            self._transition_checkpoint_plan(checkpoint, result)

    def _transition_checkpoint_plan(
        self,
        checkpoint: dict[str, Any],
        result: FutureRefreshResult,
    ) -> None:
        plan_id = str(checkpoint.get("id") or checkpoint.get("plan_id") or "")
        claim_token = str(checkpoint.get("claim_token") or "")
        if not plan_id or not claim_token:
            return
        from w2.matchday.repository import MatchdayRuntimeRepository

        status = "FAILED" if result.blockers else "CAPTURED"
        repository = MatchdayRuntimeRepository()
        repository.transition_checkpoint(
            fixture_id=str(checkpoint.get("fixture_id") or ""),
            competition_id=self.config.competition_id,
            season=self.config.season,
            checkpoint=str(checkpoint.get("checkpoint") or ""),
            policy_version=str(checkpoint.get("policy_version") or "w2.matchday_intake_policy.v2"),
            status=status,
            capture_id=None,
            now=result.generated_at_utc,
            claim_token=claim_token,
        )


def deterministic_time_bucket(now: datetime, interval_seconds: int) -> str:
    epoch = int(now.astimezone(UTC).timestamp())
    bucket = epoch - (epoch % interval_seconds)
    return datetime.fromtimestamp(bucket, tz=UTC).strftime("%Y%m%dT%H%M%SZ")


def deterministic_task_key(
    *,
    competition_id: str,
    season: str,
    now: datetime,
    interval_seconds: int,
) -> str:
    bucket = deterministic_time_bucket(now, interval_seconds)
    return f"future-refresh:{competition_id}:{season}:{bucket}"


def run_future_fixture_refresh(
    *,
    competition_id: str = "world_cup_2026",
    runtime_root: Path | None = None,
    client: LiveApiFootballPort | None = None,
    now: datetime | None = None,
    policy_path: Path = Path("config/policies/future_fixture_refresh.v1.json"),
    persistence: str | None = None,
    checkpoint_fixture_ids: tuple[str, ...] = (),
    refresh_checkpoints: tuple[dict[str, Any], ...] = (),
    materialize_public_artifacts: Callable[[list[str]], list[str]] | None = None,
) -> FutureRefreshResult:
    config = config_from_policy(
        competition_id=competition_id,
        runtime_root=runtime_root,
        policy_path=policy_path,
    )
    if persistence is not None:
        config = replace(config, persistence=persistence)
    if checkpoint_fixture_ids or refresh_checkpoints:
        lineups_count = sum(
            1 for item in refresh_checkpoints if "lineups" in set(item.get("endpoints") or [])
        )
        config = replace(
            config,
            checkpoint_fixture_ids=tuple(dict.fromkeys(checkpoint_fixture_ids)),
            refresh_checkpoints=tuple(refresh_checkpoints),
            max_fixture_candidates=max(len(set(checkpoint_fixture_ids)), 1),
            max_odds_requests=sum(
                1 for item in refresh_checkpoints if "odds" in set(item.get("endpoints") or [])
            ),
            feature_enrichment_enabled=lineups_count > 0,
            feature_enrichment_endpoints=("lineups",),
            feature_enrichment_request_budget=lineups_count,
            request_budget=max(
                config.request_budget,
                2 + len(set(checkpoint_fixture_ids)) + lineups_count,
            ),
        )
    return FutureFixtureRefreshService(
        client=client,
        config=config,
        now=now,
        materialize_public_artifacts=materialize_public_artifacts,
    ).run()


def run_future_refresh_task(
    *,
    task_id: str,
    key: str,
    owner: str | None = None,
    queued_at: datetime | None = None,
    competition_id: str = "world_cup_2026",
    runtime_root: Path | None = None,
    client: LiveApiFootballPort | None = None,
    now: datetime | None = None,
    settings: Settings | None = None,
    redis_client: Any | None = None,
    persistence: str | None = None,
    requested_interval_seconds: int | None = None,
    effective_interval_seconds: int | None = None,
    provider_refresh_min_interval_seconds: int | None = None,
    checkpoint_fixture_ids: tuple[str, ...] = (),
    refresh_checkpoints: tuple[dict[str, Any], ...] = (),
    materialize_public_artifacts: Callable[[list[str]], list[str]] | None = None,
) -> RefreshTaskAudit:
    started_at = now or utc_now()
    owner_marker = owner or str(uuid4())
    root = runtime_root or FutureRefreshConfig().runtime_root
    resolved_persistence = (
        persistence or os.environ.get("W2_FUTURE_REFRESH_PERSISTENCE", "db")
    ).lower()
    resolved_settings = settings or get_settings()
    lock: RefreshSingletonLock | None = None
    if resolved_persistence == "db":
        try:
            existing_task_key = FutureRefreshDbRepository(
                settings=resolved_settings
            ).task_key_exists(key)
        except FutureRefreshPersistenceError as exc:
            raise FutureRefreshError(f"PERSISTENCE_READ_FAILED:{exc}") from exc
        if existing_task_key:
            lock_acquired = False
        elif redis_client is not None or resolved_settings.redis_url is not None:
            lock = RefreshSingletonLock(
                key=key,
                owner=owner_marker,
                ttl_seconds=900,
                settings=resolved_settings,
                runtime_root=root,
                redis_client=redis_client,
            )
            lock_acquired = lock.acquire(now=started_at)
        else:
            lock_acquired = True
    else:
        lock = RefreshSingletonLock(
            key=key,
            owner=owner_marker,
            ttl_seconds=900,
            settings=resolved_settings,
            runtime_root=root,
            redis_client=redis_client,
        )
        lock_acquired = lock.acquire(now=started_at)
    if not lock_acquired:
        interval_metadata = {
            "requested_interval_seconds": requested_interval_seconds,
            "effective_interval_seconds": effective_interval_seconds,
            "provider_refresh_min_interval_seconds": provider_refresh_min_interval_seconds,
        }
        audit = RefreshTaskAudit(
            task_id=task_id,
            key=key,
            owner=owner_marker,
            queued_at=iso(queued_at or started_at),
            started_at=iso(started_at),
            finished_at=iso(utc_now()),
            status="ALREADY_RUNNING",
            result={
                "candidate": False,
                "formal_recommendation": False,
                **{k: v for k, v in interval_metadata.items() if v is not None},
            },
        )
        write_task_audit(root, audit, persistence=persistence)
        return audit
    status = "BLOCKED"
    summary: dict[str, Any] = {
        "blockers": ["UNHANDLED_FUTURE_REFRESH_EXCEPTION"],
        "candidate": False,
        "formal_recommendation": False,
    }
    try:
        result = run_future_fixture_refresh(
            competition_id=competition_id,
            runtime_root=root,
            client=client,
            now=started_at,
            persistence=resolved_persistence,
            checkpoint_fixture_ids=checkpoint_fixture_ids,
            refresh_checkpoints=refresh_checkpoints,
            materialize_public_artifacts=materialize_public_artifacts,
        )
        status = "COMPLETED" if not result.blockers else "BLOCKED"
        summary = {
            "fixture_count": result.fixture_count,
            "mapping_count": result.mapping_count,
            "market_snapshot_count": result.market_snapshot_count,
            "feature_enrichment_payload_count": result.feature_enrichment_payload_count,
            "ledger_appended_count": result.ledger_appended_count,
            "request_count": result.request_count,
            "remaining_quota": result.remaining_quota,
            "blockers": result.blockers,
            "candidate": False,
            "formal_recommendation": False,
            "checkpoint_fixture_ids": list(checkpoint_fixture_ids),
            "refresh_checkpoints": list(refresh_checkpoints),
            "materialized_fixture_ids": result.materialized_fixture_ids,
        }
    except Exception as exc:
        summary = {
            "blockers": [exc.__class__.__name__],
            "candidate": False,
            "formal_recommendation": False,
        }
    finally:
        released = True if lock is None else lock.release()
    audit = RefreshTaskAudit(
        task_id=task_id,
        key=key,
        owner=owner_marker,
        queued_at=iso(queued_at or started_at),
        started_at=iso(started_at),
        finished_at=iso(utc_now()),
        status=status,
        result={
            **summary,
            "lock_released": released,
            **{
                key: value
                for key, value in {
                    "requested_interval_seconds": requested_interval_seconds,
                    "effective_interval_seconds": effective_interval_seconds,
                    "provider_refresh_min_interval_seconds": provider_refresh_min_interval_seconds,
                }.items()
                if value is not None
            },
        },
    )
    write_task_audit(root, audit, persistence=persistence)
    return audit


def materialize_refreshed_public_artifacts(fixture_ids: list[str]) -> list[str]:
    from w2.api.frozen_analysis import (
        AnalysisCardCanaryMaterializer,
        write_frozen_analysis_artifacts,
    )
    from w2.api.repository import ReadModelRepository
    from w2.infrastructure.database import create_engine

    ids = [fixture_id for fixture_id in dict.fromkeys(fixture_ids) if fixture_id]
    if not ids:
        return []
    repository = ReadModelRepository()
    materializer = AnalysisCardCanaryMaterializer(repository)
    artifacts = []
    for fixture_id in ids:
        observations = repository.future_market_observations_for_fixtures([fixture_id])
        captured_at = [
            parsed
            for row in observations
            if (parsed := parse_utc(row.get("captured_at"))) is not None
        ]
        if not captured_at:
            raise FutureRefreshError(f"PUBLIC_ARTIFACT_CAPTURE_MISSING:{fixture_id}")
        artifacts.append(materializer.build(fixture_id, evaluated_at=max(captured_at)))
    write_frozen_analysis_artifacts(create_engine(), artifacts)
    return ids


def write_task_audit(
    root: Path,
    audit: RefreshTaskAudit,
    *,
    persistence: str | None = None,
) -> None:
    resolved = (persistence or os.environ.get("W2_FUTURE_REFRESH_PERSISTENCE", "db")).lower()
    if resolved == "db":
        try:
            FutureRefreshDbRepository().write_task_audit(audit.__dict__)
            return
        except FutureRefreshPersistenceError as exc:
            raise FutureRefreshError(f"PERSISTENCE_WRITE_FAILED:{exc}") from exc
    write_json_atomic(root / "task_audit" / f"{audit.task_id}.json", audit.__dict__)
