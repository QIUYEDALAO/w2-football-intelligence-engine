from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from w2.ingestion.ports import API_FOOTBALL_ENDPOINTS, ProviderRequest, ProviderResponse
from w2.operations.observability import default_metric_registry
from w2.providers.control import (
    PROVIDER_CALLS_DISABLED,
    ProviderCallsDisabledError,
    provider_calls_disabled,
    provider_endpoint_allowlist,
)
from w2.providers.ledger import ProviderRequestLedger, provider_request_ledger_from_env


class LiveNetworkDisabledError(RuntimeError):
    pass


API_FOOTBALL_HTTP_PATHS = {
    "events": "fixtures/events",
    "h2h": "fixtures/headtohead",
    "lineups": "fixtures/lineups",
    "statistics": "fixtures/statistics",
}


@dataclass(frozen=True, kw_only=True)
class LiveApiFootballResponse:
    endpoint: str
    params: dict[str, str]
    status_code: int
    elapsed_ms: int
    payload: dict[str, Any]
    headers: dict[str, str]
    captured_at: datetime
    requested_at: datetime | None = None


@dataclass(frozen=True)
class ApiFootballClient:
    api_key_env_name: str = "W2_API_FOOTBALL_API_KEY"
    allow_live: bool = False
    allowed_live_endpoints: frozenset[str] | None = None
    provider: str = "api_football"
    base_url: str = "https://v3.football.api-sports.io"
    auth_header_name: str = "x-apisports-key"
    request_ledger: ProviderRequestLedger | None = None

    def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if request.endpoint not in API_FOOTBALL_ENDPOINTS:
            raise ValueError(f"unsupported API-Football endpoint: {request.endpoint}")
        if not request.live or not self.allow_live:
            raise LiveNetworkDisabledError(
                "network is disabled unless --live is explicitly approved"
            )
        self._require_endpoint_allowed(request.endpoint)
        raise LiveNetworkDisabledError("live API-Football execution is blocked in Stage 4A")

    def parse_fixture(self, endpoint: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if endpoint not in API_FOOTBALL_ENDPOINTS:
            raise ValueError(f"unsupported API-Football endpoint: {endpoint}")
        response = payload.get("response")
        if not isinstance(response, list):
            raise ValueError("API-Football fixture payload must contain response list")
        return response

    def offline_response(self, endpoint: str, payload: dict[str, Any]) -> ProviderResponse:
        return ProviderResponse(
            provider=self.provider,
            endpoint=endpoint,
            payload=payload,
            captured_at=datetime.now(UTC),
        )

    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        if endpoint not in (*API_FOOTBALL_ENDPOINTS, "status"):
            raise ValueError(f"unsupported API-Football endpoint: {endpoint}")
        if not self.allow_live:
            raise LiveNetworkDisabledError(
                "network is disabled unless --live is explicitly approved"
            )
        if provider_calls_disabled():
            raise ProviderCallsDisabledError(PROVIDER_CALLS_DISABLED)
        self._require_endpoint_allowed(endpoint)
        api_key = os.environ.get(self.api_key_env_name)
        if not api_key:
            raise LiveNetworkDisabledError("provider credential is not visible to the process")
        query = urllib.parse.urlencode(params)
        suffix = f"?{query}" if query else ""
        path = API_FOOTBALL_HTTP_PATHS.get(endpoint, endpoint)
        request = urllib.request.Request(  # noqa: S310
            f"{self.base_url}/{path}{suffix}",
            headers={self.auth_header_name: api_key},
        )
        started = time.monotonic()
        requested_at = datetime.now(UTC)
        registry = default_metric_registry()
        registry.inc(
            "w2_provider_requests_total",
            labels={"endpoint": endpoint, "provider": self.provider},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
                raw = response.read()
                status_code = response.status
                headers = self._sanitize_headers(response.headers)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status_code = exc.code
            headers = self._sanitize_headers(exc.headers)
        except (OSError, TimeoutError, urllib.error.URLError):
            elapsed_ms = int((time.monotonic() - started) * 1000)
            registry.observe(
                "w2_provider_latency_ms",
                elapsed_ms,
                labels={"endpoint": endpoint, "provider": self.provider},
            )
            registry.inc(
                "w2_provider_failures_total",
                labels={"endpoint": endpoint, "provider": self.provider},
            )
            raise
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            registry.inc(
                "w2_provider_failures_total",
                labels={"endpoint": endpoint, "provider": self.provider},
            )
            raise
        elapsed_ms = int((time.monotonic() - started) * 1000)
        registry.observe(
            "w2_provider_latency_ms",
            elapsed_ms,
            labels={"endpoint": endpoint, "provider": self.provider},
        )
        if status_code >= 400:
            registry.inc(
                "w2_provider_failures_total",
                labels={"endpoint": endpoint, "provider": self.provider},
            )
        completed_at = datetime.now(UTC)
        ledger = self.request_ledger or provider_request_ledger_from_env()
        if ledger is not None:
            ledger.record_request(
                provider=self.provider,
                endpoint=endpoint,
                params=params,
                live=True,
                status_code=status_code,
                requested_at=requested_at,
                completed_at=completed_at,
                headers=headers,
                payload=payload,
                error=None if status_code < 400 else f"PROVIDER_HTTP_{status_code}",
            )
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=status_code,
            elapsed_ms=elapsed_ms,
            payload=payload,
            headers=headers,
            captured_at=completed_at,
            requested_at=requested_at,
        )

    def fixtures_by_team(
        self,
        *,
        team_id: str,
        season: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> LiveApiFootballResponse:
        params = {"team": team_id, "season": season}
        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to
        return self.request_live("fixtures", params)

    def h2h(
        self,
        *,
        team_a_id: str,
        team_b_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> LiveApiFootballResponse:
        params = {"h2h": f"{team_a_id}-{team_b_id}"}
        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to
        return self.request_live("h2h", params)

    def _sanitize_headers(self, headers: Any) -> dict[str, str]:
        blocked = {
            "authorization",
            self.auth_header_name.lower(),
            "x-rapidapi-key",
            "set-cookie",
            "cookie",
        }
        return {
            str(key): str(value)
            for key, value in dict(headers).items()
            if str(key).lower() not in blocked
        }

    def _require_endpoint_allowed(self, endpoint: str) -> None:
        env_allowlist = provider_endpoint_allowlist()
        if endpoint not in env_allowlist:
            raise LiveNetworkDisabledError(f"live endpoint not approved: {endpoint}")
        if self.allowed_live_endpoints is not None and endpoint not in self.allowed_live_endpoints:
            raise LiveNetworkDisabledError(f"live endpoint not approved: {endpoint}")


@dataclass(frozen=True)
class UndecidedSecondaryOddsProvider:
    provider: str = "secondary_odds_provider"
    status: str = "UNDECIDED"
    capabilities: dict[str, bool] | None = None

    def fetch_odds(self, request: ProviderRequest) -> ProviderResponse:
        raise LiveNetworkDisabledError("secondary odds provider is undecided and not callable")

    def capability_table(self) -> dict[str, bool]:
        return self.capabilities or {
            "pre_match_odds": False,
            "live_odds": False,
            "bookmaker_depth_known": False,
            "historical_snapshots": False,
            "commercial_terms_reviewed": False,
        }
