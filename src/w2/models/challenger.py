from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from w2.domain.time import require_utc
from w2.models.independent import FEATURE_ALLOWLIST, artifact_hash, assert_feature_allowlist


class ChallengerStatus(StrEnum):
    NOT_READY = "NOT_READY"
    SKIP = "SKIP"
    WATCH = "WATCH"


class ChallengerFamily(StrEnum):
    TIME_DECAY_ATTACK_DEFENCE = "TIME_DECAY_ATTACK_DEFENCE"
    REGULARIZED_MULTICLASS_LOGISTIC = "REGULARIZED_MULTICLASS_LOGISTIC"
    GRADIENT_BOOSTING = "GRADIENT_BOOSTING"
    ELO_POISSON_STACKING = "ELO_POISSON_STACKING"
    HIERARCHICAL_ATTACK_DEFENCE = "HIERARCHICAL_ATTACK_DEFENCE"
    CONSTRAINED_ENSEMBLE = "CONSTRAINED_ENSEMBLE"


@dataclass(frozen=True, kw_only=True)
class AuditSetFreeze:
    fixture_ids: tuple[str, ...]
    manifest_sha256: str
    status: str = "AUDIT_ONLY"

    @classmethod
    def from_fixture_ids(cls, fixture_ids: list[str]) -> AuditSetFreeze:
        ordered = tuple(sorted(fixture_ids))
        return cls(fixture_ids=ordered, manifest_sha256=artifact_hash({"fixture_ids": ordered}))


@dataclass(frozen=True, kw_only=True)
class ChallengerConfig:
    model_family: ChallengerFamily
    feature_allowlist: tuple[str, ...]
    calibration: str
    evaluation_metric: str
    promotion_criteria: dict[str, Any]
    selected_by: str

    def stable_hash(self) -> str:
        return artifact_hash(self.__dict__)


@dataclass(frozen=True, kw_only=True)
class ForwardPredictionLock:
    fixture_id: str
    kickoff_utc: datetime
    locked_at: datetime
    as_of_time: datetime
    data_cutoff: datetime
    model_version: str
    prediction_hash: str
    decision: ChallengerStatus

    def __post_init__(self) -> None:
        kickoff = require_utc(self.kickoff_utc, "kickoff_utc")
        locked_at = require_utc(self.locked_at, "locked_at")
        as_of_time = require_utc(self.as_of_time, "as_of_time")
        data_cutoff = require_utc(self.data_cutoff, "data_cutoff")
        if locked_at >= kickoff or as_of_time >= kickoff:
            raise ValueError("forward prediction must be locked before kickoff")
        if data_cutoff > as_of_time:
            raise ValueError("data_cutoff cannot be after as_of_time")
        object.__setattr__(self, "kickoff_utc", kickoff)
        object.__setattr__(self, "locked_at", locked_at)
        object.__setattr__(self, "as_of_time", as_of_time)
        object.__setattr__(self, "data_cutoff", data_cutoff)


class ForwardPredictionLedger:
    def __init__(self) -> None:
        self._locks: dict[str, ForwardPredictionLock] = {}

    def append_lock(self, lock: ForwardPredictionLock) -> None:
        if lock.fixture_id in self._locks:
            raise ValueError("locked forward prediction cannot be overwritten")
        self._locks[lock.fixture_id] = lock

    @property
    def locks(self) -> tuple[ForwardPredictionLock, ...]:
        return tuple(self._locks.values())


def validate_challenger_features(features: dict[str, Any]) -> None:
    assert_feature_allowlist(features)
    if not set(features).issubset(FEATURE_ALLOWLIST):
        raise ValueError("challenger features must be in the independent allowlist")


def stable_prediction_hash(probabilities: dict[str, float], config_hash: str) -> str:
    total = sum(probabilities.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError("probabilities must sum to one before locking")
    return artifact_hash({"probabilities": probabilities, "config_hash": config_hash})
