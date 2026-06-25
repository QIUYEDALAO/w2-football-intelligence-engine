from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_PATHS = [
    ROOT / "src",
    ROOT / "apps",
    ROOT / "config",
]
FORBIDDEN_ACTIVE_MARKERS = (
    "must_beat_market",
    "NOT_BEATEN",
    "BEATEN",
    "beat-market",
    "market-beating",
    "打赢市场",
)
REQUIRED_TEXT = "分析参考·非稳赢"


def main() -> int:
    failures: list[str] = []
    for root in ACTIVE_PATHS:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix in {".pyc", ".png", ".jpg", ".jpeg"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in FORBIDDEN_ACTIVE_MARKERS:
                if marker in text:
                    failures.append(f"{path.relative_to(ROOT)} contains {marker}")
    analysis_module = ROOT / "src/w2/strategy/analysis_recommendation.py"
    if REQUIRED_TEXT not in analysis_module.read_text(encoding="utf-8"):
        failures.append("analysis recommendation disclaimer is missing")
    if failures:
        for failure in failures:
            print(f"analysis governance FAIL: {failure}")
        return 1
    print("analysis governance PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
