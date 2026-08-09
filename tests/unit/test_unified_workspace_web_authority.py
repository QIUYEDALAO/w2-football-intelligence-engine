from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_dashboard_uses_only_the_unified_intelligence_workspace() -> None:
    page = source("apps/web/src/components/DashboardPage.tsx")
    workspace_api = source("apps/web/src/lib/intelligenceWorkspaceApi.ts")
    console = source("apps/web/src/components/IntelligenceConsole.tsx")

    assert "fetchIntelligenceWorkspace" in page
    assert "/dashboard/intelligence-workspace" in workspace_api
    assert "/dashboard/day-view" not in workspace_api
    assert "IntelligenceConsole" in page
    assert "W2 INTELLIGENCE" in console
    assert "Attention" in console
    assert "Match Board" in console
    assert "Data & Operations" in console
    assert "MODEL_MARKET_DISAGREEMENT" in console
    assert "no legacy dashboard or synthetic data" in page


def test_legacy_product_presentations_are_absent() -> None:
    for path in (
        "apps/web/src/components/BossDecisionView.tsx",
        "apps/web/src/components/RecommendationBoard.tsx",
        "apps/web/src/components/RecommendationCard.tsx",
        "apps/web/src/components/PerformancePage.tsx",
        "apps/web/src/lib/dashboardApi.ts",
        "apps/web/src/lib/performanceApi.ts",
    ):
        assert not (ROOT / path).exists()


def test_unified_empty_state_is_fail_closed() -> None:
    page = source("apps/web/src/components/DashboardPage.tsx")
    console = source("apps/web/src/components/IntelligenceConsole.tsx")

    assert "Unified workspace unavailable" in page
    assert "Empty football day" in console
    assert "No selected fixture" in console
    assert "DataDiagnosticsPanel" not in page
