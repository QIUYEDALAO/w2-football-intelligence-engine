from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from w2.domain.time import require_utc


class MigrationDecision(StrEnum):
    READY_FOR_TRANSFORM = "READY_FOR_TRANSFORM"
    AUDIT_ONLY = "AUDIT_ONLY"
    QUARANTINE = "QUARANTINE"
    REJECT = "REJECT"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


DATA_DOMAINS = [
    "competition_season_fixture",
    "team_player_provider_mapping",
    "raw_odds_payload",
    "bookmaker_odds_snapshots",
    "match_cards",
    "lineups_injuries",
    "weather_venue",
    "results",
    "forward_ledger",
    "w1_model_outputs",
    "w1_ai_scout_outputs",
    "recommendation_audit_records",
]


DOMAIN_TARGETS = {
    "competition_season_fixture": "NORMALIZED:Competition/Season/Fixture",
    "team_player_provider_mapping": "NORMALIZED:Team/Player/ProviderEntityMapping",
    "raw_odds_payload": "RAW:RawPayloadReference",
    "bookmaker_odds_snapshots": "NORMALIZED:OddsObservation",
    "match_cards": "QUARANTINE:Manual schema review",
    "lineups_injuries": "NORMALIZED:Lineup/Injury",
    "weather_venue": "NORMALIZED:WeatherObservation/Venue",
    "results": "NORMALIZED:Result",
    "forward_ledger": "AUDIT:Forward ledger evidence",
    "w1_model_outputs": "AUDIT:Model output evidence",
    "w1_ai_scout_outputs": "AUDIT:AI/SCOUT evidence",
    "recommendation_audit_records": "AUDIT:Recommendation audit evidence",
}


DOMAIN_DEFAULT_DECISIONS = {
    "raw_odds_payload": MigrationDecision.READY_FOR_TRANSFORM,
    "bookmaker_odds_snapshots": MigrationDecision.READY_FOR_TRANSFORM,
    "competition_season_fixture": MigrationDecision.MANUAL_REVIEW_REQUIRED,
    "team_player_provider_mapping": MigrationDecision.MANUAL_REVIEW_REQUIRED,
    "results": MigrationDecision.MANUAL_REVIEW_REQUIRED,
    "lineups_injuries": MigrationDecision.MANUAL_REVIEW_REQUIRED,
    "weather_venue": MigrationDecision.MANUAL_REVIEW_REQUIRED,
    "forward_ledger": MigrationDecision.AUDIT_ONLY,
    "w1_model_outputs": MigrationDecision.AUDIT_ONLY,
    "w1_ai_scout_outputs": MigrationDecision.AUDIT_ONLY,
    "recommendation_audit_records": MigrationDecision.AUDIT_ONLY,
    "match_cards": MigrationDecision.QUARANTINE,
}


DOMAIN_RELATIVE_PATHS = {
    "competition_season_fixture": "data/processed/international/w1_international_dataset.csv",
    "team_player_provider_mapping": "data/processed/international/w1_international_dataset.csv",
    "raw_odds_payload": "data/odds_snapshots/raw",
    "bookmaker_odds_snapshots": "data/local_odds/world_cup_odds_historical.csv",
    "match_cards": "reports/match_previews/W1_GROUP_STAGE_ROUND1_REAL_FIXTURE_CARDS.md",
    "lineups_injuries": "data/processed/international/w1_international_dataset.csv",
    "weather_venue": "data/processed/international/w1_international_dataset.csv",
    "results": "data/results/world_cup_2026_results.json",
    "forward_ledger": "reports/W1_FORWARD_LEDGER_PROSPECTIVE_RUN_V1_RESULT.md",
    "w1_model_outputs": "reports/w1_backtest_1x2_only_baseline_v1.json",
    "w1_ai_scout_outputs": "reports/W1_SCOUT_MVP_RESULT.md",
    "recommendation_audit_records": "reports/w1_recommendation_accuracy_audit.json",
}


@dataclass(frozen=True, kw_only=True)
class MigrationSourceAsset:
    domain: str
    source_system: str
    original_path: str
    original_schema_version: str
    source_sha256: str
    source_head: str
    provenance_quality: str
    target_w2_entity_layer: str
    transform_version: str
    migration_eligibility: MigrationDecision
    validation_status: str
    record_count: int


@dataclass(frozen=True, kw_only=True)
class TransformContract:
    domain: str
    source_fields: tuple[str, ...]
    target_fields: tuple[str, ...]
    id_mapping: str
    utc_time_conversion: str
    decimal_probability_conversion: str
    null_missing_policy: str
    deduplication_key: str
    provenance: str
    validation_rules: tuple[str, ...]
    rollback_metadata: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class DryRunDomainResult:
    domain: str
    accepted: int
    rejected: int
    quarantined: int
    source_sha256: str
    deterministic_hash: str
    temporary_load: str
    validation_status: str


def sha256_file(path: Path) -> str:
    if path.is_dir():
        digest = hashlib.sha256()
        for child in sorted(item for item in path.rglob("*") if item.is_file()):
            digest.update(child.relative_to(path).as_posix().encode())
            digest.update(sha256_file(child).encode())
        return digest.hexdigest()
    if not path.exists():
        return "MISSING"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_uuid(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"w1-to-w2:{value}"))


def parse_utc(value: str, field_name: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return require_utc(parsed.astimezone(UTC), field_name)


def parse_decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal value for dry-run: {value}") from exc


def count_records(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_dir():
        return sum(1 for item in path.rglob("*") if item.is_file())
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8", errors="ignore") as handle:
            return max(sum(1 for _ in csv.DictReader(handle)), 0)
    if path.suffix.lower() in {".json", ".jsonl"}:
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            return 0
        if path.suffix.lower() == ".jsonl":
            return len(text.splitlines())
        payload = json.loads(text)
        if isinstance(payload, list):
            return len(payload)
        if isinstance(payload, dict):
            for value in payload.values():
                if isinstance(value, list):
                    return len(value)
        return 1
    return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())


def build_source_inventory(w1_root: Path, source_head: str) -> list[MigrationSourceAsset]:
    inventory: list[MigrationSourceAsset] = []
    for domain in DATA_DOMAINS:
        source_path = w1_root / DOMAIN_RELATIVE_PATHS[domain]
        source_hash = sha256_file(source_path)
        decision = DOMAIN_DEFAULT_DECISIONS[domain]
        if source_hash == "MISSING":
            decision = MigrationDecision.QUARANTINE
        inventory.append(
            MigrationSourceAsset(
                domain=domain,
                source_system="W1",
                original_path=DOMAIN_RELATIVE_PATHS[domain],
                original_schema_version="W1_FROZEN_OR_LEGACY_UNKNOWN",
                source_sha256=source_hash,
                source_head=source_head,
                provenance_quality="FROZEN_AUDIT" if source_hash != "MISSING" else "MISSING",
                target_w2_entity_layer=DOMAIN_TARGETS[domain],
                transform_version="w2-stage12a-dry-run-v1",
                migration_eligibility=decision,
                validation_status="DRY_RUN_ONLY",
                record_count=count_records(source_path),
            )
        )
    return inventory


def build_default_contracts() -> list[TransformContract]:
    contracts: list[TransformContract] = []
    for domain in DATA_DOMAINS:
        contracts.append(
            TransformContract(
                domain=domain,
                source_fields=("domain_sample", "source_row_hash", "source_event_time"),
                target_fields=("w2_internal_id", "source_ref", "provenance", "payload_summary"),
                id_mapping="provider IDs and aliases revalidated before persistent load",
                utc_time_conversion="timezone-aware source time normalized to UTC",
                decimal_probability_conversion="odds and probabilities converted with Decimal",
                null_missing_policy="missing critical identity enters quarantine",
                deduplication_key=f"{domain}:source_sha256:source_row_hash",
                provenance="source_system/source_head/source_sha256/transform_version required",
                validation_rules=(
                    "no same-fixture result fields in pre-match feature payload",
                    "unknown schema rejected or quarantined",
                    "AI and model output remains audit-only",
                ),
                rollback_metadata=(
                    "batch_id",
                    "source_sha256",
                    "transform_version",
                    "target_row_ids",
                    "verification_result",
                    "rollback_eligibility",
                ),
            )
        )
    return contracts


def _domain_counts(asset: MigrationSourceAsset) -> tuple[int, int, int]:
    sample_count = min(asset.record_count, 3)
    if asset.migration_eligibility == MigrationDecision.READY_FOR_TRANSFORM:
        return sample_count, 0, 0
    if asset.migration_eligibility in {
        MigrationDecision.AUDIT_ONLY,
        MigrationDecision.MANUAL_REVIEW_REQUIRED,
    }:
        return 0, 0, sample_count
    rejected = sample_count if asset.migration_eligibility == MigrationDecision.REJECT else 0
    return 0, rejected, sample_count


class MigrationDryRunEngine:
    def __init__(self, inventory: list[MigrationSourceAsset], contracts: list[TransformContract]):
        self.inventory = sorted(inventory, key=lambda item: item.domain)
        self.contracts = {contract.domain: contract for contract in contracts}

    def run(self, *, run_id: str) -> dict[str, Any]:
        started_at = datetime(2026, 6, 22, tzinfo=UTC)
        results: list[DryRunDomainResult] = []
        with TemporaryDirectory(prefix="w2-stage12a-dry-run-") as tmp:
            tmp_path = Path(tmp)
            for asset in self.inventory:
                contract = self.contracts[asset.domain]
                accepted, rejected, quarantined = _domain_counts(asset)
                payload = {
                    "domain": asset.domain,
                    "run_id": run_id,
                    "contract": contract.deduplication_key,
                    "source_sha256": asset.source_sha256,
                    "accepted": accepted,
                    "rejected": rejected,
                    "quarantined": quarantined,
                    "stable_id": stable_uuid(f"{run_id}:{asset.domain}:{asset.source_sha256}"),
                }
                deterministic_hash = hashlib.sha256(
                    json.dumps(payload, sort_keys=True).encode()
                ).hexdigest()
                (tmp_path / f"{asset.domain}.json").write_text(
                    json.dumps(payload, sort_keys=True),
                    encoding="utf-8",
                )
                results.append(
                    DryRunDomainResult(
                        domain=asset.domain,
                        accepted=accepted,
                        rejected=rejected,
                        quarantined=quarantined,
                        source_sha256=asset.source_sha256,
                        deterministic_hash=deterministic_hash,
                        temporary_load="TEMPORARY_DIRECTORY_ONLY",
                        validation_status="VERIFIED_DETERMINISTIC",
                    )
                )
        manifest_payload = {
            "run_id": run_id,
            "started_at": started_at.isoformat(),
            "results": [item.__dict__ for item in results],
            "temporary_load_touched_w2_database": False,
            "w1_writes": False,
            "business_data_copy_retained": False,
        }
        manifest_payload["manifest_sha256"] = hashlib.sha256(
            json.dumps(manifest_payload, sort_keys=True).encode()
        ).hexdigest()
        return manifest_payload


def quarantine_registry(inventory: list[MigrationSourceAsset]) -> dict[str, Any]:
    records = [
        {
            "domain": item.domain,
            "reason": "missing, audit-only, manual-review, or schema-risk source",
            "decision": item.migration_eligibility.value,
            "source_sha256": item.source_sha256,
        }
        for item in inventory
        if item.migration_eligibility != MigrationDecision.READY_FOR_TRANSFORM
    ]
    return {
        "registry_version": "w2-stage12a-quarantine-v1",
        "records": records,
        "silent_drop_allowed": False,
    }
