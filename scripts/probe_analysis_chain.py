from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from w2.api.repository import ReadModelService  # noqa: E402
from w2.domain.recommendation_decision_v3 import validate_decision_v3_identity  # noqa: E402
from w2.infrastructure.database import create_engine  # noqa: E402

AUDIT_TABLES = (
    "provider_request_logs",
    "raw_payload_references",
    "matchday_endpoint_captures",
    "recommendations",
    "recommendation_locks",
    "forward_prediction_lock",
    "gate5_recommendation_lock_event",
    "shadow_strategy_lock",
    "shadow_strategy_event",
    "shadow_strategy_settlement",
    "settlements",
    "matchday_evidence_manifests",
)


def _pick(payload: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: payload.get(key) for key in keys if key in payload}


def _market_summary(market: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "market",
        "decision",
        "status",
        "selection",
        "line",
        "model_probability",
        "market_probability",
        "probability_delta",
        "expected_value",
        "uncertainty",
        "model_version",
        "calibration_version",
        "quote_identity",
        "blockers",
    ]
    return _pick(market, keys)


def _candidate_summary(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    evidence = candidate.get("analysis_evidence")
    evidence_payload = evidence if isinstance(evidence, dict) else {}
    comparison = evidence_payload.get("comparison")
    comparison_payload = comparison if isinstance(comparison, dict) else {}
    return {
        "market": candidate.get("market"),
        "selection": candidate.get("selection"),
        "line": candidate.get("line"),
        "odds": candidate.get("odds"),
        "decision": candidate.get("decision"),
        "analysis_evidence_status": candidate.get("analysis_evidence_status")
        or evidence_payload.get("status"),
        "evidence_hash": candidate.get("evidence_hash") or evidence_payload.get("evidence_hash"),
        "analysis_direction_allowed": comparison_payload.get("analysis_direction_allowed"),
        "reason_code": comparison_payload.get("reason_code"),
        "quote_identity": candidate.get("quote_identity"),
    }


def _v3_summary(card: dict[str, Any]) -> dict[str, Any]:
    v3 = card.get("recommendation_decision_v3")
    if not isinstance(v3, dict):
        return {"status": "MISSING"}
    try:
        validated_hash = validate_decision_v3_identity(v3)
        identity_status = "PASS"
    except Exception as exc:
        validated_hash = None
        identity_status = f"FAIL:{exc.__class__.__name__}"
    return {
        "status": "PRESENT",
        "identity_status": identity_status,
        "decision_hash": v3.get("decision_hash"),
        "validated_decision_hash": validated_hash,
        "outcome": v3.get("outcome"),
        "reason": v3.get("reason"),
        "selected_candidate": _candidate_summary(v3.get("selected_candidate")),
        "evaluated_candidate": _candidate_summary(v3.get("evaluated_candidate")),
        "audit_refs": v3.get("audit_refs"),
        "decision_envelope_hash": v3.get("decision_envelope_hash"),
        "hash_parity": {
            "card_hash": card.get("card_hash"),
            "decision_contract_card_hash": (card.get("decision_contract") or {}).get(
                "card_hash"
            )
            if isinstance(card.get("decision_contract"), dict)
            else None,
            "v3_audit_v2_card_hash": (v3.get("audit_refs") or {}).get("v2_card_hash")
            if isinstance(v3.get("audit_refs"), dict)
            else None,
        },
    }


def summarize_card(card: dict[str, Any] | None, fixture_id: str) -> dict[str, Any]:
    if card is None:
        return {"fixture_id": fixture_id, "status": "NO_CARD"}
    summary = _pick(
        card,
        [
            "fixture_id",
            "decision",
            "decision_tier",
            "data_status",
            "primary_market",
            "model_version",
            "calibration_version",
        ],
    )
    for key in (
        "data_readiness",
        "available_inputs",
        "recommendation",
        "simulation",
        "analysis_summary",
        "market_evidence",
        "decision_contract",
        "pick",
        "non_pick",
        "reason_code",
    ):
        if key in card:
            summary[key] = card[key]
    markets = card.get("markets")
    if isinstance(markets, list):
        summary["markets"] = [
            _market_summary(item) for item in markets if isinstance(item, dict)
        ]
    summary["v3"] = _v3_summary(card)
    market_decisions = []
    for item in markets if isinstance(markets, list) else []:
        if not isinstance(item, dict):
            continue
        market_decisions.append(
            {
                "market": item.get("market"),
                "decision": item.get("decision"),
                "selection": item.get("selection") or item.get("tendency"),
                "line": item.get("line"),
                "analysis_decision": item.get("analysis_decision"),
            }
        )
    summary["market_decisions"] = market_decisions
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe W2 analysis chain read model.")
    parser.add_argument("fixture_ids", nargs="+")
    parser.add_argument("--read-count", type=int, default=1)
    args = parser.parse_args()

    service = ReadModelService()
    before = _audit_snapshot()
    fixtures: list[dict[str, Any]] = []
    for _ in range(max(args.read_count, 1)):
        fixtures = [
            summarize_card(
                service.public_analysis_card_bounded(
                    fixture_id,
                    use_frozen_canary=False,
                ),
                fixture_id,
            )
            for fixture_id in args.fixture_ids
        ]
    after = _audit_snapshot()
    payload = {
        "probe": "public_analysis_card_bounded",
        "read_count": max(args.read_count, 1),
        "audit": {
            "before": before,
            "after": after,
            "delta": _audit_delta(before, after),
            "zero_write_pass": _zero_write_pass(before, after),
        },
        "fixtures": fixtures,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


def _audit_snapshot() -> dict[str, Any]:
    engine = create_engine()
    tables: dict[str, Any] = {}
    with engine.connect() as connection:
        for table in AUDIT_TABLES:
            exists = connection.execute(
                text("select to_regclass(:table_name) is not null"),
                {"table_name": f"public.{table}"},
            ).scalar()
            if not exists:
                tables[table] = {"status": "TABLE_MISSING", "count": None, "hash": None}
                continue
            count = connection.execute(text(f"select count(*) from {table}")).scalar()  # noqa: S608
            digest = connection.execute(
                text(
                    "select md5(coalesce("  # noqa: S608
                    "(select jsonb_agg(to_jsonb(t) order by to_jsonb(t)::text)::text "
                    f"from {table} t),"
                    "'[]'))"
                )
            ).scalar()
            tables[table] = {"status": "PRESENT", "count": int(count or 0), "hash": digest}
    return {"tables": tables}


def _audit_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    deltas: dict[str, Any] = {}
    raw_before_tables = before.get("tables")
    raw_after_tables = after.get("tables")
    before_tables: dict[str, Any] = raw_before_tables if isinstance(raw_before_tables, dict) else {}
    after_tables: dict[str, Any] = raw_after_tables if isinstance(raw_after_tables, dict) else {}
    for table in sorted(set(before_tables) | set(after_tables)):
        raw_left = before_tables.get(table)
        raw_right = after_tables.get(table)
        left: dict[str, Any] = raw_left if isinstance(raw_left, dict) else {}
        right: dict[str, Any] = raw_right if isinstance(raw_right, dict) else {}
        left_count = left.get("count")
        right_count = right.get("count")
        deltas[table] = {
            "count_delta": (
                int(right_count) - int(left_count)
                if isinstance(left_count, int) and isinstance(right_count, int)
                else None
            ),
            "hash_unchanged": left.get("hash") == right.get("hash"),
            "status": right.get("status") or left.get("status"),
        }
    return deltas


def _zero_write_pass(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return all(
        row.get("count_delta") in {0, None}
        and (row.get("status") == "TABLE_MISSING" or row.get("hash_unchanged") is True)
        for row in _audit_delta(before, after).values()
        if isinstance(row, dict)
    )


if __name__ == "__main__":
    raise SystemExit(main())
