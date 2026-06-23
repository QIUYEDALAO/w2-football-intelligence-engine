#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_KEYS = {
    "provider",
    "provider_fixture_id",
    "competition",
    "kickoff_utc",
    "home_team_identity",
    "away_team_identity",
    "bookmaker",
    "market",
    "canonical_selection",
    "decimal_odds",
    "captured_at",
    "source_license",
    "final_result",
    "settlement_semantics",
    "source_payload_hash",
}


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def probe_the_odds_api(payload: dict[str, Any], payload_hash: str) -> dict[str, Any]:
    timestamp = payload.get("timestamp")
    events = payload.get("data")
    rows: list[dict[str, Any]] = []
    missing: set[str] = set()
    duplicate_keys: set[tuple[str, str, str, str, str | None, str]] = set()
    seen: set[tuple[str, str, str, str, str | None, str]] = set()
    if not isinstance(events, list):
        events = []
        missing.add("events")
    for event in events:
        if not isinstance(event, dict):
            continue
        fixture_id = str(event.get("id", ""))
        competition = event.get("sport_key") or event.get("sport_title")
        kickoff = event.get("commence_time")
        home = event.get("home_team")
        away = event.get("away_team")
        for bookmaker in event.get("bookmakers", []) or []:
            if not isinstance(bookmaker, dict):
                continue
            bookmaker_id = bookmaker.get("key") or bookmaker.get("title")
            provider_updated_at = bookmaker.get("last_update")
            for market in bookmaker.get("markets", []) or []:
                if not isinstance(market, dict):
                    continue
                market_key = str(market.get("key", ""))
                canonical_market = {
                    "h2h": "ONE_X_TWO",
                    "spreads": "ASIAN_HANDICAP",
                    "totals": "TOTALS",
                }.get(market_key, market_key.upper())
                market_updated_at = market.get("last_update") or provider_updated_at
                for outcome in market.get("outcomes", []) or []:
                    if not isinstance(outcome, dict):
                        continue
                    selection = str(outcome.get("name", ""))
                    line = outcome.get("point")
                    odds = outcome.get("price")
                    row = {
                        "provider": "the_odds_api",
                        "provider_fixture_id": fixture_id,
                        "competition": competition,
                        "kickoff_utc": kickoff,
                        "home_team_identity": home,
                        "away_team_identity": away,
                        "bookmaker": bookmaker_id,
                        "market": canonical_market,
                        "raw_market_label": market_key,
                        "canonical_selection": selection.upper().replace(" ", "_"),
                        "ah_ou_line": None if line is None else str(line),
                        "decimal_odds": None if odds is None else str(odds),
                        "suspended": None,
                        "live": False,
                        "provider_event_time": market_updated_at,
                        "captured_at": timestamp,
                        "ingested_at": None,
                        "opening_closing_semantics": "SNAPSHOT",
                        "stable_event_id": fixture_id,
                        "fixture_mapping_evidence": "provider_event_id_and_team_names",
                        "final_result": None,
                        "settlement_semantics": None,
                        "source_license": None,
                        "source_payload_hash": payload_hash,
                    }
                    for key in REQUIRED_KEYS:
                        if row.get(key) in (None, ""):
                            missing.add(key)
                    identity = (
                        row["provider_fixture_id"],
                        str(row["bookmaker"]),
                        row["market"],
                        row["canonical_selection"],
                        row["ah_ou_line"],
                        str(row["captured_at"]),
                    )
                    if identity in seen:
                        duplicate_keys.add(identity)
                    seen.add(identity)
                    rows.append(row)
    return {
        "provider": "the_odds_api",
        "payload_sha256": payload_hash,
        "schema_mappable": len(rows) > 0,
        "row_count": len(rows),
        "markets_seen": sorted({row["market"] for row in rows}),
        "missing_contract_fields": sorted(missing),
        "duplicate_identity_count": len(duplicate_keys),
        "raw_hash_available": True,
        "fixture_identity_available": all(row.get("provider_fixture_id") for row in rows),
        "bookmaker_identity_available": all(row.get("bookmaker") for row in rows),
        "captured_at_available": all(row.get("captured_at") for row in rows),
        "ah_line_available": any(
            row["market"] == "ASIAN_HANDICAP" and row.get("ah_ou_line") for row in rows
        ),
        "result_settlement_available": all(
            row.get("final_result") is not None and row.get("settlement_semantics") is not None
            for row in rows
        ),
        "formal_dataset_created": False,
        "candidate": False,
        "formal_recommendation": False,
    }


def probe_payload(path: Path, provider: str) -> dict[str, Any]:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    payload_hash = sha256_bytes(raw)
    if provider == "the_odds_api":
        return probe_the_odds_api(payload, payload_hash)
    raise ValueError(f"unsupported provider probe: {provider}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True, choices=("the_odds_api",))
    parser.add_argument("--sample", type=Path, required=True)
    args = parser.parse_args(argv)
    result = probe_payload(args.sample, args.provider)
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
