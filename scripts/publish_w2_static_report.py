from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from w2.reporting.report_generator import HTML_RENDERER_VERSION
from w2.reporting.report_runner import run_report_job

FORBIDDEN_TERMS = (
    "命中率",
    "胜率",
    "ROI",
    "必中",
    "必胜",
    "稳赢",
    "稳赚",
    "可买",
    "庄家开错",
    "跟庄",
    "照这个买",
    "方向未识别",
    "正式推荐字段不完整",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Publish the current W2 football-day HTML report as the static web root."
        )
    )
    parser.add_argument("--base-url", default="http://43.155.208.138")
    parser.add_argument("--window", default="today")
    parser.add_argument("--runtime-root", type=Path, default=Path("runtime"))
    parser.add_argument(
        "--public-root",
        type=Path,
        help="Defaults to <runtime-root>/reports/public.",
    )
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--min-watermark-count", type=int, default=2)
    args = parser.parse_args()

    try:
        summary = publish_static_report(
            base_url=args.base_url,
            window=args.window,
            runtime_root=args.runtime_root,
            public_root=args.public_root,
            timeout_seconds=args.timeout,
            min_watermark_count=args.min_watermark_count,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


def publish_static_report(
    *,
    base_url: str,
    window: str = "today",
    runtime_root: Path = Path("runtime"),
    public_root: Path | None = None,
    timeout_seconds: float = 20,
    min_watermark_count: int = 2,
) -> dict[str, Any]:
    result = run_report_job(
        base_url=base_url,
        window=window,
        report_type="final",
        output_format="html",
        sink="file",
        runtime_root=runtime_root,
        include_debug=True,
        timeout_seconds=timeout_seconds,
    )
    if result.output_path is None:
        raise RuntimeError("STATIC_REPORT_PUBLISH_FAILED: missing html output path")
    html = result.output_path.read_text(encoding="utf-8")
    validation = validate_static_report_html(
        html,
        min_watermark_count=min_watermark_count,
    )
    target_root = public_root or runtime_root / "reports" / "public"
    target_root.mkdir(parents=True, exist_ok=True)
    index_path = target_root / "index.html"
    _atomic_write(index_path, html)
    day_alias = target_root / result.output_path.name
    if day_alias != index_path:
        _atomic_write(day_alias, html)
    return {
        "status": "PASS",
        "static_report_published": True,
        "renderer": HTML_RENDERER_VERSION,
        "source_report": str(result.output_path),
        "public_index": str(index_path),
        "public_day_page": str(day_alias),
        "selected_football_day": result.status_summary.get("selected_football_day"),
        "rows": result.status_summary.get("rows"),
        "provider_calls": 0,
        "db_writes": 0,
        "production_deploy": False,
        "lock_capture_write": False,
        "settlement_write": False,
        **validation,
    }


def validate_static_report_html(
    html: str,
    *,
    min_watermark_count: int = 2,
) -> dict[str, Any]:
    watermark_count = html.count(HTML_RENDERER_VERSION)
    if watermark_count < min_watermark_count:
        raise RuntimeError(
            "STATIC_REPORT_WATERMARK_MISSING: "
            f"{HTML_RENDERER_VERSION} count={watermark_count}"
        )
    forbidden = [term for term in FORBIDDEN_TERMS if term in html]
    if forbidden:
        raise RuntimeError(
            "STATIC_REPORT_FORBIDDEN_TERMS: " + ",".join(sorted(forbidden))
        )
    if "<!doctype html>" not in html.lower():
        raise RuntimeError("STATIC_REPORT_NOT_HTML")
    return {
        "watermark": HTML_RENDERER_VERSION,
        "watermark_count": watermark_count,
        "forbidden_term_count": 0,
    }


def _atomic_write(path: Path, text: str) -> None:
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
