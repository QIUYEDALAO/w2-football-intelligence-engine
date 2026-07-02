#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "src/w2/ingestion/ports.py",
    "src/w2/providers/api_football.py",
    "src/w2/ingestion/raw_store.py",
    "src/w2/ingestion/service.py",
    "src/w2/normalization/api_football.py",
    "src/w2/ingestion/quota.py",
    "src/w2/ingestion/retry.py",
    "src/w2/ingestion/freshness.py",
    "src/w2/ingestion/scheduler.py",
    "src/w2/infrastructure/persistence/ingestion_models.py",
    "migrations/versions/0003_create_stage4_ingestion_foundation.py",
    "fixtures/provider/api_football/offline_gate2_fixture.json",
    "docs/adr/ADR-0004-data-ingestion-foundation.md",
    "docs/providers/API_FOOTBALL_ADAPTER_V1.md",
    "docs/providers/SECONDARY_ODDS_PROVIDER_DECISION.md",
    "docs/runbooks/INGESTION_OFFLINE_REPLAY.md",
    "docs/runbooks/LIVE_INGESTION_CHECKPOINT.md",
    "scripts/replay_provider_fixture.py",
]

ENDPOINTS = [
    "fixtures",
    "teams",
    "standings",
    "odds",
    "lineups",
    "injuries",
    "squads",
    "fixture_detail",
    "results",
    "events",
    "statistics",
]


def fail(message: str) -> None:
    print(f"W2 Stage4 ingestion check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    for path in REQUIRED:
        if not (ROOT / path).is_file():
            fail(f"missing {path}")
    ports = read("src/w2/ingestion/ports.py")
    provider = read("src/w2/providers/api_football.py")
    migration = read("migrations/versions/0003_create_stage4_ingestion_foundation.py")
    for endpoint in ENDPOINTS:
        if endpoint not in ports:
            fail(f"missing endpoint adapter token {endpoint}")
    for token in [
        "ProviderClientPort",
        "ApiFootballClient",
        "OddsProviderPort",
        "SecondaryOddsProviderPort",
        "RawPayloadStore",
        "QuotaManager",
        "CircuitBreaker",
        "FreshnessEvaluator",
        "SNAPSHOT_PHASES",
    ]:
        if token not in "".join(read(path) for path in REQUIRED if path.endswith(".py")):
            fail(f"missing ingestion token {token}")
    if "SECONDARY_ODDS_PROVIDER=UNDECIDED" not in read(
        "docs/providers/SECONDARY_ODDS_PROVIDER_DECISION.md"
    ):
        fail("secondary odds provider must remain UNDECIDED")
    if "LiveNetworkDisabledError" not in provider or "Stage 4A" not in provider:
        fail("live network guard missing")
    for table in [
        "ingestion_runs",
        "provider_request_logs",
        "quota_usage",
        "sync_cursors",
        "freshness_alerts",
    ]:
        if table not in migration:
            fail(f"missing migration table {table}")
    fixture = json.loads(read("fixtures/provider/api_football/offline_gate2_fixture.json"))
    if "results" in json.dumps(fixture["fixtures"]).lower():
        fail("offline pre-match fixture must not leak results")
    for path in ROOT.rglob("*.py"):
        if ".venv" in path.parts or ".git" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        text = read(str(path.relative_to(ROOT)))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"urlopen", "request"} and "--live" not in text:
                    fail(f"possible unguarded network call in {path.relative_to(ROOT)}")
    print("W2 Stage4 ingestion check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
