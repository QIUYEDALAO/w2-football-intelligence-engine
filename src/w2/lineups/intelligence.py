from __future__ import annotations

import hashlib
import json
import os
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

TOP_FIVE_COMPETITION_CODES = frozenset(
    {
        "GB1",
        "ES1",
        "IT1",
        "L1",
        "FR1",
        "premier_league",
        "la_liga",
        "serie_a",
        "bundesliga",
        "ligue_1",
    }
)
MAX_AH_DELTA = 0.25
MAX_TOTALS_DELTA = 0.30
LINEUP_POLICY_RELATIVE_PATH = Path("config/policies/lineup_market_policy.v1.json")


class CoverageGrade(StrEnum):
    A = "A"
    B = "B"
    C = "C"


class MappingStatus(StrEnum):
    MATCHED = "MATCHED"
    MISSING = "MISSING"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, kw_only=True)
class PlayerIdentityCandidate:
    transfermarkt_player_id: str
    player_name: str
    team_external_id: str
    position: str | None = None


@dataclass(frozen=True, kw_only=True)
class PlayerIdentityResolution:
    status: MappingStatus
    transfermarkt_player_id: str | None
    normalized_name: str
    reason: str
    identity_hash: str


@dataclass(frozen=True, kw_only=True)
class LineupCoverage:
    registered_total: int
    registered_mapped: int
    regular_starter_total: int
    regular_starter_mapped: int
    matchday_starter_total: int
    matchday_starter_mapped: int
    valuation_total: int
    valuation_covered: int
    position_total: int
    position_covered: int
    formation_total: int
    formation_covered: int
    conflicts: int = 0

    def ratio(self, covered: int, total: int) -> float:
        return round(covered / total, 6) if total > 0 else 0.0

    def as_dict(self) -> dict[str, int | float]:
        result: dict[str, int | float] = asdict(self)
        result.update(
            registered_mapping_rate=self.ratio(self.registered_mapped, self.registered_total),
            regular_starter_mapping_rate=self.ratio(
                self.regular_starter_mapped, self.regular_starter_total
            ),
            matchday_starter_mapping_rate=self.ratio(
                self.matchday_starter_mapped, self.matchday_starter_total
            ),
            valuation_coverage_rate=self.ratio(self.valuation_covered, self.valuation_total),
            position_coverage_rate=self.ratio(self.position_covered, self.position_total),
            formation_coverage_rate=self.ratio(self.formation_covered, self.formation_total),
        )
        return result


@dataclass(frozen=True, kw_only=True)
class LineupAdjustment:
    ah_delta: float = 0.0
    totals_delta: float = 0.0
    ah_evidence_enabled: bool = False
    totals_evidence_enabled: bool = False


@dataclass(frozen=True, kw_only=True)
class LineupChangeFeatures:
    regular_starters_missing: int
    replacement_value_delta_eur: float
    out_of_position_count: int
    formation_changed: bool
    starter_continuity: float
    defensive_disruption: float
    attacking_disruption: float
    bench_value_eur: float
    status: str
    blockers: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class LineupGateResult:
    eligible: bool
    grade: CoverageGrade
    blockers: tuple[str, ...]
    numeric_adjustment_enabled: bool


class LineupGate:
    def evaluate(
        self,
        *,
        competition_code: str,
        confirmed: bool,
        home_starters: int,
        away_starters: int,
        uniquely_mapped_starters: int,
        valued_starters: int,
        formation_count: int,
        quotes_complete_and_fresh: bool,
        audited_coverage_rate: float,
    ) -> LineupGateResult:
        grade = grade_coverage(audited_coverage_rate)
        if competition_code not in TOP_FIVE_COMPETITION_CODES:
            return LineupGateResult(
                eligible=quotes_complete_and_fresh,
                grade=grade,
                blockers=() if quotes_complete_and_fresh else ("QUOTE_NOT_COMPLETE_OR_FRESH",),
                numeric_adjustment_enabled=grade is not CoverageGrade.C,
            )
        checks = {
            "LINEUP_NOT_CONFIRMED": confirmed,
            "STARTING_XI_INCOMPLETE": home_starters == 11 and away_starters == 11,
            "PLAYER_IDENTITY_INCOMPLETE": uniquely_mapped_starters == 22,
            "VALUATION_INCOMPLETE": valued_starters == 22,
            "FORMATION_INCOMPLETE": formation_count == 2,
            "QUOTE_NOT_COMPLETE_OR_FRESH": quotes_complete_and_fresh,
        }
        blockers = tuple(reason for reason, passed in checks.items() if not passed)
        return LineupGateResult(
            eligible=not blockers,
            grade=grade,
            blockers=blockers,
            numeric_adjustment_enabled=not blockers,
        )


def normalize_player_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    return "".join(character for character in decomposed if character.isalnum())


def resolve_player_identity(
    *,
    api_football_player_id: str,
    player_name: str,
    team_external_id: str,
    provider_position: str | None,
    candidates: Iterable[PlayerIdentityCandidate],
) -> PlayerIdentityResolution:
    normalized = normalize_player_name(player_name)
    matching = [
        candidate
        for candidate in candidates
        if candidate.team_external_id == team_external_id
        and normalize_player_name(candidate.player_name) == normalized
        and _positions_compatible(provider_position, candidate.position)
    ]
    matched_id = matching[0].transfermarkt_player_id if len(matching) == 1 else None
    status = (
        MappingStatus.MATCHED
        if matched_id
        else MappingStatus.CONFLICT
        if matching
        else MappingStatus.MISSING
    )
    reason = (
        "UNIQUE_TEAM_NAME_POSITION"
        if matched_id
        else "AMBIGUOUS_CANDIDATES"
        if matching
        else "NO_CANDIDATE"
    )
    identity_hash = _hash_payload(
        {
            "api_football_player_id": api_football_player_id,
            "team_external_id": team_external_id,
            "normalized_name": normalized,
            "provider_position": provider_position,
            "transfermarkt_player_id": matched_id,
            "status": status.value,
        }
    )
    return PlayerIdentityResolution(
        status=status,
        transfermarkt_player_id=matched_id,
        normalized_name=normalized,
        reason=reason,
        identity_hash=identity_hash,
    )


def grade_coverage(rate: float) -> CoverageGrade:
    if rate >= 0.90:
        return CoverageGrade.A
    if rate >= 0.50:
        return CoverageGrade.B
    return CoverageGrade.C


@lru_cache(maxsize=1)
def lineup_market_policy() -> dict[str, Any]:
    payload = json.loads(_lineup_policy_path().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("LINEUP_POLICY_INVALID")
    if payload.get("schema_version") != "w2.lineup_market_policy.v1":
        raise ValueError("LINEUP_POLICY_SCHEMA_INCOMPATIBLE")
    return {str(key): value for key, value in payload.items()}


def _lineup_policy_path() -> Path:
    configured = os.environ.get("W2_LINEUP_POLICY_PATH")
    candidates = ((Path(configured),) if configured else ()) + (
        Path.cwd() / LINEUP_POLICY_RELATIVE_PATH,
        Path(__file__).resolve().parents[3] / LINEUP_POLICY_RELATIVE_PATH,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "LINEUP_POLICY_NOT_FOUND: " + ", ".join(str(candidate) for candidate in candidates)
    )


def audited_coverage_rate(competition_id: str) -> float:
    grade = str(lineup_market_policy().get("non_top_five_grades", {}).get(competition_id, "C"))
    return 0.90 if grade == "A" else 0.50 if grade == "B" else 0.0


def build_team_baseline(
    rows: Sequence[Mapping[str, Any]],
    *,
    team_external_id: str,
    as_of: datetime,
    limit: int = 10,
) -> dict[str, Any]:
    eligible = [
        row
        for row in rows
        if str(row.get("team_external_id") or "") == team_external_id
        and isinstance(row.get("kickoff_at"), datetime)
        and row["kickoff_at"] < as_of
    ]
    eligible.sort(key=lambda row: row["kickoff_at"], reverse=True)
    selected = eligible[:limit]
    starter_weight: defaultdict[str, float] = defaultdict(float)
    position_weight: defaultdict[str, defaultdict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    formations: Counter[str] = Counter()
    for index, row in enumerate(selected):
        weight = 1.0 if index < 5 else 0.6
        formation = str(row.get("formation") or "")
        if formation:
            formations[formation] += 1
        for player in row.get("starters", []):
            if not isinstance(player, Mapping):
                continue
            player_id = str(player.get("player_id") or "")
            if not player_id:
                continue
            starter_weight[player_id] += weight
            position = str(player.get("position") or "UNKNOWN")
            position_weight[player_id][position] += weight
    payload = {
        "team_external_id": team_external_id,
        "as_of": as_of.isoformat(),
        "match_count": len(selected),
        "common_formation": formations.most_common(1)[0][0] if formations else None,
        "players": [
            {
                "player_id": player_id,
                "starter_weight": round(weight, 4),
                "usual_position": max(
                    position_weight[player_id],
                    key=lambda position: position_weight[player_id][position],
                ),
            }
            for player_id, weight in sorted(
                starter_weight.items(), key=lambda item: (-item[1], item[0])
            )
        ],
        "input_fixture_ids": [str(row.get("fixture_id")) for row in selected],
    }
    return {
        **payload,
        "artifact_hash": _hash_payload(payload),
        "schema_version": "w2.lineup_baseline.v1",
    }


def derive_lineup_change_features(
    *,
    baseline: Mapping[str, Any],
    starters: Sequence[Mapping[str, Any]],
    substitutes: Sequence[Mapping[str, Any]],
    formation: str | None,
) -> LineupChangeFeatures:
    player_ids = [str(player.get("player_id") or "") for player in starters]
    blockers: list[str] = []
    if len(starters) != 11:
        blockers.append("STARTING_XI_INCOMPLETE")
    if len({player_id for player_id in player_ids if player_id}) != len(starters):
        blockers.append("DUPLICATE_STARTER")
    baseline_players = {
        str(player.get("player_id") or ""): player
        for player in baseline.get("players", [])
        if isinstance(player, Mapping)
    }
    regular = {
        player_id
        for player_id, player in baseline_players.items()
        if float(player.get("starter_weight") or 0.0) >= 3.0
    }
    current = set(player_ids)
    missing = regular - current
    out_of_position = 0
    defensive_disruption = 0.0
    attacking_disruption = 0.0
    replacement_delta = 0.0
    for player in starters:
        player_id = str(player.get("player_id") or "")
        current_position = str(player.get("position") or "UNKNOWN")
        usual_position = str(baseline_players.get(player_id, {}).get("usual_position") or "")
        if usual_position and current_position != usual_position:
            out_of_position += 1
        value_delta = float(player.get("value_delta_eur") or 0.0)
        replacement_delta += value_delta
        if current_position[:1].upper() in {"G", "D"}:
            defensive_disruption += abs(value_delta)
        elif current_position[:1].upper() == "F":
            attacking_disruption += abs(value_delta)
    denominator = max(len(regular), 1)
    continuity = len(regular & current) / denominator
    bench_value = sum(float(player.get("market_value_eur") or 0.0) for player in substitutes)
    return LineupChangeFeatures(
        regular_starters_missing=len(missing),
        replacement_value_delta_eur=round(replacement_delta, 2),
        out_of_position_count=out_of_position,
        formation_changed=bool(
            formation
            and baseline.get("common_formation")
            and formation != baseline.get("common_formation")
        ),
        starter_continuity=round(continuity, 6),
        defensive_disruption=round(defensive_disruption, 2),
        attacking_disruption=round(attacking_disruption, 2),
        bench_value_eur=round(bench_value, 2),
        status="COMPLETE" if not blockers else "INCOMPLETE",
        blockers=tuple(blockers),
    )


def apply_lineup_adjustments(
    *,
    lambda_home: float,
    lambda_away: float,
    adjustment: LineupAdjustment,
) -> tuple[float, float]:
    ah_delta = _clamp(adjustment.ah_delta, MAX_AH_DELTA) if adjustment.ah_evidence_enabled else 0.0
    totals_delta = (
        _clamp(adjustment.totals_delta, MAX_TOTALS_DELTA)
        if adjustment.totals_evidence_enabled
        else 0.0
    )
    return (
        round(max(0.05, lambda_home + (totals_delta + ah_delta) / 2.0), 6),
        round(max(0.05, lambda_away + (totals_delta - ah_delta) / 2.0), 6),
    )


def _positions_compatible(provider: str | None, transfermarkt: str | None) -> bool:
    if not provider or not transfermarkt:
        return True
    provider_group = provider.strip().upper()[:1]
    tm = transfermarkt.casefold()
    tm_group = (
        "G"
        if "goal" in tm
        else "D"
        if "back" in tm or "defen" in tm
        else "M"
        if "mid" in tm
        else "F"
    )
    return provider_group == tm_group


def _hash_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _clamp(value: float, cap: float) -> float:
    return min(max(float(value), -cap), cap)
