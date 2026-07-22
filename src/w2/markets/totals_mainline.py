from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any

from w2.markets.asian_handicap_scope import is_full_time_totals_observation

CANONICAL_TOTALS_MAINLINE_POLICY = "canonical_bookmaker_mainline_consensus_v1"
BALANCED_MAINLINE_MAX_DISTANCE = 0.06
BALANCED_MAINLINE_MIN_DELTA = 0.03


@dataclass(frozen=True, kw_only=True)
class CanonicalTotalsMainline:
    status: str
    line: Decimal | None = None
    captured_at: datetime | None = None
    provider: str | None = None
    over_price: float | None = None
    under_price: float | None = None
    complete_pair_bookmaker_count: int = 0
    bookmaker_vote_count: int = 0
    consensus_floor: int = 0
    side_prices: dict[str, float] | None = None
    side_lines: dict[str, str] | None = None
    candidate_lines: list[dict[str, Any]] | None = None
    rejected_lines: list[dict[str, Any]] | None = None
    selected_bookmakers: list[str] | None = None
    source_payload_ids: list[str] | None = None
    authoritative_quote_rows: dict[str, dict[str, Any]] | None = None
    authoritative_quote_rows_by_line: dict[str, dict[str, dict[str, Any]]] | None = None
    candidate_ladder_hash: str | None = None
    quarantined_count: int = 0
    quarantine_reasons: dict[str, int] | None = None


def select_canonical_totals_mainline(
    observations: list[dict[str, Any]],
    *,
    fixture_id: str,
    target: datetime,
    kickoff: datetime,
    opening: bool = False,
) -> CanonicalTotalsMainline:
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
        return CanonicalTotalsMainline(
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
    pairs, pair_quarantine = _complete_pairs(bucket)
    for reason, count in pair_quarantine.items():
        quarantine_reasons[reason] = quarantine_reasons.get(reason, 0) + count
    if not pairs:
        return CanonicalTotalsMainline(
            status="NO_BALANCED_MAINLINE",
            captured_at=bucket_at,
            quarantined_count=sum(quarantine_reasons.values()),
            quarantine_reasons=quarantine_reasons,
        )

    votes = _bookmaker_mainline_votes(pairs)
    votes_by_line: dict[Decimal, list[dict[str, Any]]] = {}
    pairs_by_line: dict[Decimal, list[dict[str, Any]]] = {}
    for pair in pairs:
        pairs_by_line.setdefault(Decimal(str(pair["line"])), []).append(pair)
    for vote in votes:
        votes_by_line.setdefault(Decimal(str(vote["line"])), []).append(vote)

    candidate_lines = [
        _line_summary(
            line=line,
            pairs=line_pairs,
            votes=votes_by_line.get(line, []),
            captured_at=bucket_at,
        )
        for line, line_pairs in pairs_by_line.items()
    ]
    max_vote_count = max(int(item["bookmaker_vote_count"]) for item in candidate_lines)
    consensus_floor = _bookmaker_consensus_floor(max_vote_count)
    eligible = [
        item for item in candidate_lines if int(item["bookmaker_vote_count"]) >= consensus_floor
    ]
    eligible.sort(key=_consensus_sort_key)
    selected_summary = eligible[0]
    override = _balanced_override_candidate(eligible)
    if override is not None:
        selected_summary = override

    selected_line = Decimal(str(selected_summary["line"]))
    selected_pairs = pairs_by_line[selected_line]
    representative = min(selected_pairs, key=_pair_sort_key)
    ordered = sorted(
        candidate_lines,
        key=lambda item: (
            0 if Decimal(str(item["line"])) == selected_line else 1,
            *_consensus_sort_key(item),
        ),
    )
    ladder = []
    rejected_lines = []
    for index, item in enumerate(ordered):
        line = Decimal(str(item["line"]))
        selected = line == selected_line
        reason = (
            None
            if selected
            else _rejection_reason(
                item=item,
                selected=selected_summary,
                consensus_floor=consensus_floor,
            )
        )
        row = {
            **item,
            "selection_rank": index + 1,
            "bookmaker_consensus_floor": consensus_floor,
            "consensus_eligible": int(item["bookmaker_vote_count"]) >= consensus_floor,
            "balanced_override_eligible": (
                override is not None and Decimal(str(override["line"])) == line
            ),
            "status": "SELECTED_MARKET_MAINLINE" if selected else "REJECTED",
            **({"reason": reason} if reason else {}),
        }
        ladder.append(row)
        if reason:
            rejected_lines.append({"line": row["line"], "reason": reason})

    ladder_hash = _hash_payload(ladder)
    selected_books = sorted(str(pair["bookmaker"]) for pair in selected_pairs)
    quote_rows_by_line = {
        _format_decimal(line): {
            "over": dict(representative_pair["sides"]["OVER"]["row"]),
            "under": dict(representative_pair["sides"]["UNDER"]["row"]),
        }
        for line, line_pairs in pairs_by_line.items()
        for representative_pair in [min(line_pairs, key=_pair_sort_key)]
    }
    source_payload_ids = sorted(
        {
            str(payload_id)
            for pair in selected_pairs
            for payload_id in pair.get("source_payload_ids", [])
            if payload_id
        }
    )
    return CanonicalTotalsMainline(
        status="READY",
        line=selected_line,
        captured_at=bucket_at,
        provider=str(representative.get("provider") or "read_model"),
        over_price=float(representative["over_price"]),
        under_price=float(representative["under_price"]),
        complete_pair_bookmaker_count=int(selected_summary["complete_pair_bookmaker_count"]),
        bookmaker_vote_count=int(selected_summary["bookmaker_vote_count"]),
        consensus_floor=consensus_floor,
        side_prices={
            "over": float(representative["over_price"]),
            "under": float(representative["under_price"]),
        },
        side_lines={
            "over": _format_decimal(selected_line),
            "under": _format_decimal(selected_line),
        },
        candidate_lines=ladder,
        rejected_lines=rejected_lines,
        selected_bookmakers=selected_books,
        source_payload_ids=source_payload_ids,
        authoritative_quote_rows={
            "over": dict(representative["sides"]["OVER"]["row"]),
            "under": dict(representative["sides"]["UNDER"]["row"]),
        },
        authoritative_quote_rows_by_line=quote_rows_by_line,
        candidate_ladder_hash=ladder_hash,
        quarantined_count=sum(quarantine_reasons.values()),
        quarantine_reasons=quarantine_reasons,
    )


def _quarantine_reason(row: dict[str, Any], *, fixture_id: str) -> str | None:
    if str(row.get("fixture_id")) != fixture_id:
        return "OTHER_FIXTURE"
    if str(row.get("canonical_market") or row.get("market") or "").upper() != "TOTALS":
        return "OTHER_MARKET"
    if row.get("suspended") or row.get("live"):
        return "SUSPENDED_OR_LIVE"
    if not is_full_time_totals_observation(row):
        return "NON_FULL_TIME_TOTALS"
    if _normalize_side(row.get("selection") or row.get("canonical_selection")) not in {
        "OVER",
        "UNDER",
    }:
        return "INVALID_TOTALS_SIDE"
    if _decimal(row.get("line")) is None:
        return "INVALID_TOTALS_LINE"
    if _float(row.get("decimal_odds") or row.get("executable_odds")) is None:
        return "INVALID_PRICE_PAIR"
    if not str(row.get("bookmaker_id") or row.get("bookmaker") or row.get("bookmaker_name") or ""):
        return "MISSING_BOOKMAKER"
    return None


def _complete_pairs(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    grouped: dict[tuple[str, Decimal], dict[str, dict[str, Any]]] = {}
    for row in rows:
        bookmaker = str(
            row.get("bookmaker_id") or row.get("bookmaker") or row.get("bookmaker_name") or ""
        )
        line = _decimal(row.get("line"))
        side = _normalize_side(row.get("selection") or row.get("canonical_selection"))
        if not bookmaker or line is None or side not in {"OVER", "UNDER"}:
            continue
        key = (bookmaker, line)
        current = grouped.setdefault(key, {}).get(side)
        price = _float(row.get("decimal_odds") or row.get("executable_odds"))
        current_price = (
            _float(current.get("decimal_odds") or current.get("executable_odds"))
            if current
            else None
        )
        if price is not None and (current_price is None or price > current_price):
            grouped[key][side] = row

    pairs: list[dict[str, Any]] = []
    quarantine: dict[str, int] = {}
    for (bookmaker, line), sides in grouped.items():
        if set(sides) != {"OVER", "UNDER"}:
            quarantine["PAIR_INCOMPLETE"] = quarantine.get("PAIR_INCOMPLETE", 0) + 1
            continue
        over_price = _float(
            sides["OVER"].get("decimal_odds") or sides["OVER"].get("executable_odds")
        )
        under_price = _float(
            sides["UNDER"].get("decimal_odds") or sides["UNDER"].get("executable_odds")
        )
        prices = [value for value in (over_price, under_price) if value is not None]
        if not _valid_price_pair(prices):
            quarantine["INVALID_PRICE_PAIR"] = quarantine.get("INVALID_PRICE_PAIR", 0) + 1
            continue
        source_payload_ids = sorted(
            {
                str(value)
                for row in sides.values()
                for value in (
                    row.get("raw_payload_sha256"),
                    row.get("source_payload_id"),
                    row.get("sha256"),
                )
                if value
            }
        )
        pairs.append(
            {
                "bookmaker": bookmaker,
                "line": line,
                "sides": {
                    "OVER": {"price": prices[0], "row": sides["OVER"]},
                    "UNDER": {"price": prices[1], "row": sides["UNDER"]},
                },
                "over_price": prices[0],
                "under_price": prices[1],
                "balance_distance": _devig_balance_distance(prices),
                "price_gap": round(abs(prices[0] - prices[1]), 6),
                "mid_distance": round(abs((sum(prices) / 2) - 1.90), 6),
                "implied_sum": round(sum(1 / value for value in prices), 6),
                "provider": sides["OVER"].get("provider") or "read_model",
                "source_payload_ids": source_payload_ids,
            }
        )
    return pairs, quarantine


def _bookmaker_mainline_votes(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_bookmaker: dict[str, list[dict[str, Any]]] = {}
    for pair in pairs:
        by_bookmaker.setdefault(str(pair["bookmaker"]), []).append(pair)
    return [min(bookmaker_pairs, key=_pair_sort_key) for bookmaker_pairs in by_bookmaker.values()]


def _line_summary(
    *,
    line: Decimal,
    pairs: list[dict[str, Any]],
    votes: list[dict[str, Any]],
    captured_at: datetime,
) -> dict[str, Any]:
    over_prices = [float(item["over_price"]) for item in pairs]
    under_prices = [float(item["under_price"]) for item in pairs]
    median_over = float(median(over_prices))
    median_under = float(median(under_prices))
    implied = [1 / median_over, 1 / median_under]
    implied_total = sum(implied)
    devig_over = implied[0] / implied_total
    devig_under = implied[1] / implied_total
    return {
        "line": _json_number(float(line)),
        "over_price": _json_number(median_over),
        "under_price": _json_number(median_under),
        "median_over_price": _json_number(median_over),
        "median_under_price": _json_number(median_under),
        "complete_pair_bookmaker_count": len(pairs),
        "bookmaker_count": len(pairs),
        "bookmaker_vote_count": len(votes),
        "bookmakers": sorted(str(item["bookmaker"]) for item in pairs),
        "voting_bookmakers": sorted(str(item["bookmaker"]) for item in votes),
        "devig_over_probability": round(devig_over, 6),
        "devig_under_probability": round(devig_under, 6),
        "implied_sum": round((1 / median_over) + (1 / median_under), 6),
        "balance_distance": round(abs(devig_over - 0.5), 6),
        "price_gap": round(abs(median_over - median_under), 6),
        "mid_distance": round(abs(((median_over + median_under) / 2) - 1.90), 6),
        "captured_at": _iso_z(captured_at),
        "as_of": _iso_z(captured_at),
        "selection_policy": CANONICAL_TOTALS_MAINLINE_POLICY,
        "observation_ids": sorted(
            {
                str(side["row"].get("observation_id"))
                for pair in pairs
                for side in pair["sides"].values()
                if side["row"].get("observation_id")
            }
        ),
        "source_payload_ids": sorted(
            {str(value) for pair in pairs for value in pair.get("source_payload_ids", []) if value}
        ),
    }


def _bookmaker_consensus_floor(max_vote_count: int) -> int:
    if max_vote_count <= 1:
        return 1
    return max(2, max_vote_count - 2)


def _balanced_override_candidate(
    eligible: list[dict[str, Any]],
) -> dict[str, Any] | None:
    ordered = sorted(
        eligible,
        key=lambda item: (
            float(item["balance_distance"]),
            float(item["price_gap"]),
            float(item["mid_distance"]),
            -int(item["bookmaker_vote_count"]),
            abs(float(item["line"])),
        ),
    )
    if len(ordered) < 2:
        return None
    best = ordered[0]
    improvement = float(ordered[1]["balance_distance"]) - float(best["balance_distance"])
    if (
        float(best["balance_distance"]) <= BALANCED_MAINLINE_MAX_DISTANCE
        and improvement >= BALANCED_MAINLINE_MIN_DELTA
    ):
        return best
    return None


def _rejection_reason(
    *,
    item: dict[str, Any],
    selected: dict[str, Any],
    consensus_floor: int,
) -> str:
    if int(item["bookmaker_vote_count"]) < consensus_floor:
        if float(item["balance_distance"]) < float(selected["balance_distance"]):
            return "MORE_BALANCED_BUT_BELOW_CONSENSUS_FLOOR"
        return "LOWER_BOOKMAKER_CONSENSUS"
    if int(item["bookmaker_vote_count"]) < int(selected["bookmaker_vote_count"]):
        return "LOWER_BOOKMAKER_CONSENSUS"
    return "TIE_BREAK_LOWER_LADDER_BALANCE"


def _consensus_sort_key(item: dict[str, Any]) -> tuple[int, float, float, float, float]:
    return (
        -int(item["bookmaker_vote_count"]),
        float(item["balance_distance"]),
        float(item["price_gap"]),
        float(item["mid_distance"]),
        abs(float(item["line"])),
    )


def _pair_sort_key(item: dict[str, Any]) -> tuple[float, float, float, float, str]:
    return (
        float(item["balance_distance"]),
        float(item["price_gap"]),
        float(item["mid_distance"]),
        abs(float(item["line"])),
        str(item["bookmaker"]),
    )


def _valid_price_pair(prices: list[float]) -> bool:
    if len(prices) != 2:
        return False
    if any(price < 1.40 or price > 4.00 for price in prices):
        return False
    if max(prices) - min(prices) > 0.90:
        return False
    implied_sum = sum(1 / price for price in prices)
    return 0.98 <= implied_sum <= 1.30


def _devig_balance_distance(prices: list[float]) -> float:
    implied = [1 / value for value in prices]
    total = sum(implied)
    return round(abs((implied[0] / total) - 0.5), 6)


def _normalize_side(value: Any) -> str:
    text = str(value or "").upper().replace(" ", "_")
    if text.startswith("OVER"):
        return "OVER"
    if text.startswith("UNDER"):
        return "UNDER"
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
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return format(normalized, "f")


def _json_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
