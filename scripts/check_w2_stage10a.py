#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "src/w2/api/schemas.py",
    "src/w2/api/repository.py",
    "src/w2/api/routers.py",
    "src/w2/api/cache.py",
    "src/w2/api/metrics.py",
    "src/w2/infrastructure/persistence/api_models.py",
    "migrations/versions/0011_create_stage10a_read_api.py",
    "contracts/openapi/w2-stage10a-openapi.json",
    "docs/adr/ADR-0013-readonly-api-and-console.md",
    "docs/api/W2_READ_API_V1.md",
    "docs/api/W2_OPERATIONS_READ_API_V1.md",
    "docs/runbooks/STAGE10A_LOCAL_OPERATIONS.md",
    "reports/W2_STAGE10A_API_CONTRACT.json",
    "reports/W2_STAGE10A_RESULT.md",
    "apps/web/src/main.tsx",
    "apps/web/src/styles.css",
]

PUBLIC_PATHS = {
    "/v1/fixtures",
    "/v1/fixtures/{fixture_id}",
    "/v1/fixtures/{fixture_id}/odds-timeline",
    "/v1/fixtures/{fixture_id}/market-probabilities",
    "/v1/fixtures/{fixture_id}/model-probabilities",
    "/v1/data-health",
    "/v1/providers/status",
    "/v1/backtests/latest",
    "/v1/forward-holdout/status",
}
OPS_PATHS = {
    "/ops/health",
    "/ops/quota",
    "/ops/tasks",
    "/ops/alerts",
    "/ops/mapping-conflicts",
    "/ops/forward-cycles",
    "/ops/locks",
    "/ops/settlements",
    "/ops/gates",
}


def fail(message: str) -> None:
    print(f"W2 Stage10A check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def load(path: str) -> object:
    return json.loads(read(path))


def main() -> int:
    for path in REQUIRED:
        if not (ROOT / path).is_file():
            fail(f"missing {path}")
    openapi = load("contracts/openapi/w2-stage10a-openapi.json")
    paths = set(openapi["paths"])  # type: ignore[index]
    if not PUBLIC_PATHS.issubset(paths):
        fail("missing public read paths")
    if not OPS_PATHS.issubset(paths):
        fail("missing operations read paths")
    forbidden = ["recommendations", "candidates", "deepseek"]
    for path in paths:
        lowered = path.lower()
        if any(token in lowered for token in forbidden):
            fail(f"forbidden route present: {path}")
    for path, methods in openapi["paths"].items():  # type: ignore[index]
        for method in methods:
            if method.lower() not in {"get", "parameters"}:
                fail(f"non-read method present: {method} {path}")
    combined = "\n".join(read(path) for path in REQUIRED if path.endswith((".py", ".md", ".tsx")))
    for token in [
        "ReadModelRepository",
        "ReadModelService",
        "ReadOnlyResponseCache",
        "ETag",
        "request_id",
        "operations API disabled in production",
        "market_fair_probability",
        "independent_model_probability",
        "WATCH/SKIP",
        "正式推荐尚未启用，当前仅为研究与前瞻验证。",
    ]:
        if token not in combined:
            fail(f"missing Stage10A token {token}")
    api_contract = load("reports/W2_STAGE10A_API_CONTRACT.json")
    if api_contract["recommendation_api"] != "DISABLED":  # type: ignore[index]
        fail("recommendation API must be disabled")
    result = read("reports/W2_STAGE10A_RESULT.md")
    for token in [
        "STAGE_10A=COMPLETED",
        "STAGE_10=PROVISIONAL",
        "READ_API=ENABLED_LOCAL_OR_STAGING",
        "OPERATIONS_API=READ_ONLY",
        "RECOMMENDATION_API=DISABLED",
        "GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING",
        "STAGE_9=BLOCKED",
        "PUSH_BLOCKED_NO_ORIGIN",
    ]:
        if token not in result:
            fail(f"missing result status {token}")
    print("W2 Stage10A check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
