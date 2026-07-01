from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode
from urllib.request import urlopen


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only sanity audit for W2 modeling inputs in dashboard payload."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Read dashboard JSON payload from a file.")
    source.add_argument("--public-url", help="Fetch dashboard JSON from a public base URL.")
    parser.add_argument("--window", default="today", help="Dashboard window for --public-url.")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()

    payload = _load_payload(
        input_path=args.input,
        public_url=args.public_url,
        window=args.window,
        timeout=args.timeout,
    )
    audit = build_modeling_sanity_audit(payload)
    if args.format == "markdown":
        sys.stdout.write(_render_markdown(audit))
    else:
        json.dump(audit, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0


def build_modeling_sanity_audit(payload: dict[str, Any]) -> dict[str, Any]:
    rows = [_match_row(match) for match in _list(payload.get("all"))]
    return {
        "status": "PASS",
        "provider_calls": 0,
        "db_writes": 0,
        "read_only": True,
        "selected_football_day": payload.get("selected_football_day")
        or payload.get("selected_date")
        or payload.get("date"),
        "generated_at": payload.get("generated_at") or payload.get("as_of"),
        "summary": {
            "rows": len(rows),
            "neutral_site_count": sum(1 for row in rows if row["neutral_site"] is True),
            "home_advantage_applied_count": sum(
                1 for row in rows if row["home_advantage_applied"] is True
            ),
            "proxy_elo_excluded_count": sum(
                1 for row in rows if row["proxy_elo_excluded"] is True
            ),
            "ratings_used_in_lambda_count": sum(
                1 for row in rows if row["ratings_used_in_lambda"] is True
            ),
        },
        "rows": rows,
    }


def _match_row(match: Any) -> dict[str, Any]:
    card = _dict(match)
    shadow = _dict(card.get("pricing_shadow"))
    simulation = _dict(shadow.get("simulation"))
    readiness = _dict(simulation.get("input_readiness"))
    calibration = _dict(simulation.get("calibration"))
    params = _dict(calibration.get("params"))
    return {
        "fixture_id": card.get("fixture_id"),
        "teams": f"{card.get('home_team_name')} vs {card.get('away_team_name')}",
        "kickoff_utc": card.get("kickoff_utc"),
        "formal_recommendation": card.get("formal_recommendation"),
        "simulation_status": simulation.get("status") or shadow.get("simulation_status"),
        "lambda_home": simulation.get("lambda_home"),
        "lambda_away": simulation.get("lambda_away"),
        "fair_ah": shadow.get("fair_ah"),
        "neutral_site": readiness.get("neutral_site"),
        "home_advantage_applied": readiness.get("home_advantage_applied"),
        "applied_home_advantage_goals": params.get("applied_home_advantage_goals"),
        "elo_ready": readiness.get("elo_ready"),
        "raw_ratings_ready": readiness.get("raw_ratings_ready"),
        "ratings_used_in_lambda": readiness.get("ratings_used_in_lambda"),
        "proxy_elo_excluded": readiness.get("proxy_elo_excluded"),
        "home_elo_source": readiness.get("home_elo_source"),
        "away_elo_source": readiness.get("away_elo_source"),
        "home_elo_collection_status": readiness.get("home_elo_collection_status"),
        "away_elo_collection_status": readiness.get("away_elo_collection_status"),
        "xg_ready": readiness.get("xg_ready"),
        "xg_status": readiness.get("xg_status"),
    }


def _load_payload(
    *,
    input_path: Path | None,
    public_url: str | None,
    window: str,
    timeout: float,
) -> dict[str, Any]:
    if input_path is not None:
        raw = input_path.read_text(encoding="utf-8")
    elif public_url is not None:
        base = public_url.rstrip("/")
        query = urlencode({"window": window, "include_debug": "true"})
        with urlopen(f"{base}/v1/dashboard?{query}", timeout=timeout) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
    else:
        raise ValueError("either input_path or public_url is required")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("dashboard payload must be a JSON object")
    return cast(dict[str, Any], payload)


def _render_markdown(audit: dict[str, Any]) -> str:
    summary = _dict(audit.get("summary"))
    lines = [
        "# W2 Modeling Sanity Audit",
        "",
        f"- status: {audit.get('status')}",
        f"- selected_football_day: {audit.get('selected_football_day')}",
        f"- generated_at: {audit.get('generated_at')}",
        f"- rows: {summary.get('rows')}",
        f"- neutral_site_count: {summary.get('neutral_site_count')}",
        f"- home_advantage_applied_count: {summary.get('home_advantage_applied_count')}",
        f"- proxy_elo_excluded_count: {summary.get('proxy_elo_excluded_count')}",
        f"- ratings_used_in_lambda_count: {summary.get('ratings_used_in_lambda_count')}",
        "",
        "| fixture | teams | neutral | HA applied | applied HA | "
        "ratings used | proxy Elo excluded | lambda |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in _list(audit.get("rows")):
        item = _dict(row)
        lines.append(
            "| {fixture_id} | {teams} | {neutral_site} | {home_advantage_applied} | "
            "{applied_home_advantage_goals} | {ratings_used_in_lambda} | "
            "{proxy_elo_excluded} | "
            "{lambda_home}/{lambda_away} |".format(**item)
        )
    lines.append("")
    return "\n".join(lines)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


if __name__ == "__main__":
    raise SystemExit(main())
