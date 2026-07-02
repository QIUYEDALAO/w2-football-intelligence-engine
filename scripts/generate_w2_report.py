from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast
from urllib.request import urlopen

from w2.reporting.report_generator import render_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a W2 text report from dashboard payload."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Read dashboard JSON payload from a file.")
    source.add_argument("--url", help="Read dashboard JSON payload from a URL.")
    parser.add_argument("--report-type", choices=["morning", "final"], default="final")
    parser.add_argument("--format", choices=["markdown", "text", "html"], default="markdown")
    parser.add_argument("--output", type=Path, help="Optional output path. Defaults to stdout.")
    args = parser.parse_args()

    payload = _load_payload(input_path=args.input, url=args.url)
    report = render_report(
        payload,
        report_type=cast(Any, args.report_type),
        output_format=cast(Any, args.format),
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)
    return 0


def _load_payload(*, input_path: Path | None, url: str | None) -> dict[str, Any]:
    if input_path is not None:
        raw = input_path.read_text(encoding="utf-8")
    elif url is not None:
        with urlopen(url, timeout=20) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
    else:
        raise ValueError("either input_path or url is required")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("dashboard payload must be a JSON object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
