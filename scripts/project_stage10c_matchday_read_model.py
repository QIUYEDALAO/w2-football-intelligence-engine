from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_DECISIONS = {"WATCH", "SKIP"}


class Stage10CProjectionError(ValueError):
    pass


def canonical_sha256(payload: object) -> str:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(body).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise Stage10CProjectionError(f"naive datetime rejected: {value}")
    return parsed.astimezone(UTC)


def optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def build_fixture_payload(item: dict[str, Any]) -> dict[str, Any]:
    fixture = cast(dict[str, Any], item["fixture"])
    card = cast(dict[str, Any], item["card"])
    temporal = cast(dict[str, Any], item["temporal"])
    integrity = cast(dict[str, Any], item["integrity"])
    ranking = cast(list[dict[str, Any]], item["market_ranking"])
    market_probabilities = cast(dict[str, Any], item.get("market_probabilities", {}))
    model_probabilities = cast(dict[str, Any], item.get("model_probabilities", {}))
    expected_goals = cast(dict[str, Any], item.get("expected_goals", {}))
    captured_at = str(temporal.get("source_captured_at") or fixture.get("last_captured"))
    parse_utc(captured_at)
    parse_utc(str(fixture["kickoff_utc"]))
    primary = cast(dict[str, Any], card.get("primary_market_direction") or {})
    secondary = card.get("secondary_market_direction")
    return {
        "fixture_id": str(fixture["fixture_id"]),
        "provider_fixture_id": str(fixture["fixture_id"]),
        "competition_id": str(fixture["competition_id"]),
        "competition_name": str(fixture["competition_name"]),
        "stage": fixture.get("stage"),
        "kickoff_utc": str(fixture["kickoff_utc"]),
        "status": str(fixture["status"]),
        "home_team_id": str(fixture["home_team_id"]),
        "home_team_name": str(fixture["home_team_name"]),
        "away_team_id": str(fixture["away_team_id"]),
        "away_team_name": str(fixture["away_team_name"]),
        "venue": fixture.get("venue"),
        "captured_at": captured_at,
        "phase": temporal.get("source_phase"),
        "decision_status": str(card["action"]),
        "research_value_lean": primary.get("selection"),
        "formal_recommendation": False,
        "candidate": False,
        "gate4_status": card.get("gate4_status", "PROVISIONAL_FORWARD_HOLDOUT_PENDING"),
        "data_status": str(fixture.get("data_health", "READY")),
        "bookmaker_count": max(
            int(row.get("valid_bookmaker_count", 0) or 0) for row in ranking
        )
        if ranking
        else 0,
        "market_coverage": {
            "ONE_X_TWO": any(row.get("market") == "ONE_X_TWO" for row in ranking),
            "ASIAN_HANDICAP": any(row.get("market") == "ASIAN_HANDICAP" for row in ranking),
            "TOTALS": any(row.get("market") == "TOTALS" for row in ranking),
            "BTTS": any(row.get("market") == "BTTS" for row in ranking),
        },
        "market_probabilities": market_probabilities,
        "independent_model_probabilities": model_probabilities,
        "expected_goals": expected_goals,
        "value_rows": ranking,
        "all_market_ranking": ranking,
        "ah_ladder": [row for row in ranking if row.get("market") == "ASIAN_HANDICAP"],
        "ou_ladder": [row for row in ranking if row.get("market") == "TOTALS"],
        "primary_market": primary.get("market"),
        "primary_selection": primary.get("selection"),
        "primary_line": primary.get("line"),
        "primary_executable_odds": optional_str(primary.get("executable_decimal_odds")),
        "primary_hong_kong_odds": optional_str(primary.get("hong_kong_odds")),
        "primary_model_fair_odds": optional_str(primary.get("model_fair_odds")),
        "primary_risk_adjusted_ev": optional_str(primary.get("risk_adjusted_ev")),
        "secondary_market_direction": secondary,
        "research_grade": card.get("published_grade"),
        "published_grade": card.get("published_grade"),
        "risk_notes": card.get("invalidation_conditions", []),
        "temporal_status": temporal.get("temporal_status"),
        "valuation_generated_at": temporal.get("valuation_generated_at"),
        "projector_generated_at": temporal.get("projector_generated_at"),
        "integrity_status": integrity.get("integrity_status"),
        "source_manifest_sha256": canonical_sha256(item),
        "provenance": {
            "source": "stage10c_matchday_report",
            "snapshot_id": temporal.get("source_snapshot_id"),
            "snapshot_semantics": "CAPTURED_AT",
        },
    }


def validate_item(item: dict[str, Any]) -> None:
    card = cast(dict[str, Any], item.get("card"))
    if not isinstance(card, dict):
        raise Stage10CProjectionError("card missing")
    if card.get("action") not in ALLOWED_DECISIONS:
        raise Stage10CProjectionError("decision must be WATCH or SKIP")
    if card.get("formal_recommendation") is not False:
        raise Stage10CProjectionError("formal recommendation must remain false")
    if card.get("candidate") is not False:
        raise Stage10CProjectionError("candidate must remain false")
    if "recommend" in json.dumps(item, ensure_ascii=False).lower():
        allowed = "formal_recommendation"
        text = json.dumps(item, ensure_ascii=False).lower().replace(allowed, "")
        if "recommend" in text:
            raise Stage10CProjectionError("recommendation language found")


def checkpoint_payloads(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = report.get("items")
    if not isinstance(items, list):
        raise Stage10CProjectionError("items must be a list")
    projected_items: list[dict[str, Any]] = []
    payloads: dict[str, dict[str, Any]] = {}
    for raw_item in items:
        item = cast(dict[str, Any], raw_item)
        validate_item(item)
        fixture_payload = build_fixture_payload(item)
        fixture_id = fixture_payload["fixture_id"]
        projected_item = {
            **item,
            "fixture": {**cast(dict[str, Any], item["fixture"]), **fixture_payload},
        }
        projected_items.append(projected_item)
        payloads[f"dashboard:fixture_latest:{fixture_id}"] = fixture_payload
        payloads[
            f"dashboard:stage10c_matchday_card:{fixture_id}"
        ] = projected_item
    aggregate = {
        "items": projected_items,
        "projected_at": datetime.now(UTC).isoformat(),
        "source": "W2_STAGE10C_ALL_MARKET_CARDS.json",
        "formal_recommendation": False,
        "candidate": False,
    }
    payloads["dashboard:stage10c_matchday_cards"] = aggregate
    return payloads


def write_payloads(engine: Engine, payloads: dict[str, dict[str, Any]]) -> None:
    now = datetime.now(UTC)
    with Session(engine) as session:
        for key, payload in payloads.items():
            source_hash = canonical_sha256(payload)
            existing = session.scalar(
                select(ReadModelCheckpointModel).where(
                    ReadModelCheckpointModel.checkpoint_key == key
                )
            )
            if existing is None:
                session.add(
                    ReadModelCheckpointModel(
                        checkpoint_key=key,
                        source_hash=source_hash,
                        created_at=now,
                        payload=payload,
                    )
                )
            else:
                existing.source_hash = source_hash
                existing.created_at = now
                existing.payload = payload
        session.commit()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Project Stage10C matchday reports into dashboard read model checkpoints."
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=ROOT / "reports",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--database-url-from-env", action="store_true")
    args = parser.parse_args()
    report = load_json(args.reports_dir / "W2_STAGE10C_ALL_MARKET_CARDS.json")
    payloads = checkpoint_payloads(report)
    if not args.dry_run:
        if not args.database_url_from_env:
            parser.error("--database-url-from-env is required when writing read models")
        write_payloads(create_engine(), payloads)
    print(
        json.dumps(
            {
                "status": "DRY_RUN" if args.dry_run else "PROJECTED",
                "checkpoint_count": len(payloads),
                "fixture_count": sum(
                    1 for key in payloads if key.startswith("dashboard:fixture_latest:")
                ),
                "checkpoint_keys": sorted(payloads),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
