from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from w2.ingestion.ports import API_FOOTBALL_ENDPOINTS, ProviderRequest, ProviderResponse


class LiveNetworkDisabledError(RuntimeError):
    pass


@dataclass(frozen=True)
class ApiFootballClient:
    api_key_env_name: str = "W2_API_FOOTBALL_API_KEY"
    allow_live: bool = False
    provider: str = "api_football"

    def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if request.endpoint not in API_FOOTBALL_ENDPOINTS:
            raise ValueError(f"unsupported API-Football endpoint: {request.endpoint}")
        if not request.live or not self.allow_live:
            raise LiveNetworkDisabledError(
                "network is disabled unless --live is explicitly approved"
            )
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
