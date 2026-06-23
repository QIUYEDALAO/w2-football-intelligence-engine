from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError

from w2.config import Settings, get_settings
from w2.providers.api_football import ApiFootballClient, LiveApiFootballResponse


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
    max_fixture_candidates: int
    max_odds_requests: int
    market_freshness_seconds: int
    enabled: bool


@dataclass(frozen=True)
class FutureRefreshConfig:
    runtime_root: Path = Path("runtime/future_refresh")
    competition_id: str = "world_cup_2026"
    league_id: str = "1"
    season: str = "2026"
    horizon_days: int = 4
    max_fixture_candidates: int = 20
    max_odds_requests: int = 10
    quota_reserve: int = 1500
    market_freshness_seconds: int = 3600
    request_budget: int = 40
    scheduler_interval_seconds: int = 900
    source_revision: str = "LOCAL_UNDEPLOYED"
    enabled: bool = True


@dataclass(frozen=True)
class FutureRefreshResult:
    generated_at_utc: datetime
    fixture_count: int
    mapping_count: int
    market_snapshot_count: int
    ledger_appended_count: int
    request_count: int
    remaining_quota: int | None
    selected_market_fixture_ids: list[str]
    blockers: list[str] = field(default_factory=list)
    status: str = "COMPLETED"


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
    return parse_utc(item.get("fixture", {}).get("date"))


def sanitize_params(params: dict[str, str]) -> dict[str, str]:
    blocked = {"key", "api_key", "token", "password", "authorization"}
    return {key: ("REDACTED" if key.lower() in blocked else value) for key, value in params.items()}


def load_refresh_policy(
    *,
    competition_id: str,
    policy_path: Path = Path("config/policies/future_fixture_refresh.v1.json"),
) -> CompetitionRefreshPolicy:
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
        return CompetitionRefreshPolicy(
            competition_id=competition_id,
            provider_league_id=item["provider_league_id"],
            season=item["season"],
            horizon_days=item["horizon_days"],
            scheduler_interval_seconds=item["scheduler_interval_seconds"],
            quota_reserve=item["quota_reserve"],
            request_budget=item["request_budget"],
            max_fixture_candidates=item["max_fixture_candidates"],
            max_odds_requests=item["max_odds_requests"],
            market_freshness_seconds=item["market_freshness_seconds"],
            enabled=item["enabled"],
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
        scheduler_interval_seconds=policy.scheduler_interval_seconds,
        enabled=policy.enabled,
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
                return bool(
                    redis_client.set(self.key, self.owner, nx=True, ex=self.ttl_seconds)
                )
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
    label = raw_label.strip().lower()
    if label in {"match winner", "1x2", "winner"}:
        return "ONE_X_TWO"
    if "asian handicap" in label or label == "handicap":
        return "ASIAN_HANDICAP"
    if "goals over/under" in label or "over/under" in label or label == "total goals":
        return "TOTALS"
    if "both teams" in label or "btts" in label:
        return "BTTS"
    return raw_label.upper().replace(" ", "_")


def parse_line(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    parts = value.replace("+", " +").replace("-", " -").split()
    for part in reversed(parts):
        try:
            float(part)
        except ValueError:
            continue
        return part
    return None


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
) -> list[dict[str, Any]]:
    raw_hash = sha256_payload(payload)
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
    ) -> None:
        self.client = client or ApiFootballClient(allow_live=True)
        self.config = config or config_from_policy()
        self.now = now or utc_now()
        self.sleep = sleep or time.sleep
        self._attempt_count = 0
        self._latest_remaining: int | None = None
        self._audit: list[dict[str, Any]] = []

    def run(self) -> FutureRefreshResult:
        blockers: list[str] = []
        if not self.config.enabled:
            result = FutureRefreshResult(
                generated_at_utc=self.now,
                fixture_count=0,
                mapping_count=0,
                market_snapshot_count=0,
                ledger_appended_count=0,
                request_count=0,
                remaining_quota=None,
                selected_market_fixture_ids=[],
                blockers=["FUTURE_REFRESH_POLICY_DISABLED"],
                status="BLOCKED",
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
            result = self._persist(fixtures_response, future_fixtures, odds_responses, blockers)
        except FutureRefreshError as exc:
            blockers.append(str(exc))
            result = FutureRefreshResult(
                generated_at_utc=self.now,
                fixture_count=0,
                mapping_count=0,
                market_snapshot_count=0,
                ledger_appended_count=0,
                request_count=self._attempt_count,
                remaining_quota=self._latest_remaining,
                selected_market_fixture_ids=[],
                blockers=blockers,
                status="BLOCKED",
            )
            self._write_audit(result)
        return result

    def _request(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        last_error: Exception | None = None
        max_attempts = 3
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
            remaining = provider_remaining_quota(response)
            self._latest_remaining = remaining
            status = response.status_code
            self._audit.append(
                {
                    "endpoint": endpoint,
                    "params": sanitize_params(params),
                    "attempt": attempt,
                    "status_code": status,
                    "elapsed_ms": response.elapsed_ms,
                    "captured_at_utc": iso(response.captured_at),
                    "remaining_quota": remaining,
                    "response_count": response_count(response.payload),
                    "payload_sha256": sha256_payload(response.payload),
                    "error_code": None if status < 400 else f"PROVIDER_HTTP_{status}",
                }
            )
            if status in {401, 403}:
                raise FutureRefreshError(f"PROVIDER_HTTP_{status}")
            if remaining is None:
                raise FutureRefreshError("PROVIDER_REMAINING_QUOTA_UNKNOWN")
            if remaining < self.config.quota_reserve:
                raise FutureRefreshError("QUOTA_BELOW_RESERVE")
            if status == 429 and attempt < max_attempts:
                self.sleep(0.2 * (2 ** (attempt - 1)))
                continue
            if status >= 400:
                raise FutureRefreshError(f"PROVIDER_HTTP_{status}")
            return response
        raise FutureRefreshError(last_error.__class__.__name__ if last_error else "REQUEST_FAILED")

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
        ledger = MarketObservationLedger(
            self.config.runtime_root / "ledger" / "market_observations.jsonl"
        )
        fixtures_hash = sha256_payload(fixtures_response.payload)
        write_raw_once(
            raw_dir / f"fixtures_{fixtures_hash}.json",
            {
                "payload": fixtures_response.payload,
                "audit": self._audit_for_payload(fixtures_hash),
            },
        )
        observations: list[dict[str, Any]] = []
        for fixture_id, response in odds_responses:
            payload_hash = sha256_payload(response.payload)
            write_raw_once(
                raw_dir / f"odds_{fixture_id}_{payload_hash}.json",
                {"payload": response.payload, "audit": self._audit_for_payload(payload_hash)},
            )
            observations.extend(
                observations_from_odds_payload(
                    fixture_id=fixture_id,
                    payload=response.payload,
                    response=response,
                    source_revision=self.config.source_revision,
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
            ledger_appended_count=appended,
            request_count=self._attempt_count,
            remaining_quota=self._latest_remaining,
            selected_market_fixture_ids=[fixture_id for fixture_id, _ in odds_responses],
            blockers=blockers,
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
        write_json_atomic(
            self.config.runtime_root / "future_refresh_audit.json",
            {
                "generated_at_utc": iso(result.generated_at_utc),
                "competition_id": self.config.competition_id,
                "request_count": result.request_count,
                "remaining_quota": result.remaining_quota,
                "fixture_count": result.fixture_count,
                "mapping_count": result.mapping_count,
                "market_snapshot_count": result.market_snapshot_count,
                "ledger_appended_count": result.ledger_appended_count,
                "selected_market_fixture_ids": result.selected_market_fixture_ids,
                "blockers": result.blockers,
                "requests": self._audit,
                "candidate": False,
                "formal_recommendation": False,
            },
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
) -> FutureRefreshResult:
    config = config_from_policy(
        competition_id=competition_id,
        runtime_root=runtime_root,
        policy_path=policy_path,
    )
    return FutureFixtureRefreshService(client=client, config=config, now=now).run()


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
) -> RefreshTaskAudit:
    started_at = now or utc_now()
    owner_marker = owner or str(uuid4())
    root = runtime_root or FutureRefreshConfig().runtime_root
    lock = RefreshSingletonLock(
        key=key,
        owner=owner_marker,
        ttl_seconds=900,
        settings=settings,
        runtime_root=root,
        redis_client=redis_client,
    )
    if not lock.acquire(now=started_at):
        audit = RefreshTaskAudit(
            task_id=task_id,
            key=key,
            owner=owner_marker,
            queued_at=iso(queued_at or started_at),
            started_at=iso(started_at),
            finished_at=iso(utc_now()),
            status="ALREADY_RUNNING",
            result={"candidate": False, "formal_recommendation": False},
        )
        write_task_audit(root, audit)
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
        )
        status = "COMPLETED" if not result.blockers else "BLOCKED"
        summary = {
            "fixture_count": result.fixture_count,
            "mapping_count": result.mapping_count,
            "market_snapshot_count": result.market_snapshot_count,
            "ledger_appended_count": result.ledger_appended_count,
            "request_count": result.request_count,
            "remaining_quota": result.remaining_quota,
            "blockers": result.blockers,
            "candidate": False,
            "formal_recommendation": False,
        }
    except Exception as exc:
        summary = {
            "blockers": [exc.__class__.__name__],
            "candidate": False,
            "formal_recommendation": False,
        }
    finally:
        released = lock.release()
    audit = RefreshTaskAudit(
        task_id=task_id,
        key=key,
        owner=owner_marker,
        queued_at=iso(queued_at or started_at),
        started_at=iso(started_at),
        finished_at=iso(utc_now()),
        status=status,
        result={**summary, "lock_released": released},
    )
    write_task_audit(root, audit)
    return audit


def write_task_audit(root: Path, audit: RefreshTaskAudit) -> None:
    write_json_atomic(root / "task_audit" / f"{audit.task_id}.json", audit.__dict__)
