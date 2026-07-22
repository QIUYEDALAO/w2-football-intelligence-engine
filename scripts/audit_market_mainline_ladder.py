#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from w2.markets.asian_handicap_mainline import select_canonical_ah_mainline
from w2.markets.totals_mainline import select_canonical_totals_mainline


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only AH/OU mainline ladder audit")
    parser.add_argument("--observations-jsonl", type=Path, required=True)
    parser.add_argument("--day-view-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _parse(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _valid_pair(left: float, right: float) -> bool:
    implied = (1 / left) + (1 / right)
    return (
        1.40 <= left <= 4.00
        and 1.40 <= right <= 4.00
        and abs(left - right) <= 0.90
        and 0.98 <= implied <= 1.30
    )


def _prices(left: float, right: float) -> dict[str, float]:
    implied_left = 1 / left
    implied_right = 1 / right
    total = implied_left + implied_right
    return {
        "devig_left_probability": round(implied_left / total, 6),
        "devig_right_probability": round(implied_right / total, 6),
        "balance_distance": round(abs((implied_left / total) - 0.5), 6),
        "implied_sum": round(total, 6),
        "price_gap": round(abs(left - right), 6),
    }


def _ah_ladder(rows: list[dict[str, Any]], selected: Any) -> list[dict[str, Any]]:
    if not rows:
        return []
    latest = max(_parse(row["captured_at"]) for row in rows)
    latest_rows = [
        row
        for row in rows
        if _parse(row["captured_at"]) == latest
        and row.get("canonical_market") == "ASIAN_HANDICAP"
        and not row.get("live")
        and not row.get("suspended")
        and str(row.get("raw_market_label") or "") == "Asian Handicap"
    ]
    by_book: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"HOME": [], "AWAY": []}
    )
    for row in latest_rows:
        side = str(row.get("canonical_selection") or row.get("selection") or "")
        if side in {"HOME", "AWAY"}:
            by_book[str(row.get("bookmaker_id") or row.get("bookmaker_name"))][side].append(row)
    pairs: list[dict[str, Any]] = []
    for bookmaker, sides in by_book.items():
        for home in sides["HOME"]:
            for away in sides["AWAY"]:
                home_line = Decimal(str(home["line"]))
                away_line = Decimal(str(away["line"]))
                if away_line not in {home_line, -home_line}:
                    continue
                home_price = float(home["decimal_odds"])
                away_price = float(away["decimal_odds"])
                if not _valid_pair(home_price, away_price):
                    continue
                pairs.append(
                    {
                        "line": home_line,
                        "bookmaker": bookmaker,
                        "home_price": home_price,
                        "away_price": away_price,
                        "observation_ids": [home["observation_id"], away["observation_id"]],
                    }
                )
    by_line: dict[Decimal, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        by_line[pair["line"]].append(pair)
    selected_line = Decimal(str(selected.line)) if selected.line is not None else None
    rejected = {
        Decimal(str(item["line"])): item["reason"] for item in selected.rejected_lines or []
    }
    result = []
    for line, line_pairs in by_line.items():
        home = float(median(float(item["home_price"]) for item in line_pairs))
        away = float(median(float(item["away_price"]) for item in line_pairs))
        result.append(
            {
                "line": float(line),
                "complete_pair_bookmakers": len({item["bookmaker"] for item in line_pairs}),
                "bookmakers": sorted({item["bookmaker"] for item in line_pairs}),
                "median_home": home,
                "median_away": away,
                **_prices(home, away),
                "status": "SELECTED_MARKET_MAINLINE" if line == selected_line else "REJECTED",
                "reason": None
                if line == selected_line
                else rejected.get(line, "LOWER_BOOKMAKER_CONSENSUS"),
                "observation_ids": sorted(
                    {value for item in line_pairs for value in item["observation_ids"]}
                ),
            }
        )
    return sorted(
        result, key=lambda item: (item["status"] != "SELECTED_MARKET_MAINLINE", item["line"])
    )


def _decision(card: dict[str, Any]) -> dict[str, Any]:
    v3 = card.get("recommendation_decision_v3") or {}
    selected = v3.get("selected_candidate") or {}
    quote = selected.get("quote_identity") or {}
    side = str(selected.get("selection") or "").lower().replace("_ah", "")
    execution = (quote.get("quotes") or {}).get(side) or {}
    model = selected.get("model_probability") or {}
    market = selected.get("market_probability") or {}
    return {
        "outcome": v3.get("outcome"),
        "reason_code": (v3.get("reason") or {}).get("code"),
        "market": selected.get("market"),
        "selection": selected.get("selection"),
        "line": selected.get("line"),
        "execution_bookmaker": execution.get("bookmaker_name"),
        "execution_odds": execution.get("decimal_odds"),
        "captured_at": execution.get("captured_at"),
        "model_probability": model.get("effective_probability"),
        "market_probability": (market.get("devig") or {}).get(selected.get("selection")),
        "probability_delta": selected.get("probability_delta"),
        "expected_value": selected.get("expected_value"),
        "uncertainty": selected.get("uncertainty"),
        "decision_hash": v3.get("decision_hash"),
        "analysis_evidence_hash": selected.get("evidence_hash"),
        "quote_identity_hash": quote.get("quote_identity_hash"),
        "quote_identity": quote,
        "selected_candidate": selected,
    }


def main() -> int:
    args = _args()
    observations = _load_jsonl(args.observations_jsonl)
    day_view = json.loads(args.day_view_json.read_text())
    cards = {str(card["fixture_id"]): card for card in day_view.get("cards", [])}
    rows_by_provider_fixture: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        rows_by_provider_fixture[str(row["provider_fixture_id"])].append(row)

    fixtures = []
    for fixture_id, card in sorted(cards.items(), key=lambda item: int(item[0])):
        rows = rows_by_provider_fixture.get(fixture_id, [])
        if not rows:
            fixtures.append(
                {
                    "fixture_id": fixture_id,
                    "home_team": card.get("home_team_name"),
                    "away_team": card.get("away_team_name"),
                    "source_status": "SOURCE_LINE_ABSENT",
                    "ah_ladder": [],
                    "ou_ladder": [],
                    "fresh_decision": _decision(card),
                }
            )
            continue
        target = max(_parse(row["captured_at"]) for row in rows)
        internal_fixture_id = str(rows[0]["fixture_id"])
        ah = select_canonical_ah_mainline(
            rows,
            fixture_id=internal_fixture_id,
            target=target,
            kickoff=datetime.max.replace(tzinfo=UTC),
        )
        totals = select_canonical_totals_mainline(
            rows,
            fixture_id=internal_fixture_id,
            target=target,
            kickoff=datetime.max.replace(tzinfo=UTC),
        )
        fixtures.append(
            {
                "fixture_id": fixture_id,
                "home_team": card.get("home_team_name"),
                "away_team": card.get("away_team_name"),
                "source_status": "READY",
                "capture_id": next(
                    (row.get("capture_id") for row in rows if _parse(row["captured_at"]) == target),
                    None,
                ),
                "captured_at": target.isoformat().replace("+00:00", "Z"),
                "market_mainline": {
                    "ASIAN_HANDICAP": float(ah.line) if ah.line is not None else None,
                    "TOTALS": float(totals.line) if totals.line is not None else None,
                },
                "current_odds": card.get("current_odds"),
                "ah_ladder": _ah_ladder(rows, ah),
                "ou_ladder": totals.candidate_lines or [],
                "fresh_decision": _decision(card),
            }
        )

    picks = [
        row for row in fixtures if row["fresh_decision"]["outcome"] == "ANALYSIS_PICK"
    ]
    selected_odds = [
        float(row["fresh_decision"]["execution_odds"])
        for row in picks
        if row["fresh_decision"]["execution_odds"] is not None
    ]
    payload = {
        "schema_version": "w2.market_mainline_ladder_audit.v1",
        "audit_mode": "READ_ONLY_NO_PROVIDER_NO_DB_WRITE",
        "source_sha": args.source_sha,
        "source_observation_count": len(observations),
        "fixture_count": len(fixtures),
        "source_ready_fixture_count": sum(row["source_status"] == "READY" for row in fixtures),
        "source_absent_fixture_count": sum(
            row["source_status"] == "SOURCE_LINE_ABSENT" for row in fixtures
        ),
        "policy": "canonical_bookmaker_mainline_consensus_v1",
        "fixtures": fixtures,
        "fresh_pick_summary": {
            "pick_count": len(picks),
            "totals_pick_count": sum(
                row["fresh_decision"]["market"] == "TOTALS" for row in picks
            ),
            "ah_pick_count": sum(
                row["fresh_decision"]["market"] == "ASIAN_HANDICAP" for row in picks
            ),
            "mean_selected_odds": round(sum(selected_odds) / len(selected_odds), 6)
            if selected_odds
            else None,
            "median_selected_odds": median(selected_odds) if selected_odds else None,
            "odds_1_65_to_1_72_count": sum(1.65 <= value <= 1.72 for value in selected_odds),
        },
        "safety": {
            "provider_calls": 0,
            "database_writes": 0,
            "recommendations": 0,
            "locks": 0,
            "official": 0,
            "formal_settlements": 0,
        },
    }
    payload["audit_hash"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    lines = [
        "# W2 Market Mainline Ladder Audit",
        "",
        f"- Source SHA: `{args.source_sha}`",
        (
            f"- Fixtures: `{len(fixtures)}` "
            f"(`{payload['source_ready_fixture_count']}` source ready, "
            f"`{payload['source_absent_fixture_count']}` source absent)"
        ),
        f"- Observations: `{len(observations)}`",
        "- Mode: `READ_ONLY_NO_PROVIDER_NO_DB_WRITE`",
        "",
        "| Fixture | Fresh V3 | Fresh selected | AH mainline | OU mainline |",
        "|---|---|---|---:|---:|",
    ]
    for row in fixtures:
        decision = row["fresh_decision"]
        mainline = row.get("market_mainline") or {}
        selected = (
            "-"
            if not decision.get("market")
            else (
                f"{decision.get('market')} {decision.get('selection')} "
                f"{decision.get('line')} @{decision.get('execution_odds')}"
            )
        )
        lines.append(
            f"| {row['fixture_id']} | {decision.get('outcome')} | {selected} | "
            f"{mainline.get('ASIAN_HANDICAP', '-')} | {mainline.get('TOTALS', '-')} |"
        )
    lines.extend(
        [
            "",
            "## Fresh Findings",
            "",
            "- Each source-ready fixture includes its full ladders, quote identity, "
            "selected-side execution price, opposite-side price, and V3 evidence hash.",
            "",
            f"Audit hash: `{payload['audit_hash']}`",
        ]
    )
    args.output_md.write_text("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
