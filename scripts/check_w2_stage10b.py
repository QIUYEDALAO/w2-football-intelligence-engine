from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    web = (ROOT / "apps/web/src/main.tsx").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile.web").read_text(encoding="utf-8")
    nginx = (ROOT / "apps/web/nginx.conf").read_text(encoding="utf-8")
    compose = (ROOT / "infra/compose/compose.staging.yml").read_text(encoding="utf-8")
    projector = (ROOT / "scripts/project_stage10b_live_snapshot.py").read_text(encoding="utf-8")
    repository = (ROOT / "src/w2/api/repository.py").read_text(encoding="utf-8")
    read_models = (ROOT / "src/w2/api/dashboard_read_models.py").read_text(encoding="utf-8")

    assert_true("/api/v1/fixtures" in web, "web must use same-origin /api/v1 paths")
    assert_true("/api/ops/" in web, "web must use same-origin /api/ops paths")
    forbidden_frontend = ["127.0.0.1:18000", "api:8000", "43.155.208.138", "VITE_API_BASE_URL"]
    for token in forbidden_frontend:
        assert_true(token not in web, f"frontend hard-coded API target: {token}")
    assert_true("location /api/" in nginx, "nginx /api proxy missing")
    assert_true("proxy_pass http://api:8000/" in nginx, "nginx proxy_pass must target api service")
    assert_true(
        "COPY apps/web/nginx.conf" in dockerfile,
        "web Dockerfile must install nginx config",
    )
    assert_true(
        "VITE_API_BASE_URL" not in compose,
        "staging web must not depend on VITE_API_BASE_URL",
    )
    assert_true(
        "MatchdaySnapshotProjector" in projector,
        "projector CLI missing snapshot projector",
    )
    assert_true(
        "--database-url-from-env" in projector,
        "projector must require database URL from env",
    )
    assert_true(
        "dashboard:fixture_latest" in repository,
        "API must read dashboard fixture checkpoints",
    )
    assert_true(
        "formal_recommendation" in read_models,
        "read model must preserve recommendation disabled state",
    )
    assert_true("recommendations" not in web.lower(), "web must not render recommendations")
    assert_true("candidate" not in web.lower(), "web must not render candidate UI")
    assert_true("deepseek" not in web.lower(), "web must not render deepseek UI")

    openapi_path = ROOT / "contracts/openapi/w2-stage10a-openapi.json"
    assert_true(openapi_path.exists(), "OpenAPI snapshot missing")
    snapshot = json.loads(openapi_path.read_text(encoding="utf-8"))
    forbidden_routes = re.compile(r"(recommend|candidate|deepseek)", re.IGNORECASE)
    for route in snapshot.get("paths", {}):
        assert_true(not forbidden_routes.search(route), f"forbidden route in OpenAPI: {route}")

    print(
        json.dumps(
            {
                "status": "PASS",
                "proxy": "SAME_ORIGIN_API_PREFIX",
                "projector": "MATCHDAY_SNAPSHOT_TO_READ_MODEL",
                "recommendation_api": "DISABLED",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
