from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from w2.domain.time import require_utc
from w2.models.independent import artifact_hash


class ForwardDecision(StrEnum):
    NOT_READY = "NOT_READY"
    SKIP = "SKIP"
    WATCH = "WATCH"


@dataclass(frozen=True, kw_only=True)
class ForwardResultEvent:
    fixture_id: str
    provider: str
    confirmed_at: datetime
    raw_payload_hash: str
    home_goals_90: int | None
    away_goals_90: int | None
    extra_time: dict[str, int | None]
    penalties: dict[str, int | None]

    def __post_init__(self) -> None:
        object.__setattr__(self, "confirmed_at", require_utc(self.confirmed_at, "confirmed_at"))
        if len(self.raw_payload_hash) != 64:
            raise ValueError("raw payload hash must be sha256")

    def event_key(self) -> str:
        return artifact_hash(
            {
                "fixture_id": self.fixture_id,
                "provider": self.provider,
                "raw_payload_hash": self.raw_payload_hash,
            }
        )


@dataclass(frozen=True, kw_only=True)
class ForwardMarketSnapshot:
    fixture_id: str
    phase: str
    captured_at: datetime
    market_comparable: bool
    bookmaker_count: int
    quality: str
    power_probabilities: dict[str, float] | None
    raw_payload_hash: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))


class ForwardCycleLedger:
    def __init__(self) -> None:
        self.locks: dict[tuple[str, str], dict[str, Any]] = {}
        self.results: dict[str, ForwardResultEvent] = {}
        self.market_snapshots: dict[tuple[str, str], ForwardMarketSnapshot] = {}

    def lock_prediction(self, fixture_id: str, phase: str, payload: dict[str, Any]) -> None:
        key = (fixture_id, phase)
        if key in self.locks:
            return
        kickoff = require_utc(datetime.fromisoformat(payload["kickoff_utc"]), "kickoff_utc")
        locked_at = require_utc(datetime.fromisoformat(payload["locked_at"]), "locked_at")
        if locked_at >= kickoff:
            raise ValueError("cannot lock prediction after kickoff")
        if payload["decision"] not in {item.value for item in ForwardDecision}:
            raise ValueError("invalid forward decision")
        self.locks[key] = dict(payload)

    def append_result(self, result: ForwardResultEvent) -> None:
        self.results.setdefault(result.event_key(), result)

    def save_market_snapshot(self, snapshot: ForwardMarketSnapshot) -> None:
        key = (snapshot.fixture_id, snapshot.phase)
        if key in self.market_snapshots:
            return
        self.market_snapshots[key] = snapshot


def preregistered_evaluation_plan() -> dict[str, Any]:
    return {
        "primary_metrics": ["Log Loss", "RPS", "Brier", "ECE"],
        "market_comparison_fixture_eligibility": (
            "same fixture and phase with captured market snapshot"
        ),
        "bootstrap": {"method": "paired bootstrap", "samples": 1000, "seed": 7},
        "minimum_settled_sample": 50,
        "slice_stability": ["competition", "official_vs_friendly", "favorite_strength"],
        "optional_stopping": "forbidden before minimum settled sample and fixed audit cadence",
        "analysis_model_role": {
            "market_comparison_is_descriptive": True,
            "model_outputs_are_analysis_factors": True,
            "profit_edge_claim_disabled": True,
        },
    }


def gate4_from_power(settled_n: int, comparable_n: int, target_n: int) -> dict[str, Any]:
    remaining = max(target_n - settled_n, 0)
    information = settled_n / target_n if target_n else 0.0
    if settled_n < target_n or comparable_n < target_n:
        status = "PROVISIONAL_FORWARD_HOLDOUT_PENDING"
    else:
        status = "PROVISIONAL_ANALYSIS_FACTOR_READY"
    return {
        "current_settled_n": settled_n,
        "market_comparable_n": comparable_n,
        "target_n": target_n,
        "remaining_n": remaining,
        "estimated_information_status": round(information, 6),
        "GATE_4_NATIONAL_1X2": status,
        "GATE_4_AH": "BLOCKED_FORWARD_ONLY",
        "STAGE_9": "BLOCKED",
    }
