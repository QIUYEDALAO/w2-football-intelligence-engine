from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any

from w2.markets.asian_handicap_scope import is_full_time_asian_handicap_observation

CANONICAL_AH_MAINLINE_POLICY = "canonical_bookmaker_mainline_majority_v1"


@dataclass(frozen=True, kw_only=True)
class CanonicalAhMainline:
    status: str
    line: Decimal | None = None
    captured_at: datetime | None = None
    provider: str | None = None
    home_price: float | None = None
    away_price: float | None = None
    bookmaker_count: int = 0
    side_prices: dict[str, float] | None = None
    side_lines: dict[str, str] | None = None
    candidate_lines: list[dict[str, Any]] | None = None
    rejected_lines: list[dict[str, Any]] | None = None
    selected_bookmakers: list[str] | None = None
    source_payload_ids: list[str] | None = None
    quarantined_count: int = 0
    quarantine_reasons: dict[str, int] | None = None


def select_canonical_ah_mainline(
    observations: list[dict[str, Any]],
    *,
    fixture_id: str,
    target: datetime,
    kickoff: datetime,
    opening: bool = False,
) -> CanonicalAhMainline:
    target_utc = target.astimezone(UTC)
    kickoff_utc = kickoff.astimezone(UTC)
    scoped: list[dict[str, Any]] = []
    quarantine_reasons: dict[str, int] = {}
    for row in observations:
        reason = _quarantine_reason(row, fixture_id=fixture_id)
        if reason:
            quarantine_reasons[reason] = quarantine_reasons.get(reason, 0) + 1
            continue
        captured_at = _parse_utc(row.get("captured_at") or row.get("captured_at_utc"))
        if captured_at is None or captured_at > target_utc or captured_at >= kickoff_utc:
            continue
        scoped.append({**row, "_captured_at": captured_at})
    if not scoped:
        return CanonicalAhMainline(
            status="UNAVAILABLE",
            quarantined_count=sum(quarantine_reasons.values()),
            quarantine_reasons=quarantine_reasons,
        )
    bucket_at = (
        min(row["_captured_at"] for row in scoped)
        if opening
        else max(row["_captured_at"] for row in scoped)
    )
    bucket = [row for row in scoped if row["_captured_at"] == bucket_at]
    bookmaker_mainlines = _bookmaker_mainline_votes(bucket)
    if not bookmaker_mainlines:
        return CanonicalAhMainline(
            status="NO_BALANCED_MAINLINE",
            captured_at=bucket_at,
            quarantined_count=sum(quarantine_reasons.values()),
            quarantine_reasons=quarantine_reasons,
        )
    by_line: dict[Decimal, list[dict[str, Any]]] = {}
    for vote in bookmaker_mainlines:
        by_line.setdefault(Decimal(str(vote["line"])), []).append(vote)
    candidate_lines = [_line_summary(line=line, votes=votes) for line, votes in by_line.items()]
    candidate_lines.sort(
        key=lambda item: (
            -int(item["bookmaker_count"]),
            float(item["balance_distance"]),
            float(item["price_gap"]),
            float(item["mid_distance"]),
            abs(float(item["line"])),
        )
    )
    selected_summary = candidate_lines[0]
    selected_line = Decimal(str(selected_summary["line"]))
    selected_votes = by_line[selected_line]
    representative = min(
        selected_votes,
        key=lambda item: (
            float(item["balance_distance"]),
            float(item["price_gap"]),
            float(item["mid_distance"]),
            str(item["bookmaker"]),
        ),
    )
    ordered_candidates = [
        {
            **item,
            "selection_rank": index + 1,
            "selection_policy": CANONICAL_AH_MAINLINE_POLICY,
            "consensus_eligible": index == 0
            or int(item["bookmaker_count"]) == int(selected_summary["bookmaker_count"]),
            "balanced_override_eligible": False,
            "bookmaker_consensus_floor": int(selected_summary["bookmaker_count"]),
        }
        for index, item in enumerate(candidate_lines)
    ]
    rejected_lines = [
        {
            "line": _json_number(float(item["line"])),
            "reason": "LOWER_BOOKMAKER_MAINLINE_MAJORITY"
            if int(item["bookmaker_count"]) < int(selected_summary["bookmaker_count"])
            else "TIE_BREAK_LOWER_LADDER_BALANCE",
        }
        for item in candidate_lines
        if Decimal(str(item["line"])) != selected_line
    ]
    return CanonicalAhMainline(
        status="READY",
        line=selected_line,
        captured_at=bucket_at,
        provider=str(representative.get("provider") or "read_model"),
        home_price=float(representative["home_price"]),
        away_price=float(representative["away_price"]),
        bookmaker_count=int(selected_summary["bookmaker_count"]),
        side_prices={
            "home": float(representative["home_price"]),
            "away": float(representative["away_price"]),
        },
        side_lines={
            "home": _format_decimal(selected_line),
            "away": _format_decimal(-selected_line),
        },
        candidate_lines=ordered_candidates,
        rejected_lines=rejected_lines,
        selected_bookmakers=sorted(str(item["bookmaker"]) for item in selected_votes),
        source_payload_ids=sorted(
            {
                str(payload_id)
                for item in selected_votes
                for payload_id in item.get("source_payload_ids", [])
                if payload_id
            },
        ),
        quarantined_count=sum(quarantine_reasons.values()),
        quarantine_reasons=quarantine_reasons,
    )


def _quarantine_reason(row: dict[str, Any], *, fixture_id: str) -> str | None:
    if str(row.get("fixture_id")) != fixture_id:
        return "OTHER_FIXTURE"
    if str(row.get("canonical_market") or row.get("market") or "").upper() != "ASIAN_HANDICAP":
        return "OTHER_MARKET"
    if row.get("suspended") or row.get("live"):
        return "SUSPENDED_OR_LIVE"
    if not is_full_time_asian_handicap_observation(row, allow_unlabeled=False):
        raw_label = str(row.get("raw_market_label") or "")
        if not raw_label.strip():
            return "UNLABELED_LEGACY_AH"
        return "NON_FULL_TIME_AH_LABEL"
    if _normalize_side(row.get("selection") or row.get("canonical_selection")) not in {
        "HOME",
        "AWAY",
    }:
        return "INVALID_AH_SIDE"
    if _decimal(row.get("line")) is None:
        return "INVALID_AH_LINE"
    if _float(row.get("decimal_odds") or row.get("executable_odds")) is None:
        return "INVALID_AH_PRICE"
    bookmaker = str(
        row.get("bookmaker_id") or row.get("bookmaker") or row.get("bookmaker_name") or ""
    )
    if not bookmaker:
        return "MISSING_BOOKMAKER"
    return None


def _bookmaker_mainline_votes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_bookmaker_line: dict[tuple[str, Decimal], dict[str, Any]] = {}
    for row in rows:
        bookmaker = str(
            row.get("bookmaker_id") or row.get("bookmaker") or row.get("bookmaker_name")
        )
        line = _decimal(row.get("line"))
        side = _normalize_side(row.get("selection") or row.get("canonical_selection"))
        price = _float(row.get("decimal_odds") or row.get("executable_odds"))
        if line is None or side not in {"HOME", "AWAY"} or price is None:
            continue
        home_line = line if side == "HOME" else -line
        key = (bookmaker, abs(home_line))
        pair = by_bookmaker_line.setdefault(
            key,
            {
                "bookmaker": bookmaker,
                "line": home_line,
                "sides": {},
                "provider": row.get("provider") or row.get("source") or "read_model",
                "source_payload_ids": set(),
            },
        )
        if side == "HOME":
            pair["line"] = home_line
        payload_id = (
            row.get("raw_payload_sha256") or row.get("source_payload_id") or row.get("sha256")
        )
        if payload_id:
            pair["source_payload_ids"].add(str(payload_id))
        current = pair["sides"].get(side)
        if current is None or price > float(current["price"]):
            pair["sides"][side] = {"price": price, "line": line}
    per_bookmaker: dict[str, list[dict[str, Any]]] = {}
    for pair in by_bookmaker_line.values():
        sides = pair.get("sides") or {}
        if set(sides) < {"HOME", "AWAY"}:
            continue
        prices = [float(sides["HOME"]["price"]), float(sides["AWAY"]["price"])]
        if not _valid_price_pair(prices):
            continue
        line = Decimal(str(pair["line"]))
        vote = {
            "bookmaker": str(pair["bookmaker"]),
            "line": line,
            "home_price": prices[0],
            "away_price": prices[1],
            "price_gap": round(abs(prices[0] - prices[1]), 6),
            "balance_distance": _devig_balance_distance(prices),
            "mid_distance": round(abs((sum(prices) / 2) - 1.90), 6),
            "implied_sum": round(sum(1 / value for value in prices), 6),
            "provider": pair.get("provider"),
            "source_payload_ids": sorted(pair.get("source_payload_ids") or []),
        }
        per_bookmaker.setdefault(str(pair["bookmaker"]), []).append(vote)
    votes: list[dict[str, Any]] = []
    for candidates in per_bookmaker.values():
        candidates.sort(
            key=lambda item: (
                float(item["balance_distance"]),
                float(item["price_gap"]),
                float(item["mid_distance"]),
                abs(float(item["line"])),
            ),
        )
        votes.append(candidates[0])
    return votes


def _line_summary(*, line: Decimal, votes: list[dict[str, Any]]) -> dict[str, Any]:
    home_prices = [float(item["home_price"]) for item in votes]
    away_prices = [float(item["away_price"]) for item in votes]
    balance_distances = [float(item["balance_distance"]) for item in votes]
    price_gaps = [float(item["price_gap"]) for item in votes]
    mid_distances = [float(item["mid_distance"]) for item in votes]
    implied_sums = [float(item["implied_sum"]) for item in votes]
    return {
        "line": _json_number(float(line)),
        "home_line": _format_decimal(line),
        "away_line": _format_decimal(-line),
        "home_price": _json_number(float(median(home_prices))),
        "away_price": _json_number(float(median(away_prices))),
        "median_home_price": _json_number(float(median(home_prices))),
        "median_away_price": _json_number(float(median(away_prices))),
        "bookmaker_count": len(votes),
        "bookmakers": sorted(str(item["bookmaker"]) for item in votes),
        "implied_sum": round(float(median(implied_sums)), 6),
        "balance_distance": round(float(median(balance_distances)), 6),
        "price_gap": round(float(median(price_gaps)), 6),
        "mid_distance": round(float(median(mid_distances)), 6),
        "selection_policy": CANONICAL_AH_MAINLINE_POLICY,
    }


def _valid_price_pair(prices: list[float]) -> bool:
    if len(prices) != 2:
        return False
    if any(price < 1.40 or price > 4.00 for price in prices):
        return False
    if max(prices) - min(prices) > 0.90:
        return False
    implied_sum = sum(1 / price for price in prices)
    return 0.98 <= implied_sum <= 1.30


def _devig_balance_distance(values: list[float]) -> float:
    if len(values) != 2:
        return 999.0
    implied = [1 / value for value in values if value > 0]
    total = sum(implied)
    if len(implied) != 2 or total <= 0:
        return 999.0
    return round(abs((implied[0] / total) - 0.5), 6)


def _normalize_side(value: Any) -> str:
    text = str(value or "").upper().replace(" ", "_")
    if text in {"HOME", "HOME_HANDICAP"} or text.startswith("HOME_"):
        return "HOME"
    if text in {"AWAY", "AWAY_HANDICAP"} or text.startswith("AWAY_"):
        return "AWAY"
    return text


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return format(normalized, "f")


def _json_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value
