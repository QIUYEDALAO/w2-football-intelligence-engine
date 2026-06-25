from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

Decision = Literal["WATCH", "SKIP"]

CORE_MARKETS = frozenset({"ONE_X_TWO", "ASIAN_HANDICAP", "TOTALS"})
KNOWN_SETTLEMENT_MARKETS = CORE_MARKETS | frozenset({"BTTS"})


class HardGateReason(StrEnum):
    CORE_MARKET_MISSING = "CORE_MARKET_MISSING"
    ODDS_STALE = "ODDS_STALE"
    BOOKMAKER_MIN_NOT_MET = "BOOKMAKER_MIN_NOT_MET"
    MARKET_SUSPENDED = "MARKET_SUSPENDED"
    MARKET_LIVE = "MARKET_LIVE"
    SETTLEMENT_RULE_UNKNOWN = "SETTLEMENT_RULE_UNKNOWN"
    KICKOFF_PASSED = "KICKOFF_PASSED"


@dataclass(frozen=True, kw_only=True)
class CandidatePolicy:
    min_bookmakers: int = 2
    max_odds_age_seconds: int = 900
    core_markets: frozenset[str] = CORE_MARKETS
    known_settlement_markets: frozenset[str] = KNOWN_SETTLEMENT_MARKETS


@dataclass(frozen=True, kw_only=True)
class GeneratedCandidate:
    fixture_id: str
    decision: Decision
    market: str | None
    selection: str | None
    line: str | None
    decimal_odds: Decimal | None
    bookmaker_count: int
    hard_gate_reasons: tuple[HardGateReason, ...]
    candidate: Literal[False] = False
    formal_recommendation: Literal[False] = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "decision": self.decision,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "decimal_odds": str(self.decimal_odds) if self.decimal_odds is not None else None,
            "bookmaker_count": self.bookmaker_count,
            "hard_gate_reasons": [reason.value for reason in self.hard_gate_reasons],
            "candidate": False,
            "formal_recommendation": False,
        }


def parse_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value:
        raise ValueError("UTC datetime string is required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("UTC datetime must include timezone")
    return parsed.astimezone(UTC)


def _market(row: dict[str, Any]) -> str:
    return str(row.get("canonical_market") or row.get("market") or row.get("market_type") or "")


def _bookmaker(row: dict[str, Any]) -> str:
    return str(row.get("bookmaker_id") or row.get("bookmaker") or row.get("bookmaker_name") or "")


def _captured_at(row: dict[str, Any]) -> datetime:
    return parse_utc(row.get("captured_at_utc") or row.get("captured_at"))


def _decimal_odds(row: dict[str, Any]) -> Decimal | None:
    value = row.get("decimal_odds")
    if value is None:
        value = row.get("odds_value")
    if value is None:
        return None
    return Decimal(str(value))


def hard_gate_reasons(
    *,
    fixture: dict[str, Any],
    observations: list[dict[str, Any]],
    as_of: datetime,
    policy: CandidatePolicy | None = None,
) -> tuple[HardGateReason, ...]:
    resolved_policy = policy or CandidatePolicy()
    reasons: list[HardGateReason] = []
    markets = {_market(row) for row in observations}
    missing = resolved_policy.core_markets - markets
    if missing:
        reasons.append(HardGateReason.CORE_MARKET_MISSING)

    kickoff_value = fixture.get("kickoff_utc") or fixture.get("fixture", {}).get("date")
    if kickoff_value is not None and parse_utc(kickoff_value) <= as_of:
        reasons.append(HardGateReason.KICKOFF_PASSED)

    bookmaker_ids = {_bookmaker(row) for row in observations if _bookmaker(row)}
    if len(bookmaker_ids) < resolved_policy.min_bookmakers:
        reasons.append(HardGateReason.BOOKMAKER_MIN_NOT_MET)

    for row in observations:
        if bool(row.get("suspended")):
            reasons.append(HardGateReason.MARKET_SUSPENDED)
            break
    for row in observations:
        if bool(row.get("live")):
            reasons.append(HardGateReason.MARKET_LIVE)
            break
    for row in observations:
        if _market(row) not in resolved_policy.known_settlement_markets:
            reasons.append(HardGateReason.SETTLEMENT_RULE_UNKNOWN)
            break
    for row in observations:
        if (as_of - _captured_at(row)).total_seconds() > resolved_policy.max_odds_age_seconds:
            reasons.append(HardGateReason.ODDS_STALE)
            break

    return tuple(dict.fromkeys(reasons))


def generate_candidate(
    *,
    fixture: dict[str, Any],
    observations: list[dict[str, Any]],
    as_of: datetime,
    policy: CandidatePolicy | None = None,
) -> GeneratedCandidate:
    fixture_id = str(
        fixture.get("fixture_id")
        or fixture.get("id")
        or fixture.get("fixture", {}).get("id")
    )
    reasons = hard_gate_reasons(
        fixture=fixture,
        observations=observations,
        as_of=as_of,
        policy=policy,
    )
    bookmaker_count = len({_bookmaker(row) for row in observations if _bookmaker(row)})
    if reasons:
        return GeneratedCandidate(
            fixture_id=fixture_id,
            decision="SKIP",
            market=None,
            selection=None,
            line=None,
            decimal_odds=None,
            bookmaker_count=bookmaker_count,
            hard_gate_reasons=reasons,
        )

    best = max(
        observations,
        key=lambda row: (
            _decimal_odds(row) or Decimal("0"),
            _market(row),
            str(row.get("selection")),
        ),
    )
    return GeneratedCandidate(
        fixture_id=fixture_id,
        decision="WATCH",
        market=_market(best),
        selection=str(best.get("selection")),
        line=str(best.get("line")) if best.get("line") is not None else None,
        decimal_odds=_decimal_odds(best),
        bookmaker_count=bookmaker_count,
        hard_gate_reasons=(),
    )
