from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from time import monotonic
from typing import Any, Protocol, cast

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.domain.recommendation_capabilities import load_recommendation_capability_manifest
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.operations.observability import default_metric_registry
from w2.prematch.lifecycle import (
    DynamicEvaluationInput,
    DynamicEvaluationVersion,
    classify_evaluation,
)
from w2.prematch.repository import DynamicPrematchRepository

ANALYSIS_CARD_CANARY_SCHEMA = "w2.analysis-card.frozen.v1"
ANALYSIS_EVIDENCE_CONTRACT_VERSION = "w2.analysis-market-evidence.v2"
ANALYSIS_CARD_CANARY_PREFIX = "analysis-card:frozen:v1:"
ANALYSIS_CARD_SHADOW_PREFIX = "analysis-card:shadow:v1:"
PROJECTION_VERSION = "w2.prematch-read-model-projection.v1"
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


AnalysisCardCalculator = Callable[
    [ScopedAnalysisRepository, str, datetime],
    dict[str, Any] | None,
]


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
    evaluations: tuple[DynamicEvaluationVersion, ...] = ()
    read_time_reference: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProjectionSourceEvent:
    fixture_id: str
    event_type: str
    event_id: str
    event_at: datetime
    event_hash: str

    @classmethod
    def create(
        cls,
        *,
        fixture_id: str,
        event_type: str,
        event_id: str,
        event_at: datetime,
        payload: object,
    ) -> ProjectionSourceEvent:
        normalized_at = _normalize_evaluation_time(event_at)
        normalized_fixture = str(fixture_id).strip()
        normalized_type = str(event_type).strip().upper()
        normalized_id = str(event_id).strip()
        if not normalized_fixture or not normalized_type or not normalized_id:
            raise FrozenAnalysisError("projection source event identity incomplete")
        return cls(
            fixture_id=normalized_fixture,
            event_type=normalized_type,
            event_id=normalized_id,
            event_at=datetime.fromisoformat(normalized_at.replace("Z", "+00:00")),
            event_hash=canonical_sha256(
                {
                    "fixture_id": normalized_fixture,
                    "event_type": normalized_type,
                    "event_id": normalized_id,
                    "event_at": normalized_at,
                    "payload": payload,
                }
            ),
        )


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
    return _analysis_card_checkpoint_key(ANALYSIS_CARD_CANARY_PREFIX, fixture_id)


def analysis_card_shadow_key(fixture_id: str) -> str:
    return _analysis_card_checkpoint_key(ANALYSIS_CARD_SHADOW_PREFIX, fixture_id)


def _analysis_card_checkpoint_key(prefix: str, fixture_id: str) -> str:
    normalized = str(fixture_id).strip()
    if not normalized:
        raise FrozenAnalysisError("fixture identity missing")
    key = f"{prefix}{normalized}"
    if len(key) > 128:
        raise FrozenAnalysisError("checkpoint key exceeds storage limit")
    return key


def _checkpoint_fixture_id(checkpoint_key: str) -> str:
    for prefix in (ANALYSIS_CARD_CANARY_PREFIX, ANALYSIS_CARD_SHADOW_PREFIX):
        if checkpoint_key.startswith(prefix):
            fixture_id = checkpoint_key.removeprefix(prefix)
            if fixture_id:
                return fixture_id
    raise FrozenAnalysisError("checkpoint namespace incompatible")


def _checkpoint_key_for_payload(fixture_id: str, payload: dict[str, Any]) -> str:
    namespace = str(payload.get("checkpoint_namespace") or "frozen")
    if namespace == "shadow":
        return analysis_card_shadow_key(fixture_id)
    if namespace in {"frozen", "public"}:
        return analysis_card_canary_key(fixture_id)
    raise FrozenAnalysisError("checkpoint namespace incompatible")


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
    def __init__(
        self,
        repository: ScopedAnalysisRepository,
        *,
        calculate_analysis_card: AnalysisCardCalculator,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.calculate_analysis_card = calculate_analysis_card
        self.clock = clock or (lambda: datetime.now(UTC))

    def build(
        self,
        fixture_id: str,
        *,
        evaluated_at: datetime,
        source_event: ProjectionSourceEvent | None = None,
    ) -> FrozenAnalysisArtifact:
        registry = default_metric_registry()
        started = monotonic()
        try:
            artifact = self._build(
                fixture_id,
                evaluated_at=evaluated_at,
                source_event=source_event,
            )
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

    def _build(
        self,
        fixture_id: str,
        *,
        evaluated_at: datetime,
        source_event: ProjectionSourceEvent | None,
    ) -> FrozenAnalysisArtifact:
        key = (
            analysis_card_shadow_key(fixture_id)
            if source_event is not None
            else analysis_card_canary_key(fixture_id)
        )
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
        card = self.calculate_analysis_card(
            cast(ScopedAnalysisRepository, frozen_inputs),
            fixture_id,
            evaluated_at,
        )
        if card is None:
            raise FrozenAnalysisError("analysis-card projection unavailable")
        if str(card.get("fixture_id") or "") != fixture_id:
            raise FrozenAnalysisError("analysis-card fixture identity conflict")
        read_time_reference = self.calculate_analysis_card(
            cast(ScopedAnalysisRepository, frozen_inputs),
            fixture_id,
            evaluated_at,
        )
        if read_time_reference is None:
            raise FrozenAnalysisError("analysis-card read-time reference unavailable")
        if str(read_time_reference.get("fixture_id") or "") != fixture_id:
            raise FrozenAnalysisError("analysis-card read-time fixture identity conflict")

        input_manifest = {
            "evaluated_at": evaluation_time,
            "competition_id": str(card.get("competition_id") or identity["competition_id"]),
            "fixture_payload_sha256": canonical_sha256(fixture_payload),
            "observation_count": len(observations),
            "observation_sha256": sorted(canonical_sha256(row) for row in observations),
            "quote_identity_sha256": canonical_sha256(card.get("quote_identity_audit") or {}),
            "simulation_sha256": canonical_sha256(card.get("simulation") or {}),
            "analysis_evidence_sha256": canonical_sha256(_analysis_evidence(card)),
            # This is part of source identity, not merely metadata: a code
            # change to how same-line evidence is projected must force a new
            # immutable public artifact rather than serving an old projection.
            "analysis_evidence_contract_version": ANALYSIS_EVIDENCE_CONTRACT_VERSION,
            "capability_manifest_sha256": load_recommendation_capability_manifest().sha256,
            "lineup_policy_version": str(
                (card.get("lineup_provenance") or {}).get("policy_version")
                if isinstance(card.get("lineup_provenance"), dict)
                else "w2.lineup_market_policy.v1"
            ),
        }
        event = source_event or ProjectionSourceEvent.create(
            fixture_id=fixture_id,
            event_type="MANUAL_AUDIT",
            event_id=f"manual-audit:{fixture_id}:{evaluation_time}",
            event_at=evaluated_at,
            payload={"input_manifest": input_manifest},
        )
        if event.fixture_id != fixture_id:
            raise FrozenAnalysisError("projection source event fixture conflict")
        evaluations = tuple(_dynamic_evaluations(card, input_manifest))
        if source_event is not None and not evaluations:
            raise FrozenAnalysisError("dynamic evaluation unavailable")
        primary = min(evaluations, key=lambda item: item.evaluation_id) if evaluations else None
        event_at = _normalize_evaluation_time(event.event_at)
        projected_at = _normalize_evaluation_time(self.clock())
        reconciliation = _reconcile_analysis_cards(read_time_reference, card)
        artifact_body = {
            "schema_version": ANALYSIS_CARD_CANARY_SCHEMA,
            "projection_version": PROJECTION_VERSION,
            "source_event_type": event.event_type,
            "source_event_id": event.event_id,
            "source_event_hash": event.event_hash,
            "source_event_at": event_at,
            "source_evaluation_id": primary.evaluation_id if primary is not None else None,
            "source_evaluation_hash": primary.identity_hash if primary is not None else None,
            "source_evaluation_ids": sorted(item.evaluation_id for item in evaluations),
            "source_evaluation_hashes": sorted(item.identity_hash for item in evaluations),
            "last_projected_at": projected_at,
            "checkpoint_namespace": "shadow" if source_event is not None else "public",
            "fixture_identity": identity,
            "input_manifest": input_manifest,
            "analysis_card": card,
            "shadow_reconciliation": reconciliation,
        }
        projection_hash = _projection_business_hash(artifact_body)
        projected_payload = {**artifact_body, "projection_hash": projection_hash}
        artifact_hash = canonical_sha256(projected_payload)
        payload = {**projected_payload, "artifact_hash": artifact_hash}
        return FrozenAnalysisArtifact(
            checkpoint_key=key,
            source_hash=canonical_sha256(
                {
                    "input_manifest": input_manifest,
                    "source_event_hash": event.event_hash,
                    "source_evaluation_hashes": sorted(item.identity_hash for item in evaluations),
                }
            ),
            artifact_hash=artifact_hash,
            payload=payload,
            canonical_bytes=canonical_json_bytes(payload),
            evaluations=evaluations,
            read_time_reference=read_time_reference,
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
    required_evidence = {
        "competition_id",
        "quote_identity_sha256",
        "simulation_sha256",
        "analysis_evidence_sha256",
        "capability_manifest_sha256",
        "lineup_policy_version",
    }
    if not required_evidence.issubset(manifest):
        raise FrozenAnalysisError("frozen analysis evidence missing")
    if str(card.get("fixture_id") or "") != fixture_id:
        raise FrozenAnalysisError("checkpoint card identity conflict")
    has_projection_metadata = "projection_version" in payload
    if has_projection_metadata:
        required_projection = {
            "projection_version",
            "projection_hash",
            "source_event_type",
            "source_event_id",
            "source_event_hash",
            "source_event_at",
            "source_evaluation_id",
            "source_evaluation_hash",
            "last_projected_at",
            "fixture_identity",
            "shadow_reconciliation",
        }
        if not required_projection.issubset(payload):
            raise FrozenAnalysisError("checkpoint projection metadata missing")
        if payload.get("projection_version") != PROJECTION_VERSION:
            raise FrozenAnalysisError("checkpoint projection version incompatible")
        projection_hash = str(payload.get("projection_hash") or "")
        projection_body = {
            key: value
            for key, value in payload.items()
            if key not in {"projection_hash", "artifact_hash"}
        }
        if not projection_hash or _projection_business_hash(projection_body) != projection_hash:
            raise FrozenAnalysisError("checkpoint projection hash mismatch")
        shadow = payload.get("shadow_reconciliation")
        if (
            not isinstance(shadow, dict)
            or shadow.get("match") is not True
            or shadow.get("read_time_hash") != canonical_sha256(card)
            or shadow.get("projected_hash") != canonical_sha256(card)
            or shadow.get("differences") != []
        ):
            raise FrozenAnalysisError("projection shadow reconciliation mismatch")
    artifact_hash = str(payload.get("artifact_hash") or "")
    artifact_body = {key: value for key, value in payload.items() if key != "artifact_hash"}
    if not artifact_hash or canonical_sha256(artifact_body) != artifact_hash:
        raise FrozenAnalysisError("checkpoint artifact hash mismatch")
    evaluations = tuple(_dynamic_evaluations(card, manifest)) if has_projection_metadata else ()
    primary = min(evaluations, key=lambda item: item.evaluation_id) if evaluations else None
    if primary is not None and (
        payload.get("source_evaluation_id") != primary.evaluation_id
        or payload.get("source_evaluation_hash") != primary.identity_hash
    ):
        raise FrozenAnalysisError("checkpoint evaluation identity mismatch")
    source_hash = (
        canonical_sha256(
            {
                "input_manifest": manifest,
                "source_event_hash": payload["source_event_hash"],
                "source_evaluation_hashes": sorted(item.identity_hash for item in evaluations),
            }
        )
        if has_projection_metadata
        else canonical_sha256(manifest)
    )
    return FrozenAnalysisArtifact(
        checkpoint_key=_checkpoint_key_for_payload(fixture_id, payload),
        source_hash=source_hash,
        artifact_hash=artifact_hash,
        payload=payload,
        canonical_bytes=canonical_json_bytes(payload),
        evaluations=evaluations,
    )


def _projection_business_hash(payload: dict[str, Any]) -> str:
    """Hash the stable business projection independently of execution time."""
    return canonical_sha256(
        {
            key: value
            for key, value in payload.items()
            if key not in {"last_projected_at", "projection_hash", "artifact_hash"}
        }
    )


def _difference_fields(reference: object, projected: object, *, path: str = "") -> list[str]:
    if isinstance(reference, dict) and isinstance(projected, dict):
        differences: list[str] = []
        for key in sorted(set(reference) | set(projected)):
            child = f"{path}.{key}" if path else str(key)
            if key not in reference or key not in projected:
                differences.append(child)
                continue
            differences.extend(_difference_fields(reference[key], projected[key], path=child))
        return differences
    if isinstance(reference, list) and isinstance(projected, list):
        differences = []
        if len(reference) != len(projected):
            differences.append(f"{path}.length" if path else "length")
        for index, (left, right) in enumerate(zip(reference, projected, strict=False)):
            child = f"{path}[{index}]" if path else f"[{index}]"
            differences.extend(_difference_fields(left, right, path=child))
        return differences
    return [] if reference == projected else [path or "$"]


def _reconcile_analysis_cards(
    read_time_card: dict[str, Any],
    projected_card: dict[str, Any],
) -> dict[str, Any]:
    differences = _difference_fields(read_time_card, projected_card)
    return {
        "read_time_hash": canonical_sha256(read_time_card),
        "projected_hash": canonical_sha256(projected_card),
        "match": not differences,
        "differences": differences,
    }


def _analysis_evidence(card: dict[str, Any]) -> dict[str, Any]:
    candidates = card.get("market_candidates")
    if not isinstance(candidates, dict):
        return {}
    return {
        str(key): value.get("analysis_evidence")
        for key, value in candidates.items()
        if isinstance(value, dict) and isinstance(value.get("analysis_evidence"), dict)
    }


def write_frozen_analysis_artifacts(
    engine: Engine,
    artifacts: list[FrozenAnalysisArtifact],
) -> None:
    if len({artifact.checkpoint_key for artifact in artifacts}) != len(artifacts):
        raise FrozenAnalysisError("duplicate checkpoint identity in write batch")
    validated = []
    references: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        fixture_id = _checkpoint_fixture_id(artifact.checkpoint_key)
        candidate = validate_frozen_analysis_payload(fixture_id, artifact.payload)
        if candidate.checkpoint_key != artifact.checkpoint_key:
            raise FrozenAnalysisError("checkpoint namespace conflicts with payload")
        validated.append(candidate)
        if artifact.read_time_reference is not None:
            references[artifact.checkpoint_key] = artifact.read_time_reference
    repository = DynamicPrematchRepository(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        try:
            for artifact in validated:
                for evaluation in artifact.evaluations:
                    repository.append_evaluation_in_session(session, evaluation)
                existing = session.scalar(
                    select(ReadModelCheckpointModel).where(
                        ReadModelCheckpointModel.checkpoint_key == artifact.checkpoint_key
                    )
                )
                if existing is None:
                    existing = ReadModelCheckpointModel(
                        checkpoint_key=artifact.checkpoint_key,
                        source_hash=artifact.source_hash,
                        created_at=now,
                        payload=artifact.payload,
                    )
                    session.add(existing)
                else:
                    fixture_id = _checkpoint_fixture_id(artifact.checkpoint_key)
                    try:
                        current = validate_frozen_analysis_payload(fixture_id, existing.payload)
                    except FrozenAnalysisError as exc:
                        # A pre-evidence checkpoint is intentionally fail-closed for reads,
                        # but its verified replacement must be allowed to re-materialize.
                        if str(exc) != "frozen analysis evidence missing":
                            raise
                        existing.source_hash = artifact.source_hash
                        existing.created_at = now
                        existing.payload = artifact.payload
                    else:
                        if current.source_hash == artifact.source_hash:
                            if current.payload.get("projection_hash") != artifact.payload.get(
                                "projection_hash"
                            ):
                                raise FrozenAnalysisError(
                                    "same source produced conflicting projection"
                                )
                        else:
                            existing.source_hash = artifact.source_hash
                            existing.created_at = now
                            existing.payload = artifact.payload
                session.flush()
                session.expire(existing, ["payload"])
                persisted_payload = existing.payload
                persisted_card = persisted_payload.get("analysis_card")
                reference = references.get(artifact.checkpoint_key)
                if not isinstance(persisted_card, dict) or reference is None:
                    if (
                        reference is None
                        and artifact.payload.get("checkpoint_namespace") != "shadow"
                    ):
                        continue
                    raise FrozenAnalysisError("projection persisted-readback unavailable")
                reconciliation = _reconcile_analysis_cards(reference, persisted_card)
                if reconciliation != persisted_payload.get("shadow_reconciliation"):
                    raise FrozenAnalysisError(
                        "projection persisted-readback reconciliation mismatch:"
                        + ",".join(reconciliation["differences"])
                    )
            session.commit()
        except Exception:
            session.rollback()
            raise


def _dynamic_evaluations(
    card: dict[str, Any],
    manifest: dict[str, Any],
) -> list[DynamicEvaluationVersion]:
    fixture_id = str(card.get("fixture_id") or "")
    evaluated_at = _parse_utc(manifest.get("evaluated_at"))
    candidates = card.get("market_candidates")
    if not fixture_id or evaluated_at is None or not isinstance(candidates, dict):
        return []
    lineup = card.get("lineup_provenance")
    lineup = lineup if isinstance(lineup, dict) else {}
    lineup_confirmed_at = _parse_utc(lineup.get("captured_at"))
    lineup_input_hash = (
        canonical_sha256(
            {
                "captured_at": lineup.get("captured_at"),
                "raw_sha256": lineup.get("raw_sha256"),
                "baseline_artifact_hashes": lineup.get("baseline_artifact_hashes"),
                "lineup_change_features": lineup.get("lineup_change_features"),
            }
        )
        if lineup_confirmed_at is not None and lineup.get("confirmed") is True
        else None
    )
    versions: list[DynamicEvaluationVersion] = []
    for key, default_market in (("ah", "ASIAN_HANDICAP"), ("ou", "TOTALS")):
        candidate = candidates.get(key)
        if not isinstance(candidate, dict):
            continue
        evidence = candidate.get("analysis_evidence")
        if not isinstance(evidence, dict):
            continue
        selection, side = _dynamic_evaluation_side(candidate, evidence)
        if not selection or not isinstance(side, dict):
            continue
        model = side.get("model_probability")
        comparison = side.get("comparison")
        quote_identity = evidence.get("quote_identity")
        market_probability = evidence.get("market_probability")
        if not all(
            isinstance(item, dict)
            for item in (model, comparison, quote_identity, market_probability)
        ):
            continue
        model = cast(dict[str, Any], model)
        comparison = cast(dict[str, Any], comparison)
        quote_identity = cast(dict[str, Any], quote_identity)
        market_probability = cast(dict[str, Any], market_probability)
        normalized = selection.lower().replace("_ah", "")
        quote = (quote_identity.get("quotes") or {}).get(normalized)
        quote = quote if isinstance(quote, dict) else {}
        devig = market_probability.get("devig")
        devig = devig if isinstance(devig, dict) else {}
        capture_at = _parse_utc(quote.get("captured_at") or quote_identity.get("captured_at"))
        value = DynamicEvaluationInput(
            fixture_id=fixture_id,
            market=str(candidate.get("market") or default_market),
            selection=selection,
            exact_line=_float_or_none(quote.get("line") or candidate.get("line")),
            bookmaker_id=str(quote.get("bookmaker_id") or quote_identity.get("bookmaker_id") or "")
            or None,
            capture_id=str(
                quote.get("capture_id")
                or quote.get("raw_payload_sha256")
                or quote_identity.get("capture_id")
                or ""
            )
            or None,
            quote_identity_hash=canonical_sha256(quote_identity),
            model_input_hash=canonical_sha256(
                {
                    "simulation": manifest.get("simulation_sha256"),
                    "analysis_evidence": manifest.get("analysis_evidence_sha256"),
                    "lineup_input_hash": lineup_input_hash,
                }
            ),
            evaluated_at=evaluated_at,
            checkpoint=_latest_checkpoint(card),
            capture_at=capture_at,
            source_observations_present=True,
            exact_quote_complete=str(quote_identity.get("identity_status") or "").upper()
            == "COMPLETE",
            quote_fresh=str(quote_identity.get("freshness_status") or "COMPLETE").upper()
            == "COMPLETE",
            model_ready=str(model.get("status") or "").upper() == "READY",
            market_probability_ready=bool(devig),
            identity_conflict=False,
            model_probability=_float_or_none(model.get("effective_probability")),
            market_probability=_float_or_none(devig.get(selection)),
            expected_value=_float_or_none(model.get("expected_value")),
            ev_se=_float_or_none(model.get("ev_se")),
            decimal_odds=_float_or_none(quote.get("decimal_odds")),
            lineup_input_hash=lineup_input_hash,
            lineup_confirmed_at=lineup_confirmed_at,
            post_lineup_quote=bool(
                lineup_confirmed_at is None
                or (capture_at is not None and capture_at >= lineup_confirmed_at)
            ),
        )
        versions.append(classify_evaluation(value))
    return versions


def _dynamic_evaluation_side(
    candidate: dict[str, Any],
    evidence: dict[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    sides = evidence.get("side_evidence")
    if not isinstance(sides, dict):
        return "", None
    selected = str(candidate.get("selection") or "")
    if selected and isinstance(sides.get(selected), dict):
        return selected, cast(dict[str, Any], sides[selected])
    ready: list[tuple[float, str, dict[str, Any]]] = []
    for selection, raw in sides.items():
        if not isinstance(raw, dict):
            continue
        model = raw.get("model_probability")
        if not isinstance(model, dict) or str(model.get("status") or "") != "READY":
            continue
        ev = _float_or_none(model.get("expected_value"))
        if ev is not None:
            ready.append((ev, str(selection), raw))
    if not ready:
        return "", None
    _ev, selection, side = max(ready, key=lambda item: (item[0], item[1]))
    return selection, side


def _latest_checkpoint(card: dict[str, Any]) -> str:
    timeline = card.get("market_timeline")
    if isinstance(timeline, dict):
        checkpoints = timeline.get("checkpoints_seen")
        if isinstance(checkpoints, list) and checkpoints:
            return str(checkpoints[-1])
    return "capture"


def _parse_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def materialize_projection_events(
    events: list[ProjectionSourceEvent],
    *,
    repository: ScopedAnalysisRepository,
    calculate_analysis_card: AnalysisCardCalculator,
    engine: Engine | None = None,
) -> list[str]:
    ordered = sorted(
        {(event.fixture_id, event.event_type, event.event_id): event for event in events}.values(),
        key=lambda item: (
            item.event_at,
            item.fixture_id,
            item.event_type,
            item.event_id,
        ),
    )
    if not ordered:
        return []
    if engine is None:
        from w2.infrastructure.database import create_engine

        engine = create_engine()
    materializer = AnalysisCardCanaryMaterializer(
        repository,
        calculate_analysis_card=calculate_analysis_card,
    )
    for event in ordered:
        artifact = materializer.build(
            event.fixture_id,
            evaluated_at=event.event_at,
            source_event=event,
        )
        write_frozen_analysis_artifacts(engine, [artifact])
    return list(dict.fromkeys(event.fixture_id for event in ordered))


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
        default_metric_registry().inc("w2_checkpoint_reads_total", labels={"status": "MISS"})
        return None
    created_at = row.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    default_metric_registry().gauge(
        "w2_checkpoint_lag_seconds",
        max(0.0, (datetime.now(UTC) - created_at).total_seconds()),
    )
    try:
        artifact = validate_frozen_analysis_payload(fixture_id, row.payload)
        if row.source_hash != artifact.source_hash:
            raise FrozenAnalysisError("checkpoint source hash mismatch")
    except FrozenAnalysisError:
        default_metric_registry().inc("w2_checkpoint_reads_total", labels={"status": "INVALID"})
        raise
    default_metric_registry().inc("w2_checkpoint_reads_total", labels={"status": "HIT"})
    return artifact


def read_shadow_analysis_artifact(
    engine: Engine,
    fixture_id: str,
) -> FrozenAnalysisArtifact | None:
    key = analysis_card_shadow_key(fixture_id)
    with Session(engine) as session:
        row = session.scalar(
            select(ReadModelCheckpointModel).where(ReadModelCheckpointModel.checkpoint_key == key)
        )
    if row is None:
        return None
    artifact = validate_frozen_analysis_payload(fixture_id, row.payload)
    if artifact.checkpoint_key != key or row.source_hash != artifact.source_hash:
        raise FrozenAnalysisError("shadow checkpoint identity mismatch")
    return artifact
