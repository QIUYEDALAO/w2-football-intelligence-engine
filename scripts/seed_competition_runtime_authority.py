from __future__ import annotations

import argparse
import json
from pathlib import Path

from w2.competitions.seed import seed_competition_runtime_authority, set_competition_enabled
from w2.infrastructure.database import create_engine


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed or update the DB competition runtime authority"
    )
    parser.add_argument("--environment", default="production")
    parser.add_argument("--config-root", type=Path, default=Path("config"))
    parser.add_argument("--updated-by", default="competition-authority-operator")
    parser.add_argument("--set-enabled", metavar="COMPETITION_ID")
    parser.add_argument("--enabled", choices=("true", "false"))
    args = parser.parse_args()
    engine = create_engine()
    if args.set_enabled:
        if args.enabled is None:
            parser.error("--set-enabled requires --enabled")
        audit_hash = set_competition_enabled(
            engine,
            competition_id=args.set_enabled,
            enabled=args.enabled == "true",
            updated_by=args.updated_by,
        )
        print(json.dumps({"status": "UPDATED", "audit_sha256": audit_hash}, sort_keys=True))
        return 0
    report = seed_competition_runtime_authority(
        engine,
        config_root=args.config_root,
        environment=args.environment,
        updated_by=args.updated_by,
    )
    print(json.dumps(report.as_dict(), sort_keys=True))
    return 1 if report.conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
