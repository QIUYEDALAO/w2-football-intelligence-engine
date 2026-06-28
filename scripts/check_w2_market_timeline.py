from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from w2.ingestion.market_timeline import (  # noqa: E402
    load_timeline,
    validate_timeline_payload,
)
from w2.ingestion.market_timeline_refresh import (  # noqa: E402
    default_market_timeline_runtime_root,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate W2 market timeline snapshot artifacts.")
    parser.add_argument("--window", default="all")
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    errors: dict[str, list[str]] = {}
    warnings: dict[str, list[str]] = {}
    paths = _artifact_paths(args.runtime_root or default_market_timeline_runtime_root())
    for path in paths:
        payload = load_timeline(path)
        validation_errors = validate_timeline_payload(payload)
        if validation_errors:
            errors[path.name] = validation_errors
        snapshots = payload.get("snapshots") if isinstance(payload, dict) else None
        has_lock = any(
            isinstance(item, dict)
            and item.get("checkpoint") == "lock"
            and item.get("market") == "ASIAN_HANDICAP"
            for item in snapshots or []
        )
        if not has_lock:
            warnings[path.name] = ["MISSING_AH_LOCK_SNAPSHOT"]
    payload = {
        "status": "PASS" if not errors else "FAIL",
        "window": args.window,
        "artifact_count": len(paths),
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(payload, sort_keys=True))
    return 0 if not errors else 1


def _artifact_paths(root: Path) -> list[Path]:
    try:
        return sorted(root.glob("*.json")) if root.exists() else []
    except OSError:
        return []


if __name__ == "__main__":
    raise SystemExit(main())
