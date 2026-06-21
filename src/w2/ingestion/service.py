from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from w2.domain.entities import (
    DataProvenance,
    FeatureSnapshot,
    OddsObservation,
    ProviderEntityMapping,
)
from w2.domain.enums import DataLayer
from w2.ingestion.freshness import FreshnessAlert, FreshnessEvaluator
from w2.ingestion.raw_store import RawPayloadStore, StoredPayload
from w2.normalization.api_football import ApiFootballNormalizer


@dataclass(frozen=True)
class IngestionReplayResult:
    raw: StoredPayload
    provider_mappings: list[ProviderEntityMapping]
    odds_observations: list[OddsObservation]
    feature_snapshots: list[FeatureSnapshot]
    provenance: list[DataProvenance]
    freshness_alerts: list[FreshnessAlert]
    gate2_status: str = "PROVISIONAL"


@dataclass
class IngestionService:
    raw_store: RawPayloadStore = field(default_factory=RawPayloadStore)
    normalizer: ApiFootballNormalizer = field(default_factory=ApiFootballNormalizer)
    freshness_evaluator: FreshnessEvaluator = field(
        default_factory=lambda: FreshnessEvaluator(threshold_seconds=3600)
    )
    _odds_keys: set[tuple[str, str, str, str, str | None, datetime, datetime]] = field(
        default_factory=set
    )

    def replay_api_football_payload(
        self,
        *,
        endpoint: str,
        payload: dict[str, Any],
        captured_at: datetime,
        now: datetime,
    ) -> IngestionReplayResult:
        raw = self.raw_store.save(
            provider=self.normalizer.provider,
            endpoint=endpoint,
            payload=payload,
            captured_at=captured_at,
        )
        normalized = (
            self.normalizer.normalize_odds_payload(payload, captured_at=captured_at)
            if endpoint == "odds"
            else self.normalizer.normalize_fixture_payload(payload)
        )
        deduped_odds: list[OddsObservation] = []
        for item in normalized.odds_observations:
            key = (
                str(item.fixture_id),
                str(item.bookmaker_id),
                item.market.value,
                item.canonical_selection,
                str(item.line) if item.line is not None else None,
                item.provider_updated_at,
                item.captured_at,
            )
            if key in self._odds_keys:
                continue
            self._odds_keys.add(key)
            deduped_odds.append(item)
        provenance = [
            DataProvenance(
                entity_type="raw_payload",
                entity_id=raw.reference.id,
                layer=DataLayer.RAW,
                source_ref_id=raw.reference.id,
                event_time=raw.reference.captured_at,
                provider_updated_at=None,
                ingested_at=raw.reference.captured_at,
            )
        ]
        for feature in normalized.feature_snapshots:
            provenance.append(
                DataProvenance(
                    entity_type="feature_snapshot",
                    entity_id=feature.id,
                    layer=DataLayer.FEATURE,
                    source_ref_id=raw.reference.id,
                    event_time=feature.as_of_time,
                    provider_updated_at=None,
                    ingested_at=captured_at,
                    as_of_time=feature.as_of_time,
                )
            )
        alerts = [
            alert
            for alert in (
                self.freshness_evaluator.evaluate(
                    entity_type="raw_payload",
                    entity_id=str(raw.reference.id),
                    observed_at=raw.reference.captured_at,
                    now=now,
                ),
            )
            if alert is not None
        ]
        return IngestionReplayResult(
            raw=raw,
            provider_mappings=normalized.provider_mappings,
            odds_observations=deduped_odds,
            feature_snapshots=normalized.feature_snapshots,
            provenance=provenance,
            freshness_alerts=alerts,
        )
