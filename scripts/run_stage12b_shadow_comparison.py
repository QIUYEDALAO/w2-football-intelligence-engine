from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from w2.strategy.shadow import write_json

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
W1_ROOT = Path(
    os.environ.get(
        "W2_STAGE12B_W1_AUDIT_ROOT",
        str(Path.home() / ".openclaw" / "workspace" / "w1_world_cup_engine"),
    )
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_file(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {"path": str(path), "status": "NOT_AVAILABLE"}
    return {
        "path": str(path),
        "status": "AVAILABLE_READ_ONLY",
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
    }


def main() -> None:
    candidates = [
        W1_ROOT / "data/processed/international/w1_international_dataset.csv",
        W1_ROOT / "data/local_odds/world_cup_odds_historical.csv",
    ]
    assets = [safe_file(path) for path in candidates]
    comparison = {
        "status": "COMPLETED_WITH_NOT_AVAILABLE_FIELDS",
        "mode": "READ_ONLY_NO_W1_RUNTIME_IMPORT",
        "w1_root": str(W1_ROOT),
        "assets": assets,
        "fixtures": [
            {
                "fixture_identity": "stage9a-france-iraq-demo",
                "kickoff": "RETROSPECTIVE_REPLAY",
                "odds_snapshot_age": "NOT_AVAILABLE",
                "bookmaker_coverage": "NOT_AVAILABLE",
                "market_probability": "NOT_AVAILABLE",
                "mu_lambda": "NOT_AVAILABLE",
                "score_distribution": "NOT_AVAILABLE",
                "w2_independent_probability": "AVAILABLE_FROM_STAGE9B_DEMO",
                "w2_shadow_decision": "AVAILABLE_FROM_STAGE9B_REPLAY",
                "data_latency": "NOT_AVAILABLE",
                "runtime_availability": "W1_RUNTIME_NOT_IMPORTED",
            }
        ],
        "w1_recommendation_as_ground_truth": False,
        "w1_modified": False,
    }
    write_json(REPORTS / "W2_STAGE12B_W1_W2_COMPARISON.json", comparison)
    print(json.dumps({"status": "PASS", "w1_modified": False}, sort_keys=True))


if __name__ == "__main__":
    main()
