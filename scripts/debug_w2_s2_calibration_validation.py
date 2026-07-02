from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from w2.backtest.s2_calibration_validation import (  # noqa: E402
    S2CalibrationValidationInputs,
    build_s2_calibration_validation_report,
)


def main() -> int:
    args = parse_args()
    try:
        payload = _load_payload(args)
        report = build_s2_calibration_validation_report(
            S2CalibrationValidationInputs(payload=payload, source=_source(args))
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"S2_CALIBRATION_VALIDATION_FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only W2 S2 Dixon-Coles and lambda clipping validation."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Dashboard payload JSON file.")
    source.add_argument("--url", help="Dashboard URL to fetch.")
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser.parse_args()


def _load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.input is not None:
        value = json.loads(args.input.read_text(encoding="utf-8"))
    else:
        parsed = urlparse(str(args.url))
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("url must use http or https")
        with urlopen(  # noqa: S310 - URL scheme is restricted above.
            str(args.url),
            timeout=float(args.timeout),
        ) as response:
            value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("payload root must be an object")
    return value


def _source(args: argparse.Namespace) -> str:
    if args.input is not None:
        return f"input:{args.input}"
    return f"url:{args.url}"


if __name__ == "__main__":
    raise SystemExit(main())
