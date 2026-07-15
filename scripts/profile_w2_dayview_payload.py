#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode())


def profile(payload: dict[str, Any]) -> dict[str, Any]:
    cards = payload.get("cards") if isinstance(payload.get("cards"), list) else []
    sizes = [_bytes(card) for card in cards]
    groups = {
        "current_odds": ("current_odds",),
        "analysis_readiness": ("analysis_readiness",),
        "non_pick": ("non_pick",),
        "compact_provenance": ("compact_provenance",),
        "scoreline": ("scoreline_picks", "scoreline_reference", "scoreline_readiness"),
        "audit_identity": (
            "audit_capture_hash",
            "audit_estimate_id",
            "audit_detail_url",
            "audit_links",
        ),
    }
    largest = []
    for card in sorted(cards, key=_bytes, reverse=True)[:20]:
        attributed = {
            name: sum(_bytes(card.get(key)) for key in keys if key in card)
            for name, keys in groups.items()
        }
        attributed["other"] = max(0, _bytes(card) - sum(attributed.values()))
        largest.append(
            {
                "fixture_id": str(card.get("fixture_id") or ""),
                "decision_tier": card.get("decision_tier"),
                "card_bytes": _bytes(card),
                "field_bytes": attributed,
            }
        )
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    card_total = sum(sizes)
    top = {key: _bytes(value) for key, value in payload.items()}
    dominant = (
        "CARD_COUNT_DOMINATED"
        if len(cards) >= 50 and (statistics.median(sizes) if sizes else 0) < 64 * 1024
        else "CARD_FIELD_BLOAT"
    )
    if _bytes(payload.get("performance")) > len(raw) * 0.35:
        dominant = "PERFORMANCE_SUMMARY_BLOAT"
    if card_total < len(raw) * 0.65 and dominant != "PERFORMANCE_SUMMARY_BLOAT":
        dominant = "MIXED"
    return {
        "schema_version": "w2.dayview_payload_profile.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "total_fixture_rows": int(payload.get("counts", {}).get("total") or len(cards)),
        "returned_cards": len(cards),
        "total_uncompressed_bytes": len(raw),
        "gzip_diagnostic_bytes": len(gzip.compress(raw)),
        "top_level_field_bytes": top,
        "cards_total_bytes": card_total,
        "performance_bytes": _bytes(payload.get("performance")),
        "navigation_freshness_degradation_bytes": sum(
            _bytes(payload.get(k)) for k in ("navigation", "freshness", "degradation")
        ),
        "card_size_p50": statistics.median(sizes) if sizes else 0,
        "card_size_p95": sorted(sizes)[max(0, int(len(sizes) * 0.95) - 1)] if sizes else 0,
        "card_size_max": max(sizes, default=0),
        "largest_cards": largest,
        "diagnosis": dominant,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--window", default="future")
    parser.add_argument("--timezone", default="Asia/Shanghai")
    parser.add_argument("--payload-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/runtime-only"))
    args = parser.parse_args()
    payload = json.loads(args.payload_json.read_text(encoding="utf-8"))
    result = profile(payload)
    result["request"] = {
        "runtime_root": str(args.runtime_root) if args.runtime_root else None,
        "date": args.date,
        "window": args.window,
        "timezone": args.timezone,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    target = (
        args.output_dir
        / f"W2_DAYVIEW_PAYLOAD_PROFILE_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
