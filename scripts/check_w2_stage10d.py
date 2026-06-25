from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"STAGE10D_CHECK_FAILED: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def main() -> int:
    policy_path = ROOT / "config/policies/matchday_timezone.v1.json"
    require(policy_path.exists(), "missing matchday timezone policy")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    require(policy["display_timezone"] == "Asia/Shanghai", "display timezone must be Beijing")
    require(policy["operations_timezone"] == "Asia/Shanghai", "operations timezone must be Beijing")
    require(policy["storage_timezone"] == "UTC", "storage timezone must be UTC")
    require(
        policy["window_semantics"] == "LEFT_CLOSED_RIGHT_OPEN",
        "window semantics must be left-closed right-open",
    )

    timezone_code = (ROOT / "src/w2/matchday/timezone.py").read_text(encoding="utf-8")
    coverage_code = (ROOT / "src/w2/matchday/coverage.py").read_text(encoding="utf-8")
    repository_code = (ROOT / "src/w2/api/repository.py").read_text(encoding="utf-8")
    routers_code = (ROOT / "src/w2/api/routers.py").read_text(encoding="utf-8")
    web_code = (ROOT / "apps/web/src/main.tsx").read_text(encoding="utf-8")
    tests = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "tests").glob("**/*.py"))

    require("ZoneInfo" in timezone_code, "must use zoneinfo")
    require("timedelta(hours=8)" not in timezone_code, "must not use hard-coded UTC+8 arithmetic")
    require("OperationalDayWindow" in timezone_code, "missing OperationalDayWindow")
    require("BeijingOperationalDayPolicy" in timezone_code, "missing Beijing policy")
    require("FixtureOperationalDateResolver" in timezone_code, "missing operational date resolver")
    require("MatchdayCoverageReconciler" in coverage_code, "missing coverage reconciler")
    require("MISSING_REASONS" in coverage_code, "missing missing-reason registry")
    require("kickoff_beijing" in repository_code, "API must expose kickoff_beijing")
    require(
        "operational_date_beijing" in repository_code,
        "API must expose operational_date_beijing",
    )
    require("matchday_next_36_hours" in repository_code, "missing next 36 hours service")
    require("/matchday/next-36-hours" in routers_code, "missing next 36 hours route")
    require("/matchday-coverage" in routers_code, "missing matchday coverage ops route")
    require("Asia/Shanghai" in web_code, "web must display Beijing policy")
    require("未来36小时" in web_code, "web must include next 36 hours view")
    require("Coverage Audit" in web_code, "web must include coverage audit")
    require(
        "Asia/Tokyo" not in web_code + repository_code + routers_code + tests,
        "Japan user window forbidden",
    )
    require("Tokyo" not in tests, "Tokyo boundary tests forbidden")

    for name in [
        "W2_STAGE10D_FIXTURE_RECONCILIATION.json",
        "W2_STAGE10D_BEIJING_TIME_AUDIT.json",
        "W2_STAGE10D_COVERAGE.json",
        "W2_STAGE10D_RESULT.md",
    ]:
        require((ROOT / "reports" / name).exists(), f"missing report {name}")

    coverage = json.loads((ROOT / "reports/W2_STAGE10D_COVERAGE.json").read_text(encoding="utf-8"))
    require(coverage["timezone"] == "Asia/Shanghai", "coverage timezone must be Beijing")
    require(coverage["coverage_status"] in {"READY", "PARTIAL", "BLOCKED"}, "bad coverage status")
    require("UNKNOWN" not in coverage.get("reason_distribution", {}), "unknown reason forbidden")

    print(
        json.dumps(
            {"stage": "10D", "status": "PASS", "timezone": "Asia/Shanghai"},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
