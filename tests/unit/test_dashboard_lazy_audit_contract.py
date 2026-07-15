from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_first_screen_uses_dayview_only() -> None:
    body = (ROOT / "apps/web/src/lib/dashboardApi.ts").read_text(encoding="utf-8")

    fetch_body = body.split("export async function fetchDashboardView", 1)[1]
    assert "fetchDashboardDayViewPayloadRequired" in fetch_body
    assert "fetchDashboardPayload(" not in fetch_body
    assert "include_debug=true" not in fetch_body


def test_l2_is_lazy_singleflight_and_release_scoped() -> None:
    api = (ROOT / "apps/web/src/lib/dashboardApi.ts").read_text(encoding="utf-8")
    view = (ROOT / "apps/web/src/components/BossDecisionView.tsx").read_text(
        encoding="utf-8"
    )

    assert "fixtureAuditInflight" in api
    assert "fixtureAuditCache" in api
    assert "FIXTURE_AUDIT_CACHE_MAX_ENTRIES = 64" in api
    assert "FIXTURE_AUDIT_CACHE_TTL_MS" in api
    assert "activeFixtureAuditRelease" in api
    assert "fetchFixtureAuditDetails" in api
    fetch_body = api.split("export function fetchFixtureAuditDetails", 1)[1].split(
        "export function fetchFixtureOddsTimeline", 1
    )[0]
    assert (
        'const key = [fixtureId, captureHash, estimateId ?? "NO_ESTIMATE", apiReleaseSha]'
        in fetch_body
    )
    assert "Promise.all" not in fetch_body
    assert "/audit-detail" in fetch_body
    assert "capture_hash" in fetch_body
    for forbidden in (
        "/analysis-card",
        "/integrity",
        "/market-probabilities",
        "/model-probabilities",
        "/odds-timeline",
    ):
        assert forbidden not in fetch_body
    timeline_body = api.split("export function fetchFixtureOddsTimeline", 1)[1]
    assert "/odds-timeline" in timeline_body
    assert "fixtureTimelineInflight" in timeline_body
    assert "fixtureTimelineCache" in timeline_body
    assert "onToggle" in view
    assert "fetchFixtureAuditDetails" in view
    assert "fetchFixtureOddsTimeline" in view
    assert "card.audit_capture_hash" in view
    assert "card.audit_estimate_id" in view
    assert "auditIdentityRef.current === requestedIdentity" in view
    assert "L2 技术诊断加载失败" in view
    assert "盘口时间线" in view


def test_cached_dayview_is_explicitly_stale() -> None:
    api = (ROOT / "apps/web/src/lib/dashboardApi.ts").read_text(encoding="utf-8")
    page = (ROOT / "apps/web/src/components/DashboardPage.tsx").read_text(
        encoding="utf-8"
    )

    assert 'cache_status: "STALE_CACHE"' in api
    assert "STALE_CACHE" in page
    assert "缓存快照" in page
