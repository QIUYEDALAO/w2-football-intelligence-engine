from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from w2.models.fair_market_estimate import verify_estimate_snapshot


def evaluate_dayview_business_readiness(payload: dict[str, Any]) -> dict[str, Any]:
    cards = _cards(payload)
    ready_estimates = 0
    ready_fixtures: set[str] = set()
    market_cards = 0
    failures: list[str] = []
    blocker_sets: list[set[str]] = []
    for card in cards:
        blockers = set(_strings(card.get("blockers")))
        blockers.update(_strings(_mapping(card.get("data_readiness")).get("blockers")))
        blocker_sets.append(blockers)
        if "DECISION_SOURCE_INCONSISTENT" in blockers:
            failures.append(f"DECISION_SOURCE_INCONSISTENT:{card.get('fixture_id')}")
        snapshots = _rows(card.get("fair_market_estimate_snapshots"))
        has_market = bool(
            card.get("market_observations")
            or card.get("markets")
            or card.get("current_odds")
            or card.get("pick")
        )
        if has_market:
            market_cards += 1
        for snapshot in snapshots:
            if str(snapshot.get("status") or "") != "READY":
                continue
            ready_estimates += 1
            ready_fixtures.add(str(card.get("fixture_id") or ""))
            required = (
                "home_mu", "away_mu", "fair_line", "artifact_hash", "artifact_version",
                "train_cutoff", "feature_as_of",
            )
            missing = [field for field in required if snapshot.get(field) in (None, "")]
            if missing:
                failures.append(
                    f"READY_FME_MISSING:{card.get('fixture_id')}:{','.join(missing)}"
                )
            if not verify_estimate_snapshot(snapshot):
                failures.append(f"FME_INTEGRITY_INVALID:{card.get('fixture_id')}")
        tier = str(card.get("decision_tier") or "")
        if tier in {"ANALYSIS_PICK", "RECOMMEND"}:
            reference = _mapping(card.get("scoreline_reference"))
            if not _rows(reference.get("direction_scorelines")):
                failures.append(f"DIRECTION_EXPLANATION_MISSING:{card.get('fixture_id')}")

    feature_faults = {
        "MISSING_XG", "DATA_MISSING_XG", "MODEL_FAIR_LINE_UNAVAILABLE",
        "PROVIDER_EMPTY_OR_UNAVAILABLE", "DECISION_SOURCE_INCONSISTENT",
    }
    uniform_feature_failure = all(
        blockers & feature_faults for blockers in blocker_sets
    )
    if cards and ready_estimates == 0 and uniform_feature_failure:
        failures.append("ALL_FIXTURES_BLOCKED_BY_FEATURE_CHAIN")
    return {
        "status": "PASS" if not failures else "BLOCKED",
        "fixture_count": len(cards),
        "market_fixture_count": market_cards,
        "ready_fme_count": ready_estimates,
        "fme_readiness_coverage": (
            len(ready_fixtures) / market_cards if market_cards else 0.0
        ),
        "failures": sorted(set(failures)),
        "recommendation_count": sum(
            str(card.get("decision_tier") or "") in {"ANALYSIS_PICK", "RECOMMEND"}
            for card in cards
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check staging DayView business readiness")
    parser.add_argument("--url", required=True)
    parser.add_argument("--audit-file", type=Path)
    args = parser.parse_args()
    request = Request(args.url, headers={"Accept": "application/json"})  # noqa: S310
    with urlopen(request, timeout=15) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    report = evaluate_dayview_business_readiness(payload if isinstance(payload, dict) else {})
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.audit_file:
        args.audit_file.parent.mkdir(parents=True, exist_ok=True)
        args.audit_file.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["status"] == "PASS" else 2


def _cards(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("cards", "all"):
        rows = _rows(payload.get(key))
        if rows:
            return rows
    return []


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"business readiness check failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
