#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "src/w2/domain/entities.py",
    "src/w2/domain/enums.py",
    "src/w2/domain/odds.py",
    "src/w2/domain/time.py",
    "src/w2/schemas/domain.py",
    "src/w2/infrastructure/persistence/models.py",
    "migrations/versions/0002_create_stage3_domain_model.py",
    "docs/adr/ADR-0003-unified-football-data-model.md",
    "docs/data/W2_DOMAIN_MODEL_V1.md",
    "docs/data/W2_IDENTITY_AND_TIME_POLICY_V1.md",
    "docs/data/W2_ODDS_AND_SETTLEMENT_V1.md",
    "docs/data/W2_DATA_LAYER_POLICY_V1.md",
]

CONTRACTS = [
    "contracts/domain/provider_entity_mapping.schema.json",
    "contracts/domain/raw_payload_reference.schema.json",
    "contracts/domain/odds_observation.schema.json",
    "contracts/domain/feature_snapshot.schema.json",
    "contracts/domain/data_provenance.schema.json",
]

ENTITIES = [
    "Competition",
    "Season",
    "Stage",
    "Fixture",
    "Team",
    "Player",
    "Squad",
    "Venue",
    "Referee",
    "Bookmaker",
    "Market",
    "OddsObservation",
    "Lineup",
    "Injury",
    "Suspension",
    "WeatherObservation",
    "TeamRating",
    "FeatureSnapshot",
    "ModelRun",
    "Prediction",
    "Recommendation",
    "RecommendationLock",
    "Result",
    "Settlement",
    "AuditEvent",
    "ProviderEntityMapping",
    "RawPayloadReference",
    "DataProvenance",
]


def fail(message: str) -> None:
    print(f"W2 Stage3 data model check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    for path in [*REQUIRED, *CONTRACTS]:
        if not (ROOT / path).is_file():
            fail(f"missing {path}")
    for path in CONTRACTS:
        payload = json.loads(read(path))
        if payload.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            fail(f"schema draft mismatch {path}")
        if payload.get("additionalProperties") is not False:
            fail(f"schema must forbid unknown fields {path}")
    domain_text = read("src/w2/domain/entities.py")
    enum_text = read("src/w2/domain/enums.py")
    models_text = read("src/w2/infrastructure/persistence/models.py")
    migration_text = read("migrations/versions/0002_create_stage3_domain_model.py")
    for entity in ENTITIES:
        if f"class {entity}" not in domain_text:
            fail(f"missing domain entity {entity}")
        persistence_optional = {
            "AuditEvent",
            "Bookmaker",
            "DataProvenance",
            "FeatureSnapshot",
            "Injury",
            "Lineup",
            "Market",
            "OddsObservation",
            "Player",
            "ProviderEntityMapping",
            "RawPayloadReference",
            "Squad",
            "Suspension",
            "TeamRating",
            "WeatherObservation",
        }
        if f"{entity}Model" not in models_text and entity not in persistence_optional:
            fail(f"missing persistence model for {entity}")
    for token in ["DataLayer", "RAW", "NORMALIZED", "FEATURE", "PREDICTION_STRATEGY"]:
        if token not in domain_text + enum_text + models_text:
            fail(f"missing layer token {token}")
    for token in ["event_time", "provider_updated_at", "ingested_at", "as_of_time", "confirmed_at"]:
        if token not in domain_text + models_text:
            fail(f"missing time token {token}")
    for token in [
        "UniqueConstraint",
        "ForeignKey",
        "ix_fixtures_kickoff",
    ]:
        if token not in models_text:
            fail(f"missing persistence constraint/index token {token}")
    for token in ["split_quarter_line", "settle_asian_handicap", "settle_total_goals"]:
        if token not in read("src/w2/domain/odds.py"):
            fail(f"missing odds library function {token}")
    if "mtime" in domain_text + models_text + migration_text:
        fail("file mtime must not be used as business time")
    if "/w1_world_cup_engine" in domain_text + models_text:
        fail("W1 runtime path dependency detected")
    print("W2 Stage3 data model check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
