from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from sqlalchemy.orm import Session

from w2.audit_export import build_audit_export, write_audit_export
from w2.infrastructure.database import create_engine


def main() -> int:
    parser = argparse.ArgumentParser(description="Export W2 audit tables from read-only sources.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Dashboard JSON payload file.")
    source.add_argument("--url", help="Dashboard JSON URL.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--format", choices=["csv", "json", "both"], default="csv")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds.")
    parser.add_argument("--no-db", action="store_true", help="Skip read-only DB model export.")
    args = parser.parse_args()

    payload = _load_dashboard_payload(input_path=args.input, url=args.url, timeout=args.timeout)
    if args.no_db:
        export = build_audit_export(payload)
    else:
        engine = create_engine()
        with Session(engine) as session:
            export = build_audit_export(payload, session=session)
    written = write_audit_export(export, args.output_dir, output_format=args.format)
    summary = {
        "status": "PASS",
        "output_dir": str(args.output_dir),
        "files": [str(path) for path in written],
        "table_counts": export.manifest["table_counts"],
        "provider_calls": 0,
        "db_writes": 0,
        "read_only": True,
        "provider_call_scope": "audit_export_dashboard_payload_only",
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2), file=sys.stderr)
    return 0


def _load_dashboard_payload(
    *,
    input_path: Path | None,
    url: str | None,
    timeout: float,
) -> dict[str, Any]:
    if input_path is not None:
        raw = input_path.read_text(encoding="utf-8")
    elif url is not None:
        with urlopen(url, timeout=timeout) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
    else:
        raise ValueError("input_path or url is required")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("dashboard payload must be a JSON object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
