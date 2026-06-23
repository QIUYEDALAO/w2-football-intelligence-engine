#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

UTC = timezone.utc  # noqa: UP017 - local python3 can be 3.9 while project runtime is 3.12.
SOURCE = "W2_STAGING_PROVIDER_DATA"
DEFAULT_FRESHNESS_POLICY = "EXPLICIT_MARKET_EVIDENCE_LIMIT_SECONDS"


class CandidateBuildError(Exception):
    pass


def parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise CandidateBuildError(f"{field} must be a non-empty UTC ISO string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CandidateBuildError(f"{field} is not ISO-8601: {value}") from exc
    if parsed.tzinfo is None:
        raise CandidateBuildError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def evidence_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def validate_localhost_api(url: str) -> str:
    allowed = ("http://127.0.0.1:", "http://localhost:")
    if not url.startswith(allowed):
        raise CandidateBuildError("api-base must be localhost")
    return url.rstrip("/")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_fixture_list(api_base: str) -> dict[str, Any]:
    api = validate_localhost_api(api_base)
    request = Request(  # noqa: S310 - localhost-only guard above.
        f"{api}/v1/fixtures?status=NS&page_size=100&timezone=UTC",
        method="GET",
    )
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - localhost-only guard above.
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError) as exc:
        raise CandidateBuildError(f"localhost fixture request failed: {exc}") from exc


def list_from_payload(payload: Any, *, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise CandidateBuildError(f"payload must contain one of {', '.join(keys)}")


def key_fixture_id(item: dict[str, Any]) -> str:
    return str(item.get("fixture_id") or item.get("id") or "")


def index_by_fixture(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {key_fixture_id(item): item for item in items if key_fixture_id(item)}


def normalize_mapping(raw: dict[str, Any] | None) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(raw, dict):
        return None, ["PROVIDER_MAPPING_MISSING"]
    reasons: list[str] = []
    required = [
        "provider",
        "provider_fixture_id",
        "home_provider_team_id",
        "away_provider_team_id",
        "source",
        "confidence",
    ]
    for field in required:
        value = raw.get(field)
        if value is None or value == "":
            reasons.append(f"{field.upper()}_MISSING")
    confidence = float(raw.get("confidence", 0) or 0)
    if confidence < 0.8:
        reasons.append("PROVIDER_MAPPING_CONFIDENCE_INSUFFICIENT")
    if raw.get("conflict") is True:
        reasons.append("PROVIDER_MAPPING_CONFLICT")
    if raw.get("reliable") is not True:
        reasons.append("PROVIDER_MAPPING_NOT_RELIABLE")
    evidence_hash = str(raw.get("evidence_sha256") or evidence_sha256(raw))
    mapping = {
        "provider": str(raw.get("provider", "")),
        "provider_fixture_id": str(raw.get("provider_fixture_id", "")),
        "home_provider_team_id": str(raw.get("home_provider_team_id", "")),
        "away_provider_team_id": str(raw.get("away_provider_team_id", "")),
        "source": str(raw.get("source", "")),
        "confidence": confidence,
        "reliable": raw.get("reliable") is True,
        "conflict": raw.get("conflict") is True,
        "evidence_sha256": evidence_hash,
    }
    return mapping, reasons


def normalize_market(
    raw: dict[str, Any] | None,
    *,
    now: datetime,
) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(raw, dict):
        return None, ["MARKET_OBSERVATION_MISSING"]
    reasons: list[str] = []
    required = ["market", "captured_at_utc", "bookmaker_count", "source", "provenance"]
    for field in required:
        value = raw.get(field)
        if value is None or value == "":
            reasons.append(f"{field.upper()}_MISSING")
    try:
        captured = parse_utc(
            raw.get("captured_at_utc") or raw.get("captured_at"),
            "market.captured_at",
        )
        if captured >= now:
            reasons.append("MARKET_CAPTURED_AT_NOT_BEFORE_SELECTION")
    except CandidateBuildError:
        captured = now
        reasons.append("MARKET_CAPTURED_AT_INVALID")
    limit = raw.get("freshness_limit_seconds")
    if not isinstance(limit, int) or limit <= 0:
        reasons.append("MARKET_FRESHNESS_POLICY_MISSING")
        limit_seconds = 0
    else:
        limit_seconds = limit
    age_seconds = max(0, int((now - captured).total_seconds()))
    fresh = bool(limit_seconds and age_seconds <= limit_seconds)
    if not fresh:
        reasons.append("MARKET_STALE")
    if raw.get("live") is True:
        reasons.append("MARKET_LIVE")
    if raw.get("suspended") is True:
        reasons.append("MARKET_SUSPENDED")
    bookmaker_count = int(raw.get("bookmaker_count", 0) or 0)
    if bookmaker_count <= 0:
        reasons.append("MARKET_BOOKMAKER_COVERAGE_MISSING")
    evidence_hash = str(raw.get("evidence_sha256") or evidence_sha256(raw))
    market = {
        "market": str(raw.get("market", "")),
        "captured_at_utc": iso(captured),
        "bookmaker_count": bookmaker_count,
        "suspended": raw.get("suspended") is True,
        "live": raw.get("live") is True,
        "source": str(raw.get("source", "")),
        "provenance": raw.get("provenance"),
        "freshness_age_seconds": age_seconds,
        "freshness_limit_seconds": limit_seconds,
        "fresh": fresh,
        "freshness_policy": DEFAULT_FRESHNESS_POLICY,
        "evidence_sha256": evidence_hash,
    }
    return market, reasons


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    now = parse_utc(args.now_utc, "now_utc") if args.now_utc else datetime.now(UTC)
    fixtures_payload = (
        load_json(args.fixtures_input) if args.fixtures_input else fetch_fixture_list(args.api_base)
    )
    mappings_payload = load_json(args.mapping_input) if args.mapping_input else {"items": []}
    markets_payload = load_json(args.market_input) if args.market_input else {"items": []}
    fixtures = list_from_payload(fixtures_payload, keys=("items", "data", "fixtures", "candidates"))
    mappings = index_by_fixture(
        list_from_payload(mappings_payload, keys=("items", "data", "mappings"))
    )
    markets = index_by_fixture(
        list_from_payload(markets_payload, keys=("items", "data", "markets"))
    )
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for fixture in fixtures:
        fixture_id = key_fixture_id(fixture)
        reasons: list[str] = []
        if not fixture_id:
            reasons.append("FIXTURE_ID_MISSING")
        status = str(fixture.get("status") or "")
        if status != "NS":
            reasons.append("STATUS_NOT_NS")
        kickoff_value = fixture.get("scheduled_kickoff_utc") or fixture.get("kickoff_utc")
        try:
            kickoff = parse_utc(kickoff_value, "fixture.kickoff")
        except CandidateBuildError:
            kickoff = now
            reasons.append("KICKOFF_INVALID")
        mapping, mapping_reasons = normalize_mapping(mappings.get(fixture_id))
        market, market_reasons = normalize_market(markets.get(fixture_id), now=now)
        reasons.extend(mapping_reasons)
        reasons.extend(market_reasons)
        if reasons:
            rejected.append({"fixture_id": fixture_id, "reasons": sorted(set(reasons))})
            continue
        candidates.append(
            {
                "fixture_id": fixture_id,
                "status": status,
                "scheduled_kickoff_utc": iso(kickoff),
                "provider_mapping": mapping,
                "market_observation": market,
            }
        )
    return {
        "generated_at_utc": iso(now),
        "source": SOURCE,
        "source_revision": args.source_revision,
        "policy": {
            "candidate_manifest_required": True,
            "fixture_summary_is_not_candidate_manifest": True,
            "freshness_policy": DEFAULT_FRESHNESS_POLICY,
            "mapping_confidence_minimum": 0.8,
        },
        "candidates": candidates,
        "rejected_candidates": rejected,
        "candidate": False,
        "formal_recommendation": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Stage7I successor candidate manifest.")
    parser.add_argument("--api-base", default="http://127.0.0.1:18000")
    parser.add_argument("--fixtures-input", type=Path)
    parser.add_argument("--mapping-input", type=Path)
    parser.add_argument("--market-input", type=Path)
    parser.add_argument("--now-utc")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-revision", default="UNKNOWN")
    args = parser.parse_args()
    try:
        payload = build_manifest(args)
    except (OSError, json.JSONDecodeError, CandidateBuildError) as exc:
        print(f"Stage7I candidate manifest build FAIL: {exc}", file=sys.stderr)
        return 1
    if args.output:
        write_json_atomic(args.output, payload)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
