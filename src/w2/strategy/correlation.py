from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from w2.strategy.candidate import GeneratedCandidate

CandidateRole = Literal["PRIMARY", "BACKUP"]


@dataclass(frozen=True, kw_only=True)
class SelectedCandidate:
    role: CandidateRole
    candidate: GeneratedCandidate
    candidate_flag: Literal[False] = False
    formal_recommendation: Literal[False] = False

    def as_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "candidate": self.candidate.as_dict(),
            "candidate_flag": False,
            "formal_recommendation": False,
        }


@dataclass(frozen=True, kw_only=True)
class CorrelationSelection:
    primary: SelectedCandidate | None
    backup: SelectedCandidate | None
    suppressed_count: int
    candidate: Literal[False] = False
    formal_recommendation: Literal[False] = False

    def as_dict(self) -> dict[str, object]:
        return {
            "primary": self.primary.as_dict() if self.primary else None,
            "backup": self.backup.as_dict() if self.backup else None,
            "suppressed_count": self.suppressed_count,
            "candidate": False,
            "formal_recommendation": False,
        }


def low_correlation(primary: GeneratedCandidate, candidate: GeneratedCandidate) -> bool:
    if primary.market is None or candidate.market is None:
        return False
    if primary.market == candidate.market:
        return False
    pair = {primary.market, candidate.market}
    selections = {primary.selection, candidate.selection}
    if pair == {"TOTALS", "BTTS"} and selections in [{"OVER", "YES"}, {"UNDER", "NO"}]:
        return False
    if pair == {"ONE_X_TWO", "ASIAN_HANDICAP"}:
        one_x_two = primary if primary.market == "ONE_X_TWO" else candidate
        handicap = primary if primary.market == "ASIAN_HANDICAP" else candidate
        if one_x_two.selection == "HOME" and handicap.selection in {"HOME", "HOME_HANDICAP"}:
            return False
        if one_x_two.selection == "AWAY" and handicap.selection in {"AWAY", "AWAY_HANDICAP"}:
            return False
    return True


def select_uncorrelated_candidates(
    candidates: list[GeneratedCandidate],
) -> CorrelationSelection:
    eligible = [candidate for candidate in candidates if candidate.decision == "WATCH"]
    if not eligible:
        return CorrelationSelection(primary=None, backup=None, suppressed_count=len(candidates))
    primary = eligible[0]
    backup = next(
        (candidate for candidate in eligible[1:] if low_correlation(primary, candidate)),
        None,
    )
    kept = 1 + int(backup is not None)
    return CorrelationSelection(
        primary=SelectedCandidate(role="PRIMARY", candidate=primary),
        backup=SelectedCandidate(role="BACKUP", candidate=backup) if backup else None,
        suppressed_count=max(len(eligible) - kept, 0),
    )
