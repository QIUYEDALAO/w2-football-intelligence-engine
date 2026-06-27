from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

API_FOOTBALL_ENDPOINTS = (
    "fixtures",
    "teams",
    "standings",
    "odds",
    "lineups",
    "injuries",
    "squads",
    "fixture_detail",
    "results",
    "events",
    "statistics",
    "leagues",
    "h2h",
)


@dataclass(frozen=True, kw_only=True)
class ProviderRequest:
    endpoint: str
    params: dict[str, str]
    live: bool = False


@dataclass(frozen=True, kw_only=True)
class ProviderResponse:
    provider: str
    endpoint: str
    payload: dict[str, Any]
    captured_at: datetime


class ProviderClientPort(Protocol):
    provider: str

    def fetch(self, request: ProviderRequest) -> ProviderResponse:
        pass


class OddsProviderPort(Protocol):
    provider: str

    def fetch_odds(self, request: ProviderRequest) -> ProviderResponse:
        pass


class SecondaryOddsProviderPort(OddsProviderPort, Protocol):
    status: str
    capabilities: dict[str, bool]
