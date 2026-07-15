from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_first_screen_requests_only_first_page_and_does_not_auto_fetch_all() -> None:
    api = (ROOT / "apps/web/src/lib/dashboardApi.ts").read_text()
    page = (ROOT / "apps/web/src/components/DashboardPage.tsx").read_text()
    initial = api.split("async function fetchDashboardDayViewPayload", 1)[1].split(
        "async function fetchDashboardDayViewPayloadRequired", 1
    )[0]
    assert 'page_size: "20"' in initial
    assert "cursor" not in initial
    assert "fetchDashboardDayViewPage" in page
    assert "while" not in page.split("async function loadMore", 1)[1].split(
        "useEffect", 1
    )[0]
    assert 'fetchDashboardPayload(' not in api.split(
        "export async function fetchDashboardView", 1
    )[1]


def test_load_more_is_cursor_bound_deduplicated_and_snapshot_safe() -> None:
    api = (ROOT / "apps/web/src/lib/dashboardApi.ts").read_text()
    page = (ROOT / "apps/web/src/components/DashboardPage.tsx").read_text()
    view = (ROOT / "apps/web/src/components/BossDecisionView.tsx").read_text()
    assert "dayViewPageInflight" in api
    assert "pagination.next_cursor" in page
    assert "new Set(current.cards.map" in page
    assert "next.pagination.snapshot_id !== current.pagination.snapshot_id" in page
    assert "数据已刷新，列表已更新" in page
    assert "加载更多比赛" in view
    assert "pagination.total_count" in view


def test_first_page_cache_is_release_and_snapshot_scoped_and_bounded() -> None:
    api = (ROOT / "apps/web/src/lib/dashboardApi.ts").read_text()
    assert "DASHBOARD_FIRST_PAGE_CACHE_MAX_BYTES = 1024 * 1024" in api
    assert "view.release.api_git_sha" in api
    assert "view.day_view?.pagination.snapshot_id" in api
    assert "new Blob([encoded]).size" in api
    assert "current.cards" not in api.split("function storeCachedDashboardView", 1)[1].split(
        "async function fetchDashboardDayViewPayload", 1
    )[0]


def test_paginated_cards_preserve_frozen_l2_identity() -> None:
    page = (ROOT / "apps/web/src/components/DashboardPage.tsx").read_text()
    view = (ROOT / "apps/web/src/components/BossDecisionView.tsx").read_text()
    assert "cards: [...current.cards, ...appended]" in page
    assert "card.audit_capture_hash" in view
    assert "card.audit_estimate_id" in view
    assert "fetchFixtureAuditDetails" in view
