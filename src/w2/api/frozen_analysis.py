from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from time import monotonic
from typing import Any, Protocol, cast

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.api.repository import ReadModelRepository, ReadModelService
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.operations.observability import default_metric_registry

ANALYSIS_CARD_CANARY_SCHEMA = "w2.analysis-card.frozen.v1"
ANALYSIS_CARD_CANARY_PREFIX = "analysis-card:frozen:v1:"
ANALYSIS_CARD_CANARY_FIXTURES = frozenset({"1576804", "1494701", "1494210"})
MAX_OBSERVATIONS_PER_FIXTURE = 256
MAX_PUBLIC_FIXTURES = 512


class FrozenAnalysisError(ValueError):
    """A deterministic analysis artifact cannot be safely built or read."""


class ScopedAnalysisRepository(Protocol):
    def fixture_payload(self, fixture_id: str) -> dict[str, Any] | None: ...

    def future_market_observations_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> list[dict[str, Any]]: ...


class _FrozenScopedInputs:
    """Pin primary scoped inputs while delegating other bounded repositories."""

    def __init__(
        self,
        delegate: ScopedAnalysisRepository,
        fixture_id: str,
        fixture_payload: dict[str, Any],
        observations: list[dict[str, Any]],
    ) -> None:
        self.delegate = delegate
        self.fixture_id = fixture_id
        self.fixture = fixture_payload
        self.observations = observations

    def fixture_payload(self, fixture_id: str) -> dict[str, Any] | None:
        return self.fixture if fixture_id == self.fixture_id else None

    def future_market_observations_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> list[dict[str, Any]]:
        if fixture_ids != [self.fixture_id]:
            raise FrozenAnalysisError("materializer requested an unexpected fixture scope")
        return [dict(row) for row in self.observations]

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)


@dataclass(frozen=True)
class FrozenAnalysisArtifact:
    checkpoint_key: str
    source_hash: str
    artifact_hash: str
    payload: dict[str, Any]
    canonical_bytes: bytes


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise FrozenAnalysisError("naive datetime rejected from frozen artifact")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date | Decimal):
        return str(value)
    raise TypeError(f"unsupported frozen artifact value: {type(value).__name__}")


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")


def canonical_sha256(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def analysis_card_canary_key(fixture_id: str) -> str:
    normalized = str(fixture_id).strip()
    if not normalized:
        raise FrozenAnalysisError("fixture identity missing")
    key = f"{ANALYSIS_CARD_CANARY_PREFIX}{normalized}"
    if len(key) > 128:
        raise FrozenAnalysisError("checkpoint key exceeds storage limit")
    return key


def _fixture_identity(fixture_id: str, payload: dict[str, Any]) -> dict[str, str]:
    fixture = payload.get("fixture")
    league = payload.get("league")
    teams = payload.get("teams")
    if not isinstance(fixture, dict) or not isinstance(league, dict) or not isinstance(teams, dict):
        raise FrozenAnalysisError("fixture identity payload incomplete")
    home = teams.get("home")
    away = teams.get("away")
    if not isinstance(home, dict) or not isinstance(away, dict):
        raise FrozenAnalysisError("fixture team identity incomplete")
    identity = {
        "fixture_id": str(fixture.get("id") or ""),
        "competition_id": str(league.get("id") or ""),
        "kickoff_utc": str(fixture.get("date") or ""),
        "home_team_id": str(home.get("id") or ""),
        "away_team_id": str(away.get("id") or ""),
    }
    if identity["fixture_id"] != fixture_id:
        raise FrozenAnalysisError("fixture identity conflict")
    if any(not value for value in identity.values()):
        raise FrozenAnalysisError("fixture identity field missing")
    return identity


def _normalize_evaluation_time(value: datetime) -> str:
    if value.tzinfo is None:
        raise FrozenAnalysisError("evaluation time must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class AnalysisCardCanaryMaterializer:
    def __init__(self, repository: ScopedAnalysisRepository) -> None:
        self.repository = repository

    def build(self, fixture_id: str, *, evaluated_at: datetime) -> FrozenAnalysisArtifact:
        registry = default_metric_registry()
        started = monotonic()
        try:
            artifact = self._build(fixture_id, evaluated_at=evaluated_at)
        except Exception:
            registry.inc(
                "w2_materializer_results_total",
                labels={"status": "ERROR"},
            )
            raise
        registry.inc(
            "w2_materializer_results_total",
            labels={"status": "SUCCESS"},
        )
        registry.observe(
            "w2_materializer_duration_ms",
            (monotonic() - started) * 1000,
        )
        return artifact

    def _build(self, fixture_id: str, *, evaluated_at: datetime) -> FrozenAnalysisArtifact:
        key = analysis_card_canary_key(fixture_id)
        evaluation_time = _normalize_evaluation_time(evaluated_at)
        fixture_payload = self.repository.fixture_payload(fixture_id)
        if fixture_payload is None:
            raise FrozenAnalysisError("scoped fixture input missing")
        identity = _fixture_identity(fixture_id, fixture_payload)
        observations = self.repository.future_market_observations_for_fixtures([fixture_id])
        if not observations:
            raise FrozenAnalysisError("scoped observation input missing")
        if len(observations) > MAX_OBSERVATIONS_PER_FIXTURE:
            raise FrozenAnalysisError("scoped observation input exceeds bound")
        if any(str(row.get("fixture_id") or "") != fixture_id for row in observations):
            raise FrozenAnalysisError("scoped observation identity conflict")

        frozen_inputs = _FrozenScopedInputs(
            self.repository,
            fixture_id,
            fixture_payload,
            observations,
        )
        service = ReadModelService(repository=cast(ReadModelRepository, frozen_inputs))
        card = service.public_analysis_card_bounded(
            fixture_id,
            evaluation_time=evaluated_at,
            use_frozen_canary=False,
        )
        if card is None:
            raise FrozenAnalysisError("analysis-card projection unavailable")
        if str(card.get("fixture_id") or "") != fixture_id:
            raise FrozenAnalysisError("analysis-card fixture identity conflict")

        input_manifest = {
            "evaluated_at": evaluation_time,
            "fixture_payload_sha256": canonical_sha256(fixture_payload),
            "observation_count": len(observations),
            "observation_sha256": sorted(canonical_sha256(row) for row in observations),
        }
        artifact_body = {
            "schema_version": ANALYSIS_CARD_CANARY_SCHEMA,
            "checkpoint_namespace": "public",
            "fixture_identity": identity,
            "input_manifest": input_manifest,
            "analysis_card": card,
        }
        artifact_hash = canonical_sha256(artifact_body)
        payload = {**artifact_body, "artifact_hash": artifact_hash}
        return FrozenAnalysisArtifact(
            checkpoint_key=key,
            source_hash=canonical_sha256(input_manifest),
            artifact_hash=artifact_hash,
            payload=payload,
            canonical_bytes=canonical_json_bytes(payload),
        )


def validate_frozen_analysis_payload(
    fixture_id: str,
    payload: dict[str, Any],
) -> FrozenAnalysisArtifact:
    if payload.get("schema_version") != ANALYSIS_CARD_CANARY_SCHEMA:
        raise FrozenAnalysisError("checkpoint schema incompatible")
    identity = payload.get("fixture_identity")
    if not isinstance(identity, dict) or str(identity.get("fixture_id") or "") != fixture_id:
        raise FrozenAnalysisError("checkpoint fixture identity conflict")
    manifest = payload.get("input_manifest")
    card = payload.get("analysis_card")
    if not isinstance(manifest, dict) or not isinstance(card, dict):
        raise FrozenAnalysisError("checkpoint payload incomplete")
    if str(card.get("fixture_id") or "") != fixture_id:
        raise FrozenAnalysisError("checkpoint card identity conflict")
    artifact_hash = str(payload.get("artifact_hash") or "")
    artifact_body = {key: value for key, value in payload.items() if key != "artifact_hash"}
    if not artifact_hash or canonical_sha256(artifact_body) != artifact_hash:
        raise FrozenAnalysisError("checkpoint artifact hash mismatch")
    return FrozenAnalysisArtifact(
        checkpoint_key=analysis_card_canary_key(fixture_id),
        source_hash=canonical_sha256(manifest),
        artifact_hash=artifact_hash,
        payload=payload,
        canonical_bytes=canonical_json_bytes(payload),
    )


def write_frozen_analysis_artifacts(
    engine: Engine,
    artifacts: list[FrozenAnalysisArtifact],
) -> None:
    if len({artifact.checkpoint_key for artifact in artifacts}) != len(artifacts):
        raise FrozenAnalysisError("duplicate checkpoint identity in write batch")
    validated = [
        validate_frozen_analysis_payload(
            artifact.checkpoint_key.removeprefix(ANALYSIS_CARD_CANARY_PREFIX),
            artifact.payload,
        )
        for artifact in artifacts
    ]
    now = datetime.now(UTC)
    with Session(engine) as session:
        try:
            for artifact in validated:
                existing = session.scalar(
                    select(ReadModelCheckpointModel).where(
                        ReadModelCheckpointModel.checkpoint_key == artifact.checkpoint_key
                    )
                )
                if existing is None:
                    session.add(
                        ReadModelCheckpointModel(
                            checkpoint_key=artifact.checkpoint_key,
                            source_hash=artifact.source_hash,
                            created_at=now,
                            payload=artifact.payload,
                        )
                    )
                    continue
                fixture_id = artifact.checkpoint_key.removeprefix(ANALYSIS_CARD_CANARY_PREFIX)
                current = validate_frozen_analysis_payload(fixture_id, existing.payload)
                if current.source_hash == artifact.source_hash:
                    if current.canonical_bytes != artifact.canonical_bytes:
                        raise FrozenAnalysisError("same source produced conflicting artifact")
                    continue
                existing.source_hash = artifact.source_hash
                existing.created_at = now
                existing.payload = artifact.payload
            session.commit()
        except Exception:
            session.rollback()
            raise


def read_frozen_analysis_artifact(
    engine: Engine,
    fixture_id: str,
) -> FrozenAnalysisArtifact | None:
    key = analysis_card_canary_key(fixture_id)
    with Session(engine) as session:
        row = session.scalar(
            select(ReadModelCheckpointModel).where(ReadModelCheckpointModel.checkpoint_key == key)
        )
    if row is None:
        default_metric_registry().inc(
            "w2_checkpoint_reads_total", labels={"status": "MISS"}
        )
        return None
    try:
        artifact = validate_frozen_analysis_payload(fixture_id, row.payload)
        if row.source_hash != artifact.source_hash:
            raise FrozenAnalysisError("checkpoint source hash mismatch")
    except FrozenAnalysisError:
        default_metric_registry().inc(
            "w2_checkpoint_reads_total", labels={"status": "INVALID"}
        )
        raise
    default_metric_registry().inc(
        "w2_checkpoint_reads_total", labels={"status": "HIT"}
    )
    return artifact
