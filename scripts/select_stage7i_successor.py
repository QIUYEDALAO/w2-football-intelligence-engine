#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from w2.competitions.registry import CompetitionRegistry

RUN01_ARCHIVE_FIXTURE = "1489401"
DEFAULT_GLOBAL_LOCK = Path("/opt/w2/shared/runtime/stage7i/observer-global.lock")
DEFAULT_RUNTIME_ROOT = Path("/opt/w2/shared/runtime/stage7i")
UTC = timezone.utc  # noqa: UP017 - local python3 can be 3.9 while project runtime is 3.12.


class SelectionError(Exception):
    pass


def parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise SelectionError(f"{field} must be a non-empty UTC ISO string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SelectionError(f"{field} is not ISO-8601: {value}") from exc
    if parsed.tzinfo is None:
        raise SelectionError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def validate_localhost_api(url: str) -> str:
    allowed = ("http://127.0.0.1:", "http://localhost:")
    if not url.startswith(allowed):
        raise SelectionError("api-base must be localhost")
    return url.rstrip("/")


def load_manifest(args: argparse.Namespace) -> dict[str, Any]:
    path = args.candidate_manifest or args.input_json
    if not path:
        validate_localhost_api(args.api_base)
        raise SelectionError(
            "candidate manifest required; build it with build_stage7i_successor_candidates.py"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SelectionError("candidate manifest must be a JSON object")
    if payload.get("source") != "W2_STAGING_PROVIDER_DATA":
        raise SelectionError("candidate manifest source must be W2_STAGING_PROVIDER_DATA")
    if payload.get("candidate") is not False or payload.get("formal_recommendation") is not False:
        raise SelectionError("candidate manifest must keep candidate/formal false")
    if "candidates" not in payload:
        raise SelectionError(
            "candidate manifest required; FixtureSummary response is not sufficient"
        )
    return payload


def global_lock_active(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open("r+", encoding="utf-8") as handle:
        locked_here = False
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked_here = True
        except BlockingIOError:
            return True
        finally:
            if locked_here:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
    return False


def process_is_active(pid: int) -> bool:
    if pid <= 0:
        return False
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "pid="],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def legacy_observer_active(runtime_root: Path) -> bool:
    if not runtime_root.exists():
        return False
    for path in runtime_root.rglob("observer.pid"):
        try:
            pid = int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        if process_is_active(pid):
            return True
    return False


def iter_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("candidates")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    raise SelectionError("candidate manifest must contain a candidates list")


def reject(reason: str) -> dict[str, str]:
    return {"reason": reason}


def fixture_competition_id(item: dict[str, Any]) -> str:
    return str(
        item.get("competition_id")
        or item.get("league_id")
        or item.get("competition", {}).get("id")
        or item.get("league", {}).get("id")
        or ""
    )


def evaluate_candidate(
    item: dict[str, Any],
    *,
    now: datetime,
    run_end: datetime,
    min_pre: timedelta,
    min_post: timedelta,
) -> tuple[dict[str, Any] | None, list[str]]:
    reasons: list[str] = []
    fixture_id = str(item.get("fixture_id") or item.get("id") or "")
    competition_id = fixture_competition_id(item)
    if not fixture_id:
        reasons.append("FIXTURE_ID_MISSING")
    if not competition_id or not CompetitionRegistry().is_enabled(competition_id):
        reasons.append("COMPETITION_NOT_WHITELISTED")
    if fixture_id == RUN01_ARCHIVE_FIXTURE:
        reasons.append("ARCHIVED_FIXTURE")
    if item.get("status") != "NS":
        reasons.append("STATUS_NOT_NS")
    try:
        kickoff = parse_utc(item.get("scheduled_kickoff_utc") or item.get("kickoff_utc"), "kickoff")
    except SelectionError:
        reasons.append("KICKOFF_INVALID")
        kickoff = now
    if kickoff <= now + min_pre:
        reasons.append("PRE_MATCH_LEAD_INSUFFICIENT")
    if kickoff >= run_end - min_post:
        reasons.append("POST_KICKOFF_TAIL_INSUFFICIENT")
    mapping = item.get("provider_mapping")
    if not isinstance(mapping, dict) or mapping.get("reliable") is not True:
        reasons.append("PROVIDER_MAPPING_MISSING")
    elif mapping.get("conflict") is True:
        reasons.append("PROVIDER_MAPPING_CONFLICT")
    else:
        if not mapping.get("source"):
            reasons.append("PROVIDER_MAPPING_SOURCE_MISSING")
        if not mapping.get("evidence_sha256"):
            reasons.append("PROVIDER_MAPPING_EVIDENCE_SHA_MISSING")
    market = item.get("market_observation")
    if not isinstance(market, dict):
        reasons.append("MARKET_OBSERVATION_MISSING")
        captured = now
    else:
        try:
            captured = parse_utc(market.get("captured_at_utc"), "market captured_at")
            if captured >= now:
                reasons.append("MARKET_CAPTURED_AT_NOT_BEFORE_SELECTION")
        except SelectionError:
            reasons.append("MARKET_CAPTURED_AT_INVALID")
            captured = now
        age_seconds = max(0, int((now - captured).total_seconds()))
        limit = market.get("freshness_limit_seconds")
        if not isinstance(limit, int) or limit <= 0:
            reasons.append("MARKET_FRESHNESS_POLICY_MISSING")
        elif age_seconds > limit:
            reasons.append("MARKET_STALE")
        if not market.get("source") or not market.get("provenance"):
            reasons.append("MARKET_SOURCE_MISSING")
        if not market.get("evidence_sha256"):
            reasons.append("MARKET_EVIDENCE_SHA_MISSING")
        if market.get("live") is True:
            reasons.append("MARKET_LIVE")
        if market.get("suspended") is True:
            reasons.append("MARKET_SUSPENDED")
        if int(market.get("bookmaker_count", 0)) <= 0:
            reasons.append("MARKET_BOOKMAKER_COVERAGE_MISSING")
    if reasons:
        return None, reasons
    selected = {
        "fixture_id": fixture_id,
        "competition_id": competition_id,
        "status": item["status"],
        "scheduled_kickoff_utc": iso(kickoff),
        "provider_mapping": mapping,
        "market_observation": {
            **market,
            "captured_at_utc": iso(captured),
        },
        "selection_score": {
            "market_freshness_seconds": int((now - captured).total_seconds()),
            "bookmaker_count": int(market.get("bookmaker_count", 0)),
            "distance_from_window_center_seconds": int(
                abs((kickoff - (now + (run_end - now) / 2)).total_seconds())
            ),
        },
    }
    return selected, []


def build_selection(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    now = parse_utc(args.now_utc, "now_utc") if args.now_utc else datetime.now(UTC)
    run_end = now + timedelta(hours=args.observation_hours)
    payload = load_manifest(args)
    rejected: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    lock_active = global_lock_active(args.global_lock_path)
    legacy_active = legacy_observer_active(args.runtime_root)
    for item in iter_candidates(payload):
        fixture_id = str(item.get("fixture_id") or item.get("id") or "")
        if lock_active or legacy_active:
            rejected.append({"fixture_id": fixture_id, "reasons": ["ACTIVE_GLOBAL_OBSERVER_LOCK"]})
            if legacy_active:
                rejected[-1]["reasons"] = ["ACTIVE_STAGE7I_OBSERVER"]
            continue
        selected, reasons = evaluate_candidate(
            item,
            now=now,
            run_end=run_end,
            min_pre=timedelta(hours=args.min_pre_kickoff_hours),
            min_post=timedelta(hours=args.min_post_kickoff_hours),
        )
        if selected is None:
            rejected.append({"fixture_id": fixture_id, "reasons": reasons})
        else:
            eligible.append(selected)
    eligible.sort(
        key=lambda item: (
            item["selection_score"]["market_freshness_seconds"],
            -item["selection_score"]["bookmaker_count"],
            item["selection_score"]["distance_from_window_center_seconds"],
            item["fixture_id"],
        )
    )
    selected = eligible[0] if len(eligible) == 1 else None
    if len(eligible) > 1:
        selected = eligible[0]
        rejected.extend(
            {
                "fixture_id": item["fixture_id"],
                "reasons": ["LOWER_DETERMINISTIC_RANK"],
            }
            for item in eligible[1:]
        )
    result = {
        "generated_at_utc": iso(now),
        "source": "W2_STAGING_PROVIDER_DATA",
        "policy": {
            "observation_hours": args.observation_hours,
            "min_pre_kickoff_hours": args.min_pre_kickoff_hours,
            "min_post_kickoff_hours": args.min_post_kickoff_hours,
            "archive_fixture_excluded": RUN01_ARCHIVE_FIXTURE,
            "global_lock_path": str(args.global_lock_path),
            "runtime_root": str(args.runtime_root),
            "candidate_manifest_required": True,
            "enabled_competitions": sorted(CompetitionRegistry().enabled_ids()),
        },
        "selected_fixture": selected,
        "rejected_candidates": rejected,
        "candidate": False,
        "formal_recommendation": False,
    }
    if selected is None:
        result["blocker"] = "NO_ELIGIBLE_SUCCESSOR_FIXTURE"
        return 2, result
    return 0, result


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run select a Stage7I successor fixture.")
    parser.add_argument("--api-base", default="http://127.0.0.1:18000")
    parser.add_argument("--input-json", type=Path)
    parser.add_argument("--candidate-manifest", type=Path)
    parser.add_argument("--now-utc")
    parser.add_argument("--observation-hours", type=float, default=24)
    parser.add_argument("--min-pre-kickoff-hours", type=float, default=6)
    parser.add_argument("--min-post-kickoff-hours", type=float, default=6)
    parser.add_argument("--global-lock-path", type=Path, default=DEFAULT_GLOBAL_LOCK)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        code, payload = build_selection(args)
    except (OSError, json.JSONDecodeError, SelectionError) as exc:
        print(f"Stage7I successor selection FAIL: {exc}", file=sys.stderr)
        return 1
    if args.output:
        write_json_atomic(args.output, payload)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
