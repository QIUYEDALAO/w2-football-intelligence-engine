from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.competitions.league_whitelist_scope import load_league_whitelist_scope
from w2.competitions.registry import CompetitionRegistry
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.prematch.read_model_projection import (
    ANALYSIS_CARD_SHADOW_PREFIX,
    ANALYSIS_EVIDENCE_CONTRACT_VERSION,
    FrozenAnalysisError,
    HashDomain,
    ProjectionSourceEvent,
    canonical_sha256,
    validate_frozen_analysis_payload,
)

MAX_REPAIR_TARGETS = 512


@dataclass(frozen=True)
class ProjectionRepairReport:
    schema_version: str
    mode: str
    current_contract_version: str
    scanned: int
    eligible: int
    updated: int
    target_sha256: str
    provider_calls: int
    targets: tuple[dict[str, Any], ...]


Materialize = Callable[..., list[str]]


def repair_analysis_market_projection_v4(
    engine: Engine,
    *,
    apply: bool = False,
    expected_count: int | None = None,
    expected_target_sha256: str | None = None,
    materialize: Materialize | None = None,
) -> ProjectionRepairReport:
    if apply and (expected_count is None or expected_target_sha256 is None):
        raise ValueError("--apply requires --expected-count and --expected-target-sha256")
    competition_ids = tuple(
        load_league_whitelist_scope(CompetitionRegistry(engine)).all_whitelist
    )
    if len(competition_ids) != 13:
        raise RuntimeError(f"PROJECTION_REPAIR_SCOPE_NOT_EXACT_13:{len(competition_ids)}")

    rows = _shadow_rows(engine)
    targets_with_rows = [
        (_target(row), row)
        for row in rows
        if _competition_id(row.payload) in competition_ids
        and _contract_version(row.payload) != ANALYSIS_EVIDENCE_CONTRACT_VERSION
    ]
    if len(targets_with_rows) > MAX_REPAIR_TARGETS:
        raise RuntimeError(
            f"PROJECTION_REPAIR_TARGET_BOUND_EXCEEDED:{len(targets_with_rows)}"
        )
    targets = tuple(target for target, _row in targets_with_rows)
    target_sha256 = _target_sha256(targets)
    if apply and len(targets) != expected_count:
        raise RuntimeError(
            "PROJECTION_REPAIR_EXPECTED_COUNT_MISMATCH:"
            f"expected={expected_count}:actual={len(targets)}"
        )
    if apply and target_sha256 != expected_target_sha256:
        raise RuntimeError(
            "PROJECTION_REPAIR_EXPECTED_TARGET_MISMATCH:"
            f"expected={expected_target_sha256}:actual={target_sha256}"
        )

    updated = 0
    if apply and targets_with_rows:
        if materialize is None:
            try:
                module = importlib.import_module("scripts.run_prematch_refresh")
            except ModuleNotFoundError:
                module = importlib.import_module("run_prematch_refresh")
            materialize = module.materialize_shadow_projection_events
        events = [_source_event(row.payload) for _target, row in targets_with_rows]
        expected_source_hashes = {
            row.checkpoint_key: row.source_hash for _target, row in targets_with_rows
        }
        materialized = materialize(
            events,
            expected_existing_source_hashes=expected_source_hashes,
        )
        expected_fixture_ids = [target["fixture_id"] for target in targets]
        if sorted(materialized) != sorted(expected_fixture_ids):
            raise RuntimeError("PROJECTION_REPAIR_MATERIALIZED_SET_MISMATCH")
        _verify_current_contract(engine, tuple(expected_fixture_ids))
        updated = len(materialized)

    return ProjectionRepairReport(
        schema_version="w2.analysis-market-projection-repair.v1",
        mode="APPLY" if apply else "DRY_RUN",
        current_contract_version=ANALYSIS_EVIDENCE_CONTRACT_VERSION,
        scanned=len(rows),
        eligible=len(targets),
        updated=updated,
        target_sha256=target_sha256,
        provider_calls=0,
        targets=targets,
    )


def _shadow_rows(engine: Engine) -> list[ReadModelCheckpointModel]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(ReadModelCheckpointModel)
                .where(
                    ReadModelCheckpointModel.checkpoint_key.like(
                        f"{ANALYSIS_CARD_SHADOW_PREFIX}%"
                    )
                )
                .order_by(ReadModelCheckpointModel.checkpoint_key)
            )
        )


def _target(row: ReadModelCheckpointModel) -> dict[str, Any]:
    payload = row.payload
    fixture_id = row.checkpoint_key.removeprefix(ANALYSIS_CARD_SHADOW_PREFIX)
    event = _source_event(payload)
    return {
        "checkpoint_key": row.checkpoint_key,
        "fixture_id": fixture_id,
        "competition_id": _competition_id(payload),
        "source_hash": row.source_hash,
        "source_event_type": event.event_type,
        "source_event_id": event.event_id,
        "source_event_hash": event.event_hash,
        "old_contract_version": _contract_version(payload),
        "old_market_depth": {
            market: _bookmaker_count(payload, market)
            for market in ("ASIAN_HANDICAP", "TOTALS")
        },
    }


def _source_event(payload: Mapping[str, Any]) -> ProjectionSourceEvent:
    fixture = payload.get("fixture_identity")
    if not isinstance(fixture, Mapping):
        raise FrozenAnalysisError("projection repair fixture identity missing")
    event_at = _utc_datetime(payload.get("source_event_at"))
    values = {
        "fixture_id": str(fixture.get("fixture_id") or ""),
        "event_type": str(payload.get("source_event_type") or ""),
        "event_id": str(payload.get("source_event_id") or ""),
        "event_hash": str(payload.get("source_event_hash") or ""),
    }
    if event_at is None or any(not value for value in values.values()):
        raise FrozenAnalysisError("projection repair source event incomplete")
    return ProjectionSourceEvent(event_at=event_at, **values)


def _competition_id(payload: Mapping[str, Any]) -> str:
    card = payload.get("analysis_card")
    return str(card.get("competition_id") or "") if isinstance(card, Mapping) else ""


def _contract_version(payload: Mapping[str, Any]) -> str:
    manifest = payload.get("input_manifest")
    if not isinstance(manifest, Mapping):
        return "MISSING"
    return str(manifest.get("analysis_evidence_contract_version") or "MISSING")


def _bookmaker_count(payload: Mapping[str, Any], market: str) -> int | None:
    card = payload.get("analysis_card")
    radar = card.get("market_radar") if isinstance(card, Mapping) else None
    markets = radar.get("markets") if isinstance(radar, Mapping) else None
    market_payload = markets.get(market) if isinstance(markets, Mapping) else None
    current = market_payload.get("current") if isinstance(market_payload, Mapping) else None
    value = current.get("bookmaker_count") if isinstance(current, Mapping) else None
    return int(value) if isinstance(value, int | float | str) and str(value).isdigit() else None


def _target_sha256(targets: Sequence[Mapping[str, Any]]) -> str:
    return canonical_sha256(
        list(targets),
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
    )


def _utc_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _verify_current_contract(engine: Engine, fixture_ids: tuple[str, ...]) -> None:
    rows = {row.checkpoint_key: row for row in _shadow_rows(engine)}
    for fixture_id in fixture_ids:
        key = f"{ANALYSIS_CARD_SHADOW_PREFIX}{fixture_id}"
        row = rows.get(key)
        if row is None:
            raise RuntimeError(f"PROJECTION_REPAIR_POSTCONDITION_MISSING:{fixture_id}")
        artifact = validate_frozen_analysis_payload(fixture_id, row.payload)
        if row.source_hash != artifact.source_hash:
            raise RuntimeError(f"PROJECTION_REPAIR_POSTCONDITION_SOURCE:{fixture_id}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit or repair bounded stale analysis-market projections without Provider."
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--expected-target-sha256")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = repair_analysis_market_projection_v4(
        create_engine(),
        apply=args.apply,
        expected_count=args.expected_count,
        expected_target_sha256=args.expected_target_sha256,
    )
    print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
