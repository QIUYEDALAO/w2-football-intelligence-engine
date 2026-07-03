from __future__ import annotations

from w2.reporting.report_generator import HTML_RENDERER_VERSION, render_report


def test_html_renderer_version_pinned() -> None:
    assert HTML_RENDERER_VERSION == "w2.html_dashboard.v5"

    html = render_report(
        {
            "selected_football_day": "2026-06-30",
            "generated_at": "2026-06-30T23:40:00Z",
            "all": [],
        },
        output_format="html",
    )

    assert 'name="w2-renderer" content="w2.html_dashboard.v5"' in html
    assert "renderer w2.html_dashboard.v5" in html
