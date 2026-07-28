from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = ROOT / "docs/runbooks/W2_LEAGUE_EXPANSION_RUNBOOK.md"


def test_league_expansion_runbook_is_unique_and_complete() -> None:
    runbooks = sorted((ROOT / "docs/runbooks").glob("*LEAGUE_EXPANSION_RUNBOOK*.md"))
    assert runbooks == [RUNBOOK]

    text = RUNBOOK.read_text(encoding="utf-8")
    required = (
        "scripts/seed_competition_runtime_authority.py",
        "--set-enabled",
        "--enabled true",
        "--enabled false",
        "scripts/run_w2_matchday_refresh_plan.py",
        "quota_usage",
        "provider_request_logs",
        "league_readiness_audit",
        "Canonical identity gate",
        "七天观察",
        "ADVISORY",
        "STRICT",
        "BLOCKED",
        "Rollback",
        "provider_calls=0",
        "db_writes=0",
    )
    assert all(item in text for item in required)
    assert "Stage14A 本地 contract fixtures" in text
    assert "不得作为新联赛" in text
    assert "runtime 文件或 reports 文件伪造 audit" in text
