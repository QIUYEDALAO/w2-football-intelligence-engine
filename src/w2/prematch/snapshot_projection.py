"""Offline append-only snapshot projection kept outside the API package."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel

DASHBOARD_PREFIX = "dashboard:"
ALLOWED_DECISIONS = {"WATCH", "SKIP"}


class DashboardProjectionError(ValueError):
    pass


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise DashboardProjectionError(f"naive datetime rejected: {value}")
    return parsed.astimezone(UTC)


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def checkpoint_key(name: str) -> str:
    return f"{DASHBOARD_PREFIX}{name}"


@dataclass(frozen=True)
class DashboardProjection:
    fixture: dict[str, Any]
    provider: dict[str, Any]
    data_health: dict[str, Any]
    forward_status: dict[str, Any]
    checkpoint_payloads: dict[str, dict[str, Any]]


class MatchdaySnapshotProjector:
    def __init__(self, snapshot_root: Path) -> None:
        self.snapshot_root = snapshot_root

    def project_latest(self, fixture_id: str | None = None) -> DashboardProjection:
        snapshot_dir = self._latest_snapshot_dir(fixture_id)
        return self.project_snapshot(snapshot_dir)

    def project_snapshot(self, snapshot_dir: Path) -> DashboardProjection:
        manifest_path = snapshot_dir / "manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        quality = load_json(snapshot_dir / "data_quality.json")
        decision = load_json(snapshot_dir / "decision.json")
        model = load_json(snapshot_dir / "model_output.json")
        normalized = load_json(snapshot_dir / "normalized_odds.json")
        fixture_raw = load_json(snapshot_dir / "raw" / "01_fixture_detail.json")
        self._validate_snapshot(snapshot_dir, manifest, quality, decision, model, normalized)
        fixture_item = self._fixture_item(fixture_raw)
        captured_at = parse_utc(manifest["captured_at_utc"])
        kickoff = parse_utc(manifest["kickoff_utc"])
        rows = normalized.get("rows", [])
        value_rows = model.get("value_rows", [])
        fixture = {
            "fixture_id": str(manifest["fixture_id"]),
            "provider_fixture_id": str(manifest["fixture_id"]),
            "competition_id": str(fixture_item.get("league", {}).get("id", "world_cup_2026")),
            "competition_name": str(fixture_item.get("league", {}).get("name", "FIFA World Cup")),
            "stage": str(fixture_item.get("league", {}).get("round", "Group J")),
            "kickoff_utc": kickoff.isoformat(),
            "status": str(fixture_item.get("fixture", {}).get("status", {}).get("short", "NS")),
            "home_team_id": str(fixture_item.get("teams", {}).get("home", {}).get("id", "")),
            "home_team_name": str(fixture_item.get("teams", {}).get("home", {}).get("name", "")),
            "away_team_id": str(fixture_item.get("teams", {}).get("away", {}).get("id", "")),
            "away_team_name": str(fixture_item.get("teams", {}).get("away", {}).get("name", "")),
            "venue": fixture_item.get("fixture", {}).get("venue", {}).get("name"),
            "captured_at": captured_at.isoformat(),
            "phase": manifest.get("phase"),
            "decision_status": decision["state"],
            "research_value_lean": decision.get("research_value_lean"),
            "formal_recommendation": False,
            "candidate": False,
            "gate4_status": decision.get("gate4_status", "PROVISIONAL_FORWARD_HOLDOUT_PENDING"),
            "data_status": quality["status"],
            "bookmaker_count": self._bookmaker_count(rows),
            "market_coverage": self._market_coverage(rows),
            "market_probabilities": self._market_probabilities(value_rows),
            "independent_model_probabilities": model.get("probabilities", {}),
            "expected_goals": model.get("expected_goals", {}),
            "score_matrix_top": model.get("score_matrix_top", []),
            "value_rows": value_rows,
            "selected_value": decision.get("selected_value"),
            "risk_notes": quality.get("warnings", []),
            "source_manifest_sha256": sha256_bytes(manifest_bytes),
            "model_artifact_sha256": manifest.get("model_artifact_sha256"),
            "calibration_sha256": manifest.get("calibration_sha256"),
            "provenance": {
                "source": "append_only_matchday_snapshot",
                "snapshot_id": snapshot_dir.name,
                "snapshot_semantics": "CAPTURED_AT",
            },
        }
        provider = {
            "provider": "api_football",
            "status": "READY",
            "remaining_quota": manifest.get("remaining_quota"),
            "credential_status": "PRESENT",
            "last_request_status": 200,
            "last_successful_request": captured_at.isoformat(),
        }
        data_health = {
            "stale_data_count": 0,
            "provider_status": "READY",
            "forward_cycle_age_seconds": None,
            "gate4_progress": {"status": "PROVISIONAL_FORWARD_HOLDOUT_PENDING"},
            "generated_at": datetime.now(UTC).isoformat(),
        }
        forward = {
            "status": decision["state"],
            "locks": 0,
            "market_comparable": 1,
            "current_settled_n": 0,
            "target_n": 50,
        }
        payloads = {
            checkpoint_key(f"fixture_latest:{fixture['fixture_id']}"): fixture,
            checkpoint_key(f"fixture:{fixture['fixture_id']}:{fixture['captured_at']}"): fixture,
            checkpoint_key("provider_status"): provider,
            checkpoint_key("data_health"): data_health,
            checkpoint_key("forward_status"): forward,
        }
        return DashboardProjection(fixture, provider, data_health, forward, payloads)

    def _latest_snapshot_dir(self, fixture_id: str | None) -> Path:
        candidates: list[Path] = []
        for path in sorted(self.snapshot_root.iterdir()):
            if not path.is_dir():
                continue
            manifest_path = path / "manifest.json"
            if not manifest_path.exists():
                continue
            manifest = load_json(manifest_path)
            if fixture_id is None or str(manifest.get("fixture_id")) == fixture_id:
                candidates.append(path)
        if not candidates:
            raise DashboardProjectionError("no validated snapshot candidates found")
        ordered = sorted(
            candidates,
            key=lambda p: load_json(p / "manifest.json")["captured_at_utc"],
        )
        return ordered[-1]

    def _validate_snapshot(
        self,
        snapshot_dir: Path,
        manifest: dict[str, Any],
        quality: dict[str, Any],
        decision: dict[str, Any],
        model: dict[str, Any],
        normalized: dict[str, Any],
    ) -> None:
        if manifest.get("append_only") is not True:
            raise DashboardProjectionError("manifest append_only must be true")
        if str(manifest.get("fixture_id", "")) == "":
            raise DashboardProjectionError("fixture_id missing")
        captured_at = parse_utc(str(manifest["captured_at_utc"]))
        kickoff = parse_utc(str(manifest["kickoff_utc"]))
        if captured_at >= kickoff:
            raise DashboardProjectionError("captured_at must be before kickoff")
        if quality.get("fixture_identity") != "PASS":
            raise DashboardProjectionError("fixture identity check failed")
        if quality.get("frozen_artifact_hash") != "PASS":
            raise DashboardProjectionError("frozen artifact hash check failed")
        if quality.get("feature_leakage") != "PASS":
            raise DashboardProjectionError("feature leakage check failed")
        if quality.get("status") not in {"READY", "WATCH_ONLY"}:
            raise DashboardProjectionError("snapshot quality not displayable")
        if decision.get("state") not in ALLOWED_DECISIONS:
            raise DashboardProjectionError("decision must be WATCH or SKIP")
        if decision.get("formal_recommendation") is not False:
            raise DashboardProjectionError("formal recommendation must remain false")
        if decision.get("candidate") is not False:
            raise DashboardProjectionError("candidate must remain false")
        if abs(float(model.get("score_matrix_probability_sum", 0.0)) - 1.0) > 1e-9:
            raise DashboardProjectionError("score matrix is not normalized")
        expected = {
            "normalized_data_sha256": snapshot_dir / "normalized_odds.json",
            "decision_sha256": snapshot_dir / "decision.json",
        }
        for field, path in expected.items():
            if manifest.get(field) != file_sha256(path):
                raise DashboardProjectionError(f"{field} mismatch")
        if not isinstance(normalized.get("rows"), list):
            raise DashboardProjectionError("normalized rows missing")

    def _fixture_item(self, raw_fixture: dict[str, Any]) -> dict[str, Any]:
        response = raw_fixture.get("payload", {}).get("response", [])
        if not response:
            raise DashboardProjectionError("fixture detail payload missing")
        item = response[0]
        if str(item.get("fixture", {}).get("id")) == "":
            raise DashboardProjectionError("provider fixture id missing")
        return cast(dict[str, Any], item)

    def _bookmaker_count(self, rows: list[dict[str, Any]]) -> int:
        return len({str(row.get("bookmaker_id")) for row in rows if row.get("bookmaker_id")})

    def _market_coverage(self, rows: list[dict[str, Any]]) -> dict[str, bool]:
        markets = {row.get("market_type") for row in rows}
        return {
            "ONE_X_TWO": "ONE_X_TWO" in markets,
            "ASIAN_HANDICAP": "ASIAN_HANDICAP" in markets,
            "TOTALS": "TOTALS" in markets,
            "BTTS": "BTTS" in markets,
        }

    def _market_probabilities(self, value_rows: list[dict[str, Any]]) -> dict[str, float]:
        probabilities: dict[str, float] = {}
        for row in value_rows:
            if row.get("market") != "ONE_X_TWO" or row.get("line") is not None:
                continue
            selection = str(row.get("selection"))
            probability = row.get("market_fair_probability")
            if selection and probability is not None:
                probabilities[selection] = float(probability)
        return probabilities


def write_projection(engine: Engine, projection: DashboardProjection) -> None:
    now = datetime.now(UTC)
    with Session(engine) as session:
        for key, payload in projection.checkpoint_payloads.items():
            source_hash = str(
                payload.get("source_manifest_sha256")
                or sha256_bytes(json.dumps(payload, sort_keys=True, default=str).encode("utf-8"))
            )
            existing = session.scalar(
                select(ReadModelCheckpointModel).where(
                    ReadModelCheckpointModel.checkpoint_key == key
                )
            )
            if existing is None:
                session.add(
                    ReadModelCheckpointModel(
                        checkpoint_key=key,
                        source_hash=source_hash,
                        created_at=now,
                        payload=payload,
                    )
                )
            else:
                existing.source_hash = source_hash
                existing.created_at = now
                existing.payload = payload
        session.commit()
