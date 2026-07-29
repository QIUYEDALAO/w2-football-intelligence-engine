from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = ROOT / "docs/runbooks/W2_LEAGUE_EXPANSION_RUNBOOK.md"
CHECKLIST = (
    ROOT
    / "docs/operations/architecture_convergence"
    / "W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md"
)


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

    assert "API_FOOTBALL_QUOTA_SCOPE = PROVIDER_ACCOUNT_DAILY" in text
    assert "ENDPOINT_LIMIT_SUMMATION = FORBIDDEN" in text
    assert "QUOTA_LIMIT_VALUES" in text
    assert "distinct limit" in text
    assert "QUOTA_LIMIT_CONFLICT" in text
    assert "QUOTA_WINDOW_UNKNOWN" in text
    assert "所有 endpoint 行 used 的最大值" in text
    assert "POST_ENABLE_REMAINING >= AUTHORIZED_SAFETY_HEADROOM" in text
    assert "limit 总和" not in text
    assert "used 总和" not in text
    assert "sum(limit)" not in text
    assert "sum(used)" not in text

    assert "新联赛或新赛季加入" not in text
    assert "首次注册一个新联赛及其初始 reviewed seed season" in text
    assert "first-registration / insert-only" in text
    assert "BLOCKED_SEASON_ROLLOVER_UNSUPPORTED" in text
    assert "league_profile.payload.current_season" in text
    assert "W2_SEASON_ROLLOVER_V1.md" in text
    assert "不提供可执行的 runtime 更新能力" in text

    assert "GENERIC_LEAGUE_READINESS_PRODUCER = MISSING" in text
    assert "REAL_LEAGUE_ENABLEMENT_READY = false" in text
    assert "READINESS_GATE_BLOCKED" in text
    assert "operator direct SQL 写入假 audit" in text
    checklist = CHECKLIST.read_text(encoding="utf-8")
    assert "GENERIC_LEAGUE_READINESS_PRODUCER = MISSING" in checklist
    assert "REAL_LEAGUE_ENABLEMENT_READY = false" in checklist

    assert "W2_FORMAL_RECOMMENDATION_ENABLED" in text
    assert "Formal、Lock 和 Production 状态" in text
    assert "不等于开放\nRecommendation、Candidate、Formal、Lock 或 Production" in text
