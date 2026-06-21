#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from w2.ingestion.service import IngestionService
from w2.normalization.api_football import parse_datetime

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "fixtures/provider/api_football/offline_gate2_fixture.json"


def load_payload(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_replay(path: Path) -> dict[str, object]:
    payload = load_payload(path)
    captured_at = parse_datetime(str(payload["captured_at"]))
    service = IngestionService()
    fixtures = service.replay_api_football_payload(
        endpoint="fixtures",
        payload=payload["fixtures"],  # type: ignore[arg-type]
        captured_at=captured_at,
        now=datetime.fromisoformat("2026-06-22T03:00:00+00:00"),
    )
    odds = service.replay_api_football_payload(
        endpoint="odds",
        payload=payload["odds"],  # type: ignore[arg-type]
        captured_at=captured_at,
        now=datetime.fromisoformat("2026-06-22T03:00:00+00:00"),
    )
    replay = service.replay_api_football_payload(
        endpoint="odds",
        payload=payload["odds"],  # type: ignore[arg-type]
        captured_at=captured_at,
        now=datetime.fromisoformat("2026-06-22T03:00:00+00:00"),
    )
    result = {
        "gate2_status": "PROVISIONAL",
        "raw_payload_count": service.raw_store.count(),
        "fixtures_hash": fixtures.raw.reference.sha256,
        "odds_hash": odds.raw.reference.sha256,
        "provider_mapping_count": len(fixtures.provider_mappings) + len(odds.provider_mappings),
        "odds_observation_count": len(odds.odds_observations),
        "odds_replay_duplicate_count": len(replay.odds_observations),
        "feature_snapshot_count": len(fixtures.feature_snapshots) + len(odds.feature_snapshots),
        "freshness_alert_count": len(fixtures.freshness_alerts) + len(odds.freshness_alerts),
    }
    if result["odds_replay_duplicate_count"] != 0:
        raise SystemExit("replay idempotency failed")
    if result["gate2_status"] != "PROVISIONAL":
        raise SystemExit("Gate 2 must remain PROVISIONAL")
    print(json.dumps(result, sort_keys=True, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.live:
        raise SystemExit("--live is forbidden for W2 Stage 4A replay")
    run_replay(Path(args.fixture))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

