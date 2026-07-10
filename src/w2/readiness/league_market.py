from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from w2.competitions.registry import CompetitionRegistry
from w2.models.r4_1_artifacts import load_r4_1_artifacts

MARKETS = ("ASIAN_HANDICAP", "TOTALS")
READINESS_SOURCE = "w2.readiness.league_market.v1"
ReadinessStatus = Literal[
    "BLOCKED",
    "TECHNICALLY_READY",
    "ACCUMULATING",
    "ELIGIBLE_FOR_REVIEW",
]


@dataclass(frozen=True, kw_only=True)
class LeagueMarketReadiness:
    competition_id: str
    market: str
    status: ReadinessStatus
    fixture_coverage: bool
    xg_numeric_match_count: int
    statistics_response_count: int
    rolling_feature_team_count: int
    elo_team_count: int
    squad_value_team_count: int
    rest_days_team_count: int
    lineup_status: str
    pinnacle_line_count: int
    artifact_present: bool
    artifact_hash: str | None
    artifact_version: str | None
    train_cutoff: str | None
    feature_parity: str
    model_market_gap: float | None
    shadow_closing_pair_count: int
    entry_window_rate: float | None
    closing_pair_coverage_rate: float | None
    outcome_coverage_rate: float | None
    median_same_line_decimal_clv: float | None
    blockers: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.__dict__,
            "blockers": list(self.blockers),
        }


def build_league_market_readiness(
    *,
    evidence_path: Path | None = None,
    artifact_dir: Path = Path("runtime/model_artifacts/r4_1"),
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    evidence = _load_evidence(evidence_path)
    league_evidence = _mapping(evidence.get("leagues"))
    artifacts = load_r4_1_artifacts(artifact_dir, now=current)
    rows: list[dict[str, Any]] = []
    for competition_id in CompetitionRegistry().entries():
        common = _mapping(league_evidence.get(competition_id))
        markets = _mapping(common.get("markets"))
        for market in MARKETS:
            row = _build_row(
                competition_id=competition_id,
                market=market,
                common=common,
                market_evidence=_mapping(markets.get(market)),
                artifact=artifacts.artifacts.get(competition_id),
                artifact_invalid_reason=artifacts.invalid_reasons.get(competition_id),
            )
            rows.append(row.as_dict())
    return {
        "source": READINESS_SOURCE,
        "generated_at_utc": current.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "evidence_source": str(evidence_path) if evidence_path else None,
        "evidence_generated_at_utc": evidence.get("generated_at_utc"),
        "evidence_source_sha": evidence.get("source_sha"),
        "active_competition_count": len(CompetitionRegistry().entries()),
        "market_count": len(rows),
        "status_counts": _status_counts(rows),
        "rows": rows,
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
        "direction_allowed_changes": [],
    }


def _build_row(
    *,
    competition_id: str,
    market: str,
    common: Mapping[str, Any],
    market_evidence: Mapping[str, Any],
    artifact: Any,
    artifact_invalid_reason: str | None,
) -> LeagueMarketReadiness:
    artifact_present = artifact is not None or _bool(common.get("validated_model"))
    artifact_hash = (
        str(getattr(artifact, "artifact_hash", "") or common.get("artifact_hash") or "") or None
    )
    artifact_version = (
        str(getattr(artifact, "artifact_version", "") or common.get("artifact_version") or "")
        or None
    )
    cutoff_value = getattr(artifact, "train_cutoff_utc", None) or common.get("train_cutoff")
    train_cutoff = _timestamp(cutoff_value)
    feature_parity = str(common.get("feature_parity") or "MISSING")
    gap = _float(market_evidence.get("model_market_gap"))
    fixture_coverage = _bool(common.get("fixture_coverage"))
    xg_numeric_match_count = _int(common.get("xg_numeric_match_count"))
    rolling_feature_team_count = _int(common.get("rolling_feature_team_count"))
    pinnacle_line_count = _int(market_evidence.get("pinnacle_line_count"))
    shadow_pairs = _int(market_evidence.get("shadow_closing_pair_count"))
    entry_rate = _float(market_evidence.get("entry_window_rate"))
    closing_rate = _float(market_evidence.get("closing_pair_coverage_rate"))
    outcome_rate = _float(market_evidence.get("outcome_coverage_rate"))
    clv = _float(market_evidence.get("median_same_line_decimal_clv"))
    blockers: list[str] = []
    if not fixture_coverage:
        blockers.append("FIXTURE_COVERAGE_MISSING")
    if rolling_feature_team_count <= 0:
        blockers.append("ROLLING_FEATURES_MISSING")
    if pinnacle_line_count <= 0:
        blockers.append("PINNACLE_MARKET_MISSING")
    if not artifact_present:
        blockers.append(artifact_invalid_reason or "VALIDATED_MODEL_ARTIFACT_MISSING")
    if train_cutoff is None:
        blockers.append("TRAIN_CUTOFF_MISSING")
    if feature_parity != "PASS":
        blockers.append("FEATURE_PARITY_NOT_PROVEN")
    if gap is None:
        blockers.append("MODEL_MARKET_GAP_MISSING")
    elif gap > 0.04:
        blockers.append("MODEL_MARKET_GAP_ABOVE_0_04")
    technical_ready = not blockers
    gate_ready = (
        shadow_pairs >= 100
        and clv is not None
        and clv > 0
        and entry_rate is not None
        and entry_rate >= 0.8
        and closing_rate is not None
        and closing_rate >= 0.8
        and outcome_rate is not None
        and outcome_rate >= 0.9
    )
    if not technical_ready:
        status: ReadinessStatus = "BLOCKED"
    elif gate_ready:
        status = "ELIGIBLE_FOR_REVIEW"
    elif shadow_pairs > 0:
        status = "ACCUMULATING"
    else:
        status = "TECHNICALLY_READY"
    return LeagueMarketReadiness(
        competition_id=competition_id,
        market=market,
        status=status,
        fixture_coverage=fixture_coverage,
        xg_numeric_match_count=xg_numeric_match_count,
        statistics_response_count=_int(common.get("statistics_response_count")),
        rolling_feature_team_count=rolling_feature_team_count,
        elo_team_count=_int(common.get("elo_team_count")),
        squad_value_team_count=_int(common.get("squad_value_team_count")),
        rest_days_team_count=_int(common.get("rest_days_team_count")),
        lineup_status=str(common.get("lineup_status") or "UNKNOWN"),
        pinnacle_line_count=pinnacle_line_count,
        artifact_present=artifact_present,
        artifact_hash=artifact_hash,
        artifact_version=artifact_version,
        train_cutoff=train_cutoff,
        feature_parity=feature_parity,
        model_market_gap=gap,
        shadow_closing_pair_count=shadow_pairs,
        entry_window_rate=entry_rate,
        closing_pair_coverage_rate=closing_rate,
        outcome_coverage_rate=outcome_rate,
        median_same_line_decimal_clv=clv,
        blockers=tuple(blockers),
    )


def _load_evidence(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _bool(value: Any) -> bool:
    return value is True


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value) if value else None


def _status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row["status"])
        counts[status] = counts.get(status, 0) + 1
    return counts
