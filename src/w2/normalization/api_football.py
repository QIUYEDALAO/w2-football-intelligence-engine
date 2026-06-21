from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from w2.domain.entities import FeatureSnapshot, OddsObservation, ProviderEntityMapping
from w2.domain.enums import MarketType
from w2.domain.time import require_utc


def stable_uuid(*parts: object) -> UUID:
    return uuid5(NAMESPACE_URL, ":".join(str(part) for part in parts))


def parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return require_utc(datetime.fromisoformat(normalized), "provider datetime")


def normalize_market(raw_market: str) -> MarketType:
    key = raw_market.strip().upper().replace(" ", "_").replace("-", "_").replace("/", "_")
    aliases = {
        "MATCH_WINNER": MarketType.ONE_X_TWO,
        "1X2": MarketType.ONE_X_TWO,
        "ASIAN_HANDICAP": MarketType.ASIAN_HANDICAP,
        "GOALS_OVER_UNDER": MarketType.TOTALS,
        "TOTALS": MarketType.TOTALS,
        "BOTH_TEAMS_SCORE": MarketType.BTTS,
        "BTTS": MarketType.BTTS,
    }
    try:
        return aliases[key]
    except KeyError as exc:
        raise ValueError(f"unsupported market label {raw_market}") from exc


@dataclass(frozen=True)
class NormalizedReplay:
    provider_mappings: list[ProviderEntityMapping]
    odds_observations: list[OddsObservation]
    feature_snapshots: list[FeatureSnapshot]


class ApiFootballNormalizer:
    provider = "api_football"

    def normalize_fixture_payload(self, payload: dict[str, Any]) -> NormalizedReplay:
        mappings: list[ProviderEntityMapping] = []
        odds: list[OddsObservation] = []
        features: list[FeatureSnapshot] = []
        for fixture in payload.get("response", []):
            fixture_id = stable_uuid(self.provider, "fixture", fixture["fixture"]["id"])
            kickoff_at = parse_datetime(fixture["fixture"]["date"])
            mappings.append(
                ProviderEntityMapping(
                    entity_type="fixture",
                    entity_id=fixture_id,
                    provider=self.provider,
                    external_id=str(fixture["fixture"]["id"]),
                    source="offline fixture",
                    confidence=Decimal("1.0"),
                    valid_from=kickoff_at,
                )
            )
            features.append(
                FeatureSnapshot(
                    fixture_id=fixture_id,
                    as_of_time=kickoff_at,
                    features={"offline_fixture_seen": Decimal("1")},
                )
            )
        return NormalizedReplay(mappings, odds, features)

    def normalize_odds_payload(
        self,
        payload: dict[str, Any],
        *,
        captured_at: datetime,
        pre_match_only: bool = True,
    ) -> NormalizedReplay:
        mappings: list[ProviderEntityMapping] = []
        odds: list[OddsObservation] = []
        features: list[FeatureSnapshot] = []
        captured_utc = require_utc(captured_at, "captured_at")
        for item in payload.get("response", []):
            fixture = item["fixture"]
            kickoff_at = parse_datetime(fixture["date"])
            if pre_match_only and captured_utc > kickoff_at:
                raise ValueError("pre-match odds cannot be written after kickoff")
            fixture_id = stable_uuid(self.provider, "fixture", fixture["id"])
            mappings.append(
                ProviderEntityMapping(
                    entity_type="fixture",
                    entity_id=fixture_id,
                    provider=self.provider,
                    external_id=str(fixture["id"]),
                    source="offline odds",
                    confidence=Decimal("1.0"),
                    valid_from=kickoff_at,
                )
            )
            for bookmaker in item.get("bookmakers", []):
                bookmaker_id = stable_uuid(self.provider, "bookmaker", bookmaker["id"])
                mappings.append(
                    ProviderEntityMapping(
                        entity_type="bookmaker",
                        entity_id=bookmaker_id,
                        provider=self.provider,
                        external_id=str(bookmaker["id"]),
                        source="offline odds",
                        confidence=Decimal("1.0"),
                        valid_from=captured_utc,
                    )
                )
                for bet in bookmaker.get("bets", []):
                    market = normalize_market(bet["name"])
                    for value in bet.get("values", []):
                        line = value.get("line")
                        odds.append(
                            OddsObservation(
                                fixture_id=fixture_id,
                                bookmaker_id=bookmaker_id,
                                market=market,
                                selection=value["value"],
                                line=Decimal(str(line)) if line is not None else None,
                                decimal_odds=Decimal(str(value["odd"])),
                                suspended=bool(value.get("suspended", False)),
                                live=bool(item.get("live", False)),
                                stale=bool(item.get("stale", False)),
                                provider_updated_at=parse_datetime(item["update"]),
                                captured_at=captured_utc,
                                raw_label=f"{bet['name']}:{value['value']}",
                                settlement_rule=str(value.get("settlement_rule", bet["name"])),
                            )
                        )
        return NormalizedReplay(mappings, odds, features)
