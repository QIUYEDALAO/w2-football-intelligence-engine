from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from w2.domain.time import require_utc


@dataclass(frozen=True, kw_only=True)
class Snapshot:
    source: str
    fixture_identity: str
    kickoff_utc: datetime
    odds_snapshot_age_seconds: int
    bookmaker_count: int
    one_x_two_home_probability: Decimal
    ou_mu: Decimal
    lambda_home: Decimal
    lambda_away: Decimal
    score_matrix_summary: str
    independent_home_probability: Decimal | None
    lifecycle_state: str
    data_latency_seconds: int
    runtime_errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_utc(self.kickoff_utc, "kickoff_utc")


@dataclass(frozen=True, kw_only=True)
class ShadowRunManifest:
    run_id: str
    created_at: datetime
    w1_source: str
    w2_source: str
    strategy_comparison_status: str
    runtime_network: bool = False
    live_prediction: bool = False

    def __post_init__(self) -> None:
        require_utc(self.created_at, "created_at")


@dataclass(frozen=True, kw_only=True)
class ShadowComparisonRecord:
    run_id: str
    fixture_identity: str
    identity_match: bool
    kickoff_delta_seconds: int
    probability_delta: Decimal
    mu_delta: Decimal
    lambda_home_delta: Decimal
    lambda_away_delta: Decimal
    odds_freshness_delta_seconds: int
    data_completeness_delta: int
    runtime_availability_delta: int
    strategy_comparison_status: str
    decision_output: str = "NOT_AVAILABLE_GATE4"


class W1SnapshotAdapter:
    def load_sample(self) -> Snapshot:
        return Snapshot(
            source="W1_FROZEN_OUTPUT_SAMPLE",
            fixture_identity="archived-fixture-001",
            kickoff_utc=datetime(2026, 7, 1, 18, 0, tzinfo=UTC),
            odds_snapshot_age_seconds=3600,
            bookmaker_count=4,
            one_x_two_home_probability=Decimal("0.42"),
            ou_mu=Decimal("2.45"),
            lambda_home=Decimal("1.35"),
            lambda_away=Decimal("1.10"),
            score_matrix_summary="top3:1-1,1-0,2-1",
            independent_home_probability=None,
            lifecycle_state="WATCH",
            data_latency_seconds=120,
        )


class W2SnapshotAdapter:
    def load_sample(self) -> Snapshot:
        return Snapshot(
            source="W2_ARCHIVED_OUTPUT_SAMPLE",
            fixture_identity="archived-fixture-001",
            kickoff_utc=datetime(2026, 7, 1, 18, 0, tzinfo=UTC),
            odds_snapshot_age_seconds=3300,
            bookmaker_count=5,
            one_x_two_home_probability=Decimal("0.40"),
            ou_mu=Decimal("2.50"),
            lambda_home=Decimal("1.33"),
            lambda_away=Decimal("1.17"),
            score_matrix_summary="top3:1-1,2-1,1-0",
            independent_home_probability=Decimal("0.39"),
            lifecycle_state="WATCH",
            data_latency_seconds=90,
        )


class ShadowComparisonEngine:
    def compare(
        self,
        *,
        manifest: ShadowRunManifest,
        w1_snapshot: Snapshot,
        w2_snapshot: Snapshot,
    ) -> dict[str, Any]:
        record = ShadowComparisonRecord(
            run_id=manifest.run_id,
            fixture_identity=w2_snapshot.fixture_identity,
            identity_match=w1_snapshot.fixture_identity == w2_snapshot.fixture_identity,
            kickoff_delta_seconds=int(
                (w2_snapshot.kickoff_utc - w1_snapshot.kickoff_utc).total_seconds()
            ),
            probability_delta=(
                w2_snapshot.one_x_two_home_probability
                - w1_snapshot.one_x_two_home_probability
            ),
            mu_delta=w2_snapshot.ou_mu - w1_snapshot.ou_mu,
            lambda_home_delta=w2_snapshot.lambda_home - w1_snapshot.lambda_home,
            lambda_away_delta=w2_snapshot.lambda_away - w1_snapshot.lambda_away,
            odds_freshness_delta_seconds=(
                w2_snapshot.odds_snapshot_age_seconds
                - w1_snapshot.odds_snapshot_age_seconds
            ),
            data_completeness_delta=w2_snapshot.bookmaker_count - w1_snapshot.bookmaker_count,
            runtime_availability_delta=(
                len(w2_snapshot.runtime_errors) - len(w1_snapshot.runtime_errors)
            ),
            strategy_comparison_status=manifest.strategy_comparison_status,
        )
        payload = {
            "manifest": manifest.__dict__,
            "record": record.__dict__,
            "deltas": {
                "identity_mismatch": not record.identity_match,
                "probability_delta": str(record.probability_delta),
                "mu_delta": str(record.mu_delta),
                "lambda_home_delta": str(record.lambda_home_delta),
                "lambda_away_delta": str(record.lambda_away_delta),
                "odds_freshness_delta_seconds": record.odds_freshness_delta_seconds,
                "data_completeness_delta": record.data_completeness_delta,
                "runtime_availability_delta": record.runtime_availability_delta,
            },
            "network_used": False,
            "real_prediction_run": False,
            "candidate_or_recommend_output": False,
        }
        payload["comparison_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()
        return payload
