from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

from w2.domain.time import require_utc

FEATURE_RESULT_FIELDS = frozenset(
    {"home_goals", "away_goals", "result", "final_score", "settlement"}
)


def stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_id() -> UUID:
    return uuid4()


@dataclass(frozen=True, kw_only=True)
class DatasetSource:
    source_id: str
    provider: str
    registry_ref: str
    provenance: dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class DatasetVersion:
    dataset_id: str
    version: str
    created_at: datetime
    source_ids: tuple[str, ...]
    manifest_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))


@dataclass(frozen=True, kw_only=True)
class DatasetArtifact:
    artifact_id: str
    dataset_id: str
    version: str
    path: str
    media_type: str
    sha256: str
    row_count: int

    def __post_init__(self) -> None:
        if len(self.sha256) != 64:
            raise ValueError("artifact sha256 must be a 64-character digest")


@dataclass(frozen=True, kw_only=True)
class LabelReference:
    fixture_id: str
    result_status: str
    home_goals: int | None
    away_goals: int | None
    confirmed_at: datetime
    raw_payload_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "confirmed_at", require_utc(self.confirmed_at, "confirmed_at"))


@dataclass(frozen=True, kw_only=True)
class AsOfSample:
    fixture_id: str
    competition: str
    season: str
    kickoff_utc: datetime
    prediction_phase: str
    as_of_time: datetime
    data_cutoff: datetime
    odds_snapshot: dict[str, Any]
    lineup_status: dict[str, Any]
    injury_status: dict[str, Any]
    team_rating_features: dict[str, Any]
    raw_payload_refs: tuple[str, ...]
    feature_snapshot_version: str
    label_reference: LabelReference
    provenance: dict[str, Any]
    sample_id: UUID = field(default_factory=new_id)

    def __post_init__(self) -> None:
        kickoff = require_utc(self.kickoff_utc, "kickoff_utc")
        as_of = require_utc(self.as_of_time, "as_of_time")
        cutoff = require_utc(self.data_cutoff, "data_cutoff")
        if as_of >= kickoff:
            raise ValueError("as_of_time must be before kickoff")
        if cutoff > as_of:
            raise ValueError("data_cutoff cannot be after as_of_time")
        if self.label_reference.confirmed_at <= as_of:
            raise ValueError("label_reference must be physically independent from pre-match sample")
        feature_payload = {
            **self.odds_snapshot,
            **self.lineup_status,
            **self.injury_status,
            **self.team_rating_features,
        }
        if FEATURE_RESULT_FIELDS & set(feature_payload):
            raise ValueError("label fields must not enter feature payload")
        object.__setattr__(self, "kickoff_utc", kickoff)
        object.__setattr__(self, "as_of_time", as_of)
        object.__setattr__(self, "data_cutoff", cutoff)
        for name in (
            "odds_snapshot",
            "lineup_status",
            "injury_status",
            "team_rating_features",
            "provenance",
        ):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))

    def identity_key(self) -> tuple[str, str, str]:
        return (self.fixture_id, self.prediction_phase, self.as_of_time.isoformat())

    def feature_payload(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "competition": self.competition,
            "season": self.season,
            "kickoff_utc": self.kickoff_utc.isoformat(),
            "prediction_phase": self.prediction_phase,
            "as_of_time": self.as_of_time.isoformat(),
            "data_cutoff": self.data_cutoff.isoformat(),
            "odds_snapshot": dict(self.odds_snapshot),
            "lineup_status": dict(self.lineup_status),
            "injury_status": dict(self.injury_status),
            "team_rating_features": dict(self.team_rating_features),
            "raw_payload_refs": list(self.raw_payload_refs),
            "feature_snapshot_version": self.feature_snapshot_version,
            "provenance": dict(self.provenance),
        }

    def label_payload(self) -> dict[str, Any]:
        return {
            "fixture_id": self.label_reference.fixture_id,
            "result_status": self.label_reference.result_status,
            "home_goals": self.label_reference.home_goals,
            "away_goals": self.label_reference.away_goals,
            "confirmed_at": self.label_reference.confirmed_at.isoformat(),
            "raw_payload_refs": list(self.label_reference.raw_payload_refs),
        }


@dataclass(frozen=True, kw_only=True)
class DataQualityRun:
    dataset_id: str
    version: str
    run_at: datetime
    status: str
    checks: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_at", require_utc(self.run_at, "run_at"))
        if self.status not in {"PASS", "WARN", "FAIL"}:
            raise ValueError("quality status must be PASS, WARN, or FAIL")
        object.__setattr__(self, "checks", MappingProxyType(dict(self.checks)))
