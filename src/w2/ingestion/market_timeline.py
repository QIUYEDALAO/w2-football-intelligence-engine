from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

MARKET_TIMELINE_SCHEMA_VERSION = "w2.market_timeline.v1"
DEFAULT_TIMELINE_DIR = Path("runtime/market_timeline_snapshots")
CHECKPOINTS = ("opening", "T-24h", "T-12h", "T-6h", "T-3h", "T-1h", "lock")
AUTO_CHECKPOINT_GRACE = timedelta(minutes=20)
AUTO_LOCK_WINDOW = timedelta(hours=1)
BALANCED_MAINLINE_MAX_DISTANCE = 0.06
BALANCED_MAINLINE_MIN_DELTA = 0.03

_CHECKPOINT_OFFSETS = {
    "T-24h": timedelta(hours=24),
    "T-12h": timedelta(hours=12),
    "T-6h": timedelta(hours=6),
    "T-3h": timedelta(hours=3),
    "T-1h": timedelta(hours=1),
}


@dataclass(frozen=True, kw_only=True)
class TimelineWriteResult:
    written: bool
    status: str
    path: Path
    snapshot: dict[str, Any] | None = None


@dataclass(frozen=True, kw_only=True)
class SnapshotSelectionResult:
    snapshot: dict[str, Any] | None
    reason: str | None = None


def parse_utc(value: Any) -> datetime | None:
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


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timeline_path(root: Path, fixture_id: str) -> Path:
    return root / f"{fixture_id}.json"


def due_checkpoints(kickoff: datetime, now: datetime, checkpoint: str) -> list[str]:
    if checkpoint != "auto":
        return [checkpoint] if checkpoint in CHECKPOINTS else []
    due = ["opening"]
    kickoff_utc = kickoff.astimezone(UTC)
    now_utc = now.astimezone(UTC)
    for item, offset in _CHECKPOINT_OFFSETS.items():
        target = kickoff_utc - offset
        if target <= now_utc <= target + AUTO_CHECKPOINT_GRACE:
            due.append(item)
    if kickoff_utc - AUTO_LOCK_WINDOW <= now_utc < kickoff_utc:
        due.append("lock")
    return list(dict.fromkeys(due))


def select_mainline_snapshot(
    *,
    observations: list[dict[str, Any]],
    fixture_id: str,
    kickoff: datetime,
    checkpoint: str,
    market: str,
    generated_at: datetime | None = None,
    lock_max_age_minutes: int = 60,
) -> dict[str, Any] | None:
    return select_mainline_snapshot_result(
        observations=observations,
        fixture_id=fixture_id,
        kickoff=kickoff,
        checkpoint=checkpoint,
        market=market,
        generated_at=generated_at,
        lock_max_age_minutes=lock_max_age_minutes,
    ).snapshot


def select_mainline_snapshot_result(
    *,
    observations: list[dict[str, Any]],
    fixture_id: str,
    kickoff: datetime,
    checkpoint: str,
    market: str,
    generated_at: datetime | None = None,
    lock_max_age_minutes: int = 60,
) -> SnapshotSelectionResult:
    if checkpoint not in CHECKPOINTS:
        return SnapshotSelectionResult(snapshot=None, reason="NO_OBSERVATION")
    kickoff_utc = kickoff.astimezone(UTC)
    target = _checkpoint_target(checkpoint=checkpoint, kickoff=kickoff_utc)
    groups = _market_groups(
        observations=observations,
        fixture_id=fixture_id,
        market=market,
        target=target,
        kickoff=kickoff_utc,
    )
    if not groups:
        return SnapshotSelectionResult(
            snapshot=None,
            reason=_missing_snapshot_reason(
                observations=observations,
                fixture_id=fixture_id,
                market=market,
                target=target,
                kickoff=kickoff_utc,
            ),
        )
    if checkpoint == "lock":
        fresh_after = kickoff_utc - timedelta(minutes=max(lock_max_age_minutes, 0))
        groups = [item for item in groups if item["captured_at"] >= fresh_after]
        if not groups:
            return SnapshotSelectionResult(
                snapshot=None,
                reason="NO_FRESH_LOCK_OBSERVATION",
            )
    selected = _select_mainline_group(groups, market=market, checkpoint=checkpoint)
    captured_at = selected["captured_at"]
    line = selected["line"]
    sides = selected["sides"]
    source = {
        "bookmaker_count": selected["bookmaker_count"],
        "bookmakers": sorted(selected["bookmakers"]),
        "source_payload_ids": sorted(selected["source_payload_ids"]),
    }
    snapshot: dict[str, Any] = {
        "schema_version": MARKET_TIMELINE_SCHEMA_VERSION,
        "fixture_id": fixture_id,
        "checkpoint": checkpoint,
        "market": market,
        "as_of": iso_z(captured_at),
        "kickoff_utc": iso_z(kickoff_utc),
        "line": _json_number(line),
        "bookmaker_count": selected["bookmaker_count"],
        "source_payload_id": ",".join(sorted(selected["source_payload_ids"])) or None,
        "provider": selected["provider"],
        "immutable": True,
        "generated_at": iso_z(generated_at or datetime.now(UTC)),
    }
    if market == "ASIAN_HANDICAP":
        snapshot["selection_policy"] = selected.get(
            "selection_policy",
            "latest_bucket_ladder_balance_same_bookmaker_pair",
        )
        if selected.get("selection_warning"):
            snapshot["selection_warning"] = selected.get("selection_warning")
        snapshot["candidate_lines"] = selected.get("candidate_lines", [])
        snapshot["rejected_lines"] = selected.get("rejected_lines", [])
    if market == "ASIAN_HANDICAP":
        snapshot["home_price"] = _json_number(sides["HOME"]["decimal_odds"])
        snapshot["away_price"] = _json_number(sides["AWAY"]["decimal_odds"])
    else:
        snapshot["over_price"] = _json_number(sides["OVER"]["decimal_odds"])
        snapshot["under_price"] = _json_number(sides["UNDER"]["decimal_odds"])
    snapshot["source_hash"] = _source_hash({**snapshot, "source": source})
    return SnapshotSelectionResult(snapshot=snapshot)


def write_timeline_snapshot(
    *,
    root: Path,
    fixture_id: str,
    kickoff: datetime,
    snapshot: dict[str, Any],
) -> TimelineWriteResult:
    path = timeline_path(root, fixture_id)
    as_of = parse_utc(snapshot.get("as_of"))
    if as_of is None or as_of >= kickoff.astimezone(UTC):
        return TimelineWriteResult(
            written=False,
            status="POST_KICKOFF_AS_OF_REJECTED",
            path=path,
            snapshot=snapshot,
        )
    existing = load_timeline(path)
    if not existing:
        existing = {
            "schema_version": MARKET_TIMELINE_SCHEMA_VERSION,
            "fixture_id": fixture_id,
            "kickoff_utc": iso_z(kickoff),
            "snapshots": [],
        }
    snapshots = existing.setdefault("snapshots", [])
    if not isinstance(snapshots, list):
        return TimelineWriteResult(
            written=False,
            status="INVALID_EXISTING_TIMELINE",
            path=path,
            snapshot=snapshot,
        )
    for item in snapshots:
        if not isinstance(item, dict):
            continue
        if item.get("checkpoint") == snapshot.get("checkpoint") and item.get(
            "market"
        ) == snapshot.get("market"):
            if item.get("source_hash") == snapshot.get("source_hash"):
                return TimelineWriteResult(
                    written=False,
                    status="ALREADY_LOCKED",
                    path=path,
                    snapshot=item,
                )
            if item.get("immutable") is True:
                return TimelineWriteResult(
                    written=False,
                    status="IMMUTABLE_CONFLICT",
                    path=path,
                    snapshot=item,
                )
    snapshots.append(snapshot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, sort_keys=True) + "\n", encoding="utf-8")
    return TimelineWriteResult(written=True, status="WRITTEN", path=path, snapshot=snapshot)


def load_timeline(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def validate_timeline_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != MARKET_TIMELINE_SCHEMA_VERSION:
        errors.append("INVALID_SCHEMA_VERSION")
    fixture_id = str(payload.get("fixture_id") or "")
    if not fixture_id:
        errors.append("MISSING_FIXTURE_ID")
    kickoff = parse_utc(payload.get("kickoff_utc"))
    if kickoff is None:
        errors.append("MISSING_KICKOFF_UTC")
    snapshots = payload.get("snapshots")
    if not isinstance(snapshots, list):
        return [*errors, "MISSING_SNAPSHOTS"]
    seen: set[tuple[str, str]] = set()
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            errors.append("INVALID_SNAPSHOT")
            continue
        checkpoint = str(snapshot.get("checkpoint") or "")
        market = str(snapshot.get("market") or "")
        if checkpoint not in CHECKPOINTS:
            errors.append("INVALID_CHECKPOINT")
        if market not in {"ASIAN_HANDICAP", "TOTALS"}:
            errors.append("INVALID_MARKET")
        key = (checkpoint, market)
        if key in seen:
            errors.append("DUPLICATE_CHECKPOINT_MARKET")
        seen.add(key)
        as_of = parse_utc(snapshot.get("as_of"))
        if as_of is None:
            errors.append("MISSING_AS_OF")
        elif kickoff is not None and as_of >= kickoff:
            errors.append("POST_KICKOFF_AS_OF")
        if snapshot.get("immutable") is not True:
            errors.append("SNAPSHOT_NOT_IMMUTABLE")
        if not snapshot.get("source_hash"):
            errors.append("MISSING_SOURCE_HASH")
        if market == "ASIAN_HANDICAP":
            if snapshot.get("home_price") is None or snapshot.get("away_price") is None:
                errors.append("MISSING_AH_PRICES")
        if market == "TOTALS":
            if snapshot.get("over_price") is None or snapshot.get("under_price") is None:
                errors.append("MISSING_TOTAL_PRICES")
    return list(dict.fromkeys(errors))


def find_lock_snapshot(
    *,
    root: Path,
    fixture_id: str,
    kickoff: datetime | None = None,
    market: str = "ASIAN_HANDICAP",
) -> dict[str, Any] | None:
    payload = load_timeline(timeline_path(root, fixture_id))
    snapshots = payload.get("snapshots")
    if not isinstance(snapshots, list):
        return None
    resolved_kickoff = kickoff or parse_utc(payload.get("kickoff_utc"))
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        if snapshot.get("checkpoint") != "lock" or snapshot.get("market") != market:
            continue
        if snapshot.get("immutable") is not True:
            continue
        as_of = parse_utc(snapshot.get("as_of"))
        if as_of is None or (resolved_kickoff is not None and as_of >= resolved_kickoff):
            continue
        if market == "ASIAN_HANDICAP" and (
            snapshot.get("home_price") is None or snapshot.get("away_price") is None
        ):
            continue
        return snapshot
    return None


def _checkpoint_target(*, checkpoint: str, kickoff: datetime) -> datetime:
    if checkpoint == "opening":
        return kickoff
    if checkpoint == "lock":
        return kickoff
    return kickoff - _CHECKPOINT_OFFSETS[checkpoint]


def _market_groups(
    *,
    observations: list[dict[str, Any]],
    fixture_id: str,
    market: str,
    target: datetime,
    kickoff: datetime,
) -> list[dict[str, Any]]:
    required = {"HOME", "AWAY"} if market == "ASIAN_HANDICAP" else {"OVER", "UNDER"}
    grouped: dict[tuple[datetime, str, str], dict[str, Any]] = {}
    for row in observations:
        if str(row.get("fixture_id")) != fixture_id:
            continue
        if _normalize_market(row.get("canonical_market") or row.get("market")) != market:
            continue
        captured_at = parse_utc(row.get("captured_at") or row.get("captured_at_utc"))
        if captured_at is None or captured_at > target or captured_at >= kickoff:
            continue
        side = _normalize_selection(row.get("selection") or row.get("canonical_selection"))
        if side not in required:
            continue
        decimal_odds = _float_or_none(row.get("decimal_odds") or row.get("executable_odds"))
        line = _float_or_none(row.get("line"))
        if decimal_odds is None or line is None:
            continue
        bookmaker = str(
            row.get("bookmaker_id") or row.get("bookmaker") or row.get("bookmaker_name") or ""
        )
        if not bookmaker:
            continue
        group_line = abs(line) if market == "ASIAN_HANDICAP" else line
        key = (captured_at, f"{group_line:.4f}", bookmaker)
        group = grouped.setdefault(
            key,
            {
                "captured_at": captured_at,
                "line": -group_line if market == "ASIAN_HANDICAP" else line,
                "sides": {},
                "bookmakers": set(),
                "source_payload_ids": set(),
                "provider": row.get("provider") or row.get("source") or "read_model",
            },
        )
        if market == "ASIAN_HANDICAP" and side == "HOME":
            group["line"] = line
        group["bookmakers"].add(bookmaker)
        source_payload_id = (
            row.get("raw_payload_sha256") or row.get("source_payload_id") or row.get("sha256")
        )
        if source_payload_id:
            group["source_payload_ids"].add(str(source_payload_id))
        current_side = group["sides"].get(side)
        if current_side is None or decimal_odds > current_side["decimal_odds"]:
            group["sides"][side] = {"decimal_odds": decimal_odds, "bookmaker": bookmaker}
    complete: list[dict[str, Any]] = []
    for group in grouped.values():
        if set(group["sides"]) >= required and _valid_two_way_price_pair(
            market=market,
            sides=group["sides"],
            required=required,
        ):
            group["bookmaker_count"] = len(group["bookmakers"]) or 1
            group["balance_gap"] = _price_balance_gap(group["sides"], required)
            group["balance_distance"] = _devig_balance_distance(group["sides"], required)
            group["mid_distance"] = _price_mid_distance(group["sides"], required)
            group["implied_sum"] = _implied_sum(group["sides"], required)
            complete.append(group)
    return complete


def _select_mainline_group(
    groups: list[dict[str, Any]],
    *,
    market: str,
    checkpoint: str,
) -> dict[str, Any]:
    if market != "ASIAN_HANDICAP":
        return (
            min(groups, key=_opening_sort_key)
            if checkpoint == "opening"
            else max(groups, key=_latest_sort_key)
        )
    bucket_at = (
        min(group["captured_at"] for group in groups)
        if checkpoint == "opening"
        else max(group["captured_at"] for group in groups)
    )
    bucket = [group for group in groups if group["captured_at"] == bucket_at]
    by_line: dict[float, list[dict[str, Any]]] = {}
    for group in bucket:
        line = round(float(group["line"]), 4)
        by_line.setdefault(line, []).append(group)
    candidate_lines = [
        _line_candidate_summary(line, line_groups)
        for line, line_groups in by_line.items()
    ]
    max_bookmaker_count = max(int(item["bookmaker_count"]) for item in candidate_lines)
    consensus_floor = max_bookmaker_count
    eligible_lines = [
        item for item in candidate_lines if int(item["bookmaker_count"]) == max_bookmaker_count
    ] or candidate_lines
    eligible_lines.sort(
        key=lambda item: (
            -int(item["bookmaker_count"]),
            float(item["balance_distance"]),
            float(item["price_gap"]),
            float(item["mid_distance"]),
            abs(float(item["line"])),
        )
    )
    selected_summary = eligible_lines[0]
    selection_warning = selected_summary.get("selection_warning")
    selected_line = float(selected_summary["line"])
    selected_groups = by_line[round(selected_line, 4)]
    selected = min(
        selected_groups,
        key=lambda group: (
            float(group.get("balance_distance") or 999.0),
            abs(float(group.get("balance_gap") or 999.0) - float(selected_summary["price_gap"])),
            float(group.get("mid_distance") or 999.0),
            str(next(iter(group.get("bookmakers") or [""]))),
        ),
    )
    selected["bookmaker_count"] = int(selected_summary["bookmaker_count"])
    selected["selection_policy"] = "latest_bucket_ladder_balance_same_bookmaker_pair"
    if selection_warning:
        selected["selection_warning"] = selection_warning
    candidate_order = sorted(
        candidate_lines,
        key=lambda item: (
            0 if float(item["line"]) == selected_line else 1,
            -int(item["bookmaker_count"]),
            float(item["balance_distance"]),
            float(item["price_gap"]),
            float(item["mid_distance"]),
            abs(float(item["line"])),
        ),
    )
    selected["candidate_lines"] = [
        {
            **item,
            "selection_rank": index + 1,
            "bookmaker_consensus_floor": consensus_floor,
            "consensus_eligible": int(item["bookmaker_count"]) >= consensus_floor,
            "balanced_override_eligible": False,
            **({"selection_warning": selection_warning} if selection_warning else {}),
        }
        for index, item in enumerate(candidate_order)
    ]
    selected["rejected_lines"] = [
        {
            "line": item["line"],
            "reason": "LOWER_BOOKMAKER_CONSENSUS"
            if int(item["bookmaker_count"]) < consensus_floor
            else "TIE_BREAK_LOWER_LADDER_BALANCE",
        }
        for item in candidate_lines
        if float(item["line"]) != selected_line
    ]
    return selected


def _line_candidate_summary(line: float, groups: list[dict[str, Any]]) -> dict[str, Any]:
    home_prices = [float(group["sides"]["HOME"]["decimal_odds"]) for group in groups]
    away_prices = [float(group["sides"]["AWAY"]["decimal_odds"]) for group in groups]
    price_gaps = [float(group.get("balance_gap") or 999.0) for group in groups]
    balance_distances = [float(group.get("balance_distance") or 999.0) for group in groups]
    mid_distances = [float(group.get("mid_distance") or 999.0) for group in groups]
    implied_sums = [float(group.get("implied_sum") or 0.0) for group in groups]
    bookmakers = sorted(
        {
            str(bookmaker)
            for group in groups
            for bookmaker in group.get("bookmakers", set())
        }
    )
    return {
        "line": _json_number(float(line)),
        "home_price": _json_number(_median(home_prices)),
        "away_price": _json_number(_median(away_prices)),
        "median_home_price": _json_number(_median(home_prices)),
        "median_away_price": _json_number(_median(away_prices)),
        "bookmaker_count": len(bookmakers) or len(groups),
        "bookmakers": bookmakers,
        "captured_at": iso_z(groups[0]["captured_at"]),
        "as_of": iso_z(groups[0]["captured_at"]),
        "implied_sum": round(_median(implied_sums), 6),
        "balance_distance": round(_median(balance_distances), 6),
        "price_gap": round(_median(price_gaps), 6),
        "mid_distance": round(_median(mid_distances), 6),
        "selection_policy": "latest_bucket_ladder_balance_same_bookmaker_pair",
    }


def _bookmaker_consensus_floor(max_bookmaker_count: int) -> int:
    if max_bookmaker_count <= 1:
        return 1
    return max(2, max_bookmaker_count - 2)


def _balanced_override_candidate(candidate_lines: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidate_lines:
        return None
    ordered = sorted(
        candidate_lines,
        key=lambda item: (
            float(item["balance_distance"]),
            float(item["price_gap"]),
            float(item["mid_distance"]),
            -int(item["bookmaker_count"]),
            abs(float(item["line"])),
        ),
    )
    best = ordered[0]
    second_distance = float(ordered[1]["balance_distance"]) if len(ordered) > 1 else 999.0
    best_distance = float(best["balance_distance"])
    if (
        int(best["bookmaker_count"]) >= 1
        and best_distance <= BALANCED_MAINLINE_MAX_DISTANCE
        and second_distance - best_distance >= BALANCED_MAINLINE_MIN_DELTA
    ):
        return best
    return None


def _valid_two_way_price_pair(
    *,
    market: str,
    sides: dict[str, dict[str, Any]],
    required: set[str],
) -> bool:
    prices = [_float_or_none(sides.get(side, {}).get("decimal_odds")) for side in required]
    if any(price is None for price in prices):
        return False
    values = [float(price) for price in prices if price is not None]
    if any(price < 1.40 or price > 4.00 for price in values):
        return False
    if max(values) - min(values) > 0.90:
        return False
    implied_sum = sum(1 / price for price in values)
    if not 0.98 <= implied_sum <= 1.30:
        return False
    if market == "ASIAN_HANDICAP" and required != {"HOME", "AWAY"}:
        return False
    if market == "TOTALS" and required != {"OVER", "UNDER"}:
        return False
    return True


def _price_balance_gap(
    sides: dict[str, dict[str, Any]],
    required: set[str],
) -> float:
    values = [
        float(sides[side]["decimal_odds"])
        for side in sorted(required)
        if side in sides and _float_or_none(sides[side].get("decimal_odds")) is not None
    ]
    return round(max(values) - min(values), 6) if values else 999.0


def _devig_balance_distance(
    sides: dict[str, dict[str, Any]],
    required: set[str],
) -> float:
    values = [
        float(sides[side]["decimal_odds"])
        for side in sorted(required)
        if side in sides and _float_or_none(sides[side].get("decimal_odds")) is not None
    ]
    if len(values) != 2:
        return 999.0
    implied = [1 / value for value in values if value > 0]
    total = sum(implied)
    if len(implied) != 2 or total <= 0:
        return 999.0
    return round(abs((implied[0] / total) - 0.5), 6)


def _price_mid_distance(
    sides: dict[str, dict[str, Any]],
    required: set[str],
) -> float:
    values = [
        float(sides[side]["decimal_odds"])
        for side in sorted(required)
        if side in sides and _float_or_none(sides[side].get("decimal_odds")) is not None
    ]
    if not values:
        return 999.0
    return round(abs((sum(values) / len(values)) - 1.90), 6)


def _implied_sum(
    sides: dict[str, dict[str, Any]],
    required: set[str],
) -> float:
    values = [
        float(sides[side]["decimal_odds"])
        for side in sorted(required)
        if side in sides and _float_or_none(sides[side].get("decimal_odds")) is not None
    ]
    return round(sum(1 / value for value in values), 6) if values else 0.0


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _missing_snapshot_reason(
    *,
    observations: list[dict[str, Any]],
    fixture_id: str,
    market: str,
    target: datetime,
    kickoff: datetime,
) -> str:
    required = {"HOME", "AWAY"} if market == "ASIAN_HANDICAP" else {"OVER", "UNDER"}
    saw_relevant = False
    saw_post_kickoff = False
    grouped_sides: dict[tuple[datetime, str], set[str]] = {}
    for row in observations:
        if str(row.get("fixture_id")) != fixture_id:
            continue
        if _normalize_market(row.get("canonical_market") or row.get("market")) != market:
            continue
        captured_at = parse_utc(row.get("captured_at") or row.get("captured_at_utc"))
        if captured_at is None:
            continue
        saw_relevant = True
        if captured_at >= kickoff:
            saw_post_kickoff = True
            continue
        if captured_at > target:
            continue
        side = _normalize_selection(row.get("selection") or row.get("canonical_selection"))
        decimal_odds = _float_or_none(row.get("decimal_odds") or row.get("executable_odds"))
        line = _float_or_none(row.get("line"))
        if side not in required or decimal_odds is None or line is None:
            continue
        group_line = abs(line) if market == "ASIAN_HANDICAP" else line
        grouped_sides.setdefault((captured_at, f"{group_line:.4f}"), set()).add(side)
    if any(sides and sides < required for sides in grouped_sides.values()):
        return "INCOMPLETE_SIDES"
    if saw_post_kickoff and not grouped_sides:
        return "POST_KICKOFF_REJECTED"
    if saw_relevant:
        return "INCOMPLETE_SIDES"
    return "NO_OBSERVATION"


def _normalize_market(value: Any) -> str:
    text = str(value or "").upper().replace(" ", "_")
    if text in {"AH", "ASIAN_HANDICAP", "HANDICAP"}:
        return "ASIAN_HANDICAP"
    if text in {"OU", "TOTALS", "GOALS_OVER_UNDER", "OVER_UNDER"}:
        return "TOTALS"
    return text


def _normalize_selection(value: Any) -> str:
    text = str(value or "").upper().replace(" ", "_")
    if text in {"HOME", "HOME_HANDICAP"} or text.startswith("HOME_"):
        return "HOME"
    if text in {"AWAY", "AWAY_HANDICAP"} or text.startswith("AWAY_"):
        return "AWAY"
    if text.startswith("OVER"):
        return "OVER"
    if text.startswith("UNDER"):
        return "UNDER"
    return text


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_number(value: float) -> int | float:
    if value.is_integer():
        return int(value)
    return value


def _opening_sort_key(group: dict[str, Any]) -> tuple[datetime, float, float, int]:
    return (
        group["captured_at"],
        float(group.get("balance_gap") or 999.0),
        float(group.get("mid_distance") or 999.0),
        -int(group["bookmaker_count"]),
    )


def _latest_sort_key(group: dict[str, Any]) -> tuple[datetime, float, float, int]:
    return (
        group["captured_at"],
        -float(group.get("balance_gap") or 999.0),
        -float(group.get("mid_distance") or 999.0),
        int(group["bookmaker_count"]),
    )


def _source_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
