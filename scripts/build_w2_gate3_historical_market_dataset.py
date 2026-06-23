#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from w2.markets.historical_dataset import (
    MarketObservation,
    ah_walk_forward,
    inventory_source,
    normalize_source,
    phase_coverage,
    validate_observations,
)

ROOT = Path(__file__).resolve().parents[1]
W1_ROOT = ROOT.parent / ("w1_" + "world_cup_engine")
REPORTS = ROOT / "reports"


def git_ls_files(root: Path) -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    return {str(root / line.strip()) for line in result.stdout.splitlines() if line.strip()}


def candidate_sources() -> list[tuple[str, Path]]:
    sources: list[tuple[str, Path]] = []
    for path in [
        W1_ROOT / "data/local_odds/world_cup_odds_historical.csv",
        W1_ROOT / "data/local_odds/world_cup_odds_2018.csv",
        W1_ROOT / "data/local_odds/world_cup_odds_2022.csv",
        W1_ROOT / "data/local_odds/world_cup_odds_2026.csv",
    ]:
        if path.is_file():
            sources.append(("W1", path))
    snapshots = W1_ROOT / "data/odds_snapshots/raw"
    if snapshots.is_dir():
        for path in sorted(snapshots.glob("*/odds_snapshots.jsonl")):
            sources.append(("W1", path))
    for path in sorted((ROOT / "runtime/stage5b/raw").glob("*odds*.json")):
        sources.append(("W2_RUNTIME", path))
    for path in sorted((ROOT / "runtime/stage7c/raw").glob("*odds*.json")):
        sources.append(("W2_RUNTIME", path))
    for path in sorted((ROOT / "runtime/stage7e/raw").glob("*odds*.json")):
        sources.append(("W2_RUNTIME", path))
    return sources


def market_counts(observations: list[MarketObservation]) -> dict[str, int]:
    return dict(sorted(Counter(obs.market for obs in observations).items()))


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    tracked_w1 = git_ls_files(W1_ROOT) if W1_ROOT.exists() else set()
    tracked_w2 = git_ls_files(ROOT)
    inventory = []
    observations: list[MarketObservation] = []
    source_errors: list[dict[str, str]] = []
    for source_system, path in candidate_sources():
        try:
            tracked_paths = tracked_w1 if source_system == "W1" else tracked_w2
            inventory.append(inventory_source(path, source_system, tracked_paths).__dict__)
            observations.extend(normalize_source(path, source_system))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            source_errors.append(
                {
                    "source_system": source_system,
                    "path": str(path),
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )
    validation = validate_observations(observations)
    coverage = phase_coverage(observations)
    ah = ah_walk_forward(observations)
    normalized_counts = {
        "observation_count": len(observations),
        "fixture_count": len({obs.fixture_source_id for obs in observations}),
        "bookmaker_count": len({obs.bookmaker for obs in observations}),
        "market_coverage": market_counts(observations),
        "snapshot_semantics": dict(
            sorted(Counter(obs.snapshot_semantics for obs in observations).items())
        ),
        "candidate": False,
        "formal_recommendation": False,
    }
    inventory_payload = {
        "schema_version": "W2_GATE3_HISTORICAL_MARKET_SOURCE_INVENTORY_V1",
        "generated_at_utc": generated_at,
        "source_count": len(inventory),
        "sources": inventory,
        "source_errors": source_errors,
        "candidate": False,
        "formal_recommendation": False,
    }
    phase_payload = {
        "schema_version": "W2_GATE3_PHASE_COVERAGE_V1",
        "generated_at_utc": generated_at,
        **coverage,
        "candidate": False,
        "formal_recommendation": False,
    }
    ah_payload = {
        "schema_version": "W2_GATE3_AH_WALK_FORWARD_V1",
        "generated_at_utc": generated_at,
        **ah,
    }
    build_status = (
        "NO_USABLE_INTERNAL_HISTORICAL_AH_DATA"
        if ah["status"] == "NO_USABLE_INTERNAL_HISTORICAL_AH_DATA"
        else ah["status"]
    )
    (REPORTS / "W2_GATE3_HISTORICAL_MARKET_SOURCE_INVENTORY.json").write_text(
        json.dumps(inventory_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (REPORTS / "W2_GATE3_PHASE_COVERAGE.json").write_text(
        json.dumps(phase_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (REPORTS / "W2_GATE3_AH_WALK_FORWARD.json").write_text(
        json.dumps(ah_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = "\n".join(
        [
            "# W2 Gate3 Historical Market Build Result",
            "",
            f"Generated at: `{generated_at}`",
            "",
            f"HISTORICAL_MARKET_BUILD_STATUS={build_status}",
            f"SOURCE_COUNT={len(inventory)}",
            f"NORMALIZED_OBSERVATION_COUNT={len(observations)}",
            f"NORMALIZED_VALIDATION_STATUS={validation['status']}",
            "CAPTURED_AT_OBSERVATIONS="
            f"{normalized_counts['snapshot_semantics'].get('CAPTURED_AT', 0)}",
            f"AH_WALK_FORWARD_STATUS={ah['status']}",
            "GATE3_STATUS=PARTIAL",
            "candidate=false",
            "formal_recommendation=false",
            "",
            "Boundary notes:",
            "",
            "- No provider call, network request, deployment, migration, or runtime mutation "
            "was performed.",
            "- Closing-only data remains closing baseline only.",
            "- UNKNOWN_PREMATCH_AGGREGATE data remains aggregate baseline only.",
            "- W1 captured-at snapshots provide phase coverage evidence but do not include "
            "settled historical AH results.",
            "- Gate3 remains PARTIAL until historical AH baseline/backtest and mandatory "
            "phase semantics are complete.",
        ]
    )
    (REPORTS / "W2_GATE3_HISTORICAL_MARKET_BUILD_RESULT.md").write_text(
        result + "\n",
        encoding="utf-8",
    )
    print(f"W2 Gate3 historical market build completed: {build_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
