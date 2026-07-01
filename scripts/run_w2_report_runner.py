from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

from w2.reporting.report_runner import run_report_job


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the W2 report generator against a dashboard endpoint."
    )
    parser.add_argument("--base-url", default="http://43.155.208.138")
    parser.add_argument("--window", default="today")
    parser.add_argument("--report-type", choices=["morning", "final"], default="final")
    parser.add_argument("--format", choices=["markdown", "text"], default="markdown")
    sink = parser.add_mutually_exclusive_group()
    sink.add_argument("--dry-run", action="store_true", help="Print the report to stdout.")
    sink.add_argument(
        "--file-sink",
        action="store_true",
        help="Write the report under runtime/reports.",
    )
    parser.add_argument("--runtime-root", type=Path, default=Path("runtime"))
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()

    sink_name = "file" if args.file_sink else "stdout"
    result = run_report_job(
        base_url=args.base_url,
        window=args.window,
        report_type=cast(Any, args.report_type),
        output_format=cast(Any, args.format),
        sink=cast(Any, sink_name),
        runtime_root=args.runtime_root,
        timeout_seconds=args.timeout,
    )
    summary = json.dumps(result.summary(), ensure_ascii=False, sort_keys=True)
    if sink_name == "stdout":
        sys.stdout.write(result.report)
        print(summary, file=sys.stderr)
    else:
        print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
