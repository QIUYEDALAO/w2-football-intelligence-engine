from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import cast

from w2.domain.enums import SettlementOutcome
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.models.dixon_coles import tau_correction

MARKET_ASIAN_HANDICAP = "ASIAN_HANDICAP"
MARKET_TOTALS = "TOTALS"
STATUS_READY = "READY"
STATUS_INSUFFICIENT = "INSUFFICIENT"
STATUS_INVALID = "INVALID"
SNAPSHOT_SCHEMA_V2 = "w2.fme_snapshot.v2"
SEMANTIC_VERIFIED = "VERIFIED"
LEGACY_SEMANTIC_STATUS = "LEGACY_DISTRIBUTION_CONTEXT_UNVERIFIED"
MAX_GOALS = 12
PROBABILITY_QUANTUM = Decimal("0.000000000001")
EFFECTIVE_COVER_INDEX_SEMANTICS = (
    "WIN_1_HALF_WIN_0.75_PUSH_0.5_HALF_LOSS_0.25_LOSS_0"
)


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
    artifact_id: str | None = None
    artifact_hash: str | None = None
    artifact_version: str | None = None
    fallback_reason: str | None = None
    dixon_coles_rho: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class _CanonicalScoreDistribution:
    matrix: Mapping[str, float]
    mass_before_normalization: str


@dataclass(frozen=True, kw_only=True)
class FairMarketEstimateSnapshot:
    schema_version: str
    estimate_id: str
    model_basis_id: str
    fixture_id: str
    market: str
    status: str
    fallback_reason: str | None
    fair_line: float | None
    probabilities: Mapping[str, float]
    home_mu: float | None
    away_mu: float | None
    score_matrix: Mapping[str, float]
    distribution_context: Mapping[str, object]
    model_one_x_two_probabilities: Mapping[str, float]
    model_fair_ah: float | None
    model_fair_ou: float | None
    model_score_distribution: Mapping[str, float]
    model_settlement_distributions: Mapping[str, object]
    effective_cover_index: Mapping[str, object]
    effective_cover_index_semantics: str
    semantic_status: str
    evidence_eligible: bool
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
        input_context["input_source_hash"] = canonical_estimate_hash(
            {
                "odds_snapshot_hash": input_context["odds_snapshot_hash"],
                "feature_snapshot_hash": input_context["feature_snapshot_hash"],
            }
        )
        model_context: dict[str, object] = {
            "artifact_id": estimate.artifact_id,
            "artifact_hash": estimate.artifact_hash,
            "artifact_version": estimate.artifact_version,
            "model_family": estimate.model_family,
            "train_cutoff": estimate.train_cutoff,
            "feature_as_of": estimate.feature_as_of,
            "dixon_coles_rho": estimate.dixon_coles_rho,
        }
        matrix_result = (
            _canonical_score_distribution(
                home_mu=estimate.home_mu,
                away_mu=estimate.away_mu,
                rho=estimate.dixon_coles_rho,
            )
            if estimate.home_mu is not None
            and estimate.home_mu > 0
            and estimate.away_mu is not None
            and estimate.away_mu > 0
            else None
        )
        score_matrix = dict(matrix_result.matrix) if matrix_result is not None else {}
        numeric_matrix = _score_matrix_from_flat(score_matrix) or {}
        fair_ah = (
            _balanced_line(numeric_matrix, market=MARKET_ASIAN_HANDICAP)
            if numeric_matrix
            else None
        )
        fair_ou = _balanced_line(numeric_matrix, market=MARKET_TOTALS) if numeric_matrix else None
        model_one_x_two = _one_x_two_probabilities(numeric_matrix) if numeric_matrix else {}
        settlement_distributions = (
            _model_settlement_distributions(
                numeric_matrix,
                fair_ah=fair_ah,
                fair_ou=fair_ou,
                quote_lines=_quote_lines(odds_payload),
            )
            if numeric_matrix
            else {}
        )
        effective_cover_index = _effective_cover_indices(settlement_distributions)
        fair_line = fair_ah if estimate.market == MARKET_ASIAN_HANDICAP else fair_ou
        market_cover_index = effective_cover_index.get(estimate.market)
        probabilities = dict(market_cover_index) if isinstance(market_cover_index, Mapping) else {}
        distribution_context = _distribution_context(
            rho=estimate.dixon_coles_rho,
            matrix_mass_before_normalization=(
                matrix_result.mass_before_normalization if matrix_result is not None else None
            ),
            score_matrix=score_matrix,
        )
        model_fair_lines = {
            "model_fair_ah": fair_ah,
            "model_fair_ou": fair_ou,
        }
        model_basis_payload = {
            "fixture_id": fixture_id,
            "market": estimate.market,
            "feature_snapshot_hash": input_context["feature_snapshot_hash"],
            "artifact_context": model_context,
            "distribution_context": distribution_context,
            "model_score_distribution": score_matrix,
            **model_fair_lines,
        }
        model_basis_id = f"fmb_{canonical_estimate_hash(model_basis_payload)}"
        semantic_status = SEMANTIC_VERIFIED if numeric_matrix else "INSUFFICIENT"
        evidence_eligible = semantic_status == SEMANTIC_VERIFIED
        payload = {
            "schema_version": SNAPSHOT_SCHEMA_V2,
            "model_basis_id": model_basis_id,
            "fixture_id": fixture_id,
            "market": estimate.market,
            "status": estimate.status,
            "fallback_reason": estimate.fallback_reason,
            "fair_line": fair_line,
            "probabilities": probabilities,
            "home_mu": estimate.home_mu,
            "away_mu": estimate.away_mu,
            "score_matrix": score_matrix,
            "distribution_context": distribution_context,
            "model_one_x_two_probabilities": model_one_x_two,
            **model_fair_lines,
            "model_score_distribution": score_matrix,
            "model_settlement_distributions": settlement_distributions,
            "effective_cover_index": effective_cover_index,
            "effective_cover_index_semantics": EFFECTIVE_COVER_INDEX_SEMANTICS,
            "semantic_status": semantic_status,
            "evidence_eligible": evidence_eligible,
            "input_context": input_context,
            "model_context": model_context,
        }
        estimate_hash = canonical_estimate_hash(payload)
        return cls(
            schema_version=SNAPSHOT_SCHEMA_V2,
            estimate_id=f"fme_{estimate_hash}",
            model_basis_id=model_basis_id,
            fixture_id=fixture_id,
            market=estimate.market,
            status=estimate.status,
            fallback_reason=estimate.fallback_reason,
            fair_line=fair_line,
            probabilities=probabilities,
            home_mu=estimate.home_mu,
            away_mu=estimate.away_mu,
            score_matrix=score_matrix,
            distribution_context=distribution_context,
            model_one_x_two_probabilities=model_one_x_two,
            model_fair_ah=fair_ah,
            model_fair_ou=fair_ou,
            model_score_distribution=score_matrix,
            model_settlement_distributions=settlement_distributions,
            effective_cover_index=effective_cover_index,
            effective_cover_index_semantics=EFFECTIVE_COVER_INDEX_SEMANTICS,
            semantic_status=semantic_status,
            evidence_eligible=evidence_eligible,
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
                "dixon_coles_rho": self.model_context.get("dixon_coles_rho"),
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
    if snapshot.get("schema_version") == SNAPSHOT_SCHEMA_V2:
        compatibility_fields["dixon_coles_rho"] = "dixon_coles_rho"
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
    if snapshot.get("schema_version") == SNAPSHOT_SCHEMA_V2:
        payload = _v2_snapshot_payload(snapshot, input_context, model_context)
        return canonical_estimate_hash(payload) == estimate_hash
    payload = {
        "fixture_id": snapshot.get("fixture_id"),
        "market": snapshot.get("market"),
        "status": snapshot.get("status"),
        "fair_line": snapshot.get("fair_line"),
        "probabilities": dict(_mapping(snapshot.get("probabilities"))),
        "home_mu": snapshot.get("home_mu"),
        "away_mu": snapshot.get("away_mu"),
        "score_matrix": dict(_mapping(snapshot.get("score_matrix"))),
        "input_context": dict(input_context),
        "model_context": dict(model_context),
    }
    # Snapshots created before fallback_reason became part of the immutable
    # estimate remain verifiable with their original content identity.
    if "fallback_reason" in snapshot:
        payload["fallback_reason"] = snapshot.get("fallback_reason")
    return canonical_estimate_hash(payload) == estimate_hash


def verify_estimate_semantics(snapshot: Mapping[str, object]) -> bool:
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_V2:
        return False
    if not verify_estimate_snapshot(snapshot):
        return False
    home_mu = _number(snapshot.get("home_mu"))
    away_mu = _number(snapshot.get("away_mu"))
    model_context = _mapping(snapshot.get("model_context"))
    rho = _number(model_context.get("dixon_coles_rho"))
    if home_mu is None or home_mu <= 0 or away_mu is None or away_mu <= 0 or rho is None:
        return False
    result = _canonical_score_distribution(home_mu=home_mu, away_mu=away_mu, rho=rho)
    score_matrix = dict(result.matrix)
    if dict(_mapping(snapshot.get("model_score_distribution"))) != score_matrix:
        return False
    if dict(_mapping(snapshot.get("score_matrix"))) != score_matrix:
        return False
    numeric_matrix = _score_matrix_from_flat(score_matrix)
    if numeric_matrix is None:
        return False
    fair_ah = _balanced_line(numeric_matrix, market=MARKET_ASIAN_HANDICAP)
    fair_ou = _balanced_line(numeric_matrix, market=MARKET_TOTALS)
    if snapshot.get("model_fair_ah") != fair_ah or snapshot.get("model_fair_ou") != fair_ou:
        return False
    expected_fair_line = fair_ah if snapshot.get("market") == MARKET_ASIAN_HANDICAP else fair_ou
    if snapshot.get("fair_line") != expected_fair_line:
        return False
    distribution_context = _distribution_context(
        rho=rho,
        matrix_mass_before_normalization=result.mass_before_normalization,
        score_matrix=score_matrix,
    )
    if dict(_mapping(snapshot.get("distribution_context"))) != distribution_context:
        return False
    if dict(_mapping(snapshot.get("model_one_x_two_probabilities"))) != (
        _one_x_two_probabilities(numeric_matrix)
    ):
        return False
    input_context = _mapping(snapshot.get("input_context"))
    settlements = _model_settlement_distributions(
        numeric_matrix,
        fair_ah=fair_ah,
        fair_ou=fair_ou,
        quote_lines=_quote_lines(_mapping(input_context.get("odds_snapshot"))),
    )
    if dict(_mapping(snapshot.get("model_settlement_distributions"))) != settlements:
        return False
    cover_indices = _effective_cover_indices(settlements)
    if dict(_mapping(snapshot.get("effective_cover_index"))) != cover_indices:
        return False
    market_cover = cover_indices.get(str(snapshot.get("market")), {})
    if dict(_mapping(snapshot.get("probabilities"))) != market_cover:
        return False
    model_basis_payload = {
        "fixture_id": snapshot.get("fixture_id"),
        "market": snapshot.get("market"),
        "feature_snapshot_hash": input_context.get("feature_snapshot_hash"),
        "artifact_context": dict(model_context),
        "distribution_context": distribution_context,
        "model_score_distribution": score_matrix,
        "model_fair_ah": fair_ah,
        "model_fair_ou": fair_ou,
    }
    if snapshot.get("model_basis_id") != f"fmb_{canonical_estimate_hash(model_basis_payload)}":
        return False
    return (
        snapshot.get("semantic_status") == SEMANTIC_VERIFIED
        and snapshot.get("evidence_eligible") is True
        and snapshot.get("effective_cover_index_semantics")
        == EFFECTIVE_COVER_INDEX_SEMANTICS
    )


def estimate_semantic_status(snapshot: Mapping[str, object]) -> str:
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_V2:
        return LEGACY_SEMANTIC_STATUS
    return SEMANTIC_VERIFIED if verify_estimate_semantics(snapshot) else "INVALID"


def _v2_snapshot_payload(
    snapshot: Mapping[str, object],
    input_context: Mapping[str, object],
    model_context: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_version": snapshot.get("schema_version"),
        "model_basis_id": snapshot.get("model_basis_id"),
        "fixture_id": snapshot.get("fixture_id"),
        "market": snapshot.get("market"),
        "status": snapshot.get("status"),
        "fallback_reason": snapshot.get("fallback_reason"),
        "fair_line": snapshot.get("fair_line"),
        "probabilities": dict(_mapping(snapshot.get("probabilities"))),
        "home_mu": snapshot.get("home_mu"),
        "away_mu": snapshot.get("away_mu"),
        "score_matrix": dict(_mapping(snapshot.get("score_matrix"))),
        "distribution_context": dict(_mapping(snapshot.get("distribution_context"))),
        "model_one_x_two_probabilities": dict(
            _mapping(snapshot.get("model_one_x_two_probabilities"))
        ),
        "model_fair_ah": snapshot.get("model_fair_ah"),
        "model_fair_ou": snapshot.get("model_fair_ou"),
        "model_score_distribution": dict(
            _mapping(snapshot.get("model_score_distribution"))
        ),
        "model_settlement_distributions": dict(
            _mapping(snapshot.get("model_settlement_distributions"))
        ),
        "effective_cover_index": dict(_mapping(snapshot.get("effective_cover_index"))),
        "effective_cover_index_semantics": snapshot.get(
            "effective_cover_index_semantics"
        ),
        "semantic_status": snapshot.get("semantic_status"),
        "evidence_eligible": snapshot.get("evidence_eligible"),
        "input_context": dict(input_context),
        "model_context": dict(model_context),
    }


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


def snapshot_score_matrix(
    snapshot: Mapping[str, object],
) -> dict[tuple[int, int], float] | None:
    value = snapshot.get("score_matrix")
    if not isinstance(value, Mapping):
        return None
    matrix: dict[tuple[int, int], float] = {}
    for key, raw_probability in value.items():
        parts = str(key).split("-", maxsplit=1)
        if len(parts) != 2 or not isinstance(raw_probability, int | float):
            return None
        try:
            score = (int(parts[0]), int(parts[1]))
        except ValueError:
            return None
        matrix[score] = float(raw_probability)
    if not matrix or abs(sum(matrix.values()) - 1.0) > 1e-8:
        return None
    return matrix


def _canonical_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(json.dumps(value, sort_keys=True, default=str)),
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _number(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _canonical_score_distribution(
    *,
    home_mu: float,
    away_mu: float,
    rho: float,
) -> _CanonicalScoreDistribution:
    raw: dict[str, float] = {}
    for home_goals in range(MAX_GOALS + 1):
        home_probability = _poisson(home_mu, home_goals)
        for away_goals in range(MAX_GOALS + 1):
            probability = home_probability * _poisson(away_mu, away_goals)
            probability *= tau_correction(home_goals, away_goals, home_mu, away_mu, rho)
            raw[f"{home_goals}-{away_goals}"] = max(probability, 0.0)
    total = sum(raw.values())
    if total <= 0:
        raise ValueError("score distribution has no probability mass")
    normalized = {
        score: Decimal(str(probability / total)).quantize(
            PROBABILITY_QUANTUM,
            rounding=ROUND_HALF_EVEN,
        )
        for score, probability in raw.items()
    }
    residual = Decimal("1") - sum(normalized.values(), Decimal("0"))
    residual_cell = min(normalized, key=lambda score: (-normalized[score], score))
    normalized[residual_cell] += residual
    matrix = {score: float(probability) for score, probability in normalized.items()}
    mass = Decimal(str(total)).quantize(PROBABILITY_QUANTUM, rounding=ROUND_HALF_EVEN)
    return _CanonicalScoreDistribution(
        matrix=matrix,
        mass_before_normalization=format(mass, "f"),
    )


def _score_matrix_from_flat(
    value: Mapping[str, object],
) -> dict[tuple[int, int], float] | None:
    matrix: dict[tuple[int, int], float] = {}
    for key, raw_probability in value.items():
        parts = str(key).split("-", maxsplit=1)
        probability = _number(raw_probability)
        if len(parts) != 2 or probability is None:
            return None
        try:
            matrix[(int(parts[0]), int(parts[1]))] = probability
        except ValueError:
            return None
    if not matrix or abs(sum(matrix.values()) - 1.0) > 1e-8:
        return None
    return matrix


def _distribution_context(
    *,
    rho: float,
    matrix_mass_before_normalization: str | None,
    score_matrix: Mapping[str, float],
) -> dict[str, object]:
    return {
        "distribution_family": "DIXON_COLES_POISSON",
        "dixon_coles_rho": format(Decimal(str(rho)), "f"),
        "max_goals": MAX_GOALS,
        "tail_policy": "TRUNCATE_AND_RENORMALIZE",
        "matrix_mass_before_normalization": matrix_mass_before_normalization,
        "probability_quantization": "DECIMAL_12_HALF_EVEN",
        "negative_tau_policy": "CLAMP_CELL_TO_ZERO",
        "normalization_residual_policy": (
            "ADD_TO_MAX_PROBABILITY_CELL_TIE_LEXICOGRAPHIC"
        ),
        "fair_line_candidate_grid_ah": {
            "minimum": -4.0,
            "maximum": 4.0,
            "step": 0.25,
        },
        "fair_line_candidate_grid_totals": {
            "minimum": 0.5,
            "maximum": 8.0,
            "step": 0.25,
        },
        "fair_line_tie_break_policy": (
            "MIN_EXPECTED_SETTLEMENT_ABS_THEN_MIN_ABS_LINE_THEN_NUMERIC_LINE"
        ),
        "settlement_rules_version": "w2.asian_settlement.v1",
        "fair_line_rules_version": "w2.fair_line.v2",
        "score_matrix_hash": canonical_estimate_hash(dict(score_matrix)),
    }


def _one_x_two_probabilities(
    matrix: Mapping[tuple[int, int], float],
) -> dict[str, float]:
    return _quantized_probabilities(
        {
            "HOME": sum(value for (home, away), value in matrix.items() if home > away),
            "DRAW": sum(value for (home, away), value in matrix.items() if home == away),
            "AWAY": sum(value for (home, away), value in matrix.items() if home < away),
        }
    )


def _quote_lines(odds_snapshot: Mapping[str, object]) -> dict[str, float | None]:
    ah = _mapping(odds_snapshot.get("ah"))
    totals = _mapping(odds_snapshot.get("ou"))
    ah_line = ah.get("home_line") if ah.get("home_line") is not None else ah.get("line")
    return {
        MARKET_ASIAN_HANDICAP: _number(ah_line),
        MARKET_TOTALS: _number(totals.get("line")),
    }


def _model_settlement_distributions(
    matrix: Mapping[tuple[int, int], float],
    *,
    fair_ah: float | None,
    fair_ou: float | None,
    quote_lines: Mapping[str, float | None],
) -> dict[str, object]:
    output: dict[str, object] = {}
    for market, fair_line, selections in (
        (MARKET_ASIAN_HANDICAP, fair_ah, ("HOME", "AWAY")),
        (MARKET_TOTALS, fair_ou, ("OVER", "UNDER")),
    ):
        quote_line = quote_lines.get(market)
        output[market] = {
            "fair_line": fair_line,
            "at_fair_line": {
                selection: _settlement_distribution(
                    matrix,
                    market=market,
                    selection=selection,
                    line=fair_line,
                )
                for selection in selections
                if fair_line is not None
            },
            "quote_line": quote_line,
            "at_quote_line": {
                selection: _settlement_distribution(
                    matrix,
                    market=market,
                    selection=selection,
                    line=quote_line,
                )
                for selection in selections
                if quote_line is not None
            },
        }
    return output


def _settlement_distribution(
    matrix: Mapping[tuple[int, int], float],
    *,
    market: str,
    selection: str,
    line: float,
) -> dict[str, float]:
    buckets = {outcome.value: 0.0 for outcome in SettlementOutcome}
    selection_line = -line if market == MARKET_ASIAN_HANDICAP and selection == "AWAY" else line
    decimal_line = Decimal(str(selection_line))
    for (home_goals, away_goals), probability in matrix.items():
        outcome = (
            settle_asian_handicap(
                home_goals,
                away_goals,
                selection,
                decimal_line,
            )
            if market == MARKET_ASIAN_HANDICAP
            else settle_total_goals(home_goals + away_goals, selection, decimal_line)
        )
        buckets[outcome.value] += probability
    return _quantized_probabilities(buckets)


def _quantized_probabilities(values: Mapping[str, float]) -> dict[str, float]:
    quantized = {
        key: Decimal(str(value)).quantize(PROBABILITY_QUANTUM, rounding=ROUND_HALF_EVEN)
        for key, value in values.items()
    }
    residual = Decimal("1") - sum(quantized.values(), Decimal("0"))
    residual_key = min(quantized, key=lambda key: (-quantized[key], key))
    quantized[residual_key] += residual
    return {key: float(value) for key, value in quantized.items()}


def _effective_cover_indices(
    settlement_distributions: Mapping[str, object],
) -> dict[str, object]:
    output: dict[str, object] = {}
    for market, payload in settlement_distributions.items():
        at_fair_line = _mapping(_mapping(payload).get("at_fair_line"))
        output[market] = {
            selection: _effective_cover_index(_mapping(distribution))
            for selection, distribution in at_fair_line.items()
        }
    return output


def _effective_cover_index(distribution: Mapping[str, object]) -> float:
    value = (
        (_number(distribution.get("WIN")) or 0.0)
        + 0.75 * (_number(distribution.get("HALF_WIN")) or 0.0)
        + 0.5 * (_number(distribution.get("PUSH")) or 0.0)
        + 0.25 * (_number(distribution.get("HALF_LOSS")) or 0.0)
    )
    return float(Decimal(str(value)).quantize(PROBABILITY_QUANTUM, rounding=ROUND_HALF_EVEN))


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
) -> Decimal:
    total = Decimal("0")
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
        total += Decimal(str(probability)) * _settlement_score(outcome)
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
        selection_line = (
            -line if market == MARKET_ASIAN_HANDICAP and selection == "AWAY" else line
        )
        expected = _expected_settlement_score(
            matrix,
            market=market,
            selection=selection,
            line=selection_line,
        )
        probabilities[selection] = round(float((expected + Decimal("1")) / Decimal("2")), 8)
    return probabilities


def _settlement_score(outcome: SettlementOutcome) -> Decimal:
    return {
        SettlementOutcome.WIN: Decimal("1"),
        SettlementOutcome.HALF_WIN: Decimal("0.5"),
        SettlementOutcome.PUSH: Decimal("0"),
        SettlementOutcome.HALF_LOSS: Decimal("-0.5"),
        SettlementOutcome.LOSS: Decimal("-1"),
    }[outcome]


def _poisson(mu: float, goals: int) -> float:
    return math.exp(-mu) * mu**goals / math.factorial(goals)
