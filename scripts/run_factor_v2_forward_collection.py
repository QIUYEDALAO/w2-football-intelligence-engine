from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from w2.factor_model.forward_collection import (
    ForwardCollectionConfig,
    disable_forward_collection,
    run_forward_collection,
    write_run_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the DB-only Factor V2 delayed forward collector once."
    )
    parser.add_argument("--write-db", action="store_true")
    parser.add_argument("--computed-at")
    args = parser.parse_args()

    config = ForwardCollectionConfig.from_environment()
    computed_at = (
        datetime.fromisoformat(args.computed_at.replace("Z", "+00:00")).astimezone(UTC)
        if args.computed_at
        else None
    )
    try:
        report = run_forward_collection(
            config=config,
            computed_at=computed_at,
            write_db=args.write_db,
        )
    except Exception as exc:
        disable_forward_collection(config)
        report = {
            "schema_version": "w2.factor_model.forward_collection_run.v1",
            "computed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "status": "ERROR_COLLECTION_DISABLED",
            "error_type": type(exc).__name__,
            "provider_calls": 0,
            "database_writes": 0,
            "production_worker_used": False,
        }
        path = write_run_report(report, config.report_dir)
        print(json.dumps({"status": report["status"], "report": str(path)}))
        return 1

    path = write_run_report(report, config.report_dir)
    print(
        json.dumps(
            {
                "status": report["status"],
                "database_writes": report.get("database_writes", 0),
                "provider_calls": report.get("provider_calls", 0),
                "report": str(path),
            }
        )
    )
    return 1 if "FAILED" in report["status"] or "ANOMALY" in report["status"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
