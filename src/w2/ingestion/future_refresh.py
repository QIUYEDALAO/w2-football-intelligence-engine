from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError

from w2.competitions.registry import CompetitionRegistry, CompetitionRegistryError
from w2.config import Settings, get_settings
from w2.domain.canonical_serialization import (
    HashDomain,
    SerializerVersion,
    canonical_bytes,
    canonical_sha256,
)
from w2.ingestion.authoritative_lineup import (
    AuthoritativeLineupError,
    validate_authoritative_lineup,
)
from w2.ingestion.future_refresh_repository import (
    FutureRefreshDbRepository,
    FutureRefreshPersistenceError,
)
from w2.markets.asian_handicap_scope import canonical_market_from_label
from w2.operations.gate_a import (
    GATE_A_CANARY_ENDPOINTS,
    GATE_A_CANARY_PROVIDER_CALL_CAP,
    GATE_A_EXACT_FIXTURE_SCOPE,
    GATE_A_WINDOW_FIXTURE_SCOPE,
    GateARunReservation,
    GateARuntimeAuthorization,
    select_fixture_from_authorization,
)
from w2.prematch.read_model_projection import (
    FrozenAnalysisError,
    ProjectionSourceEvent,
)
from w2.providers.api_football import ApiFootballClient, LiveApiFootballResponse
from w2.providers.control import (
    env_int,
    provider_endpoint_allowlist,
    provider_http_max_attempts,
    provider_refresh_tick_hard_cap,
)
from w2.providers.quota import (
    API_FOOTBALL_FREE_UNALLOCATED_BUFFER,
    REGISTERED_PROVIDER_DAILY_QUOTA_POOLS,
    parse_api_football_quota,
    postmatch_result_quota_decision,
    provider_daily_budget_contract,
    provider_daily_hard_cap_decision,
    quota_guard_decision,
)

logger = logging.getLogger(__name__)


class FutureRefreshError(RuntimeError):
    pass


class RefreshLockError(RuntimeError):
    pass


_FULL_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_UNBOUND_SOURCE_REVISIONS = frozenset({"", "UNKNOWN", "LOCAL_UNDEPLOYED"})


class LiveApiFootballPort(Protocol):
    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        pass


ResultMaterializer = Callable[[tuple[str, ...], datetime], dict[str, Any]]


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
    daily_unallocated_buffer: int
    daily_reserve: int
    daily_usage_scope: str
    checkpoint_mode: str
    trickle_backfill_daily_budget: int
    config_hash: str


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
    daily_unallocated_buffer: int = API_FOOTBALL_FREE_UNALLOCATED_BUFFER
    daily_reserve: int = 1500
    daily_usage_scope: str = "w2_ledger"
    checkpoint_mode: str = "matchday_checkpoint_plan"
    trickle_backfill_daily_budget: int = 0
    actual_provider_calls_today: int | None = None
    provider_refresh_batch_size: int = 3
    policy_config_hash: str = ""
    checkpoint_fixture_ids: tuple[str, ...] = ()
    refresh_checkpoints: tuple[dict[str, Any], ...] = ()
    result_refresh_fixture_ids: tuple[str, ...] = ()
    discovery_date: str | None = None


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
    exact_pair_count: int = 0
    identity_pool_expansions: list[dict[str, Any]] = field(default_factory=list)
    requests: list[dict[str, Any]] = field(default_factory=list)


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
    gate_a_authorization_id: str | None = None
    gate_a_lease_epoch: int | None = None


def refresh_progress_status(result: FutureRefreshResult) -> str:
    if result.blockers or result.status in {"BLOCKED", "PARTIAL_FAILED", "FAILED"}:
        return "FAILED"
    if (
        result.status == "DISCOVERY_COMPLETE"
        or result.market_snapshot_count > 0
        or result.materialized_fixture_ids
    ):
        return "DATA_PROGRESS"
    return "PROVIDER_EMPTY"


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
    return canonical_bytes(
        payload,
        domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
        version=SerializerVersion.LEGACY_V1,
    ).decode("utf-8")


def sha256_payload(payload: Any, *, domain: HashDomain) -> str:
    return canonical_sha256(payload, domain=domain, version=SerializerVersion.LEGACY_V1)


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
    return len(response) if isinstance(response, list) else int(isinstance(response, dict))


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


def _api_football_fixture_id(fixture_id: str) -> str:
    prefix, separator, provider_fixture_id = fixture_id.partition(":")
    if separator and prefix == "api_football" and provider_fixture_id:
        return provider_fixture_id
    return fixture_id


def kickoff_from_payload(item: dict[str, Any]) -> datetime | None:
    return parse_utc(item.get("fixture", {}).get("date"))


def sanitize_params(params: dict[str, str]) -> dict[str, str]:
    blocked = {"key", "api_key", "token", "password", "authorization"}
    return {key: ("REDACTED" if key.lower() in blocked else value) for key, value in params.items()}


def load_refresh_policy(
    *,
    competition_id: str,
    registry: CompetitionRegistry | None = None,
) -> CompetitionRefreshPolicy:
    try:
        entry = (registry or CompetitionRegistry()).require_enabled(competition_id)
    except CompetitionRegistryError as exc:
        raise FutureRefreshError(str(exc)) from exc
    item = entry.future_refresh_policy
    if isinstance(item, dict):
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
            enabled=entry.enabled and entry.refresh_switches.get("fixtures") is True,
            daily_hard_cap=int(item.get("daily_hard_cap", 7500)),
            daily_unallocated_buffer=int(
                item.get("daily_unallocated_buffer", API_FOOTBALL_FREE_UNALLOCATED_BUFFER)
            ),
            daily_reserve=int(item.get("daily_reserve", quota_reserve)),
            daily_usage_scope=str(item.get("daily_usage_scope", "provider_quota")),
            checkpoint_mode=str(item.get("checkpoint_mode", "matchday_checkpoint_plan")),
            trickle_backfill_daily_budget=int(item.get("trickle_backfill_daily_budget", 0)),
            config_hash=entry.config_hash,
        )
    raise FutureRefreshError("FUTURE_REFRESH_COMPETITION_NOT_REGISTERED")


def config_from_policy(
    *,
    competition_id: str = "world_cup_2026",
    runtime_root: Path | None = None,
    registry: CompetitionRegistry | None = None,
) -> FutureRefreshConfig:
    policy = load_refresh_policy(competition_id=competition_id, registry=registry)
    effective_daily_cap = env_int(
        "W2_PROVIDER_DAILY_HARD_CAP",
        default=policy.daily_hard_cap,
    )
    pool_limits = {
        pool.name: env_int(
            pool.env_var,
            default=effective_daily_cap if pool.name == "GENERAL" else pool.default_limit,
        )
        for pool in REGISTERED_PROVIDER_DAILY_QUOTA_POOLS
    }
    daily_unallocated_buffer = env_int(
        "W2_PROVIDER_DAILY_UNALLOCATED_BUFFER",
        default=policy.daily_unallocated_buffer,
    )
    budget = provider_daily_budget_contract(
        pool_limits=pool_limits,
        unallocated_buffer=daily_unallocated_buffer,
    )
    if not budget["valid"]:
        raise FutureRefreshError("PROVIDER_DAILY_BUDGET_EXCEEDS_KNOWN_FREE_PLAN_LIMIT")
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
        source_revision=_bound_source_revision(),
        enabled=policy.enabled,
        persistence=os.environ.get("W2_FUTURE_REFRESH_PERSISTENCE", "db").lower(),
        daily_hard_cap=policy.daily_hard_cap,
        daily_unallocated_buffer=policy.daily_unallocated_buffer,
        daily_reserve=policy.daily_reserve,
        daily_usage_scope=policy.daily_usage_scope,
        checkpoint_mode=policy.checkpoint_mode,
        trickle_backfill_daily_budget=policy.trickle_backfill_daily_budget,
        policy_config_hash=policy.config_hash,
    )


def _bound_source_revision() -> str:
    revision = (os.environ.get("W2_GIT_SHA") or "").strip()
    environment = (os.environ.get("W2_ENVIRONMENT") or "").strip().lower()
    local_or_test = environment in {"", "local", "test", "development"}
    if _FULL_GIT_SHA.fullmatch(revision):
        return revision
    if local_or_test and revision not in _UNBOUND_SOURCE_REVISIONS:
        return revision
    if local_or_test:
        return "LOCAL_UNDEPLOYED"
    raise FutureRefreshError("SOURCE_REVISION_NOT_BOUND_TO_EXACT_GIT_SHA")


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
    raw_hash = raw_payload_sha256 or sha256_payload(
        payload, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD
    )
    captured_at = iso(response.captured_at)
    capture_id = sha256_payload(
        {
            "schema_version": "w2.future_refresh.odds_capture.v1",
            "endpoint": response.endpoint,
            "params": sanitize_params(dict(response.params)),
            "captured_at": captured_at,
            "raw_payload_sha256": raw_hash,
            "source_revision": source_revision,
        },
        domain=HashDomain.FUTURE_REFRESH_ENDPOINT_CAPTURE,
    )
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
                        "capture_id": capture_id,
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
                    observation_id = sha256_payload(
                        identity, domain=HashDomain.FUTURE_REFRESH_MARKET_OBSERVATION
                    )
                    rows.append(
                        {
                            "observation_id": observation_id,
                            "fixture_id": fixture_id,
                            "provider": "api_football",
                            "bookmaker_id": bookmaker_id,
                            "bookmaker_name": bookmaker_name,
                            "capture_id": capture_id,
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
        materialize_public_artifacts: Callable[[list[ProjectionSourceEvent]], list[str]]
        | None = None,
        materialize_results: ResultMaterializer | None = None,
        runtime_authorization: GateARuntimeAuthorization | None = None,
        provider_call_reservation: GateARunReservation | None = None,
    ) -> None:
        self.config = config or config_from_policy()
        self.runtime_authorization = runtime_authorization
        self.provider_call_reservation = provider_call_reservation
        self.client = client or ApiFootballClient(
            allow_live=runtime_authorization is not None,
            allowed_live_endpoints=self._allowed_live_endpoints(self.config),
        )
        self.now = now or utc_now()
        self.sleep = sleep or time.sleep
        self.materialize_public_artifacts = materialize_public_artifacts
        self.materialize_results = materialize_results
        self._attempt_count = 0
        self._latest_remaining: int | None = None
        self._audit: list[dict[str, Any]] = []
        self._odds_request_fixture_ids: list[str] = []
        self._raw_payload_written: set[str] = set()
        self._raw_payload_written_count = 0
        self._feature_enrichment_batch_count = 0
        self._matchday_capture_by_payload: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        self._projection_events: dict[tuple[str, str, str], ProjectionSourceEvent] = {}
        self._checkpoint_errors: list[str] = []
        self._checkpoint_attempted_plan_ids: set[str] = set()
        self._checkpoint_preflight_failures: set[str] = set()
        self._identity_pool_expansions: list[dict[str, Any]] = []

    def _db_repository(self) -> FutureRefreshDbRepository:
        return FutureRefreshDbRepository()

    def _load_persisted_provider_remaining(self) -> None:
        if self.config.persistence != "db":
            return
        day_start = self.now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            remaining = self._db_repository().provider_quota_snapshot(day_start).get("remaining")
        except FutureRefreshPersistenceError:
            return
        if remaining is not None:
            self._latest_remaining = max(int(remaining), 0)

    def _allowed_live_endpoints(self, config: FutureRefreshConfig) -> frozenset[str]:
        base = {"status", "fixtures", "odds"}
        enrichment = (
            set(config.feature_enrichment_endpoints) if config.feature_enrichment_enabled else set()
        )
        configured = base | (enrichment & {"statistics", "lineups", "injuries"})
        endpoints = configured & set(provider_endpoint_allowlist())
        if self.runtime_authorization is not None:
            endpoints &= set(self.runtime_authorization.allowed_endpoints)
        return frozenset(endpoints)

    def run(self) -> FutureRefreshResult:
        blockers: list[str] = []
        if self.runtime_authorization is not None and self.provider_call_reservation is None:
            raise FutureRefreshError("GATE_A_PROVIDER_CALL_RESERVATION_REQUIRED")
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
        self._load_persisted_provider_remaining()
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
                    "billable_calls_today": preflight["billable_calls_today"],
                    "successful_calls_today": preflight["successful_calls_today"],
                    "budget_basis": "BILLABLE_CALLS",
                    "planned_calls": preflight["planned_calls"],
                    "reserved_capture_count": preflight.get("reserved_capture_count", 0),
                    "reserved_capture_calls": preflight.get("reserved_capture_calls", 0),
                    "daily_cap": preflight["daily_cap"],
                    "reserve_bucket": preflight["reserve_bucket"],
                    "remaining_after_plan": preflight["remaining_after_plan"],
                    "quota_scope": preflight.get("quota_scope", "GENERAL"),
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
            checkpoint_mode = self._checkpoint_mode()
            direct_checkpoint = checkpoint_mode == "DIRECT"
            discovery_only = self.config.discovery_date is not None
            if discovery_only:
                fixtures_response = self._request(
                    "fixtures",
                    self._fixtures_request_params(),
                    allow_empty_response=True,
                )
                future_fixtures = self._discovery_fixtures(fixtures_response.payload)
                odds_responses: list[tuple[str, LiveApiFootballResponse]] = []
                enrichment_responses: list[tuple[str, str, LiveApiFootballResponse]] = []
            elif direct_checkpoint:
                (
                    fixtures_response,
                    future_fixtures,
                    odds_responses,
                    enrichment_responses,
                ) = self._run_checkpoint_requests()
                blockers.extend(self._checkpoint_errors)
            elif checkpoint_mode in {"NONE", "POSTMATCH"}:
                self._request("status", {})
                fixtures_response = self._request("fixtures", self._fixtures_request_params())
                future_fixtures = self._future_fixtures(fixtures_response.payload)
                odds_responses = self._fetch_market_snapshots(future_fixtures)
                enrichment_responses = self._fetch_feature_enrichment(future_fixtures)
            else:
                raise FutureRefreshError("CHECKPOINT_ENDPOINT_SET_INVALID")
            result = self._persist(
                fixtures_response,
                future_fixtures,
                odds_responses,
                enrichment_responses,
                blockers,
                persist_fixture_identities=not direct_checkpoint,
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
            error_code = (
                str(exc)
                if self.runtime_authorization is not None or isinstance(exc, FrozenAnalysisError)
                else exc.__class__.__name__
            )
            blockers.append(error_code)
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
                status="BLOCKED" if self.runtime_authorization is not None else "PARTIAL_FAILED",
                raw_payload_written_count=self._raw_payload_written_count,
                error_code=error_code,
            )
            self._write_audit(result)
        return result

    def run_staged_gate_a_canary(self, fixture_id: str | None = None) -> FutureRefreshResult:
        """Run the isolated five-call Pre/Lineup/Post feasibility path."""
        authorization = self.runtime_authorization
        if (
            authorization is None
            or self.provider_call_reservation is None
            or self.config.persistence != "db"
        ):
            raise FutureRefreshError("GATE_A_STAGED_CANARY_AUTHORIZATION_REQUIRED")
        if (
            authorization.fixture_scope_mode == GATE_A_EXACT_FIXTURE_SCOPE
            and fixture_id != authorization.fixture_id
        ):
            raise FutureRefreshError("GATE_A_FIXTURE_SCOPE_MISMATCH")
        if (
            authorization.allowed_endpoints != GATE_A_CANARY_ENDPOINTS
            or authorization.provider_call_cap != GATE_A_CANARY_PROVIDER_CALL_CAP
        ):
            raise FutureRefreshError("GATE_A_STAGED_CANARY_SCOPE_INVALID")

        self._request("status", {})
        if authorization.fixture_scope_mode == GATE_A_WINDOW_FIXTURE_SCOPE:
            assert authorization.kickoff_window_start_utc is not None
            assert authorization.kickoff_window_end_utc is not None
            fixture_params = {
                "league": authorization.provider_league_id,
                "season": authorization.season,
                "from": authorization.kickoff_window_start_utc.date().isoformat(),
                "to": authorization.kickoff_window_end_utc.date().isoformat(),
            }
        else:
            assert fixture_id is not None
            fixture_params = {"id": fixture_id}
        fixtures_response = self._request("fixtures", fixture_params, allow_empty_response=True)
        if authorization.fixture_scope_mode == GATE_A_WINDOW_FIXTURE_SCOPE:
            selection = select_fixture_from_authorization(
                fixtures_response.payload,
                authorization,
            )
            fixture_id = selection.selected_fixture_id
            fixtures = self._selected_fixture_rows(fixtures_response.payload, fixture_id)
        else:
            assert fixture_id is not None
            fixtures = self._signed_fixture_rows(fixtures_response.payload, fixture_id)
            selection = select_fixture_from_authorization(
                fixtures_response.payload,
                authorization,
            )
        discovery_capture_id = self._fixture_discovery_capture_id(
            fixtures_response,
            request_params=fixture_params,
        )
        self.provider_call_reservation.bind_selected_fixture(
            fixture_id=fixture_id,
            candidate_set_sha256=selection.candidate_set_sha256,
            discovery_capture_id=discovery_capture_id,
            eligible_candidate_count=selection.eligible_candidate_count,
            selected_at=fixtures_response.captured_at,
        )
        self._persist_canary_fixture_identity(
            fixtures_response,
            fixtures,
            request_params=fixture_params,
        )
        # The staged path begins evaluation at odds_pre. Fixture identity is
        # already durable and must not trigger an earlier empty-market build.
        self._projection_events.clear()

        odds_pre = self._request("odds", {"fixture": fixture_id})
        _pre_inserted, pre_rows = self._persist_canary_odds(fixture_id, odds_pre)
        pre_capture_at = odds_pre.captured_at
        from w2.operations.gate_a_staged import (
            materialize_staged_dynamic_v2,
            persist_staged_lineup_event,
        )

        materialize_staged_dynamic_v2(
            pre_rows,
            captured_at=pre_capture_at,
            lineup_input_hash=None,
            lineup_confirmed_at=None,
            checkpoint="GATE_A_STAGED_PRE",
            competition_id=self.config.competition_id,
            season=self.config.season,
        )
        self._projection_events.clear()
        materialized = [fixture_id]

        lineups = self._request("lineups", {"fixture": fixture_id})
        if response_count(lineups.payload) == 0:
            raise FutureRefreshError("GATE_A_CANARY_LINEUPS_EMPTY")
        self._materialize_lineup_enrichment(
            fixtures=fixtures,
            enrichment_responses=[(fixture_id, "lineups", lineups)],
        )
        canonical_lineup = self._db_repository().canonical_lineup_confirmed_event(fixture_id)
        if canonical_lineup is None:
            raise FutureRefreshError("LINEUP_MATERIALIZATION_FAILED:CANONICAL_EVENT_MISSING")
        persist_staged_lineup_event(canonical_lineup)
        lineup_events = [
            event
            for event in self._projection_events.values()
            if event.event_type == "LINEUP_CHANGED"
        ]
        if len(lineup_events) != 1 or pre_capture_at >= lineup_events[0].event_at:
            raise FutureRefreshError("GATE_A_CANARY_PRE_LINEUP_ORDER_INVALID")
        lineup_event_at = lineup_events[0].event_at
        lineup_hash = str(lineup_events[0].event_id).removeprefix("lineup:")
        self._projection_events.clear()

        odds_post = self._request("odds", {"fixture": fixture_id})
        if odds_post.captured_at < lineup_event_at:
            raise FutureRefreshError("GATE_A_CANARY_POST_LINEUP_ORDER_INVALID")
        appended, post_rows = self._persist_canary_odds(fixture_id, odds_post)
        materialize_staged_dynamic_v2(
            post_rows,
            captured_at=odds_post.captured_at,
            lineup_input_hash=lineup_hash,
            lineup_confirmed_at=lineup_event_at,
            checkpoint="GATE_A_STAGED_POST",
            competition_id=self.config.competition_id,
            season=self.config.season,
        )
        self._projection_events.clear()

        from w2.infrastructure.database import create_engine
        from w2.prematch.repository import project_exact_eval_02b_pairs

        pair_count = sum(
            pair.identity.canonical_fixture_id in {fixture_id, f"api_football:{fixture_id}"}
            for pair in project_exact_eval_02b_pairs(create_engine()).pairs
        )
        result = FutureRefreshResult(
            generated_at_utc=utc_now(),
            fixture_count=1,
            mapping_count=1,
            market_snapshot_count=2,
            feature_enrichment_payload_count=1,
            ledger_appended_count=appended,
            request_count=self._attempt_count,
            remaining_quota=self._latest_remaining,
            selected_market_fixture_ids=[fixture_id],
            raw_payload_written_count=self._raw_payload_written_count,
            materialized_fixture_ids=list(dict.fromkeys(materialized)),
            exact_pair_count=pair_count,
        )
        self._write_audit(result)
        return result

    @staticmethod
    def _selected_fixture_rows(
        payload: dict[str, Any],
        fixture_id: str,
    ) -> list[dict[str, Any]]:
        response = payload.get("response")
        if not isinstance(response, list):
            raise FutureRefreshError("PROVIDER_FIXTURES_SCHEMA_DRIFT")
        row = next(
            (
                item
                for item in response
                if isinstance(item, dict) and fixture_id_from_payload(item) == fixture_id
            ),
            None,
        )
        if row is None:
            raise FutureRefreshError("GATE_A_NO_ELIGIBLE_FIXTURE_IN_SIGNED_WINDOW")
        return [row]

    def _fixture_discovery_capture_id(
        self,
        response: LiveApiFootballResponse,
        *,
        request_params: dict[str, str],
    ) -> str:
        raw_record = self._raw_payload_record(
            endpoint="fixtures",
            params=request_params,
            payload=response.payload,
        )
        raw_sha = sha256_payload(raw_record, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)
        capture = self._matchday_capture_by_payload.get(
            self._capture_lookup_key(
                endpoint="fixtures",
                params=request_params,
                raw_payload_sha256=raw_sha,
                captured_at=response.captured_at,
            )
        )
        if capture is None:
            raise FutureRefreshError("GATE_A_FIXTURE_BINDING_FAILED")
        return str(capture["capture_id"])

    def _signed_fixture_rows(
        self,
        payload: dict[str, Any],
        fixture_id: str,
    ) -> list[dict[str, Any]]:
        response = payload.get("response")
        if not isinstance(response, list) or not response:
            raise FutureRefreshError("GATE_A_SIGNED_FIXTURE_NOT_FOUND")
        if any(
            not isinstance(item, dict) or fixture_id_from_payload(item) != fixture_id
            for item in response
        ):
            raise FutureRefreshError("GATE_A_FIXTURE_SCOPE_MISMATCH")
        rows = self._future_fixtures(payload)
        if len(rows) != 1 or fixture_id_from_payload(rows[0]) != fixture_id:
            raise FutureRefreshError("GATE_A_SIGNED_FIXTURE_NOT_ELIGIBLE")
        return rows

    def _persist_canary_fixture_identity(
        self,
        response: LiveApiFootballResponse,
        fixtures: list[dict[str, Any]],
        *,
        request_params: dict[str, str],
    ) -> None:
        from w2.matchday.repository import MatchdayRuntimeRepository

        identities = self._fixture_identities_from_response(
            fixtures_response=response,
            fixtures=fixtures,
            request_params=request_params,
        )
        if len(identities) != 1:
            raise FutureRefreshError("FIXTURE_IDENTITY_PERSISTENCE_FAILED:IDENTITY_MISSING")
        try:
            _persisted, changed = (
                MatchdayRuntimeRepository().upsert_fixture_identities_with_business_changes(
                    identities
                )
            )
        except Exception as exc:
            raise FutureRefreshError(
                f"FIXTURE_IDENTITY_PERSISTENCE_FAILED:{exc.__class__.__name__}"
            ) from exc
        if changed:
            identity = identities[0]
            self._record_projection_event(
                ProjectionSourceEvent.create(
                    fixture_id=str(identity["provider_fixture_id"]),
                    event_type="FIXTURE_CHANGED",
                    event_id=f"fixture:{identity['identity_hash']}",
                    event_at=response.captured_at,
                    payload=identity,
                )
            )

    def _persist_canary_odds(
        self,
        fixture_id: str,
        response: LiveApiFootballResponse,
    ) -> tuple[int, list[dict[str, Any]]]:
        from w2.matchday.intake_v2 import normalize_matchday_odds_payload
        from w2.matchday.repository import MatchdayRuntimeRepository

        params = {"fixture": fixture_id}
        raw_record = self._raw_payload_record(
            endpoint="odds", params=params, payload=response.payload
        )
        raw_sha = sha256_payload(raw_record, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)
        capture = self._matchday_capture_by_payload.get(
            self._capture_lookup_key(
                endpoint="odds",
                params=params,
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
        if any(item.get("reason") == "OBSERVATION_IDENTITY_CONFLICT" for item in rejections):
            raise FutureRefreshError("OBSERVATION_NORMALIZATION_CONFLICT")
        inserted = MatchdayRuntimeRepository().insert_market_observations(rows)
        if inserted > 0:
            self._record_projection_event(
                ProjectionSourceEvent.create(
                    fixture_id=fixture_id,
                    event_type="ODDS_CHANGED",
                    event_id=f"odds:{capture['capture_id']}",
                    event_at=response.captured_at,
                    payload={
                        "observation_ids": sorted(str(row["observation_id"]) for row in rows),
                        "inserted": inserted,
                    },
                )
            )
        return inserted, rows

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
            canonical = repository.validate_checkpoint_claim(
                plan_id=plan_id,
                claim_token=claim_token,
                now=self.now,
                fixture_id=fixture_id or None,
                competition_id=self.config.competition_id,
                season=self.config.season,
            )
            if any(
                (
                    checkpoint.get("checkpoint") != canonical.get("checkpoint"),
                    tuple(checkpoint.get("endpoints") or ())
                    != tuple(canonical.get("endpoints") or ()),
                    checkpoint.get("policy_version") != canonical.get("policy_version"),
                )
            ):
                raise FutureRefreshError("CHECKPOINT_CLAIM_PAYLOAD_MISMATCH")

    def _request(
        self,
        endpoint: str,
        params: dict[str, str],
        *,
        allow_empty_response: bool = False,
    ) -> LiveApiFootballResponse:
        if not self._endpoint_authorized(endpoint):
            raise FutureRefreshError(f"ENDPOINT_NOT_AUTHORIZED:{endpoint}")
        last_error: Exception | None = None
        max_attempts = provider_http_max_attempts()
        for attempt in range(1, max_attempts + 1):
            if self._attempt_count >= self.config.request_budget:
                raise FutureRefreshError("REQUEST_BUDGET_EXHAUSTED")
            self._attempt_count += 1
            call_ordinal = None
            if self.provider_call_reservation is not None:
                call_ordinal = self.provider_call_reservation.reserve_provider_call(
                    endpoint,
                    fixture_id=params.get("fixture"),
                )
            captured_at = utc_now()
            started = time.monotonic()
            try:
                response = self.client.request_live(endpoint, params)
            except Exception as exc:
                if self.provider_call_reservation is not None and call_ordinal is not None:
                    self.provider_call_reservation.record_provider_outcome(
                        call_ordinal,
                        state="DELIVERY_UNCERTAIN",
                        error_code=exc.__class__.__name__,
                    )
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
                if self.runtime_authorization is not None:
                    raise FutureRefreshError(
                        f"PROVIDER_DELIVERY_UNCERTAIN:{exc.__class__.__name__}"
                    ) from exc
                if attempt < max_attempts:
                    self.sleep(0.2 * (2 ** (attempt - 1)))
                    continue
                raise FutureRefreshError(exc.__class__.__name__) from exc
            if self.provider_call_reservation is not None and call_ordinal is not None:
                self.provider_call_reservation.record_provider_outcome(
                    call_ordinal,
                    state="RESPONSE_RECEIVED",
                )
            quota = parse_api_football_quota(
                headers=response.headers,
                payload=response.payload,
                observed_at=response.captured_at,
            )
            remaining = quota.daily_remaining
            if remaining is None and self._latest_remaining is not None:
                remaining = max(self._latest_remaining - 1, 0)
            self._latest_remaining = remaining
            status = response.status_code
            raw_payload = self._raw_payload_record(
                endpoint=endpoint,
                params=params,
                payload=response.payload,
            )
            payload_sha = sha256_payload(raw_payload, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)
            response_size = response_count(response.payload)
            provider_errors = response.payload.get("errors")
            payload_error = provider_errors not in (None, {}, [], "")
            response_value = response.payload.get("response")
            response_schema_error = (
                not isinstance(response_value, dict)
                if endpoint == "status"
                else not isinstance(response_value, list)
            )
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
            if self.config.persistence == "db" and (
                endpoint_capture_error is not None or endpoint_capture_id is None
            ):
                raise FutureRefreshError(f"ENDPOINT_CAPTURE_WRITE_FAILED:{endpoint_capture_error}")
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
                    "error_code": (
                        f"PROVIDER_HTTP_{status}"
                        if status >= 400
                        else f"PROVIDER_{endpoint.upper()}_ERRORS"
                        if payload_error
                        else f"PROVIDER_{endpoint.upper()}_SCHEMA_DRIFT"
                        if response_schema_error
                        else None
                    ),
                }
            )
            if status == 429 and self.runtime_authorization is not None:
                raise FutureRefreshError("PROVIDER_HTTP_429")
            if status == 429 and attempt < max_attempts:
                self.sleep(0.2 * (2 ** (attempt - 1)))
                continue
            if status >= 400:
                raise FutureRefreshError(f"PROVIDER_HTTP_{status}")
            if payload_error:
                raise FutureRefreshError(f"PROVIDER_{endpoint.upper()}_ERRORS")
            if response_schema_error:
                raise FutureRefreshError(f"PROVIDER_{endpoint.upper()}_SCHEMA_DRIFT")
            postmatch_result = self._checkpoint_mode() == "POSTMATCH"
            if not postmatch_result:
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
            if self.runtime_authorization is not None:
                self._validate_gate_a_response(
                    endpoint,
                    response.payload,
                    allow_empty_response=allow_empty_response,
                )
            return response
        raise FutureRefreshError(last_error.__class__.__name__ if last_error else "REQUEST_FAILED")

    @staticmethod
    def _validate_gate_a_response(
        endpoint: str,
        payload: dict[str, Any],
        *,
        allow_empty_response: bool,
    ) -> None:
        response = payload.get("response")
        if endpoint == "status":
            if not isinstance(response, dict):
                raise FutureRefreshError("PROVIDER_STATUS_SCHEMA_DRIFT")
            return
        if not isinstance(response, list):
            raise FutureRefreshError(f"PROVIDER_{endpoint.upper()}_SCHEMA_DRIFT")
        if not response and not allow_empty_response:
            raise FutureRefreshError(f"PROVIDER_{endpoint.upper()}_EMPTY")

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
                competition_id=(
                    None
                    if self.config.discovery_date is not None and endpoint == "fixtures"
                    else self.config.competition_id
                ),
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
                request_task_key_override=(
                    self.runtime_authorization.task_key
                    if self.runtime_authorization is not None
                    else None
                ),
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

    def _checkpoint_mode(self) -> str:
        if not self.config.refresh_checkpoints:
            return "NONE"
        endpoint_sets = [
            set(item.get("endpoints") or []) for item in self.config.refresh_checkpoints
        ]
        if all(
            endpoints == {"status", "fixtures"}
            and str(item.get("checkpoint") or "") == "POSTMATCH_RESULT"
            for item, endpoints in zip(self.config.refresh_checkpoints, endpoint_sets, strict=True)
        ):
            return "POSTMATCH"
        if self.config.persistence == "db" and all(
            endpoints and endpoints <= {"odds", "lineups"} for endpoints in endpoint_sets
        ):
            return "DIRECT"
        return "INVALID"

    def _run_checkpoint_requests(
        self,
    ) -> tuple[
        LiveApiFootballResponse,
        list[dict[str, Any]],
        list[tuple[str, LiveApiFootballResponse]],
        list[tuple[str, str, LiveApiFootballResponse]],
    ]:
        fixtures: dict[str, dict[str, Any]] = {}
        odds: list[tuple[str, LiveApiFootballResponse]] = []
        lineups: list[tuple[str, str, LiveApiFootballResponse]] = []
        seen: set[tuple[str, str]] = set()
        repository = self._db_repository()
        for plan in self.config.refresh_checkpoints:
            plan_id = str(plan.get("id") or plan.get("plan_id") or "")
            fixture_id = _api_football_fixture_id(str(plan.get("fixture_id") or ""))
            payload = fixtures.get(fixture_id) or repository.fixture_payload(fixture_id)
            if payload is None or fixture_id_from_payload(payload) != fixture_id:
                self._checkpoint_preflight_failures.add(plan_id)
                self._checkpoint_errors.append(f"CHECKPOINT_FIXTURE_PAYLOAD_MISSING:{fixture_id}")
                continue
            fixtures[fixture_id] = payload
            for endpoint in plan.get("endpoints") or []:
                if (fixture_id, endpoint) in seen:
                    continue
                seen.add((fixture_id, endpoint))
                if endpoint == "odds":
                    self._odds_request_fixture_ids.append(fixture_id)
                self._checkpoint_attempted_plan_ids.update(
                    str(item.get("id") or item.get("plan_id") or "")
                    for item in self.config.refresh_checkpoints
                    if _api_football_fixture_id(str(item.get("fixture_id") or "")) == fixture_id
                    and endpoint in set(item.get("endpoints") or [])
                )
                try:
                    response = self._request(str(endpoint), {"fixture": fixture_id})
                except FutureRefreshError as exc:
                    reason = str(exc)
                    if reason in {
                        f"PROVIDER_{str(endpoint).upper()}_ERRORS",
                        f"PROVIDER_{str(endpoint).upper()}_SCHEMA_DRIFT",
                    }:
                        self._checkpoint_errors.append(reason)
                        continue
                    raise
                if endpoint == "odds" and bookmaker_count(response.payload) > 0:
                    odds.append((fixture_id, response))
                elif endpoint == "lineups" and response_count(response.payload) > 0:
                    lineups.append((fixture_id, "lineups", response))
        fixture_rows = list(fixtures.values())
        return (
            LiveApiFootballResponse(
                endpoint="fixtures",
                params={},
                status_code=200,
                elapsed_ms=0,
                payload={"response": fixture_rows},
                headers={},
                captured_at=self.now,
            ),
            fixture_rows,
            odds,
            lineups,
        )

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
            sha256_payload(
                sanitize_params(params), domain=HashDomain.FUTURE_REFRESH_REQUEST_PARAMETERS
            ),
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

    def _record_projection_event(self, event: ProjectionSourceEvent) -> None:
        self._projection_events[(event.fixture_id, event.event_type, event.event_id)] = event

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
            self._raw_payload_record(endpoint=endpoint, params=params, payload=payload),
            domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
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
        planned_calls = self._planned_provider_calls()
        if self._checkpoint_mode() == "POSTMATCH":
            daily_cap = env_int("W2_POSTMATCH_RESULT_DAILY_HARD_CAP", default=20)
            day_start = self.now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            try:
                repository = self._db_repository()
                actual_calls_today = (
                    repository.postmatch_result_request_count_since(day_start)
                    if self.config.persistence == "db"
                    else 0
                )
                successful_calls_today = (
                    self._postmatch_result_successful_calls_today(day_start)
                    if self.config.persistence == "db"
                    else 0
                )
                reserved_capture_count = (
                    repository.unsettled_model_forecast_postmatch_count(
                        window_start=day_start,
                        window_end=day_start + timedelta(days=1),
                        exclude_fixture_ids=self.config.checkpoint_fixture_ids,
                    )
                    if self.config.persistence == "db"
                    else 0
                )
            except FutureRefreshPersistenceError as exc:
                raise FutureRefreshError("RESULT_USAGE_AUDIT_UNAVAILABLE") from exc
            return {
                **postmatch_result_quota_decision(
                    actual_calls_today=actual_calls_today,
                    planned_calls=planned_calls,
                    reserved_capture_calls=reserved_capture_count * planned_calls,
                    daily_cap=daily_cap,
                ),
                "reserved_capture_count": reserved_capture_count,
                "successful_calls_today": successful_calls_today,
            }
        daily_cap = env_int("W2_PROVIDER_DAILY_HARD_CAP", default=self.config.daily_hard_cap)
        reserve = env_int("W2_PROVIDER_DAILY_RESERVE", default=self.config.daily_reserve)
        actual_calls_today = self._actual_provider_calls_today()
        return {
            **provider_daily_hard_cap_decision(
                actual_calls_today=actual_calls_today,
                planned_calls=planned_calls,
                daily_cap=daily_cap,
                reserve_bucket=reserve,
            ),
            "successful_calls_today": self._successful_provider_calls_today(),
        }

    def _provider_tick_hard_cap_preflight(self) -> dict[str, Any]:
        projected_calls = self._planned_provider_calls()
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
        if self.config.discovery_date is not None:
            return 1
        if self._checkpoint_mode() == "DIRECT":
            return len(
                {
                    (str(item.get("fixture_id") or ""), str(endpoint))
                    for item in self.config.refresh_checkpoints
                    for endpoint in item.get("endpoints") or []
                }
            )
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
        return self._projected_provider_calls() * provider_http_max_attempts()

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
                include_quota_usage=True,
            )
        except FutureRefreshPersistenceError as exc:
            raise FutureRefreshError("PROVIDER_USAGE_AUDIT_UNAVAILABLE") from exc

    def _successful_provider_calls_today(self) -> int:
        if self.config.persistence != "db":
            return 0
        day_start = self.now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            reader = getattr(self._db_repository(), "successful_request_count_since", None)
            return int(reader(day_start)) if callable(reader) else 0
        except FutureRefreshPersistenceError as exc:
            raise FutureRefreshError("PROVIDER_SUCCESS_AUDIT_UNAVAILABLE") from exc

    def _postmatch_result_successful_calls_today(self, day_start: datetime) -> int:
        reader = getattr(
            self._db_repository(),
            "postmatch_result_successful_request_count_since",
            None,
        )
        return int(reader(day_start)) if callable(reader) else 0

    def _future_fixtures(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        response = payload.get("response")
        if not isinstance(response, list):
            return []
        allowed_fixture_ids = {
            _api_football_fixture_id(fixture_id)
            for fixture_id in self.config.checkpoint_fixture_ids
        }
        rows: list[dict[str, Any]] = []
        for item in response:
            if not isinstance(item, dict):
                continue
            fixture_id = fixture_id_from_payload(item)
            if allowed_fixture_ids and fixture_id not in allowed_fixture_ids:
                continue
            if self.config.result_refresh_fixture_ids:
                rows.append(item)
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
    ) -> list[tuple[str, str, LiveApiFootballResponse]]:
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
        responses: list[tuple[str, str, LiveApiFootballResponse]] = []
        batch_size = max(
            env_int(
                "W2_PROVIDER_REFRESH_BATCH_SIZE",
                default=self.config.provider_refresh_batch_size,
            ),
            1,
        )
        pending: list[tuple[str, str, LiveApiFootballResponse]] = []
        for item in fixtures:
            fixture_id = fixture_id_from_payload(item)
            if not fixture_id:
                continue
            for endpoint in endpoints:
                if not self._endpoint_authorized(endpoint):
                    self._append_unauthorized_endpoint_skip(endpoint, fixture_id)
                    continue
                if self._attempt_count >= self.config.request_budget:
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
                            "error_code": "FEATURE_ENRICHMENT_SKIPPED_REQUEST_BUDGET",
                        }
                    )
                    if pending:
                        self._feature_enrichment_batch_count += 1
                        responses.extend(pending)
                    return responses
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
                pending.append((fixture_id, endpoint, response))
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
        enrichment_responses: list[tuple[str, str, LiveApiFootballResponse]],
        blockers: list[str],
        *,
        persist_fixture_identities: bool = True,
    ) -> FutureRefreshResult:
        if self.config.persistence == "db":
            return self._persist_db(
                fixtures_response,
                fixtures,
                odds_responses,
                enrichment_responses,
                blockers,
                persist_fixture_identities=persist_fixture_identities,
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
        if appended > 0:
            for fixture_id, response in odds_responses:
                self._record_projection_event(
                    ProjectionSourceEvent.create(
                        fixture_id=fixture_id,
                        event_type="ODDS_CHANGED",
                        event_id="odds:"
                        + sha256_payload(
                            response.payload,
                            domain=HashDomain.FUTURE_REFRESH_LINEUP_EVENT,
                        ),
                        event_at=response.captured_at,
                        payload=response.payload,
                    )
                )
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
            materialized_fixture_ids=self._materialize_refreshed_public_artifacts(),
        )
        self._write_audit(result)
        return result

    def _materialize_refreshed_public_artifacts(
        self,
    ) -> list[str]:
        if not self._projection_events:
            return []
        # File persistence is retained for offline/local audit flows. Production
        # DB refreshes project automatically; file-mode callers must opt in with
        # an explicit materializer so they never acquire an accidental DB write.
        if self.config.persistence != "db" and self.materialize_public_artifacts is None:
            return []
        if self.materialize_public_artifacts is None:
            raise FutureRefreshError("PROJECTION_MATERIALIZER_NOT_INJECTED")
        materializer = self.materialize_public_artifacts
        events = sorted(
            self._projection_events.values(),
            key=lambda item: (
                item.event_at,
                item.fixture_id,
                item.event_type,
                item.event_id,
            ),
        )
        return materializer(events)

    def _persist_db(
        self,
        fixtures_response: LiveApiFootballResponse,
        fixtures: list[dict[str, Any]],
        odds_responses: list[tuple[str, LiveApiFootballResponse]],
        enrichment_responses: list[tuple[str, str, LiveApiFootballResponse]],
        blockers: list[str],
        *,
        persist_fixture_identities: bool = True,
    ) -> FutureRefreshResult:
        try:
            from w2.matchday.repository import MatchdayRuntimeRepository

            repository = MatchdayRuntimeRepository()
            fixture_identities = (
                self._fixture_identities_from_response(
                    fixtures_response=fixtures_response,
                    fixtures=fixtures,
                )
                if persist_fixture_identities
                else []
            )
            for fixture_identity in fixture_identities:
                try:
                    _persisted, changed_fixture_ids = (
                        repository.upsert_fixture_identities_with_business_changes(
                            [fixture_identity]
                        )
                    )
                except Exception as exc:
                    raise FutureRefreshError(
                        f"FIXTURE_IDENTITY_PERSISTENCE_FAILED:{exc.__class__.__name__}"
                    ) from exc
                if changed_fixture_ids and not self.config.result_refresh_fixture_ids:
                    fixture_id = str(
                        fixture_identity.get("provider_fixture_id")
                        or fixture_identity.get("fixture_id")
                        or ""
                    )
                    if fixture_id:
                        self._record_projection_event(
                            ProjectionSourceEvent.create(
                                fixture_id=fixture_id,
                                event_type="FIXTURE_CHANGED",
                                event_id=(
                                    "fixture:" + str(fixture_identity.get("identity_hash") or "")
                                ),
                                event_at=fixtures_response.captured_at,
                                payload=fixture_identity,
                            )
                        )
            self._seed_provider_primary_identities(
                fixture_identities=fixture_identities,
                captured_at=fixtures_response.captured_at,
            )
            self._materialize_lineup_enrichment(
                fixtures=fixtures,
                enrichment_responses=enrichment_responses,
            )
            observations: list[dict[str, Any]] = []
            for fixture_id, response in odds_responses:
                from w2.matchday.intake_v2 import normalize_matchday_odds_payload

                raw_record = self._raw_payload_record(
                    endpoint="odds",
                    params={"fixture": fixture_id},
                    payload=response.payload,
                )
                raw_sha = sha256_payload(raw_record, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)
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
                    item.get("reason") == "OBSERVATION_IDENTITY_CONFLICT" for item in rejections
                ):
                    raise FutureRefreshError("OBSERVATION_NORMALIZATION_CONFLICT")
                observations.extend(rows)
            appended = 0
            observations_by_fixture: dict[str, list[dict[str, Any]]] = {}
            for row in observations:
                fixture_id = str(row.get("provider_fixture_id") or row.get("fixture_id") or "")
                observations_by_fixture.setdefault(fixture_id, []).append(row)
            for fixture_id, rows in observations_by_fixture.items():
                inserted = repository.insert_market_observations(rows)
                appended += inserted
                if inserted > 0:
                    latest = max(
                        rows,
                        key=lambda item: str(item.get("captured_at") or ""),
                    )
                    event_at = parse_utc(latest.get("captured_at"))
                    if event_at is None:
                        raise FutureRefreshError("ODDS_EVENT_TIME_MISSING")
                    self._record_projection_event(
                        ProjectionSourceEvent.create(
                            fixture_id=fixture_id,
                            event_type="ODDS_CHANGED",
                            event_id=f"odds:{latest.get('capture_id')}",
                            event_at=event_at,
                            payload={
                                "observation_ids": sorted(
                                    str(item.get("observation_id") or "") for item in rows
                                ),
                                "inserted": inserted,
                            },
                        )
                    )
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
        if self.config.result_refresh_fixture_ids:
            if self.materialize_results is None:
                raise FutureRefreshError("RESULT_MATERIALIZER_UNAVAILABLE")
            result_refresh = self.materialize_results(
                self.config.result_refresh_fixture_ids,
                self.now,
            )
            materialized_fixture_ids = list(result_refresh["confirmed_fixture_ids"])
            if result_refresh["status"] == "BLOCKED":
                blockers.extend(str(item) for item in result_refresh.get("blockers", []))
        elif self.config.discovery_date is not None:
            materialized_fixture_ids = []
        else:
            materialized_fixture_ids = self._materialize_refreshed_public_artifacts()
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
            materialized_fixture_ids=materialized_fixture_ids,
            identity_pool_expansions=self._identity_pool_expansions,
            status=(
                "DISCOVERY_COMPLETE" if self.config.discovery_date is not None else "COMPLETED"
            ),
        )
        self._write_audit(result)
        return result

    def _materialize_lineup_enrichment(
        self,
        *,
        fixtures: list[dict[str, Any]],
        enrichment_responses: list[tuple[str, str, LiveApiFootballResponse]],
    ) -> None:
        kickoff_by_fixture = {
            fixture_id: kickoff_from_payload(item)
            for item in fixtures
            if (fixture_id := fixture_id_from_payload(item))
        }
        teams_by_fixture = {
            fixture_id: (
                str(item.get("teams", {}).get("home", {}).get("id") or ""),
                str(item.get("teams", {}).get("away", {}).get("id") or ""),
            )
            for item in fixtures
            if (fixture_id := fixture_id_from_payload(item))
        }
        repository = self._db_repository()
        for fixture_id, endpoint, response in enrichment_responses:
            if endpoint != "lineups":
                continue
            raw_record = self._raw_payload_record(
                endpoint=endpoint,
                params={"fixture": fixture_id},
                payload=response.payload,
            )
            raw_sha = sha256_payload(raw_record, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)
            capture = self._matchday_capture_by_payload.get(
                self._capture_lookup_key(
                    endpoint=endpoint,
                    params={"fixture": fixture_id},
                    raw_payload_sha256=raw_sha,
                    captured_at=response.captured_at,
                )
            )
            if capture is None:
                raise FutureRefreshError("LINEUP_MATERIALIZATION_FAILED:ENDPOINT_CAPTURE_MISSING")
            try:
                validate_authoritative_lineup(
                    raw_record.get("response"),
                    expected_team_ids=teams_by_fixture.get(fixture_id),
                    captured_at=response.captured_at,
                    kickoff_utc=kickoff_by_fixture.get(fixture_id),
                )
                previous_identity = repository.confirmed_lineup_business_identity(
                    fixture_id=fixture_id
                )
                materialized_rows = repository.save_lineup_snapshots(
                    fixture_id=fixture_id,
                    captured_at=response.captured_at,
                    raw_sha256=raw_sha,
                    payload=raw_record,
                    kickoff_at=kickoff_by_fixture.get(fixture_id),
                    source_capture_id=str(capture["capture_id"]),
                    expected_team_ids=teams_by_fixture.get(fixture_id),
                )
                lineup_event = repository.canonical_lineup_confirmed_event(fixture_id)
            except AuthoritativeLineupError as exc:
                raise FutureRefreshError(f"LINEUP_MATERIALIZATION_FAILED:{exc.code}") from exc
            except FutureRefreshPersistenceError as exc:
                reason = str(exc)
                if reason.startswith("LINEUP_MATERIALIZATION_FAILED:"):
                    raise FutureRefreshError(reason) from exc
                raise FutureRefreshError(f"LINEUP_MATERIALIZATION_FAILED:{reason}") from exc
            if lineup_event is None:
                raise FutureRefreshError("LINEUP_MATERIALIZATION_FAILED:CANONICAL_EVENT_MISSING")
            exact_replay = materialized_rows == 0 and lineup_event.source_capture_id == str(
                capture["capture_id"]
            )
            if (
                exact_replay
                or materialized_rows > 0
                and lineup_event.lineup_input_hash != previous_identity
            ):
                self._record_projection_event(
                    ProjectionSourceEvent.create(
                        fixture_id=fixture_id,
                        event_type="LINEUP_CHANGED",
                        event_id=f"lineup:{lineup_event.lineup_input_hash}",
                        event_at=lineup_event.captured_at,
                        payload={
                            "lineup_business_identity": lineup_event.lineup_input_hash,
                            "materialized_rows": materialized_rows,
                            "source_capture_id": lineup_event.source_capture_id,
                        },
                    )
                )

    def _fixtures_request_params(self) -> dict[str, str]:
        if self.config.discovery_date is not None:
            return {"date": self.config.discovery_date}
        if self.config.result_refresh_fixture_ids:
            if len(self.config.result_refresh_fixture_ids) == 1:
                return {"id": _api_football_fixture_id(self.config.result_refresh_fixture_ids[0])}
            kickoff_dates = [
                parsed.date()
                for item in self.config.refresh_checkpoints
                if (parsed := parse_utc(item.get("kickoff_utc"))) is not None
            ]
            start = min(kickoff_dates, default=self.now.date())
            return {
                "league": self.config.league_id,
                "season": self.config.season,
                "from": start.isoformat(),
                "to": self.now.date().isoformat(),
            }
        return {
            "league": self.config.league_id,
            "season": self.config.season,
            "from": self.now.date().isoformat(),
            "to": (self.now + timedelta(days=self.config.horizon_days)).date().isoformat(),
        }

    def _fixture_identities_from_response(
        self,
        *,
        fixtures_response: LiveApiFootballResponse,
        fixtures: list[dict[str, Any]],
        request_params: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        params = request_params or self._fixtures_request_params()
        raw_record = self._raw_payload_record(
            endpoint="fixtures",
            params=params,
            payload=fixtures_response.payload,
        )
        raw_sha = sha256_payload(raw_record, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)
        capture = self._matchday_capture_by_payload.get(
            self._capture_lookup_key(
                endpoint="fixtures",
                params=params,
                raw_payload_sha256=raw_sha,
                captured_at=fixtures_response.captured_at,
            )
        )
        policy_by_league: dict[str, Any] = {}
        team_mappings: dict[tuple[str, str], dict[str, str]] = {}
        reader: Any = None
        if self.config.persistence == "db":
            from w2.matchday.intake_v2 import (
                REQUIRED_MATCHDAY_COMPETITIONS,
                competition_policies,
                load_matchday_policy,
            )

            policy_by_league = {
                policy.provider_league_id: policy
                for competition_id, policy in competition_policies(load_matchday_policy()).items()
                if competition_id in REQUIRED_MATCHDAY_COMPETITIONS and policy.enabled
            }
            reader = getattr(self._db_repository(), "provider_team_mapping", None)
        rows: list[dict[str, Any]] = []
        for item in fixtures:
            if not isinstance(item, dict):
                continue
            provider_fixture_id = fixture_id_from_payload(item)
            kickoff = kickoff_from_payload(item)
            teams_value = item.get("teams")
            fixture_value = item.get("fixture")
            league_value = item.get("league")
            teams: Mapping[str, Any] = teams_value if isinstance(teams_value, dict) else {}
            fixture: Mapping[str, Any] = fixture_value if isinstance(fixture_value, dict) else {}
            league: Mapping[str, Any] = league_value if isinstance(league_value, dict) else {}
            status_value = fixture.get("status")
            home_value = teams.get("home")
            away_value = teams.get("away")
            status: Mapping[str, Any] = status_value if isinstance(status_value, dict) else {}
            home: Mapping[str, Any] = home_value if isinstance(home_value, dict) else {}
            away: Mapping[str, Any] = away_value if isinstance(away_value, dict) else {}
            if not provider_fixture_id or kickoff is None:
                continue
            provider_league_id = str(league.get("id") or self.config.league_id)
            policy = policy_by_league.get(provider_league_id)
            if self.config.discovery_date is not None and policy is None:
                continue
            competition_id = (
                str(policy.competition_id) if policy is not None else self.config.competition_id
            )
            season = str(league.get("season") or (policy.season if policy else self.config.season))
            mapping_key = (competition_id, season)
            if callable(reader) and mapping_key not in team_mappings:
                team_mappings[mapping_key] = reader(
                    provider="api_football",
                    competition_id=competition_id,
                    season=season,
                    as_of=fixtures_response.captured_at,
                )
            team_mapping = team_mappings.get(mapping_key, {})
            fixture_id = f"api_football:{provider_fixture_id}"
            home_provider_team_id = str(home.get("id") or "")
            away_provider_team_id = str(away.get("id") or "")
            home_w2_team_id = team_mapping.get(home_provider_team_id)
            away_w2_team_id = team_mapping.get(away_provider_team_id)
            identity_body = {
                "fixture_id": fixture_id,
                "provider": "api_football",
                "provider_fixture_id": provider_fixture_id,
                "competition_id": competition_id,
                "provider_league_id": provider_league_id,
                "season": season,
                "kickoff_utc": iso(kickoff),
                "fixture_status": str(status.get("short") or ""),
                "home_provider_team_id": home_provider_team_id,
                "away_provider_team_id": away_provider_team_id,
                "home_w2_team_id": home_w2_team_id,
                "away_w2_team_id": away_w2_team_id,
                "team_identity_status": (
                    "PROVIDER_PRIMARY_READY"
                    if home_w2_team_id and away_w2_team_id
                    else "REVIEW_REQUIRED"
                ),
                "raw_payload_sha256": raw_sha,
                "endpoint_capture_id": str(capture["capture_id"]) if capture else None,
                "captured_at": iso(fixtures_response.captured_at),
                "payload": item,
                "schema_version": "MatchdayFixtureIdentityV1",
            }
            rows.append(
                {
                    **identity_body,
                    "identity_hash": sha256_payload(
                        identity_body, domain=HashDomain.FUTURE_REFRESH_FIXTURE_IDENTITY
                    ),
                }
            )
        return rows

    def _seed_provider_primary_identities(
        self,
        *,
        fixture_identities: list[dict[str, Any]],
        captured_at: datetime,
    ) -> None:
        unresolved_scopes = {
            (
                str(item["competition_id"]),
                str(item["provider_league_id"]),
                str(item["season"]),
            )
            for item in fixture_identities
            if item.get("team_identity_status") != "PROVIDER_PRIMARY_READY"
        }
        if not unresolved_scopes:
            return
        repository = self._db_repository()

        for competition_id, provider_league_id, season in sorted(unresolved_scopes):
            result = repository.seed_provider_primary_identity(
                competition_id=competition_id,
                season=season,
                now=captured_at,
            )
            event = {
                "event": "TEAM_IDENTITY_POOL_EXPANDED",
                "competition_id": competition_id,
                "provider_league_id": provider_league_id,
                "season": season,
                **result,
            }
            self._identity_pool_expansions.append(event)
            logger.warning("TEAM_IDENTITY_POOL_EXPANDED %s", event)

    def _discovery_fixtures(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        response = payload.get("response")
        if not isinstance(response, list) or any(not isinstance(item, dict) for item in response):
            raise FutureRefreshError("PROVIDER_FIXTURES_SCHEMA_DRIFT")
        from w2.matchday.intake_v2 import (
            REQUIRED_MATCHDAY_COMPETITIONS,
            competition_policies,
            load_matchday_policy,
        )

        allowed = {
            policy.provider_league_id: policy.fixture_status_allowlist
            for competition_id, policy in competition_policies(load_matchday_policy()).items()
            if competition_id in REQUIRED_MATCHDAY_COMPETITIONS and policy.enabled
        }
        rows = [
            item
            for item in response
            if str((item.get("league") or {}).get("id") or "") in allowed
            and str(((item.get("fixture") or {}).get("status") or {}).get("short") or "")
            in allowed[str((item.get("league") or {}).get("id") or "")]
        ]
        rows.sort(key=lambda item: kickoff_from_payload(item) or datetime.max.replace(tzinfo=UTC))
        return rows

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
            "evidence_sha256": sha256_payload(item, domain=HashDomain.FUTURE_REFRESH_EVIDENCE),
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
            "competition_id": (
                "fixture_discovery"
                if self.config.discovery_date is not None
                else self.config.competition_id
            ),
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
            "progress_status": refresh_progress_status(result),
            "error_code": result.error_code,
            "requests": self._audit,
            "identity_pool_expansions": result.identity_pool_expansions,
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
                calls_by_fixture[fixture_id] = calls_by_fixture.get(fixture_id, 0) + 1
        for checkpoint in self.config.refresh_checkpoints:
            fixture_id = str(checkpoint.get("fixture_id") or "")
            name = str(checkpoint.get("checkpoint") or "")
            if not fixture_id or not name:
                continue
            capture_id = None
            capture_ids: list[str] = []
            checkpoint_mode = self._checkpoint_mode()
            if checkpoint_mode == "DIRECT":
                progress_status, capture_id, capture_ids = self._checkpoint_capture_outcome(
                    checkpoint, result
                )
            elif (
                checkpoint_mode == "POSTMATCH"
                and result.request_count == 0
                and any(
                    blocker in result.blockers
                    for blocker in (
                        "DAILY_PROVIDER_HARD_CAP_EXCEEDED",
                        "RESULT_QUOTA_EXHAUSTED",
                    )
                )
            ):
                progress_status = "NOT_ATTEMPTED"
            else:
                progress_status = refresh_progress_status(result)
            if progress_status == "NOT_ATTEMPTED":
                repository.write_checkpoint_audit(
                    fixture_id=fixture_id,
                    checkpoint=name,
                    as_of=result.generated_at_utc,
                    calls_used=0,
                    status="RETRY_PENDING",
                    details={
                        "contract": "w2.checkpoint_refresh.v1",
                        "blockers": result.blockers,
                        "progress_status": "RETRY_PENDING",
                        "result_collection_state": (
                            "RESULT_QUOTA_EXHAUSTED"
                            if "RESULT_QUOTA_EXHAUSTED" in result.blockers
                            else None
                        ),
                        "endpoints": list(checkpoint.get("endpoints") or []),
                        "endpoint_capture_ids": [],
                        "source": checkpoint.get("source"),
                    },
                )
                from w2.matchday.repository import MatchdayRuntimeRepository

                MatchdayRuntimeRepository().release_checkpoint_claim(
                    plan_id=str(checkpoint.get("id") or checkpoint.get("plan_id") or ""),
                    claim_token=str(checkpoint.get("claim_token") or ""),
                    reason=(
                        "RESULT_QUOTA_EXHAUSTED"
                        if "RESULT_QUOTA_EXHAUSTED" in result.blockers
                        else "CHECKPOINT_BATCH_NOT_ATTEMPTED"
                    ),
                    restore_attempt=True,
                )
                continue
            if checkpoint_mode == "DIRECT":
                status = "COMPLETED" if progress_status == "CAPTURED" else progress_status
            else:
                status = "COMPLETED" if progress_status == "DATA_PROGRESS" else progress_status
            repository.write_checkpoint_audit(
                fixture_id=fixture_id,
                checkpoint=name,
                as_of=result.generated_at_utc,
                calls_used=max(
                    calls_by_fixture.get(_api_football_fixture_id(fixture_id), 0),
                    0,
                ),
                status=status,
                details={
                    "contract": "w2.checkpoint_refresh.v1",
                    "request_count": result.request_count,
                    "selected_market_fixture_ids": result.selected_market_fixture_ids,
                    "blockers": result.blockers,
                    "progress_status": progress_status,
                    "endpoints": list(checkpoint.get("endpoints") or []),
                    "endpoint_capture_ids": capture_ids,
                    "source": checkpoint.get("source"),
                },
            )
            self._transition_checkpoint_plan(
                checkpoint,
                result,
                status_override=progress_status if checkpoint_mode == "DIRECT" else None,
                capture_id=capture_id,
            )

    def _checkpoint_capture_outcome(
        self,
        checkpoint: dict[str, Any],
        result: FutureRefreshResult,
    ) -> tuple[str, str | None, list[str]]:
        plan_id = str(checkpoint.get("id") or checkpoint.get("plan_id") or "")
        expected = {str(item) for item in checkpoint.get("endpoints") or []}
        latest: dict[str, dict[str, Any]] = {}
        for capture in self._matchday_capture_by_payload.values():
            endpoint = str(capture.get("endpoint") or "")
            if (
                plan_id not in set(capture.get("checkpoint_plan_ids") or [])
                or endpoint not in expected
            ):
                continue
            current = latest.get(endpoint)
            order = (
                int(capture.get("attempt") or 0),
                str(capture.get("provider_captured_at") or ""),
            )
            if current is None or order >= (
                int(current.get("attempt") or 0),
                str(current.get("provider_captured_at") or ""),
            ):
                latest[endpoint] = capture
        capture_ids = sorted(str(item["capture_id"]) for item in latest.values())
        if plan_id in self._checkpoint_preflight_failures:
            return "FAILED", None, []
        if not latest:
            return (
                ("FAILED", None, [])
                if plan_id in self._checkpoint_attempted_plan_ids
                else ("NOT_ATTEMPTED", None, [])
            )
        if not expected or set(latest) != expected:
            return "FAILED", None, capture_ids
        statuses = {str(item.get("capture_status") or "") for item in latest.values()}
        if "FAILED" in statuses:
            return "FAILED", None, capture_ids
        status = "PROVIDER_EMPTY" if "PROVIDER_EMPTY" in statuses else "CAPTURED"
        return status, capture_ids[0] if len(capture_ids) == 1 else None, capture_ids

    def _transition_checkpoint_plan(
        self,
        checkpoint: dict[str, Any],
        result: FutureRefreshResult,
        *,
        status_override: str | None = None,
        capture_id: str | None = None,
    ) -> None:
        plan_id = str(checkpoint.get("id") or checkpoint.get("plan_id") or "")
        claim_token = str(checkpoint.get("claim_token") or "")
        if not plan_id or not claim_token:
            return
        from w2.matchday.repository import MatchdayRuntimeRepository

        progress_status = refresh_progress_status(result)
        status = status_override or (
            "FAILED"
            if progress_status == "FAILED"
            else "CAPTURED"
            if progress_status == "DATA_PROGRESS"
            else "PROVIDER_EMPTY"
        )
        repository = MatchdayRuntimeRepository()
        repository.transition_checkpoint(
            fixture_id=str(checkpoint.get("fixture_id") or ""),
            competition_id=self.config.competition_id,
            season=self.config.season,
            checkpoint=str(checkpoint.get("checkpoint") or ""),
            policy_version=str(checkpoint.get("policy_version") or "w2.matchday_intake_policy.v2"),
            status=status,
            capture_id=capture_id,
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
    season: str | None = None,
    runtime_root: Path | None = None,
    client: LiveApiFootballPort | None = None,
    now: datetime | None = None,
    persistence: str | None = None,
    checkpoint_fixture_ids: tuple[str, ...] = (),
    refresh_checkpoints: tuple[dict[str, Any], ...] = (),
    materialize_public_artifacts: Callable[[list[ProjectionSourceEvent]], list[str]] | None = None,
    materialize_results: ResultMaterializer | None = None,
    runtime_authorization: GateARuntimeAuthorization | None = None,
    provider_call_reservation: GateARunReservation | None = None,
    discovery_date: str | None = None,
) -> FutureRefreshResult:
    config = config_from_policy(
        competition_id=competition_id,
        runtime_root=runtime_root,
    )
    if season is not None and season != config.season:
        raise FutureRefreshError("GATE_A_POLICY_SEASON_MISMATCH")
    if persistence is not None:
        config = replace(config, persistence=persistence)
    if discovery_date is not None:
        try:
            datetime.fromisoformat(discovery_date)
        except ValueError as exc:
            raise FutureRefreshError("FIXTURE_DISCOVERY_DATE_INVALID") from exc
        config = replace(
            config,
            discovery_date=discovery_date,
            max_fixture_candidates=500,
            max_odds_requests=0,
            feature_enrichment_enabled=False,
            feature_enrichment_request_budget=0,
            request_budget=max(config.request_budget, provider_http_max_attempts()),
        )
    if checkpoint_fixture_ids or refresh_checkpoints:
        endpoint_sets = [set(item.get("endpoints") or []) for item in refresh_checkpoints]
        logical_calls = (
            2
            if endpoint_sets
            and all(
                endpoints == {"status", "fixtures"}
                and str(item.get("checkpoint") or "") == "POSTMATCH_RESULT"
                for item, endpoints in zip(refresh_checkpoints, endpoint_sets, strict=True)
            )
            else len(
                {
                    (str(item.get("fixture_id") or ""), str(endpoint))
                    for item in refresh_checkpoints
                    for endpoint in item.get("endpoints") or []
                }
            )
        )
        result_refresh_fixture_ids = (
            tuple(dict.fromkeys(checkpoint_fixture_ids))
            if any(
                str(item.get("checkpoint") or "") == "POSTMATCH_RESULT"
                for item in refresh_checkpoints
            )
            else ()
        )
        lineups_count = sum(
            1 for item in refresh_checkpoints if "lineups" in set(item.get("endpoints") or [])
        )
        config = replace(
            config,
            checkpoint_fixture_ids=tuple(dict.fromkeys(checkpoint_fixture_ids)),
            refresh_checkpoints=tuple(refresh_checkpoints),
            result_refresh_fixture_ids=result_refresh_fixture_ids,
            max_fixture_candidates=max(len(set(checkpoint_fixture_ids)), 1),
            max_odds_requests=sum(
                1 for item in refresh_checkpoints if "odds" in set(item.get("endpoints") or [])
            ),
            feature_enrichment_enabled=lineups_count > 0,
            feature_enrichment_endpoints=("lineups",),
            feature_enrichment_request_budget=lineups_count,
            request_budget=max(
                config.request_budget,
                logical_calls * provider_http_max_attempts(),
            ),
        )
    service = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=now,
        materialize_public_artifacts=materialize_public_artifacts,
        materialize_results=materialize_results,
        runtime_authorization=runtime_authorization,
        provider_call_reservation=provider_call_reservation,
    )
    return replace(service.run(), requests=list(service._audit))


def run_future_refresh_task(
    *,
    task_id: str,
    key: str,
    owner: str | None = None,
    queued_at: datetime | None = None,
    competition_id: str = "world_cup_2026",
    season: str | None = None,
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
    materialize_public_artifacts: Callable[[list[ProjectionSourceEvent]], list[str]] | None = None,
    materialize_results: ResultMaterializer | None = None,
    runtime_authorization: GateARuntimeAuthorization | None = None,
    provider_call_reservation: GateARunReservation | None = None,
    discovery_date: str | None = None,
) -> RefreshTaskAudit:
    execution_started_at = utc_now()
    evaluation_time = now or execution_started_at
    owner_marker = owner or str(uuid4())
    root = runtime_root or FutureRefreshConfig().runtime_root
    resolved_persistence = (
        persistence or os.environ.get("W2_FUTURE_REFRESH_PERSISTENCE", "db")
    ).lower()
    resolved_settings = settings or get_settings()
    lock: RefreshSingletonLock | None = None
    if resolved_persistence == "db":
        if runtime_authorization is not None:
            if (
                provider_call_reservation is None
                or provider_call_reservation.task_key != key
                or provider_call_reservation.authorization_id
                != runtime_authorization.authorization_id
            ):
                raise FutureRefreshError("GATE_A_TASK_KEY_DB_FENCE_REQUIRED")
            lock_acquired = True
        else:
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
                lock_acquired = lock.acquire(now=evaluation_time)
            elif client is not None:
                # Offline/fake-provider C9 has no live-capable client construction path.
                lock_acquired = True
            else:
                raise FutureRefreshError("DB_TASK_KEY_FENCE_UNAVAILABLE")
    else:
        lock = RefreshSingletonLock(
            key=key,
            owner=owner_marker,
            ttl_seconds=900,
            settings=resolved_settings,
            runtime_root=root,
            redis_client=redis_client,
        )
        lock_acquired = lock.acquire(now=evaluation_time)
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
            queued_at=iso(queued_at or evaluation_time),
            started_at=iso(execution_started_at),
            finished_at=iso(utc_now()),
            status="ALREADY_RUNNING",
            result={
                "candidate": False,
                "formal_recommendation": False,
                **{k: v for k, v in interval_metadata.items() if v is not None},
            },
            gate_a_authorization_id=(
                runtime_authorization.authorization_id
                if runtime_authorization is not None
                else None
            ),
            gate_a_lease_epoch=(
                getattr(provider_call_reservation, "lease_epoch", None)
                if provider_call_reservation is not None
                else None
            ),
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
            season=season,
            runtime_root=root,
            client=client,
            now=evaluation_time,
            persistence=resolved_persistence,
            checkpoint_fixture_ids=checkpoint_fixture_ids,
            refresh_checkpoints=refresh_checkpoints,
            materialize_public_artifacts=materialize_public_artifacts,
            materialize_results=materialize_results,
            runtime_authorization=runtime_authorization,
            provider_call_reservation=provider_call_reservation,
            discovery_date=discovery_date,
        )
        progress_status = refresh_progress_status(result)
        status = (
            "COMPLETED"
            if progress_status == "DATA_PROGRESS"
            else "BLOCKED"
            if progress_status == "FAILED"
            else progress_status
        )
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
            "identity_pool_expansions": result.identity_pool_expansions,
            "requests": result.requests,
            "progress_status": progress_status,
            "discovery_date": discovery_date,
        }
    except Exception as exc:
        summary = {
            "blockers": [str(exc) or exc.__class__.__name__],
            "candidate": False,
            "formal_recommendation": False,
        }
    finally:
        released = True if lock is None else lock.release()
    audit = RefreshTaskAudit(
        task_id=task_id,
        key=key,
        owner=owner_marker,
        queued_at=iso(queued_at or evaluation_time),
        started_at=iso(execution_started_at),
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
        gate_a_authorization_id=(
            runtime_authorization.authorization_id if runtime_authorization is not None else None
        ),
        gate_a_lease_epoch=(
            getattr(provider_call_reservation, "lease_epoch", None)
            if provider_call_reservation is not None
            else None
        ),
    )
    write_task_audit(root, audit, persistence=persistence)
    if provider_call_reservation is not None:
        provider_call_reservation.finalize(status)
    return audit


def run_staged_gate_a_canary_task(
    *,
    task_id: str,
    key: str,
    queued_at: datetime,
    competition_id: str,
    season: str,
    fixture_id: str | None,
    runtime_authorization: GateARuntimeAuthorization,
    provider_call_reservation: GateARunReservation,
    now: datetime | None = None,
    client: LiveApiFootballPort | None = None,
) -> RefreshTaskAudit:
    """Execute only the signed five-call staged canary and bind its DB audit."""
    started_at = utc_now()
    evaluation_time = now or started_at
    if (
        key != runtime_authorization.task_key
        or (
            runtime_authorization.fixture_scope_mode == GATE_A_EXACT_FIXTURE_SCOPE
            and fixture_id != runtime_authorization.fixture_id
        )
        or (
            runtime_authorization.fixture_scope_mode == GATE_A_WINDOW_FIXTURE_SCOPE
            and fixture_id is not None
        )
        or provider_call_reservation.task_key != key
        or provider_call_reservation.authorization_id != runtime_authorization.authorization_id
    ):
        raise FutureRefreshError("GATE_A_TASK_KEY_DB_FENCE_REQUIRED")
    try:
        config = config_from_policy(competition_id=competition_id)
        if season != config.season:
            raise FutureRefreshError("GATE_A_POLICY_SEASON_MISMATCH")
        if runtime_authorization.provider_league_id != config.league_id:
            raise FutureRefreshError("GATE_A_POLICY_PROVIDER_LEAGUE_MISMATCH")
        if runtime_authorization.competition_policy_config_hash != config.policy_config_hash:
            raise FutureRefreshError("GATE_A_POLICY_CONFIG_HASH_MISMATCH")
    except FutureRefreshError:
        provider_call_reservation.finalize("BLOCKED")
        raise
    config = replace(
        config,
        persistence="db",
        request_budget=GATE_A_CANARY_PROVIDER_CALL_CAP,
        max_fixture_candidates=1,
        max_odds_requests=2,
        checkpoint_fixture_ids=((fixture_id,) if fixture_id is not None else ()),
        feature_enrichment_enabled=True,
        feature_enrichment_endpoints=("lineups",),
        feature_enrichment_request_budget=1,
    )
    status = "BLOCKED"
    summary: dict[str, Any]
    service = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=evaluation_time,
        runtime_authorization=runtime_authorization,
        provider_call_reservation=provider_call_reservation,
    )
    try:
        result = service.run_staged_gate_a_canary(fixture_id)
        status = "COMPLETED"
        summary = {
            "fixture_count": result.fixture_count,
            "request_count": result.request_count,
            "raw_payload_written_count": result.raw_payload_written_count,
            "selected_market_fixture_ids": result.selected_market_fixture_ids,
            "materialized_fixture_ids": result.materialized_fixture_ids,
            "exact_pair_count": result.exact_pair_count,
            "blockers": [],
            "candidate": False,
            "formal_recommendation": False,
        }
    except Exception as exc:
        summary = {
            "request_count": service._attempt_count,
            "blockers": [str(exc) or exc.__class__.__name__],
            "candidate": False,
            "formal_recommendation": False,
        }
    audit = RefreshTaskAudit(
        task_id=task_id,
        key=key,
        owner=provider_call_reservation.owner,
        queued_at=iso(queued_at),
        started_at=iso(started_at),
        finished_at=iso(utc_now()),
        status=status,
        result=summary,
        gate_a_authorization_id=runtime_authorization.authorization_id,
        gate_a_lease_epoch=provider_call_reservation.lease_epoch,
    )
    write_task_audit(config.runtime_root, audit, persistence="db")
    provider_call_reservation.finalize(status)
    return audit


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
