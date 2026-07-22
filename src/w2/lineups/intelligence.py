from __future__ import annotations

import hashlib
import json
import math
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
    CANDIDATE = "CANDIDATE"
    REVIEWED = "REVIEWED"
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
    replacement_value_delta_eur: float | None
    out_of_position_count: int
    formation_changed: bool
    starter_continuity: float
    defensive_disruption: float
    attacking_disruption: float
    bench_value_eur: float | None
    status: str
    blockers: tuple[str, ...]
    expected_xi_value_eur: float | None = None
    confirmed_xi_value_eur: float | None = None
    value_delta_eur: float | None = None
    value_delta_ratio: float | None = None
    log_normalized_value_delta: float | None = None
    goalkeeper_replacement_delta: float | None = None
    defensive_replacement_delta: float | None = None
    midfield_replacement_delta: float | None = None
    attacking_replacement_delta: float | None = None
    goalkeeper_change: bool = False
    centre_back_pair_continuity: float = 0.0
    central_midfield_continuity: float = 0.0
    front_line_continuity: float = 0.0
    captain_missing: bool | None = None
    valuation_coverage: float = 0.0
    mapping_coverage: float = 0.0
    baseline_match_count: int = 0


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
                numeric_adjustment_enabled=False,
            )
        checks = {
            "LINEUP_NOT_CONFIRMED": confirmed,
            "STARTING_XI_INCOMPLETE": home_starters == 11 and away_starters == 11,
            "QUOTE_NOT_COMPLETE_OR_FRESH": quotes_complete_and_fresh,
        }
        blockers = tuple(reason for reason, passed in checks.items() if not passed)
        return LineupGateResult(
            eligible=not blockers,
            grade=grade,
            blockers=blockers,
            numeric_adjustment_enabled=False,
        )


def lineup_requirement(competition_id: str) -> str:
    """Return the only authoritative lineup admission policy for a competition."""
    return "STRICT" if competition_id in TOP_FIVE_COMPETITION_CODES else "ADVISORY"


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
        MappingStatus.CANDIDATE
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
    captain_weight: defaultdict[str, float] = defaultdict(float)
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
            if bool(player.get("captain")):
                captain_weight[player_id] += weight
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
                "captain_weight": round(captain_weight[player_id], 4),
                **(
                    {"market_value_eur": float(player_value)}
                    if (
                        player_value := _latest_baseline_player_value(
                            selected,
                            player_id=player_id,
                            as_of=as_of,
                        )
                    )
                    is not None
                    else {}
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
    expected_players = sorted(
        baseline_players.values(),
        key=lambda player: (
            -float(player.get("starter_weight") or 0.0),
            str(player.get("player_id") or ""),
        ),
    )[:11]
    regular = {
        str(player.get("player_id") or "")
        for player in expected_players
        if float(player.get("starter_weight") or 0.0) >= 3.0
    }
    current = set(player_ids)
    missing = regular - current
    out_of_position = 0
    defensive_disruption = 0.0
    attacking_disruption = 0.0
    for player in starters:
        player_id = str(player.get("player_id") or "")
        current_position = str(player.get("position") or "UNKNOWN")
        usual_position = str(baseline_players.get(player_id, {}).get("usual_position") or "")
        if usual_position and current_position != usual_position:
            out_of_position += 1
        value_delta = _optional_float(player.get("value_delta_eur"))
        if value_delta is not None:
            if _position_group(current_position) in {"GOALKEEPER", "DEFENCE"}:
                defensive_disruption += abs(value_delta)
            elif _position_group(current_position) == "ATTACK":
                attacking_disruption += abs(value_delta)
    denominator = max(len(regular), 1)
    continuity = len(regular & current) / denominator
    expected_values = [_player_value(player) for player in expected_players]
    confirmed_values = [_player_value(player) for player in starters]
    substitute_values = [_player_value(player) for player in substitutes]
    expected_value = _covered_sum(expected_values, required=len(expected_players))
    confirmed_value = _covered_sum(confirmed_values, required=11)
    bench_value = _covered_sum(substitute_values, required=len(substitute_values))
    value_delta = (
        confirmed_value - expected_value
        if confirmed_value is not None and expected_value is not None
        else None
    )
    value_delta_ratio = (
        value_delta / max(expected_value, 1.0)
        if value_delta is not None and expected_value is not None
        else None
    )
    log_value_delta = (
        sum(math.log1p(value) for value in confirmed_values if value is not None)
        - sum(math.log1p(value) for value in expected_values if value is not None)
        if confirmed_values
        and expected_values
        and all(value is not None for value in [*confirmed_values, *expected_values])
        else None
    )

    newcomers = [player for player in starters if str(player.get("player_id") or "") not in regular]
    missing_players = [baseline_players[player_id] for player_id in sorted(missing)]
    replacement_by_group: dict[str, list[float]] = defaultdict(list)
    unresolved_replacement = False
    used_newcomers: set[int] = set()
    for missing_player in missing_players:
        group = _position_group(str(missing_player.get("usual_position") or "UNKNOWN"))
        replacement_index = next(
            (
                index
                for index, player in enumerate(newcomers)
                if index not in used_newcomers
                and _position_group(str(player.get("position") or "UNKNOWN")) == group
            ),
            None,
        )
        missing_value = _player_value(missing_player)
        replacement_value = (
            _player_value(newcomers[replacement_index]) if replacement_index is not None else None
        )
        if replacement_index is None or missing_value is None or replacement_value is None:
            unresolved_replacement = True
            continue
        used_newcomers.add(replacement_index)
        replacement_by_group[group].append(replacement_value - missing_value)
    if unresolved_replacement:
        blockers.append("ROLE_REPLACEMENT_UNRESOLVED")
    resolved_replacement_deltas = [
        value for values in replacement_by_group.values() for value in values
    ]
    replacement_delta = (
        round(sum(resolved_replacement_deltas), 2)
        if not unresolved_replacement
        else None
    )
    defensive_delta = _group_delta(replacement_by_group, "DEFENCE")
    goalkeeper_delta = _group_delta(replacement_by_group, "GOALKEEPER")
    midfield_delta = _group_delta(replacement_by_group, "MIDFIELD")
    attacking_delta = _group_delta(replacement_by_group, "ATTACK")
    if defensive_delta is not None:
        defensive_disruption += abs(defensive_delta)
    if goalkeeper_delta is not None:
        defensive_disruption += abs(goalkeeper_delta)
    if attacking_delta is not None:
        attacking_disruption += abs(attacking_delta)

    mapping_coverage = _coverage(
        [
            bool(player.get("canonical_player_id"))
            or str(player.get("mapping_status") or "").upper() == "REVIEWED"
            for player in starters
        ]
    )
    valuation_coverage = _coverage([value is not None for value in confirmed_values])
    expected_by_group = _ids_by_group(expected_players, position_key="usual_position")
    current_by_group = _ids_by_group(starters, position_key="position")
    goalkeeper_change = bool(expected_by_group["GOALKEEPER"] - current_by_group["GOALKEEPER"])
    captain_ids = {
        str(player.get("player_id") or "")
        for player in expected_players
        if float(player.get("captain_weight") or 0.0) >= 3.0
    }
    captain_missing = bool(captain_ids - current) if captain_ids else None
    return LineupChangeFeatures(
        regular_starters_missing=len(missing),
        replacement_value_delta_eur=replacement_delta,
        out_of_position_count=out_of_position,
        formation_changed=bool(
            formation
            and baseline.get("common_formation")
            and formation != baseline.get("common_formation")
        ),
        starter_continuity=round(continuity, 6),
        defensive_disruption=round(defensive_disruption, 2),
        attacking_disruption=round(attacking_disruption, 2),
        bench_value_eur=round(bench_value, 2) if bench_value is not None else None,
        status="COMPLETE" if not blockers else "INCOMPLETE",
        blockers=tuple(dict.fromkeys(blockers)),
        expected_xi_value_eur=round(expected_value, 2) if expected_value is not None else None,
        confirmed_xi_value_eur=round(confirmed_value, 2)
        if confirmed_value is not None
        else None,
        value_delta_eur=round(value_delta, 2) if value_delta is not None else None,
        value_delta_ratio=round(value_delta_ratio, 6)
        if value_delta_ratio is not None
        else None,
        log_normalized_value_delta=round(log_value_delta, 6)
        if log_value_delta is not None
        else None,
        goalkeeper_replacement_delta=goalkeeper_delta,
        defensive_replacement_delta=defensive_delta,
        midfield_replacement_delta=midfield_delta,
        attacking_replacement_delta=attacking_delta,
        goalkeeper_change=goalkeeper_change,
        centre_back_pair_continuity=_group_continuity(
            expected_by_group["DEFENCE"], current_by_group["DEFENCE"], cap=2
        ),
        central_midfield_continuity=_group_continuity(
            expected_by_group["MIDFIELD"], current_by_group["MIDFIELD"], cap=3
        ),
        front_line_continuity=_group_continuity(
            expected_by_group["ATTACK"], current_by_group["ATTACK"], cap=3
        ),
        captain_missing=captain_missing,
        valuation_coverage=valuation_coverage,
        mapping_coverage=mapping_coverage,
        baseline_match_count=int(baseline.get("match_count") or 0),
    )


def select_asof_player_valuation(
    observations: Sequence[Mapping[str, Any]],
    *,
    valuation_source_player_id: str,
    as_of: datetime,
) -> dict[str, Any]:
    """Select the newest pre-lineup valuation without historical backfill leakage."""
    if as_of.tzinfo is None:
        raise ValueError("AS_OF_MUST_BE_TIMEZONE_AWARE")
    eligible = [
        row
        for row in observations
        if str(row.get("valuation_source_player_id") or row.get("transfermarkt_player_id") or "")
        == str(valuation_source_player_id)
        and isinstance(row.get("observed_at"), datetime)
        and row["observed_at"].astimezone(as_of.tzinfo) <= as_of
    ]
    eligible.sort(key=lambda row: row["observed_at"], reverse=True)
    if not eligible:
        return {
            "status": "MISSING",
            "valuation_source_player_id": str(valuation_source_player_id),
            "market_value_eur": None,
            "observed_at": None,
            "source_artifact_hash": None,
        }
    selected = eligible[0]
    payload = {
        "status": "READY",
        "valuation_source_player_id": str(valuation_source_player_id),
        "market_value_eur": float(selected["market_value_eur"]),
        "source_system": str(selected.get("source_system") or selected.get("source") or ""),
        "source_artifact_hash": str(
            selected.get("source_artifact_hash") or selected.get("source_sha256") or ""
        ),
        "observed_at": selected["observed_at"].isoformat(),
        "confidence": _optional_float(selected.get("confidence")),
        "mapping_review_status": str(selected.get("mapping_review_status") or "UNKNOWN"),
    }
    return {**payload, "valuation_hash": _hash_payload(payload)}


def validate_confirmed_lineup_snapshot(
    *,
    fixture_id: str,
    expected_fixture_id: str,
    captured_at: datetime,
    kickoff_at: datetime,
    starters: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    blockers: list[str] = []
    if str(fixture_id) != str(expected_fixture_id):
        blockers.append("FIXTURE_IDENTITY_CONFLICT")
    if captured_at.tzinfo is None or kickoff_at.tzinfo is None:
        blockers.append("LINEUP_TIMEZONE_INVALID")
    elif captured_at >= kickoff_at:
        blockers.append("POST_KICKOFF_LINEUP_REJECTED")
    ids = [
        str(player.get("player_id") or player.get("api_football_player_id") or "")
        for player in starters
    ]
    if len(starters) != 11 or any(not player_id for player_id in ids):
        blockers.append("STARTING_XI_INCOMPLETE")
    if len(set(ids)) != len(ids):
        blockers.append("DUPLICATE_STARTER")
    if any(str(player.get("mapping_status") or "") == "CONFLICT" for player in starters):
        blockers.append("PLAYER_MAPPING_CONFLICT")
    return tuple(dict.fromkeys(blockers))


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


def _latest_baseline_player_value(
    rows: Sequence[Mapping[str, Any]],
    *,
    player_id: str,
    as_of: datetime,
) -> float | None:
    candidates: list[tuple[datetime, float]] = []
    for row in rows:
        kickoff = row.get("kickoff_at")
        if not isinstance(kickoff, datetime) or kickoff >= as_of:
            continue
        for player in row.get("starters", []):
            if not isinstance(player, Mapping) or str(player.get("player_id") or "") != player_id:
                continue
            value = _player_value(player)
            observed_at = player.get("valuation_observed_at")
            if value is None:
                continue
            if isinstance(observed_at, datetime) and observed_at > as_of:
                continue
            candidates.append((kickoff, value))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1] if candidates else None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _player_value(player: Mapping[str, Any]) -> float | None:
    return _optional_float(player.get("market_value_eur"))


def _covered_sum(values: Sequence[float | None], *, required: int) -> float | None:
    if required == 0:
        return 0.0
    if len(values) != required or any(value is None for value in values):
        return None
    return float(sum(value for value in values if value is not None))


def _position_group(position: str) -> str:
    normalized = position.strip().casefold()
    initial = normalized[:1].upper()
    if initial == "G" or "goal" in normalized:
        return "GOALKEEPER"
    if initial == "D" or any(token in normalized for token in ("back", "defen", "centre-back")):
        return "DEFENCE"
    if initial == "M" or "mid" in normalized:
        return "MIDFIELD"
    if initial in {"F", "A", "S", "W"} or any(
        token in normalized for token in ("forward", "striker", "wing", "attack")
    ):
        return "ATTACK"
    return "UNKNOWN"


def _group_delta(values: Mapping[str, Sequence[float]], group: str) -> float | None:
    group_values = values.get(group, ())
    return round(sum(group_values), 2) if group_values else None


def _coverage(values: Sequence[bool]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def _ids_by_group(
    players: Sequence[Mapping[str, Any]],
    *,
    position_key: str,
) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {
        group: set() for group in ("GOALKEEPER", "DEFENCE", "MIDFIELD", "ATTACK")
    }
    for player in players:
        player_id = str(player.get("player_id") or "")
        group = _position_group(str(player.get(position_key) or "UNKNOWN"))
        if player_id and group in grouped:
            grouped[group].add(player_id)
    return grouped


def _group_continuity(expected: set[str], current: set[str], *, cap: int) -> float:
    denominator = min(max(len(expected), 1), cap)
    return round(min(len(expected & current), cap) / denominator, 6)


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
