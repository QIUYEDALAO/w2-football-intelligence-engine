from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from w2.backtest.free_tier_2024 import (  # noqa: E402
    ANNUAL_COMPETITIONS,
    DEFAULT_RAW_DIRS,
    build_free_tier_2024_backtest_report,
    collect_provider_dataset,
    report_sha256,
)


def main() -> int:
    args = _parse_args()
    raw_dirs = tuple(Path(item) for item in args.raw_dir) if args.raw_dir else DEFAULT_RAW_DIRS
    competitions = tuple(args.competition) if args.competition else ANNUAL_COMPETITIONS
    try:
        provider_result = None
        if args.collect_provider:
            if not args.approved_provider_calls or not args.live_provider_fetch:
                print("NEED_USER_APPROVAL: PROVIDER_CALLS", file=sys.stderr)
                return 1
            provider_result = collect_provider_dataset(
                out_dir=args.out_dir,
                season=args.season,
                competitions=competitions,
                daily_hard_cap=args.daily_hard_cap,
                max_statistics_calls=args.max_statistics_calls,
                request_interval_seconds=args.request_interval_seconds,
                requester=_api_football_request,
            )
            raw_dirs = (args.out_dir / "raw", *raw_dirs)
        report = build_free_tier_2024_backtest_report(
            raw_dirs=raw_dirs,
            season=args.season,
            competitions=competitions,
            generated_at=datetime.now(UTC),
        )
        if provider_result is not None:
            report["provider_collection"] = {
                "provider_calls": provider_result.provider_calls,
                "written_files": list(provider_result.written_files),
                "skipped_existing": list(provider_result.skipped_existing),
                "stopped_reason": provider_result.stopped_reason,
                "ledger_records": len(provider_result.ledger),
            }
            report["provider_calls"] = provider_result.provider_calls
        report["report_sha256"] = report_sha256(report)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True if args.json else False))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build W2 free-tier 2024 historical backtest and calibration report."
    )
    parser.add_argument("--season", default="2024")
    parser.add_argument("--competition", action="append", default=[])
    parser.add_argument("--raw-dir", action="append", default=[])
    parser.add_argument("--out-dir", type=Path, default=Path("runtime/w2_free_tier_2024"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--collect-provider", action="store_true", default=False)
    parser.add_argument("--live-provider-fetch", action="store_true", default=False)
    parser.add_argument("--approved-provider-calls", action="store_true", default=False)
    parser.add_argument("--daily-hard-cap", type=int, default=80)
    parser.add_argument("--max-statistics-calls", type=int, default=0)
    parser.add_argument("--request-interval-seconds", type=float, default=10.0)
    parser.add_argument("--json", action="store_true", default=False)
    return parser.parse_args()


def _api_football_request(
    endpoint: str,
    params: dict[str, str],
) -> tuple[int, dict[str, str], dict[str, Any]]:
    _ensure_provider_key_http_safe()
    api_key = _provider_key()
    path = "fixtures/statistics" if endpoint == "statistics" else endpoint
    url = "https://v3.football.api-sports.io/" + path
    encoded = urllib.parse.urlencode(params)
    request = urllib.request.Request(  # noqa: S310 - fixed HTTPS API-Football host.
        f"{url}?{encoded}",
        headers={"x-apisports-key": api_key},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
        headers = {key.lower(): value for key, value in response.headers.items()}
        return int(response.status), headers, payload


def _ensure_provider_key_http_safe() -> None:
    value = _provider_key()
    problems: list[str] = []
    if value != value.strip():
        problems.append("LEADING_OR_TRAILING_WHITESPACE")
    if "\n" in value or "\r" in value:
        problems.append("NEWLINE_OR_CRLF")
    if value.startswith(
        (
            "W2_API_FOOTBALL_API_KEY=",
            "API_FOOTBALL=",
            "x-apisports-key:",
            "X-APISPORTS-KEY:",
        )
    ):
        problems.append("LOOKS_LIKE_ASSIGNMENT_OR_HEADER_LINE")
    if value.startswith(("'", '"')) or value.endswith(("'", '"')):
        problems.append("WRAPPED_IN_QUOTES")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        problems.append("CONTROL_CHARACTER")
    try:
        value.encode("latin-1")
    except UnicodeEncodeError:
        problems.append("NOT_HTTP_HEADER_SAFE_ENCODING")
    if problems:
        raise RuntimeError("PROVIDER_KEY_INVALID:" + ",".join(problems))


def _provider_key() -> str:
    value = os.environ.get("W2_API_FOOTBALL_API_KEY")
    if value is None:
        raise RuntimeError("PROVIDER_KEY_MISSING")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
