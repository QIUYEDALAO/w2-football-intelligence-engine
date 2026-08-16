from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs/review_packages/SC19_TEAM_IDENTITY_AND_DATE_STRIP"


def load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def main() -> None:
    trace = load(PACKAGE / "SC19_TEAM_IDENTITY_TRACE.json")
    coverage = load(PACKAGE / "PUBLIC_LABEL_COVERAGE_MATRIX.json")
    labels = load(ROOT / "config/identity/public_team_labels.zh-CN.v1.json")
    fixtures = trace["fixtures"]
    assert isinstance(fixtures, list) and len(fixtures) == 5
    sides = [side for fixture in fixtures for side in fixture["sides"]]
    assert len(sides) == 10
    assert sum(side["public_label_state"] == "CHINESE_LABEL_READY" for side in sides) == 4
    assert sum(side["classification"] == "GENUINELY_UNRESOLVED" for side in sides) == 6
    assert coverage["target_football_day"]["recoverable_placeholder_count"] == 0
    assert trace["provider_calls"] == trace["db_writes"] == 0
    assert coverage["provider_calls"] == coverage["db_writes"] == 0
    assert sum(entry["review_status"] == "APPROVED" for entry in labels["entries"]) == 66
    assert {
        int(str(entry["w2_team_id"]).rsplit(":", 1)[-1])
        for entry in labels["entries"]
        if entry["review_status"] == "PENDING_OWNER_REVIEW"
    } == {319, 325, 326, 329, 332, 333, 757, 2149}

    date_strip = (ROOT / "src/w2/dashboard/date_strip.py").read_text(encoding="utf-8")
    repository = (ROOT / "src/w2/api/repository.py").read_text(encoding="utf-8")
    console = (ROOT / "apps/web/src/components/IntelligenceConsole.tsx").read_text(
        encoding="utf-8"
    )
    assert "WINDOW_RADIUS_DAYS = 7" in date_strip
    assert "PERSISTED_FIXTURE_OUTSIDE_MARKET_COLLECTION_WINDOW" in date_strip
    assert "MARKET_COLLECTION_DUE_EVIDENCE_NOT_READY" in date_strip
    assert "def persisted_date_strip(" in repository
    assert "session.commit" not in repository[repository.index("def persisted_date_strip(") :]
    assert "workspace.date_strip.slice" in console
    assert "不额外查询 Provider" in console
    print("SC19 team identity and date strip check PASS")


if __name__ == "__main__":
    main()
