#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "docs" / "review_packages" / "SC18_INPUT_AUTHORITY_CONVERGENCE"
EXACT_13 = {
    "premier_league",
    "la_liga",
    "bundesliga",
    "serie_a",
    "ligue_1",
    "brasileirao_serie_a",
    "argentina_primera",
    "mls",
    "chinese_super_league",
    "allsvenskan",
    "eliteserien",
    "eredivisie",
    "primeira_liga",
}
CLASSES = {
    "VERIFIED",
    "PARTIAL",
    "NOT_AUDITED",
    "NOT_AVAILABLE_FROM_CURRENT_PROVIDER",
    "DATASET_MAPPING_REQUIRED",
    "OWNER_DECISION_REQUIRED",
}


def load(name: str) -> dict[str, Any]:
    return json.loads((REPORTS / name).read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"SC18 input authority check FAIL: {message}")


def main() -> int:
    trace = load("SC18_INPUT_AUTHORITY_TRACE.json")
    coverage = load("STAGE14_COVERAGE_MATRIX.json")
    labels = load("PUBLIC_LABEL_COVERAGE_MATRIX.json")
    enums = load("PUBLIC_ENUM_LABEL_COVERAGE.json")
    rows = coverage["competitions"]
    require({row["competition_id"] for row in rows} == EXACT_13, "exact 13 mismatch")
    require(len(rows) == 13, "coverage rows must be unique")
    require(set(coverage["classification_values"]) == CLASSES, "classification enum drift")
    require(coverage["provider_calls"] == coverage["db_writes"] == 0, "audit must be read-only")
    for row in rows:
        require(row["overall"] in CLASSES, f"invalid class for {row['competition_id']}")
        has_evidence = row["fixture_count"] > 0 or row["analysis_card_count"] > 0
        no_enable_source = not any(
            row[key]
            for key in ("profile_enabled", "future_refresh_enabled", "matchday_enabled")
        )
        if has_evidence and no_enable_source:
            require(
                row["overall"] == "OWNER_DECISION_REQUIRED",
                f"{row['competition_id']} must not blame enabled:false",
            )
    fixtures = {row["fixture_id"]: row for row in trace["fixtures"]}
    require(set(fixtures) == {"1493049", "1575453", "1494239"}, "trace fixture set")
    target = fixtures["1493049"]
    require(target["match_market_aggregate_status"] == "PARTIAL", "1493049 aggregate")
    require(
        target["markets"]["ASIAN_HANDICAP"]["bookmaker_count"] == 1
        and target["markets"]["TOTALS"]["bookmaker_count"] == 7,
        "AH/OU depth must remain independent",
    )
    require(
        target["markets"]["TOTALS"]["candidate_quote_identity_status"] == "NOT_READY",
        "radar median must not become an executable quote",
    )
    require(trace["provider_calls"] == trace["db_writes"] == 0, "trace must be read-only")
    require(labels["canonical_team_count"] >= labels["canonical_chinese_label_count"], "labels")
    for row in labels["competitions"]:
        total = sum(
            row[key]
            for key in (
                "CHINESE_LABEL_READY",
                "CANONICAL_IDENTITY_READY_LABEL_MISSING",
                "IDENTITY_UNRESOLVED",
                "AMBIGUOUS",
            )
        )
        require(total == row["provider_team_count"], f"label coverage {row['competition_id']}")
    registry = (ROOT / enums["registry"]).read_text(encoding="utf-8")
    for code, translated in enums["required_labels"].items():
        require(code in registry and translated in registry, f"missing public label {code}")
    workspace = (ROOT / "src/w2/dashboard/workspace.py").read_text(encoding="utf-8")
    for token in ('"formal": "OFF"', '"lock": "OFF"', '"production": "OFF"'):
        require(token in workspace, f"stop-line drift: {token}")
    print("SC18 input authority check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
