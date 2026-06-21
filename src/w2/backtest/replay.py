from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from w2.domain.time import require_utc


class ReplayEventType(StrEnum):
    FEATURE_BUILD = "FEATURE_BUILD"
    MODEL_LOAD = "MODEL_LOAD"
    PREDICTION = "PREDICTION"
    EVALUATION = "EVALUATION"


class ReplayDecision(StrEnum):
    NOT_READY = "NOT_READY"
    SKIP = "SKIP"
    WATCH = "WATCH"


@dataclass(frozen=True, kw_only=True)
class ReplayEvent:
    event_id: str
    fixture_id: str
    event_time: datetime
    event_type: ReplayEventType
    sequence: int
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_time", require_utc(self.event_time, "event_time"))


class EventOrderingPolicy:
    def order(self, events: list[ReplayEvent]) -> list[ReplayEvent]:
        return sorted(
            events,
            key=lambda event: (
                event.event_time,
                event.sequence,
                event.fixture_id,
                event.event_type.value,
                event.event_id,
            ),
        )


@dataclass(frozen=True, kw_only=True)
class ReplayManifest:
    replay_id: str
    dataset_version: str
    model_version: str
    calibration_version: str
    event_count: int
    input_sha256: str

    def stable_hash(self) -> str:
        return stable_hash(self.__dict__)


@dataclass(frozen=True, kw_only=True)
class ReplayCheckpoint:
    replay_id: str
    last_event_id: str | None
    ledger_hash: str
    processed_events: int


class ReplayClock:
    def __init__(self, start_time: datetime) -> None:
        self.current_time = require_utc(start_time, "start_time")

    def advance_to(self, event_time: datetime) -> None:
        next_time = require_utc(event_time, "event_time")
        if next_time < self.current_time:
            raise ValueError("replay clock cannot move backwards")
        self.current_time = next_time


class AsOfDataRepository:
    def __init__(self, rows: dict[str, dict[str, Any]]) -> None:
        self.rows = rows

    def read_as_of(self, fixture_id: str, as_of_time: datetime) -> dict[str, Any]:
        as_of = require_utc(as_of_time, "as_of_time")
        row = self.rows[fixture_id]
        kickoff = require_utc(datetime.fromisoformat(row["kickoff_utc"]), "kickoff_utc")
        if as_of > kickoff:
            raise ValueError("future data requested after kickoff")
        if row.get("snapshot_semantics") == "CLOSING" and row.get("prediction_phase") != "CLOSING":
            raise ValueError("closing odds cannot enter an early prediction phase")
        return dict(row)


class ReplayLedger:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}

    def append_once(self, event: ReplayEvent, record: dict[str, Any]) -> None:
        if event.event_id in self.records:
            return
        self.records[event.event_id] = {
            "event_id": event.event_id,
            "fixture_id": event.fixture_id,
            "event_type": event.event_type.value,
            "event_time": event.event_time.isoformat(),
            "record": record,
            "record_hash": stable_hash(record),
        }

    def hash(self) -> str:
        return stable_hash(list(self.records.values()))


class FeatureBuildStep:
    def run(self, row: dict[str, Any]) -> dict[str, Any]:
        forbidden = {"home_goals", "away_goals", "result", "settlement"}
        if forbidden & set(row.get("features", {})):
            raise ValueError("future result leakage in feature payload")
        features = row.get("features", {})
        return {"features": features, "feature_hash": stable_hash(features)}


class ModelLoadStep:
    def run(self, *, model_version: str, expected_version: str) -> dict[str, Any]:
        if model_version != expected_version:
            raise ValueError("model artifact version mismatch")
        return {"model_version": model_version, "loaded": True}


class PredictionStep:
    def run(self, probabilities: dict[str, float]) -> dict[str, Any]:
        total = sum(probabilities.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError("prediction probabilities must sum to one")
        payload = {"probabilities": probabilities, "decision": ReplayDecision.WATCH.value}
        return {**payload, "prediction_hash": stable_hash(payload)}


class EvaluationStep:
    def run(self, probabilities: dict[str, float], actual: str) -> dict[str, Any]:
        loss = -__import__("math").log(max(probabilities[actual], 1e-12))
        return {"actual": actual, "log_loss": loss}


def stable_hash(payload: object) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chronological_holdout(fixtures: list[str]) -> dict[str, set[str]]:
    return _three_way(fixtures)


def rolling_window(
    fixtures: list[str],
    *,
    train_size: int,
    test_size: int,
) -> list[dict[str, set[str]]]:
    output: list[dict[str, set[str]]] = []
    for start in range(0, max(len(fixtures) - train_size - test_size + 1, 0), test_size):
        output.append(
            {
                "train": set(fixtures[start : start + train_size]),
                "test": set(fixtures[start + train_size : start + train_size + test_size]),
            }
        )
    return output


def expanding_window(
    fixtures: list[str],
    *,
    min_train_size: int,
    test_size: int,
) -> list[dict[str, set[str]]]:
    output: list[dict[str, set[str]]] = []
    for end in range(min_train_size, len(fixtures), test_size):
        output.append({"train": set(fixtures[:end]), "test": set(fixtures[end : end + test_size])})
    return output


def walk_forward(
    fixtures: list[str],
    *,
    initial_train_size: int,
    step_size: int,
) -> list[dict[str, set[str]]]:
    return expanding_window(fixtures, min_train_size=initial_train_size, test_size=step_size)


def season_based_future_test(fixtures_by_season: dict[str, list[str]]) -> dict[str, set[str]]:
    seasons = sorted(fixtures_by_season)
    if len(seasons) < 2:
        return {"train": set(), "test": set()}
    return {
        "train": {fixture for season in seasons[:-1] for fixture in fixtures_by_season[season]},
        "test": set(fixtures_by_season[seasons[-1]]),
    }


def nested_walk_forward(fixtures: list[str]) -> dict[str, Any]:
    outer = walk_forward(
        fixtures,
        initial_train_size=max(len(fixtures) // 2, 1),
        step_size=max(len(fixtures) // 10, 1),
    )
    return {"outer_folds": len(outer), "inner_selection": "validation_only"}


def assert_fixture_split_integrity(
    snapshot_to_fixture: dict[str, str],
    split_by_snapshot: dict[str, str],
) -> None:
    fixture_splits: dict[str, str] = {}
    for snapshot_id, fixture_id in snapshot_to_fixture.items():
        split = split_by_snapshot[snapshot_id]
        previous = fixture_splits.setdefault(fixture_id, split)
        if previous != split:
            raise ValueError("same fixture snapshots crossed splits")


def _three_way(fixtures: list[str]) -> dict[str, set[str]]:
    train_end = int(len(fixtures) * 0.60)
    validation_end = int(len(fixtures) * 0.80)
    return {
        "train": set(fixtures[:train_end]),
        "validation": set(fixtures[train_end:validation_end]),
        "test": set(fixtures[validation_end:]),
    }
