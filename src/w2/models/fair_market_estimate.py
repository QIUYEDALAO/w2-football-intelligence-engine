from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import cast

from w2.domain.enums import SettlementOutcome
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.models.dixon_coles import tau_correction

MARKET_ASIAN_HANDICAP = "ASIAN_HANDICAP"
MARKET_TOTALS = "TOTALS"
STATUS_READY = "READY"
STATUS_INSUFFICIENT = "INSUFFICIENT"
STATUS_INVALID = "INVALID"


@dataclass(frozen=True, kw_only=True)
class FairMarketEstimate:
    market: str
    status: str
    model_family: str
    fair_line: float | None
    probabilities: Mapping[str, float]
    home_mu: float | None
    away_mu: float | None
    feature_as_of: str | None
    train_cutoff: str | None
    artifact_hash: str | None = None
    artifact_version: str | None = None
    fallback_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, kw_only=True)
class FairMarketEstimateSnapshot:
    estimate_id: str
    fixture_id: str
    market: str
    status: str
    fair_line: float | None
    probabilities: Mapping[str, float]
    home_mu: float | None
    away_mu: float | None
    input_context: Mapping[str, object]
    model_context: Mapping[str, object]
    integrity: Mapping[str, str]

    @classmethod
    def create(
        cls,
        *,
        fixture_id: str,
        estimate: FairMarketEstimate,
        odds_snapshot: Mapping[str, object],
        feature_snapshot: Mapping[str, object],
        created_at: str,
    ) -> FairMarketEstimateSnapshot:
        odds_payload = _canonical_mapping(odds_snapshot)
        feature_payload = _canonical_mapping(feature_snapshot)
        input_context: dict[str, object] = {
            "odds_snapshot_hash": canonical_estimate_hash(odds_payload),
            "feature_snapshot_hash": canonical_estimate_hash(feature_payload),
            "odds_snapshot": odds_payload,
            "feature_snapshot": feature_payload,
        }
        model_context: dict[str, object] = {
            "artifact_hash": estimate.artifact_hash,
            "artifact_version": estimate.artifact_version,
            "model_family": estimate.model_family,
            "train_cutoff": estimate.train_cutoff,
            "feature_as_of": estimate.feature_as_of,
        }
        payload = {
            "fixture_id": fixture_id,
            "market": estimate.market,
            "status": estimate.status,
            "fair_line": estimate.fair_line,
            "probabilities": dict(estimate.probabilities),
            "home_mu": estimate.home_mu,
            "away_mu": estimate.away_mu,
            "input_context": input_context,
            "model_context": model_context,
        }
        estimate_hash = canonical_estimate_hash(payload)
        return cls(
            estimate_id=f"fme_{estimate_hash}",
            fixture_id=fixture_id,
            market=estimate.market,
            status=estimate.status,
            fair_line=estimate.fair_line,
            probabilities=dict(estimate.probabilities),
            home_mu=estimate.home_mu,
            away_mu=estimate.away_mu,
            input_context=input_context,
            model_context=model_context,
            integrity={
                "estimate_hash": estimate_hash,
                "created_at": created_at,
            },
        )

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload.update(
            {
                "model_family": self.model_context.get("model_family"),
                "artifact_hash": self.model_context.get("artifact_hash"),
                "artifact_version": self.model_context.get("artifact_version"),
                "train_cutoff": self.model_context.get("train_cutoff"),
                "feature_as_of": self.model_context.get("feature_as_of"),
                "odds_snapshot_hash": self.input_context.get("odds_snapshot_hash"),
                "feature_snapshot_hash": self.input_context.get("feature_snapshot_hash"),
                "estimate_hash": self.integrity.get("estimate_hash"),
                "created_at": self.integrity.get("created_at"),
            }
        )
        return payload


def canonical_estimate_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def verify_estimate_snapshot(snapshot: Mapping[str, object]) -> bool:
    input_context = _mapping(snapshot.get("input_context"))
    model_context = _mapping(snapshot.get("model_context"))
    compatibility_fields = {
        "model_family": "model_family",
        "artifact_hash": "artifact_hash",
        "artifact_version": "artifact_version",
        "train_cutoff": "train_cutoff",
        "feature_as_of": "feature_as_of",
    }
    if any(
        snapshot.get(flat_key) != model_context.get(context_key)
        for flat_key, context_key in compatibility_fields.items()
    ):
        return False
    if snapshot.get("odds_snapshot_hash") != input_context.get("odds_snapshot_hash"):
        return False
    if snapshot.get("feature_snapshot_hash") != input_context.get("feature_snapshot_hash"):
        return False
    if input_context.get("odds_snapshot_hash") != canonical_estimate_hash(
        _mapping(input_context.get("odds_snapshot"))
    ):
        return False
    if input_context.get("feature_snapshot_hash") != canonical_estimate_hash(
        _mapping(input_context.get("feature_snapshot"))
    ):
        return False
    estimate_hash = str(
        _mapping(snapshot.get("integrity")).get("estimate_hash")
        or snapshot.get("estimate_hash")
        or ""
    )
    estimate_id = str(snapshot.get("estimate_id") or "")
    if not estimate_hash or estimate_id != f"fme_{estimate_hash}":
        return False
    payload = {
        "fixture_id": snapshot.get("fixture_id"),
        "market": snapshot.get("market"),
        "status": snapshot.get("status"),
        "fair_line": snapshot.get("fair_line"),
        "probabilities": dict(_mapping(snapshot.get("probabilities"))),
        "home_mu": snapshot.get("home_mu"),
        "away_mu": snapshot.get("away_mu"),
        "input_context": dict(input_context),
        "model_context": dict(model_context),
    }
    return canonical_estimate_hash(payload) == estimate_hash


def estimate_snapshots(card: Mapping[str, object]) -> list[Mapping[str, object]]:
    value = card.get("fair_market_estimate_snapshots")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    legacy = card.get("fair_market_estimates")
    if isinstance(legacy, list):
        return [item for item in legacy if isinstance(item, Mapping)]
    return []


def estimate_snapshot_by_id(
    card: Mapping[str, object],
    estimate_id: object,
) -> Mapping[str, object] | None:
    target = str(estimate_id or "")
    if not target:
        return None
    return next(
        (item for item in estimate_snapshots(card) if str(item.get("estimate_id") or "") == target),
        None,
    )


def estimate_snapshot_for_market(
    card: Mapping[str, object],
    market: str,
) -> Mapping[str, object] | None:
    ids = card.get("fair_market_estimate_ids")
    allowed_ids = (
        {str(item) for item in ids}
        if isinstance(ids, list | tuple)
        else set()
    )
    return next(
        (
            item
            for item in estimate_snapshots(card)
            if str(item.get("market") or "") == market
            and (not allowed_ids or str(item.get("estimate_id") or "") in allowed_ids)
        ),
        None,
    )


def _canonical_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(json.dumps(value, sort_keys=True, default=str)),
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def fair_lines_from_lambdas(
    *,
    home_mu: float,
    away_mu: float,
    rho: float = 0.0,
) -> tuple[float, float, dict[str, float], dict[str, float]]:
    matrix = score_distribution(home_mu=home_mu, away_mu=away_mu, rho=rho)
    fair_ah = _balanced_line(matrix, market=MARKET_ASIAN_HANDICAP)
    fair_ou = _balanced_line(matrix, market=MARKET_TOTALS)
    return (
        fair_ah,
        fair_ou,
        _outcome_probabilities(matrix, market=MARKET_ASIAN_HANDICAP, line=fair_ah),
        _outcome_probabilities(matrix, market=MARKET_TOTALS, line=fair_ou),
    )


def score_distribution(
    *,
    home_mu: float,
    away_mu: float,
    rho: float = 0.0,
    max_goals: int = 12,
) -> dict[tuple[int, int], float]:
    if home_mu <= 0 or away_mu <= 0:
        raise ValueError("goal lambdas must be positive")
    matrix: dict[tuple[int, int], float] = {}
    for home_goals in range(max_goals + 1):
        home_probability = _poisson(home_mu, home_goals)
        for away_goals in range(max_goals + 1):
            probability = home_probability * _poisson(away_mu, away_goals)
            probability *= tau_correction(home_goals, away_goals, home_mu, away_mu, rho)
            matrix[(home_goals, away_goals)] = max(probability, 0.0)
    total = sum(matrix.values())
    if total <= 0:
        raise ValueError("score distribution has no probability mass")
    return {score: probability / total for score, probability in matrix.items()}


def _balanced_line(matrix: Mapping[tuple[int, int], float], *, market: str) -> float:
    if market == MARKET_ASIAN_HANDICAP:
        candidates = [quarter / 4 for quarter in range(-16, 17)]
        selection = "HOME"
    elif market == MARKET_TOTALS:
        candidates = [quarter / 4 for quarter in range(2, 33)]
        selection = "OVER"
    else:
        raise ValueError(f"unsupported market: {market}")
    return min(
        candidates,
        key=lambda line: (
            abs(_expected_settlement_score(matrix, market=market, selection=selection, line=line)),
            abs(line),
            line,
        ),
    )


def _expected_settlement_score(
    matrix: Mapping[tuple[int, int], float],
    *,
    market: str,
    selection: str,
    line: float,
) -> float:
    total = 0.0
    decimal_line = Decimal(str(line))
    for (home_goals, away_goals), probability in matrix.items():
        if market == MARKET_ASIAN_HANDICAP:
            outcome = settle_asian_handicap(
                home_goals,
                away_goals,
                selection,
                decimal_line,
            )
        else:
            outcome = settle_total_goals(
                home_goals + away_goals,
                selection,
                decimal_line,
            )
        total += probability * _settlement_score(outcome)
    return total


def _outcome_probabilities(
    matrix: Mapping[tuple[int, int], float],
    *,
    market: str,
    line: float,
) -> dict[str, float]:
    selections = ("HOME", "AWAY") if market == MARKET_ASIAN_HANDICAP else ("OVER", "UNDER")
    probabilities: dict[str, float] = {}
    for selection in selections:
        expected = _expected_settlement_score(
            matrix,
            market=market,
            selection=selection,
            line=line,
        )
        probabilities[selection] = round((expected + 1.0) / 2.0, 8)
    return probabilities


def _settlement_score(outcome: SettlementOutcome) -> float:
    return {
        SettlementOutcome.WIN: 1.0,
        SettlementOutcome.HALF_WIN: 0.5,
        SettlementOutcome.PUSH: 0.0,
        SettlementOutcome.HALF_LOSS: -0.5,
        SettlementOutcome.LOSS: -1.0,
    }[outcome]


def _poisson(mu: float, goals: int) -> float:
    return math.exp(-mu) * mu**goals / math.factorial(goals)
