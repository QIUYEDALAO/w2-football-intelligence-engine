from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def get_json(base_url: str, path: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    scheme = urlparse(url).scheme
    if scheme not in {"http", "https"}:
        raise ValueError(f"unsupported URL scheme: {scheme}")
    request = Request(url, headers={"Accept": "application/json"})  # noqa: S310 - scheme checked above
    with urlopen(request, timeout=15) as response:  # noqa: S310 - scheme checked above
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def sha_matches(expected: str, actual: str) -> bool:
    if expected == "UNKNOWN" or actual == "UNKNOWN":
        return False
    return expected.startswith(actual) or actual.startswith(expected) or expected[:7] == actual[:7]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify W2 web/API/data release sync.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-sha", default=git_sha())
    parser.add_argument("--min-fixtures", type=int, default=0)
    parser.add_argument("--allow-empty-data", action="store_true")
    args = parser.parse_args()
    try:
        meta = get_json(args.base_url, "/meta.json")
        version = get_json(args.base_url, "/v1/version")
        dashboard = get_json(args.base_url, "/v1/dashboard?window=next36&include_debug=true")
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"release sync check failed: {exc}", file=sys.stderr)
        return 2
    debug = dashboard.get("debug") if isinstance(dashboard.get("debug"), dict) else {}
    all_rows = dashboard.get("all") if isinstance(dashboard.get("all"), list) else []
    checks = {
        "local_expected_sha": args.expected_sha,
        "web_git_sha": meta.get("web_git_sha", "UNKNOWN"),
        "api_git_sha": version.get("api_git_sha", "UNKNOWN"),
        "data_profile": dashboard.get("data_profile"),
        "data_source": dashboard.get("data_source"),
        "dashboard_rows": len(all_rows),
        "read_model_fixture_count": debug.get("read_model_fixture_count"),
        "matchday_card_count": debug.get("matchday_card_count"),
        "future_fixture_count": debug.get("future_fixture_count"),
        "empty_reason": debug.get("empty_reason"),
    }
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    failures: list[str] = []
    if not sha_matches(args.expected_sha, str(checks["web_git_sha"])):
        failures.append("web sha mismatch")
    if not sha_matches(args.expected_sha, str(checks["api_git_sha"])):
        failures.append("api sha mismatch")
        if checks["api_git_sha"] == "UNKNOWN":
            print(
                "hint: API SHA is UNKNOWN; check /opt/w2/shared/release.env and "
                "the w2-staging systemd EnvironmentFile wiring.",
                file=sys.stderr,
            )
    if len(all_rows) < args.min_fixtures:
        failures.append("dashboard fixture count below minimum")
    if not args.allow_empty_data and dashboard.get("data_profile") == "empty":
        failures.append("dashboard data is empty")
    if failures:
        print("FAILED: " + "; ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
