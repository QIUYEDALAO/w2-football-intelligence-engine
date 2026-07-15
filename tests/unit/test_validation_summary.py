from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_dashboard_hides_rate_when_integrity_blocked() -> None:
    body = (ROOT / "apps/web/src/components/BossDecisionView.tsx").read_text(
        encoding="utf-8"
    )

    assert "验证口径校验中，暂不用于决策" in body
    assert "performanceIntegrity.status === \"BLOCKED\"" in body


def test_dashboard_labels_legacy_canonical_performance() -> None:
    body = (ROOT / "apps/web/src/components/BossDecisionView.tsx").read_text(
        encoding="utf-8"
    )

    assert "历史兼容口径，不属于 corrected evidence" in body


def test_dashboard_normalizer_preserves_l2_outcome_audit() -> None:
    body = (ROOT / "apps/web/src/lib/dashboardApi.ts").read_text(encoding="utf-8")

    for field in (
        "performance_integrity",
        "outcomes_raw_audit",
        "outcomes_shadow_wide",
        "outcomes_shadow_strict",
        "outcomes_official",
    ):
        assert field in body


def test_dashboard_calls_raw_outcomes_rows_not_fixtures() -> None:
    body = (ROOT / "apps/web/src/components/BossDecisionView.tsx").read_text(
        encoding="utf-8"
    )

    assert "原始 outcome 行" in body
    assert "原始 outcome 场" not in body
