from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime/stage5b/processed/national_fixtures_cleaned.json"
OUTPUT = ROOT / "runtime/dashboard/staging_seed_dashboard.json"


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def load_fixtures(limit: int) -> list[dict[str, Any]]:
    if not SOURCE.exists():
        return []
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    items = payload.get("items", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)][:limit]


def team_name(item: dict[str, Any], side: str) -> str:
    teams = item.get("teams") if isinstance(item.get("teams"), dict) else {}
    team = teams.get(side) if isinstance(teams.get(side), dict) else {}
    fallback = "主队" if side == "home" else "客队"
    return str(item.get(f"{side}_team_name") or team.get("name") or fallback)


def fixture_id(item: dict[str, Any], index: int) -> str:
    fixture = item.get("fixture") if isinstance(item.get("fixture"), dict) else {}
    return str(item.get("fixture_id") or fixture.get("id") or f"staging-seed-{index + 1}")


def kickoff(item: dict[str, Any]) -> str:
    fixture = item.get("fixture") if isinstance(item.get("fixture"), dict) else {}
    return str(item.get("kickoff_utc") or fixture.get("date") or datetime.now(UTC).isoformat())


def card_from_fixture(item: dict[str, Any], index: int) -> dict[str, Any]:
    market_pick = index == 0
    return {
        "fixture_id": fixture_id(item, index),
        "kickoff_utc": kickoff(item),
        "competition_name": str(item.get("competition_name") or "世界杯"),
        "home_team_name": team_name(item, "home"),
        "away_team_name": team_name(item, "away"),
        "status": str(item.get("status") or "UPCOMING"),
        "watch_level": 3 if market_pick else 0,
        "data_readiness": {
            "bookmakers": 12 if market_pick else 0,
            "odds_snapshots": 12 if market_pick else 0,
            "xg": False,
            "h2h": False,
            "lineups": False,
        },
        "recommendation": {
            "tier": "ANALYSIS_PICK",
            "market": "TOTALS",
            "market_label_cn": "大小球",
            "selection": "OVER",
            "selection_label_cn": "大 2.5",
            "line": "2.5",
            "confidence": 0.62,
            "reasons": ["STAGING SEED：仅用于验证发布同步与页面渲染。"],
            "risks": ["这不是实时云端数据。"],
            "candidate": False,
            "formal_recommendation": False,
        }
        if market_pick
        else None,
        "scoreline_picks": [],
        "result": None,
        "validation": None,
        "current_odds": {},
        "odds_movement": {},
        "market_strip": [
            {
                "market": "TOTALS",
                "decision": "PICK" if market_pick else "SKIP",
                "label_cn": "大小球",
                "confidence": 0.62 if market_pick else 0.0,
            },
            {"market": "ASIAN_HANDICAP", "decision": "SKIP", "label_cn": "让球", "confidence": 0.0},
        ],
        "bookmaker_intent": {"intent": "INSUFFICIENT_DATA", "label_cn": "数据不足"},
        "missing_inputs": ["xG", "交锋", "首发"],
        "candidate": False,
        "formal_recommendation": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed an explicit staging dashboard fallback.")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if os.getenv("W2_ENVIRONMENT") == "production":
        raise SystemExit("Refusing to seed dashboard in production.")
    if OUTPUT.exists() and not args.force:
        raise SystemExit(f"{OUTPUT} already exists; pass --force to replace it.")
    cards = [card_from_fixture(item, index) for index, item in enumerate(load_fixtures(args.limit))]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "data_profile": "staging-seed",
        "data_source": "staging-json-fallback",
        "git_sha": git_sha(),
        "all": cards,
        "upcoming": cards,
        "recommendations": [card for card in cards if card.get("recommendation")],
        "finished": [],
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(OUTPUT),
                "fixtures_written": len(cards),
                "git_sha": payload["git_sha"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
